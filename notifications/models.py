import requests
from django.db import models
from django.db.models import Max
from django.contrib.postgres.fields import JSONField, ArrayField
from django.contrib.auth.models import User
from django.conf import settings
from django.utils import timezone
from councilmatic_core import models as councilmatic_models
from opencivicdata.core.models.base import OCDIDField

try:
    HAYSTACK_URL = settings.HAYSTACK_CONNECTIONS['default']['URL']
except KeyError:
    HAYSTACK_URL = None


# XXX: Consider having some global notifications configuration model/data such as a flag for NOT sending notifications (e.g. if you need to drop and reload the whole OCD dataset)

class NotificationsUser(User):
    """
    Proxy model for a Django User providing useful methods related to this app.
    """
    class Meta:
        proxy = True

    @property
    def has_subscriptions(self):
        """
        Return a boolean representing whether or not the user has any
        subscriptions.
        """
        return 0 < (
            self.personsubscriptions.count() +
            self.billactionsubscriptions.count() +
            self.committeeactionsubscriptions.count() +
            self.committeeeventsubscriptions.count() +
            self.billsearchsubscriptions.count()
        )


class Subscription(models.Model):
    # Each Subscription will have:
    # - A user ID
    # - A type of subscription:
    #    1) PersonSubscription: recent sponsorships by a person
    #    2) CommitteeActionSubscription: recent actions taken by a committee
    #    3) CommitteeEventSubscription: recent events for a committee
    #    4) BillSearchSubscription: recent legislation for a given faceted search
    #    5) BillActionSubscription: actions on individual bills
    #    6) EventsSubscription: all events (e.g. https://nyc.councilmatic.org/events/ )

    user = models.ForeignKey(
        User,
        related_name='%(class)ss',
        db_column='user_id',
        on_delete=models.CASCADE
    )
    last_datetime_updated = models.DateTimeField(auto_now=True)

    # Make this an abstract base class
    class Meta:
        abstract = True

    def set_last_datetime_updated(self):
        # Set the last_datetime_updated value to the current time, even if the
        # model itself hasn't been updated. This is useful for knowing when the
        # last notification went out, even if the subscription data itself hasn't
        # changed.
        self.last_datetime_updated = timezone.now()
        self.save()


class PersonSubscription(Subscription):
    # related_name lets us go from the user to their committee member subscriptions
    person = models.ForeignKey(
        councilmatic_models.Person,
        related_name='subscriptions',
        on_delete=models.CASCADE
    )
    # Keep track of sponsorships that have already been seen, as an array of
    # Bill.ids. This way, we can tell if sponsorships have been added or removed
    # for this person.
    seen_sponsorship_ids = ArrayField(OCDIDField(ocd_type='bill'), default=list)

    def get_updates(self):
        person_update = {}
        new_sponsorships = councilmatic_models.BillSponsorship.objects.filter(
            person__id=self.person.id
        ).exclude(id__in=self.seen_sponsorship_ids)
        if new_sponsorships.count() > 0:
            person_update = {
                'New sponsorships': {
                    'slug': self.person.slug,
                    'name': self.person.name,
                    'bills': []
                }
            }
            for sponsorship in new_sponsorships:
                person_update['New sponsorships']['bills'].append({
                    'id': sponsorship.id,
                    'identifier': sponsorship.bill.identifier,
                    'slug': sponsorship.bill.slug,
                    'description': sponsorship.bill.title,
                })
        self.seen_sponsorship_ids.extend([spon.id for spon in new_sponsorships])
        self.save()
        return person_update


class BillActionSubscription(Subscription):
    bill = models.ForeignKey(
        councilmatic_models.Bill,
        related_name='subscriptions',
        on_delete=models.CASCADE
    )
    # The last BillAction.order that the user has seen. Use this to determine
    # which BillActions are new.
    last_seen_order = models.PositiveIntegerField(default=0)

    def get_updates(self):
        bill_action_updates = []
        new_actions = councilmatic_models.BillAction.objects.filter(
            bill__id=self.bill.id,
            order__gte=self.last_seen_order
        )
        for action in new_actions:
            bill = {
                'slug': action.bill.councilmatic_bill.slug,
                'identifier': action.bill.identifier,
                'description': action.bill.title
            }
            action = {
                'description': action.description,
                'date': action.date,
                'order': action.order
            }
            bill_action_updates.append((bill, action))

        if new_actions.count() > 0:
            self.last_seen_order = new_actions.aggregate(max=Max('order'))['max']
            self.save()

        return bill_action_updates


class CommitteeActionSubscriptionBill(models.Model):
    bill = models.ForeignKey(
        councilmatic_models.Bill,
        related_name='committee_subscriptions',
        on_delete=models.CASCADE
    )
    # The last BillAction.order that the user has seen. Use this to determine
    # which BillActions are new.
    last_seen_order = models.PositiveIntegerField(default=0)


class CommitteeActionSubscription(Subscription):
    committee = models.ForeignKey(
        councilmatic_models.Organization,
        related_name='subscriptions_actions',
        on_delete=models.CASCADE
    )
    seen_bills = models.ManyToManyField(CommitteeActionSubscriptionBill)

    def _get_updated_actions_by_bill(self):
        existing_actions = {}
        for bill_sub in self.seen_bills.all():
            actions = councilmatic_models.BillAction.objects.filter(
                bill__id=bill_sub.bill.id,
                order__gte=bill_sub.last_seen_order
            )
            if actions.count() > 0:
                existing_actions[bill_sub] = {
                    'actions': [],
                    'last_seen_order': bill_sub.last_seen_order
                }
                for action in actions.order_by('-date_dt'):
                    existing_actions[bill_sub]['actions'].append(action)
                    if action.order > existing_actions[bill_sub]['last_seen_order']:
                        existing_actions[bill_sub]['last_seen_order'] = action.order
        return [(bill_sub, metadata['actions'], metadata['last_seen_order'])
                for bill_sub, metadata in existing_actions.items()]

    def get_updates(self):
        # Updates for existing actions
        updated_bills = {}
        for bill_sub, actions, last_seen_order in self._get_updated_actions_by_bill():
            updated_bills[bill_sub.bill.id] = {
                'identifier': bill_sub.bill.identifier,
                'slug': bill_sub.bill.slug,
                'description': bill_sub.bill.title,
                'actions': [{
                    'date': action.date,
                    'description': action.description,
                    'order': action.order
                } for action in actions]
            }
            bill_sub.last_seen_order = last_seen_order
            bill_sub.save()
        # Updates for new actions
        new_bills = {}
        new_actions = councilmatic_models.BillAction.objects.filter(
            organization__id=self.committee.id
        ).exclude(
            bill__in=[ba.bill for ba in self.seen_bills.all()]
        )
        for action in new_actions.order_by('-date_dt'):
            bill_id = action.bill.id
            if not new_bills.get(bill_id):
                new_bills[bill_id] = {
                    'identifier': action.bill.identifier,
                    'slug': action.bill.slug,
                    'description': action.bill.title,
                    'actions': []
                }
            new_bills[bill_id]['actions'].append({
                'order': action.order,
                'date': action.date,
                'description': action.description
            })
        for bill_id, bill_metadata in new_bills.items():
            self.seen_bills.add(CommitteeActionSubscriptionBill.objects.create(
                bill=councilmatic_models.Bill.objects.get(id=bill_id),
                last_seen_order=max(act['order'] for act in bill_metadata['actions'])
            ))
        # Flatten the dict of bills to a list to match the data structure
        # expected by the template
        all_bills = list(new_bills.values()) + list(updated_bills.values())
        return {
            'name': self.committee.name,
            'slug': self.committee.slug,
            'bills': all_bills
        }


class CommitteeEventSubscription(Subscription):
    committee = models.ForeignKey(
        councilmatic_models.Organization,
        related_name='subscriptions_events',
        on_delete=models.CASCADE
    )

    def get_updates(self):
        new_events = councilmatic_models.Event.objects.filter(
            participants__organization__id=self.committee.id,
            created_at__gte=self.last_datetime_updated,
            start_time__gte=timezone.now()
        )
        events = []
        for event in new_events.order_by('-start_time'):
            events.append({
                'slug': event.slug,
                'name': event.name,
                'start_date': event.start_date,
                'description': event.description
            })
        self.set_last_datetime_updated()
        if len(events) > 0:
            return {
                'name': self.committee.name,
                'slug': self.committee.slug,
                'events': events
            }
        else:
            return {}


class BillSearchSubscription(Subscription):
    search_params = JSONField(db_index=True, null=True)

    def get_updates(self):
        if not HAYSTACK_URL:
            raise AttributeError(
                'Solr must be configured to return BillSearchSubscription updates'
            )

        term = self.search_params['term'].strip() or '*:*'

        query_params = {
            'q': term,
            'fq': [],
            'wt': 'json'
        }

        for facet, values in self.search_params['facets'].items():
            for value in values:
                query_params['fq'].append('{0}:{1}'.format(facet, value))

        results = requests.get('{}/select'.format(HAYSTACK_URL), params=query_params)

        ocd_ids = tuple(r['ocd_id'] for r in results.json()['response']['docs'])

        search_update = {}
        if ocd_ids:
            new_bills = councilmatic_models.Bill.objects.filter(
                id__in=ocd_ids,
                created_at__gte=self.last_datetime_updated
            )
            self.set_last_datetime_updated()

            bills = []
            for bill in new_bills:
                bill_attrs = {
                    'slug': bill.slug,
                    'identifier': bill.identifier,
                    'description': bill.title,
                }
                bills.append(bill_attrs)

            if bills:
                search_update = {
                    'params': self.search_params,
                    'bills': bills
                }
        return search_update


class EventsSubscription(Subscription):
    # This subscribes to all recent/upcoming events as per https://github.com/datamade/nyc-councilmatic/issues/175
    # XXX: not implemented yet
    pass


class SubscriptionProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    activation_key = models.CharField(max_length=40)
    key_expires = models.DateTimeField()

    def __str__(self):
        return '{} Subscription profile'.format(self.user.username)
