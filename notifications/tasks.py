import json

import django_rq

from django.core.mail import EmailMessage

from councilmatic_core.models import Bill, Events

from notifications.models import PersonSubscription, \
    CommitteeActionSubscription, 


def handle_bill_search_subscriptions(user, update_since, created_bills_ids, updated_bills_ids, created_events_ids, updated_events_ids):
    billsearch_subscriptions = BillSearchSubscription.objects.filter(user=user)
    person_updates = [] # list of bills sponsored by a person since subscriptions' last_datetime_updated
    committee_action_updates = [] # list of actions taken by a committee since subscriptions' last_datetime_updated
    committee_event_updates = [] # list of events taken by a committee since subscriptions' last_datetime_updated
    bill_search_updates = [] # list of new bills now showing up on a search since subscriptions' last_datetime_updated
    bill_action_updates = [] # list of actions taken on a bill since subscriptions' last_datetime_updated
    events_updates = [] # list of events since subscriptions' last_datetime_updated
    # XXX It's unclear how to proceed here but perhaps evz can weigh in on what the search actually searches,
    # XXX and whether we can simulate that in Python or whether it makes more sense to interact directly with
    # XXX the solr interface on the imported stuff.
    # XXX
    # XXX However, the problem is that with the current cron system, the indexes are not updated immediately
    # XXX with the new data.
    print ("NOT doing bill search subscriptions")

    return bill_search_updates

def handle_events_subscriptions(user, update_since, created_bills_ids, updated_bills_ids, created_events_ids, updated_events_ids):
    event_updates = []
    events_subscriptions = EventsSubscription.objects.filter(user=user)

    # Basically just return all new events if this is what we are subscribed
    # to.  XXX: Whether we include or differentiate updated events will depend
    # on how often updated events actually occur in practice with daily
    # updates.
    all_events_ids = created_events_ids + updated_events_ids
    events = Event.objects.filter(
        Q(id__in=all_events_ids)).order_by('-start_time')
    for event in events:
        event_updates.append(event) #XXX for now, conflate created and updated events
    return event_updates

