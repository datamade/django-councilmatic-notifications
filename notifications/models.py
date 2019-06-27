from django.db import models

from django.contrib.auth.models import User
from councilmatic_core.models import Bill, Organization, Person

from django.contrib.postgres.fields import JSONField


# XXX: Consider having some global notifications configuration model/data such as a flag for NOT sending notifications (e.g. if you need to drop and reload the whole OCD dataset)

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


class PersonSubscription(Subscription):
    # related_name lets us go from the user to their committee member subscriptions
    person = models.ForeignKey(
        Person,
        related_name='subscriptions',
        on_delete=models.CASCADE
    )

class CommitteeActionSubscription(Subscription):
    committee = models.ForeignKey(
        Organization,
        related_name='subscriptions_actions',
        on_delete=models.CASCADE
    )

class CommitteeEventSubscription(Subscription):
    committee = models.ForeignKey(
        Organization,
        related_name='subscriptions_events',
        on_delete=models.CASCADE
    )

class BillSearchSubscription(Subscription):
    search_params = JSONField(db_index=True, null=True)

class BillActionSubscription(Subscription):
    bill = models.ForeignKey(
        Bill,
        related_name='subscriptions',
        on_delete=models.CASCADE
    )

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
