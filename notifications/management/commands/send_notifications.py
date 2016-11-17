import os
import json
from collections import OrderedDict
import itertools

import django_rq

from django.core.management.base import BaseCommand, CommandError
from django.core.mail import EmailMultiAlternatives

from django.db import transaction, connection
from django.db.utils import ProgrammingError

from django.template.loader import get_template
from django.conf import settings

from django.contrib.auth.models import User

class Command(BaseCommand):
    help = 'Send email notifications to subscribed users'
    
    def add_arguments(self, parser):
        pass
        # parser.add_argument(
        #     '--subscription_types',
        #     default='organizations,people,bills,events,search',
        #     help='Comma separated list of subscription types to send notifications for'
        # )
    
    def handle(self, *args, **options):
        
        subscribed_users = ''' 
            SELECT 
              u.id AS user_id,
              MAX(u.email) as user_email,
              array_agg(bas.bill_id) AS bill_action_ids,
              array_agg(bss.search_term) AS bill_search_terms,
              array_agg(bss.search_facets) AS bill_search_facets,
              array_agg(cas.committee_id) AS committee_action_ids,
              array_agg(ces.committee_id) AS committee_event_ids,
              array_agg(ps.person_id) as person_ids
            FROM auth_user AS u
            LEFT JOIN notifications_billactionsubscription AS bas
              ON u.id = bas.user_id
            LEFT JOIN notifications_billsearchsubscription AS bss
              ON u.id = bss.user_id
            LEFT JOIN notifications_committeeactionsubscription AS cas
              ON u.id = cas.user_id
            LEFT JOIN notifications_committeeeventsubscription AS ces
              ON u.id = ces.user_id
            LEFT JOIN notifications_personsubscription AS ps
              ON u.id = ps.user_id
            WHERE bas.bill_id IS NOT NULL
              OR bss.search_term IS NOT NULL
              OR bss.search_facets IS NOT NULL
              OR cas.committee_id IS NOT NULL
              OR ces.committee_id IS NOT NULL
              OR ps.person_id IS NOT NULL
            GROUP BY u.id
        '''
        
        cursor = connection.cursor()
        cursor.execute(subscribed_users)
        columns = [c[0] for c in cursor.description]
        
        for row in cursor:
            user_subscriptions = dict(zip(columns, row))
            
            bill_action_updates = []
            bill_search_updates = []
            committee_action_updates = []
            committee_event_updates = []
            person_updates = []
            
            bill_action_ids = [i for i in user_subscriptions['bill_action_ids'] if i]
            bill_search_terms = [i for i in user_subscriptions['bill_search_terms'] if i]
            bill_search_facets = [i for i in user_subscriptions['bill_search_facets'] if i]
            committee_action_ids = [i for i in user_subscriptions['committee_action_ids'] if i]
            committee_event_ids = [i for i in user_subscriptions['committee_event_ids'] if i]
            person_ids = [i for i in user_subscriptions['person_ids'] if i]
            
            send_notification = False

            if bill_action_ids:
                bill_action_updates = self.find_bill_action_updates(bill_action_ids)
                
                if bill_action_updates:
                    send_notification = True

            if bill_search_terms or bill_search_facets:
                bill_search_updates = self.find_bill_search_updates(bill_search_terms, 
                                                                    bill_search_facets)

                if bill_search_updates:
                    send_notification = True

            if committee_action_ids:
                committee_action_updates = self.find_committee_action_updates(committee_action_ids)

                if committee_action_updates:
                    send_notification = True

            if committee_event_ids:
                committee_event_updates = self.find_committee_event_updates(committee_event_ids)

                if committee_event_updates:
                    send_notification = True
            
            if person_ids:
                person_updates = self.find_person_updates(person_ids)

                if person_updates:
                    send_notification = True
            
            if send_notification:
                send_notification_email.delay(user_id=user_subscriptions['user_id'],
                                              user_email=user_subscriptions['user_email'],
                                              bill_action_updates=bill_action_updates,
                                              bill_search_updates=bill_search_updates,
                                              person_updates=person_updates,
                                              committee_action_updates=committee_action_updates,
                                              committee_event_updates=committee_event_updates)

    def find_bill_action_updates(self, bill_ids):
        
        new_actions = ''' 
            SELECT DISTINCT ON (bill.ocd_id)
              bill.slug AS bill_slug,
              bill.identifier AS bill_identifier,
              bill.description AS bill_description,
              action.description AS action_description,
              action.date AS action_date
            FROM new_action AS new
            JOIN councilmatic_core_bill AS bill
              ON new.bill_id = bill.ocd_id
            JOIN councilmatic_core_action AS action
              ON new.bill_id = action.bill_id
            WHERE new.bill_id IN %s
        '''
        
        cursor = connection.cursor()
        cursor.execute(new_actions, [tuple(bill_ids)])
        
        bill_action_updates = []

        for row in cursor:
            
            bill = {
                'slug': row[0],
                'identifier': row[1],
                'description': row[2],
            }
            action = {
                'description': row[3],
                'date': row[4],
            }

            bill_action_updates.append((bill, action))
            
        return bill_action_updates

    def find_bill_search_updates(self, search_terms, search_facets):
        pass
    
    def find_person_updates(self, person_ids):
        # If person sponsors something new
        # If bill sponsored by person has new or updated action
        # Return list of (person, bill)
        
        new_sponsorships = ''' 
            SELECT DISTINCT ON (person.ocd_id, bill.ocd_id)
              person.name,
              person.slug,
              bill.identifier,
              bill.slug,
              bill.description
            FROM new_sponsorship AS new
            JOIN councilmatic_core_person AS person
              ON new.person_id = person.ocd_id
            JOIN councilmatic_core_bill AS bill
              ON new.bill_id = bill.ocd_id
            WHERE new.person_id IN %s
        '''

        new_actions = ''' 
            SELECT DISTINCT ON (person.ocd_id, bill.ocd_id)
              person.name,
              person.slug,
              bill.identifier,
              bill.slug, 
              bill.description
            FROM new_action AS new
            JOIN councilmatic_core_bill AS bill
              ON new.bill_id = bill.ocd_id
            JOIN councilmatic_core_sponsorship AS sponsor
              ON bill.ocd_id = sponsor.bill_id
            JOIN councilmatic_core_person AS person
              ON sponsor.person_id = person.ocd_id
            WHERE person.ocd_id IN %s
        '''
        
        person_updates = []
        
        cursor = connection.cursor()
        cursor.execute(new_sponsorships, [tuple(person_ids)])

        for row in cursor:
            person = {
                'name': row[0],
                'slug': row[1],
            }
            bill = {
                'identifier': row[2],
                'slug': row[3],
                'description': row[4],
                'update_type': 'New Sponsorship'
            }
            person_updates.append((person, bill))

        cursor.execute(new_actions, [tuple(person_ids)])

        for row in cursor:
            person = {
                'name': row[0],
                'slug': row[1],
            }
            bill = {
                'identifier': row[2],
                'slug': row[3],
                'description': row[4],
                'update_type': 'New Action'
            }
            person_updates.append((person, bill))
        
        update_groups = []
        for person, group in itertools.groupby(person_updates, key=lambda x: x[0]['slug']):
            person['bills'] = [i[1] for i in group]
            update_groups.append(person)

        return update_groups
    
    def find_committee_action_updates(self):
        pass
    
    def find_committee_event_updates(self):
        pass

@django_rq.job
def send_notification_email(user_id=None,
                            user_email=None,
                            bill_action_updates=[],
                            bill_search_updates=[],
                            person_updates=[],
                            committee_action_updates=[],
                            committee_event_updates=[]):
    
    context = {
        # 'user': user, 
        'SITE_META': settings.SITE_META,
        'CITY_VOCAB': settings.CITY_VOCAB,
        'bill_action_updates': bill_action_updates,
        'bill_search_updates': bill_search_updates,
        'person_updates': person_updates,
        'committee_action_updates': committee_action_updates,
        'committee_event_updates': committee_event_updates,
    }

    html = "notifications_email.html"
    txt = "notifications_email.txt"
    html_template = get_template(html)
    text_template = get_template(txt)
    html_content = html_template.render(context)
    text_content = text_template.render(context)
    subject = '{0} Updates!'.format(settings.SITE_META['site_name'])

    msg = EmailMultiAlternatives(subject, 
                                 text_content, 
                                 settings.EMAIL_HOST_USER, 
                                 [user_email])

    msg.attach_alternative(html_content, 'text/html')
    msg.send()
