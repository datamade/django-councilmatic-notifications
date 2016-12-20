import os
import json
from collections import OrderedDict
import itertools
import requests
from datetime import date
from io import StringIO

import django_rq
import pysolr

from django.core.management.base import BaseCommand, CommandError
from django.core.mail import EmailMultiAlternatives

from django.db import transaction, connection
from django.db.utils import ProgrammingError

from django.template.loader import get_template
from django.conf import settings

from django.contrib.auth.models import User

try:
    haystack_url = settings.HAYSTACK_CONNECTIONS['default']['URL']
except KeyError:
    haystack_url = None

class Command(BaseCommand):

    help = 'Send email notifications to subscribed users'

    def add_arguments(self, parser):
        parser.add_argument(
            '--users',
            default='all',
            help='Comma separated list of usernames to send notifications to.'
        )

    def handle(self, *args, **options):

        subscribed_users = '''
            SELECT
              u.id AS user_id,
              MAX(u.email) as user_email,
              array_agg(DISTINCT bas.bill_id) AS bill_action_ids,
              array_agg(DISTINCT bss.search_params) AS bill_search_params,
              array_agg(DISTINCT cas.committee_id) AS committee_action_ids,
              array_agg(DISTINCT ces.committee_id) AS committee_event_ids,
              array_agg(DISTINCT ps.person_id) as person_ids
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
            WHERE (bas.bill_id IS NOT NULL
                   OR bss.search_params IS NOT NULL
                   OR cas.committee_id IS NOT NULL
                   OR ces.committee_id IS NOT NULL
                   OR ps.person_id IS NOT NULL)
        '''

        q_args = []

        if options['users'] != 'all':
            users = tuple(options['users'].split(','))
            subscribed_users = '{} AND u.username IN %s'.format(subscribed_users)
            q_args.append(users)


        subscribed_users = '{} GROUP BY u.id'.format(subscribed_users)
        cursor = connection.cursor()
        cursor.execute(subscribed_users, q_args)
        columns = [c[0] for c in cursor.description]

        bill_action_updates = []
        bill_search_updates = []
        committee_action_updates = []
        committee_event_updates = []
        person_updates = []

        send_notification = False
        output = None

        for row in cursor:
            user_subscriptions = dict(zip(columns, row))

            # bill_action_updates = []
            # bill_search_updates = []
            # committee_action_updates = []
            # committee_event_updates = []
            # person_updates = []

            bill_action_ids = [i for i in user_subscriptions['bill_action_ids'] if i]
            bill_search_params = [i for i in user_subscriptions['bill_search_params'] if i]
            committee_action_ids = [i for i in user_subscriptions['committee_action_ids'] if i]
            committee_event_ids = [i for i in user_subscriptions['committee_event_ids'] if i]
            person_ids = [i for i in user_subscriptions['person_ids'] if i]

            # send_notification = False

            if bill_action_ids:
                bill_action_updates = self.find_bill_action_updates(bill_action_ids)

                if bill_action_updates:
                    send_notification = True

            if bill_search_params:
                bill_search_updates = self.find_bill_search_updates(bill_search_params)

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

                output = dict(bill_action_updates=bill_action_updates,
                          bill_search_updates=bill_search_updates,
                          person_updates=person_updates,
                          committee_action_updates=committee_action_updates,
                          committee_event_updates=committee_event_updates)

        if output is None:
            self.stdout.write('no email')

        else:
            dthandler = lambda x: x.isoformat() if isinstance(x, date) else None
            self.stdout.write(json.dumps(output, default=dthandler))


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

    def find_bill_search_updates(self, search_params):

        if not haystack_url:
            self.stdout.write(self.style.ERROR('Solr is not configured so no search notifications will be sent'))
            return []

        search_updates = []

        cursor = connection.cursor()

        for params in search_params:
            query_params = {
                'q': params['term'],
                'fq': [],
                'wt': 'json'
            }

            for facet, values in params['facets'].items():
                for value in values:
                    query_params['fq'].append('{0}:{1}'.format(facet, value))

            results = requests.get('{}/select'.format(haystack_url), params=query_params)

            ocd_ids = tuple(r['ocd_id'] for r in results.json()['response']['docs'])

            new_bills = '''
                SELECT DISTINCT ON (bill.ocd_id)
                  bill.slug AS bill_slug,
                  bill.identifier AS bill_identifier,
                  bill.description AS bill_description
                FROM new_bill AS new
                JOIN councilmatic_core_bill AS bill
                  ON new.ocd_id = bill.ocd_id
                WHERE new.ocd_id IN %s
            '''

            cursor.execute(new_bills, [ocd_ids])

            bills = []

            for row in cursor:
                bill = {
                    'slug': row[0],
                    'identifier': row[1],
                    'description': row[2]
                }
                bills.append(bill)

            if bills:
                search_updates.append({
                    'params': params,
                    'bills': bills
                })

        return search_updates

    def find_person_updates(self, person_ids):
        # If person sponsors something new
        # If bill sponsored by person has new or updated action

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
              bill.description,
              action.description,
              action.date
            FROM new_action AS new
            JOIN councilmatic_core_bill AS bill
              ON new.bill_id = bill.ocd_id
            JOIN councilmatic_core_action AS action
              ON bill.ocd_id = action.bill_id
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
                'action_description': None,
                'action_date': None,
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
                'action_description': row[5],
                'action_date': row[6],
                'update_type': 'New Action'
            }
            person_updates.append((person, bill))

        update_groups = []

        outer_grouper = lambda x: x[0]['slug']
        person_updates = sorted(person_updates, key=outer_grouper)

        inner_grouper = lambda x: x[1]['update_type']

        for slug, group in itertools.groupby(person_updates, key=outer_grouper):
            bill_group = {}

            group = sorted(group, key=inner_grouper)

            for update_type, inner_group in itertools.groupby(group, key=inner_grouper):
                bill_group[update_type] = {}

                for person, bill in inner_group:
                    bill_group[update_type].update(person)

                    try:
                        bill_group[update_type]['bills'].append(bill)
                    except KeyError:
                        bill_group[update_type]['bills'] = [bill]

            update_groups.append(bill_group)

        return update_groups

    def find_committee_action_updates(self, committee_ids):
        # New actions taken by a committee on a bill

        new_actions = '''
            SELECT DISTINCT ON (committee.ocd_id, bill.ocd_id, action.id)
              committee.name,
              committee.slug,
              bill.identifier,
              bill.slug,
              bill.description,
              action.description,
              action.date,
              action.order
            FROM councilmatic_core_organization AS committee
            JOIN councilmatic_core_action AS action
              ON committee.ocd_id = action.organization_id
            JOIN councilmatic_core_bill AS bill
              ON action.bill_id = bill.ocd_id
            JOIN new_action AS new
              ON bill.ocd_id = new.bill_id
            WHERE committee.ocd_id IN %s
            ORDER BY committee.ocd_id,
                     bill.ocd_id,
                     action.id,
                     action.order DESC
        '''

        cursor = connection.cursor()
        cursor.execute(new_actions, [tuple(committee_ids)])

        committee_updates = []

        outer_grouper = lambda x: x[1]
        inner_grouper = lambda x: x[3]
        groups = sorted(cursor, key=outer_grouper)

        for committee_slug, group in itertools.groupby(groups, key=outer_grouper):

            group = sorted(group, key=inner_grouper)

            committee_group = {
                'name': group[0][0],
                'slug': group[0][1],
                'bills': []
            }


            for bill_slug, bill_group in itertools.groupby(group, key=inner_grouper):

                bill_group = list(bill_group)

                bill = {
                    'identifier': bill_group[0][2],
                    'slug': bill_group[0][3],
                    'description': bill_group[0][4],
                    'actions': []
                }


                for row in sorted(bill_group, key=lambda x: x[7], reverse=True):
                    action = {
                        'description': row[5],
                        'date': row[6]
                    }

                    bill['actions'].append(action)

                committee_group['bills'].append(bill)

            committee_updates.append(committee_group)

        return committee_updates

    def find_committee_event_updates(self, committee_ids):
        new_events = '''
            SELECT DISTINCT ON (committee.ocd_id, event.ocd_id)
              committee.name,
              committee.slug,
              event.*
            FROM councilmatic_core_event AS event
            JOIN new_event AS new
              ON event.ocd_id = new.ocd_id
            JOIN councilmatic_core_eventparticipant AS p
              ON event.ocd_id = p.event_id
            JOIN councilmatic_core_organization AS committee
              ON p.entity_name = committee.name
            WHERE committee.ocd_id IN %s
            ORDER BY committee.ocd_id,
                     event.ocd_id,
                     event.start_time DESC
        '''

        cursor = connection.cursor()
        cursor.execute(new_events, [tuple(committee_ids)])
        columns = [c[0] for c in cursor.description]

        updates = []

        grouper = lambda x: x[1]
        event_groups = sorted(cursor, key=grouper)

        for slug, group in itertools.groupby(event_groups, key=grouper):
            group = list(group)

            committee = {
                'name': group[0][0],
                'slug': group[0][1],
                'events': []
            }

            for row in group:
                event = dict(zip(columns[2:], row[2:]))
                committee['events'].append(event)

            committee['events'] = sorted(committee['events'],
                                         key=lambda x: x['start_time'],
                                         reverse=True)

            updates.append(committee)

        return updates

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