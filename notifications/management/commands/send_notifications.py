import os
import json
from collections import OrderedDict

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

            if bill_action_ids:
                bill_action_updates = self.find_bill_action_updates(bill_action_ids)
            
            if bill_search_terms or bill_search_facets:
                bill_search_updates = self.find_bill_search_updates(bill_search_terms, 
                                                                    bill_search_facets)

            if committee_action_ids:
                committee_action_updates = self.find_committee_action_updates(committee_action_ids)

            if committee_event_ids:
                committee_event_updates = self.find_committee_event_updates(committee_event_ids)
            
            if person_ids:
                person_updates = self.find_person_updates(person_ids)
        
            send_notification_email.delay(user_id=user_subscriptions['user_id'],
                                          user_email=user_subscriptions['user_email'],
                                          bill_action_updates=bill_action_updates,
                                          bill_search_updates=bill_search_updates,
                                          person_updates=person_updates,
                                          committee_action_updates=committee_action_updates,
                                          committee_event_updates=committee_event_updates)

    def find_bill_action_updates(self, bill_ids):
        
        new_actions = ''' 
            SELECT 
              bill.slug AS bill_slug,
              bill.identifier AS bill_identifier,
              action.description AS action_description
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
            
            bill = dict(zip(['slug', 'identifier'], row[:2]))
            action = {'description': row[2]}

            bill_action_updates.append((bill, action))
            
        return bill_action_updates

    def find_bill_search_updates(self):
        pass
    
    def find_person_updates(self):
        # If person sponsors something new
        # If bill sponsored by person has new or updated action
        pass
    
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
