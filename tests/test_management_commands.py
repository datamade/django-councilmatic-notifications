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
def test_find_bill_action_updates(db, setup):
    bill = councilmatic_models.Bill.objects.first()
    action = councilmatic_models.BillAction.objects.create(
        bill=bill,
        organization=councilmatic_models.Organization.objects.first(),
        description='test action',
        order=1,
        date=datetime.datetime.now(pytz.timezone(settings.TIME_ZONE)).strftime('%Y-%m-%d %H:%M:%S%z')
    )
    command = Command()
    bill_action_updates = command.find_bill_action_updates([bill.id], minutes=15)
    assert len(bill_action_updates) == 1
    assert bill_action_updates[0][0]['slug'] == bill.slug
    assert bill_action_updates[0][1]['description'] == action.description


@pytest.mark.django_db
def test_find_bill_search_updates(db, setup, mocker):
    bill = councilmatic_models.Bill.objects.create(
        legislative_session=ocd_legislative_models.LegislativeSession.objects.first(),
        from_organization=councilmatic_models.Organization.objects.first(),
        identifier='test bill'
    )
    new_response = mocker.MagicMock(spec=requests.Response)
    new_response.json.return_value = {
        'response': {
            'docs': [{
                'ocd_id': bill.id,
            }]
        }
    }
    new_requests_get = mocker.MagicMock(
        spec='requests.get',
        return_value=new_response
    )
    mock_requests_get = mocker.patch('requests.get', new=new_requests_get)
    command = Command()
    bill_search_updates = command.find_bill_search_updates([{'term': 'test', 'facets': {}}])
    assert len(bill_search_updates) == 1
    assert len(bill_search_updates[0]['bills']) == 1
    assert bill_search_updates[0]['bills'][0]['identifier'] == bill.identifier


@pytest.mark.django_db
def test_find_person_updates(db, setup):
    person = councilmatic_models.Person.objects.first()
    bill = councilmatic_models.Bill.objects.create(
        legislative_session=ocd_legislative_models.LegislativeSession.objects.first(),
        from_organization=councilmatic_models.Organization.objects.first(),
        identifier='test bill'
    )
    councilmatic_models.BillSponsorship.objects.create(
        bill=bill,
        organization=councilmatic_models.Organization.objects.first(),
        person=person
    )
    command = Command()
    person_updates = command.find_person_updates([person.id])
    assert len(person_updates) == 1
    assert person_updates[0]['New sponsorships']['name'] == person.name
    assert person_updates[0]['New sponsorships']['slug'] == person.slug
    assert person_updates[0]['New sponsorships']['bills'][0]['slug'] == bill.slug


@pytest.mark.django_db
def test_find_committee_action_updates(db, setup):
    bill = councilmatic_models.Bill.objects.first()
    organization = councilmatic_models.Organization.objects.first()
    first_action = councilmatic_models.BillAction.objects.create(
        bill=bill,
        organization=organization,
        description='test action 1',
        date=datetime.datetime.now(pytz.timezone(settings.TIME_ZONE)).strftime('%Y-%m-%d %H:%M:%S%z'),
        order=1
    )
    second_action = councilmatic_models.BillAction.objects.create(
        bill=bill,
        organization=organization,
        description='test action 2',
        date=datetime.datetime.now(pytz.timezone(settings.TIME_ZONE)).strftime('%Y-%m-%d %H:%M:%S%z'),
        order=2
    )
    command = Command()
    committee_action_updates = command.find_committee_action_updates([organization.id])
    assert len(committee_action_updates) == 1
    assert committee_action_updates[0]['slug'] == organization.slug
    assert len(committee_action_updates[0]['bills']) == 1
    assert committee_action_updates[0]['bills'][0]['slug'] == bill.slug
    assert len(committee_action_updates[0]['bills'][0]['actions']) == 2
    assert committee_action_updates[0]['bills'][0]['actions'][0]['description'] == first_action.description
    assert committee_action_updates[0]['bills'][0]['actions'][1]['description'] == second_action.description


@pytest.mark.django_db
def test_find_committee_event_updates(db, setup):
    organization = councilmatic_models.Organization.objects.first()
    event = councilmatic_models.Event.objects.create(
        name='test event',
        start_date=(
            datetime.datetime.now(pytz.timezone(settings.TIME_ZONE)) +
            datetime.timedelta(minutes=15)
        ).strftime('%Y-%m-%d %H:%M:%S%z'),
        jurisdiction=organization.jurisdiction
    )
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
def test_find_new_events(db, setup):
    organization = councilmatic_models.Organization.objects.first()
    first_event = councilmatic_models.Event.objects.create(
        name='test event 1',
        jurisdiction=organization.jurisdiction
    )
    second_event = councilmatic_models.Event.objects.create(
        name='test event 2',
        jurisdiction=organization.jurisdiction
    )
    command = Command()
    new_events = command.find_new_events()
    assert len(new_events) == 2
    assert new_events[0]['name'] == first_event.name
    assert new_events[1]['name'] == second_event.name


@pytest.mark.django_db
def test_find_updated_events(db, setup):
    organization = councilmatic_models.Organization.objects.first()
    first_event = councilmatic_models.Event.objects.create(
        name='test event 1',
        jurisdiction=organization.jurisdiction
    )
    second_event = councilmatic_models.Event.objects.create(
        name='test event 2',
        jurisdiction=organization.jurisdiction
    )
    command = Command()
    new_events = command.find_updated_events()
    assert len(new_events) == 2
    assert new_events[0]['name'] == first_event.name
    assert new_events[1]['name'] == second_event.name


@pytest.mark.django_db
def test_send_users_updates(db, setup, user, mocker):
    """
    Test that users will be sent emails for subscriptions when updates are
    available.
    """
    bill = councilmatic_models.Bill.objects.first()
    notifications_models.BillActionSubscription.objects.create(
        bill=bill,
        user=user
    )
    councilmatic_models.BillAction.objects.create(
        bill=bill,
        organization=councilmatic_models.Organization.objects.first(),
        description='test action',
        order=1
    )
    send_notification_email = mocker.patch(
        'notifications.management.commands.send_notifications.send_notification_email',
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
