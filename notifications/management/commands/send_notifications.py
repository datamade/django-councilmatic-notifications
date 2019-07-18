# -*- coding: utf-8 -*-

import json
from itertools import chain
from datetime import datetime, date, timedelta

import requests
import django_rq
import pytz
from django.core.management.base import BaseCommand
from django.core.mail import EmailMultiAlternatives
from django.db import connection
from django.template.loader import get_template
from django.conf import settings
from django.contrib.auth.models import User

from councilmatic_core import models as councilmatic_models


class Command(BaseCommand):

    help = 'Send email notifications to subscribed users'

    def add_arguments(self, parser):
        parser.add_argument(
            '--users',
            default='all',
            help='Comma separated list of usernames to send notifications to.'
        )

    def _is_empty(self, elem):
        return len(elem) > 0

    def handle(self, *args, **options):
        subscribed_users = User.objects.filter(subscriptions__isnull=False)
        for user in subscribed_users:
            # BillActionSubscription.get_updates() returns a list, so make
            # sure to flatten the outer list.
            bill_action_updates = filter(self._is_empty, chain.from_iterable([
                sub.get_updates() for sub in user.billactionsubscription.all()
            ]))
            committee_action_updates = filter(self._is_empty, [
                sub.get_updates() for sub in user.committeeactionsubscription.all()
            ])
            committee_event_updates = filter(self._is_empty, [
                sub.get_updates() for sub in user.committeeeventsubscription.all()
            ])
            person_updates = filter(self._is_empty, [
                sub.get_updates() for sub in user.personsubscription.all()
            ])

            try:
                bill_search_updates = filter(self._is_empty, [
                    sub.get_updates() for sub in user.billsearchsubscription.all()
                ])
            except AttributeError:
                self.stdout.write(self.style.ERROR('Solr is not configured so no search notifications will be sent'))
                bill_search_updates = []

            send_notification = any([
                bill_action_updates, bill_search_updates,
                committee_action_updates, committee_event_updates,
                person_updates
            ])

            if send_notification:
                send_notification_email.delay(
                    user_id=user.id,
                    user_email=user.email,
                    bill_action_updates=bill_action_updates,
                    bill_search_updates=bill_search_updates,
                    person_updates=person_updates,
                    committee_action_updates=committee_action_updates,
                    committee_event_updates=committee_event_updates
                )


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
