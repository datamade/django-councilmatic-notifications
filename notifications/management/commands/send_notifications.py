# -*- coding: utf-8 -*-

import os
import json
from collections import OrderedDict
import itertools
import requests
from datetime import datetime, date, timedelta
from io import StringIO

import django_rq
import pysolr
import pytz

from django.core.management.base import BaseCommand, CommandError
from django.core.mail import EmailMultiAlternatives

from django.db import transaction, connection
from django.db import models as django_models
from django.db.models.functions import Cast, Coalesce
from django.db.utils import ProgrammingError

from django.template.loader import get_template
from django.conf import settings

from django.contrib.auth.models import User

from opencivicdata.legislative import models as ocd_legislative_models
from councilmatic_core import models as councilmatic_models

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

        parser.add_argument(
            '--minutes',
            default=15,
            type=int,
            help='How many minutes ago to set the threshold for considering an update to be "new".'
        )

    def get_threshold(self, minutes):
        """
        Return the date threshold after which objects should be considered
        new enough to warrant a notification.

        :param minutes: The number of minutes before the current time to set the threshold.
        :return: A datetime object representing the threshold.
        """
        return (
            datetime.now(pytz.timezone(settings.TIME_ZONE)) -
            timedelta(minutes=minutes)
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
              array_agg(DISTINCT ps.person_id) as person_ids,
              bool_and(es.id::bool) AS event_subscription
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
            LEFT JOIN notifications_eventssubscription AS es
              ON u.id = es.user_id
            WHERE (bas.bill_id IS NOT NULL
                   OR bss.search_params IS NOT NULL
                   OR cas.committee_id IS NOT NULL
                   OR ces.committee_id IS NOT NULL
                   OR ps.person_id IS NOT NULL
                   OR es.id IS NOT NULL)
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

            bill_action_ids = [i for i in user_subscriptions['bill_action_ids'] if i]
            bill_search_params = [i for i in user_subscriptions['bill_search_params'] if i]
            committee_action_ids = [i for i in user_subscriptions['committee_action_ids'] if i]
            committee_event_ids = [i for i in user_subscriptions['committee_event_ids'] if i]
            person_ids = [i for i in user_subscriptions['person_ids'] if i]
            event_subscription = user_subscriptions['event_subscription']

            send_notification = False

            if bill_action_ids:
                bill_action_updates = self.find_bill_action_updates(
                    bill_action_ids,
                    minutes=options['minutes']
                )

                if bill_action_updates:
                    send_notification = True

            if bill_search_params:
                bill_search_updates = self.find_bill_search_updates(
                    bill_search_params,
                    minutes=options['minutes']
                )

                if bill_search_updates:
                    send_notification = True

            if committee_action_ids:
                committee_action_updates = self.find_committee_action_updates(
                    committee_action_ids,
                    minutes=options['minutes']
                )

                if committee_action_updates:
                    send_notification = True

            if committee_event_ids:
                committee_event_updates = self.find_committee_event_updates(
                    committee_event_ids,
                    minutes=options['minutes']
                )

                if committee_event_updates:
                    send_notification = True

            if person_ids:
                person_updates = self.find_person_updates(
                    person_ids,
                    minutes=options['minutes']
                )

                if person_updates:
                    send_notification = True

            new_events = []
            updated_events = []

            if event_subscription:
                new_events = self.find_new_events(minutes=options['minutes'])
                updated_events = self.find_updated_events(minutes=options['minutes'])

                if new_events or updated_events:
                    send_notification = True

            if send_notification:
                send_notification_email.delay(user_id=user_subscriptions['user_id'],
                                              user_email=user_subscriptions['user_email'],
                                              bill_action_updates=bill_action_updates,
                                              bill_search_updates=bill_search_updates,
                                              person_updates=person_updates,
                                              committee_action_updates=committee_action_updates,
                                              committee_event_updates=committee_event_updates,
                                              updated_events=updated_events,
                                              new_events=new_events)

                output = dict(bill_action_updates=bill_action_updates,
                              bill_search_updates=bill_search_updates,
                              person_updates=person_updates,
                              committee_action_updates=committee_action_updates,
                              committee_event_updates=committee_event_updates,
                              updated_events=updated_events,
                              new_events=new_events)

        if output is None:
            self.stdout.write('no email')

        else:
            dthandler = lambda x: x.isoformat() if isinstance(x, date) else None
            self.stdout.write(json.dumps(output, default=dthandler))

    def find_bill_action_updates(self, bill_ids, minutes=15):
        new_actions = ocd_legislative_models.BillAction.objects.annotate(
            action_date=Cast(
                # If the 'date' is null, set it beyond the threshold to
                # prevent it from matching the filter
                Coalesce('date', django_models.Value(self.get_threshold(minutes+1))),
                django_models.DateTimeField()
            )
        ).filter(
            bill__id__in=bill_ids,
            action_date__gte=self.get_threshold(minutes)
        )

        bill_action_updates = []

        for action in new_actions:

            bill = {
                'slug': action.bill.councilmatic_bill.slug,
                'identifier': action.bill.identifier,
                'description': action.bill.title
            }
            action = {
                'description': action.description,
                'date': action.date,
            }

            bill_action_updates.append((bill, action))

        return bill_action_updates

    def find_bill_search_updates(self, search_params, minutes=15):

        if not haystack_url:
            self.stdout.write(self.style.ERROR('Solr is not configured so no search notifications will be sent'))
            return []

        search_updates = []

        cursor = connection.cursor()

        for params in search_params:

            term = params['term'].strip()

            if not term:
                term = '*:*'

            query_params = {
                'q': term,
                'fq': [],
                'wt': 'json'
            }

            for facet, values in params['facets'].items():
                for value in values:
                    query_params['fq'].append('{0}:{1}'.format(facet, value))

            results = requests.get('{}/select'.format(haystack_url), params=query_params)

            ocd_ids = tuple(r['ocd_id'] for r in results.json()['response']['docs'])

            if ocd_ids:
                new_bills = councilmatic_models.Bill.objects.filter(
                    id__in=ocd_ids,
                    created_at__gte=self.get_threshold(minutes)
                )

                bills = []

                for bill in new_bills:
                    bill_attrs = {
                        'slug': bill.slug,
                        'identifier': bill.identifier,
                        'description': bill.title,
                    }
                    bills.append(bill_attrs)

                if bills:
                    search_updates.append({
                        'params': params,
                        'bills': bills
                    })

        return search_updates

    def find_person_updates(self, person_ids, minutes=15):
        # Set a base dictionary providing the output data structure for an update
        base_update_dct = {
            'New sponsorships': {
                'slug': '',
                'name': '',
                'bills': []
            }
        }
        person_updates = []
        for person_id in person_ids:
            new_sponsorships = councilmatic_models.BillSponsorship.objects.filter(
                bill__created_at__gte=self.get_threshold(minutes),
                person__id=person_id
            )
            if new_sponsorships.count() > 0:
                person_update = base_update_dct.copy()
                person = councilmatic_models.Person.objects.get(id=person_id)
                person_update['New sponsorships'].update({
                    'name': person.name,
                    'slug': person.slug,
                })
                for sponsorship in new_sponsorships:
                    person_update['New sponsorships']['bills'].append({
                        'identifier': sponsorship.bill.identifier,
                        'slug': sponsorship.bill.slug,
                        'description': sponsorship.bill.title,
                    })
                person_updates.append(person_update)
        return person_updates

    def find_committee_action_updates(self, committee_ids, minutes=15):
        committee_updates = []
        for committee_id in committee_ids:
            new_actions = councilmatic_models.BillAction.objects.annotate(
                action_date=Cast(
                    Coalesce(
                        'date',
                        django_models.Value(str(self.get_threshold(minutes+1)))
                    ),
                    django_models.DateTimeField()
                )
            ).filter(
                organization__id=committee_id,
                action_date__gte=self.get_threshold(minutes)
            )
            if new_actions.count() > 0:
                committee = councilmatic_models.Organization.objects.get(
                    id=committee_id
                )
                committee_update = {
                    'name': committee.name,
                    'slug': committee.slug,
                    'bills': {}
                }
                for action in new_actions.distinct(
                    'date', 'organization__id', 'bill__id', 'id'
                ).order_by('-date'):
                    # Check if the bill is already initialized in the
                    # committee_update object
                    if not committee_update['bills'].get(action.bill.id):
                        committee_update['bills'][action.bill.id] = {
                            'identifier': action.bill.identifier,
                            'slug': action.bill.slug,
                            'description': action.bill.title,
                            'actions': []
                        }
                    committee_update['bills'][action.bill.id]['actions'].append({
                        'date': action.date,
                        'description': action.description
                    })
                # Flatten the dict of bills to a list to match the data structure
                # expected by the template
                committee_update['bills'] = list(committee_update['bills'].values())
                committee_updates.append(committee_update)
        return committee_updates

    def find_committee_event_updates(self, committee_ids, minutes=15):
        committee_updates = []
        for committee_id in committee_ids:
            new_event_particip = ocd_legislative_models.EventParticipant.objects.annotate(
                event_start_date=Cast(
                    Coalesce(
                        'event__start_date',
                        # If 'start_date' is null, set it to the current time
                        # to prevent it from matching the filter
                        django_models.Value(
                            str(datetime.now(pytz.timezone(settings.TIME_ZONE)))
                        )
                    ),
                    django_models.DateTimeField()
                )
            ).filter(
                organization__id=committee_id,
                event__created_at__gte=self.get_threshold(minutes),
                event_start_date__gte=datetime.now(pytz.timezone(settings.TIME_ZONE))
            )
            if new_event_particip.count() > 0:
                committee = councilmatic_models.Organization.objects.get(
                    id=committee_id
                )
                committee_update = {
                    'name': committee.name,
                    'slug': committee.slug,
                    'events': []
                }
                for event_particip in new_event_particip.distinct(
                    'event__start_date', 'organization__id', 'event__id'
                ).order_by('-event__start_date'):
                    event = event_particip.event.councilmatic_event
                    committee_update['events'].append({
                        'slug': event.slug,
                        'name': event.name,
                        'start_date': event.start_date,
                        'description': event.description
                    })
                committee_updates.append(committee_update)
        return committee_updates

    def find_new_events(self, minutes=15):
        new_events = '''
            SELECT * FROM (
            SELECT DISTINCT ON (event.ocd_id)
              event.name,
              event.start_time,
              event.end_time,
              event.slug,
              event.all_day,
              event.location_name,
              event.slug
            FROM councilmatic_core_event AS event
            JOIN new_event AS new
              ON event.ocd_id = new.ocd_id
            WHERE event.start_time > NOW()
            ) AS events
            ORDER BY events.start_time
        '''

        cursor = connection.cursor()
        cursor.execute(new_events)
        columns = [c[0] for c in cursor.description]

        return [dict(zip(columns, r)) for r in cursor]

    def find_updated_events(self, minutes=15):
        new_events = '''
            SELECT * FROM (
            SELECT DISTINCT ON (event.ocd_id)
              event.name,
              event.start_time,
              event.end_time,
              event.slug,
              event.all_day,
              event.location_name,
              event.slug
            FROM councilmatic_core_event AS event
            JOIN change_event AS change
              ON event.ocd_id = change.ocd_id
            WHERE event.start_time > NOW()
            ) AS events
            ORDER BY events.start_time
        '''

        cursor = connection.cursor()
        cursor.execute(new_events)
        columns = [c[0] for c in cursor.description]

        return [dict(zip(columns, r)) for r in cursor]

@django_rq.job
def send_notification_email(user_id=None,
                            user_email=None,
                            bill_action_updates=[],
                            bill_search_updates=[],
                            person_updates=[],
                            committee_action_updates=[],
                            committee_event_updates=[],
                            updated_events=[],
                            new_events=[]):

    context = {
        # 'user': user,
        'SITE_META': settings.SITE_META,
        'CITY_VOCAB': settings.CITY_VOCAB,
        'bill_action_updates': bill_action_updates,
        'bill_search_updates': bill_search_updates,
        'person_updates': person_updates,
        'committee_action_updates': committee_action_updates,
        'committee_event_updates': committee_event_updates,
        'updated_events': updated_events,
        'new_events': new_events,
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
