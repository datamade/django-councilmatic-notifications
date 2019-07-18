import datetime
import pytz

import pytest
import requests
from django.core.management import call_command
from django.conf import settings
from councilmatic_core import models as councilmatic_models
from opencivicdata.legislative import models as ocd_legislative_models
from notifications import models as notifications_models

from notifications.management.commands.send_notifications import Command


@pytest.mark.django_db
def test_find_bill_action_updates(new_bill, new_bill_actions, subscriptions):
    assert subscriptions['bill_action'].last_seen_order == 0
    bill_action_updates = subscriptions['bill_action'].get_updates()
    assert len(bill_action_updates) == 2
    assert bill_action_updates[0][0]['slug'] == new_bill.slug
    assert bill_action_updates[0][1]['description'] == new_bill_actions[0].description
    assert bill_action_updates[1][0]['slug'] == new_bill.slug
    assert bill_action_updates[1][1]['description'] == new_bill_actions[1].description
    assert subscriptions['bill_action'].last_seen_order == new_bill_actions[1].order


@pytest.mark.django_db
def test_find_bill_search_updates(new_bill, mocker, subscriptions):
    new_response = mocker.MagicMock(spec=requests.Response)
    new_response.json.return_value = {
        'response': {
            'docs': [{
                'ocd_id': new_bill.id,
            }]
        }
    }
    new_requests_get = mocker.MagicMock(
        spec='requests.get',
        return_value=new_response
    )
    mocker.patch('requests.get', new=new_requests_get)
    bill_search_updates = subscriptions['bill_search'].get_updates()
    assert len(bill_search_updates['bills']) == 1
    assert bill_search_updates['bills'][0]['identifier'] == new_bill.identifier


@pytest.mark.django_db
def test_find_person_updates(new_bill):
    person = councilmatic_models.Person.objects.first()
    councilmatic_models.BillSponsorship.objects.create(
        bill=new_bill,
        organization=new_bill.from_organization.councilmatic_organization,
        person=person
    )
    command = Command()
    person_updates = command.find_person_updates([person.id])
    assert len(person_updates) == 1
    assert person_updates[0]['New sponsorships']['name'] == person.name
    assert person_updates[0]['New sponsorships']['slug'] == person.slug
    assert person_updates[0]['New sponsorships']['bills'][0]['slug'] == new_bill.slug


@pytest.mark.django_db
def test_find_committee_action_updates(new_bill, new_bill_actions):
    organization = new_bill.from_organization.councilmatic_organization
    command = Command()
    committee_action_updates = command.find_committee_action_updates([organization.id])
    assert len(committee_action_updates) == 1
    assert committee_action_updates[0]['slug'] == organization.slug
    assert len(committee_action_updates[0]['bills']) == 1
    assert committee_action_updates[0]['bills'][0]['slug'] == new_bill.slug
    assert len(committee_action_updates[0]['bills'][0]['actions']) == 2
    assert committee_action_updates[0]['bills'][0]['actions'][0]['description'] == new_bill_actions[1].description
    assert committee_action_updates[0]['bills'][0]['actions'][1]['description'] == new_bill_actions[0].description


@pytest.mark.django_db
def test_find_committee_event_updates(new_events):
    organization = councilmatic_models.Organization.objects.first()
    event = new_events[0]
    ocd_legislative_models.EventParticipant.objects.create(
        event=event,
        organization=organization
    )
    command = Command()
    committee_event_updates = command.find_committee_event_updates([organization.id])
    assert len(committee_event_updates) == 1
    assert committee_event_updates[0]['slug'] == organization.slug
    assert len(committee_event_updates[0]['events']) == 1
    assert committee_event_updates[0]['events'][0]['name'] == event.name


@pytest.mark.django_db
def test_find_new_events(new_events):
    command = Command()
    found_events = command.find_new_events()
    assert len(found_events) == 2
    assert found_events[0]['name'] == new_events[1].name
    assert found_events[1]['name'] == new_events[0].name


@pytest.mark.django_db
def test_find_new_events_skips_null_dates(new_events):
    for event in new_events:
        # Null dates are saved as empty strings in the OCD data model
        event.start_date = ''
        event.save()
    command = Command()
    found_events = command.find_new_events()
    assert len(found_events) == 0


@pytest.mark.django_db
def test_find_updated_events(new_events):
    first_event, second_event = new_events
    # We need to assign the Event.created_at field such that the filter will believe
    # it was created beyond the threshold for new events. Since this field is
    # assigned automatically during object creation, reassign it afterwards.
    new_creation_time = (
        datetime.datetime.now(pytz.timezone(settings.TIME_ZONE)) -
        datetime.timedelta(minutes=20)
    )
    first_event.created_at = second_event.created_at = new_creation_time
    first_event.save()
    second_event.save()
    command = Command()
    updated_events = command.find_updated_events()
    assert len(updated_events) == 2
    assert updated_events[0]['name'] == first_event.name
    assert updated_events[1]['name'] == second_event.name


@pytest.mark.django_db
def test_send_users_updates(db, setup, new_bill_actions, user, mocker):
    """
    Test that users will be sent emails for subscriptions when updates are
    available.
    """
    notifications_models.BillActionSubscription.objects.create(
        bill=new_bill_actions[0].bill,
        user=user
    )
    send_notification_email = mocker.patch(
        'notifications.management.commands.send_notifications.send_notification_email.delay',
        autospec=True
    )
    call_command('send_notifications')
    assert send_notification_email.call_count == 1


@pytest.mark.django_db
def test_dont_send_users_updates(mocker):
    """
    Test that users won't be sent emails when no updates are available for
    their subscriptions.
    """
    send_notification_email = mocker.patch(
        'notifications.management.commands.send_notifications.send_notification_email',
        autospec=True
    )
    call_command('send_notifications')
    assert send_notification_email.call_count == 0
