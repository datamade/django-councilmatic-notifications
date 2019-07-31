import pytest
from django.core.management import call_command
from councilmatic_core import models as councilmatic_models
from opencivicdata.legislative import models as ocd_legislative_models
from notifications import models as notifications_models


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
def test_find_bill_search_updates(new_bill, mocker, mock_bill_search, subscriptions):
    bill_search_updates = subscriptions['bill_search'].get_updates()
    assert len(bill_search_updates['bills']) == 1
    assert bill_search_updates['bills'][0]['identifier'] == new_bill.identifier


@pytest.mark.django_db
def test_find_person_updates(new_bill, subscriptions):
    person = subscriptions['person'].person
    spon = councilmatic_models.BillSponsorship.objects.create(
        bill=new_bill,
        organization=new_bill.from_organization.councilmatic_organization,
        person=person
    )

    person_updates = subscriptions['person'].get_updates()
    assert len(person_updates) == 1

    assert person_updates['New sponsorships']['name'] == person.name
    assert person_updates['New sponsorships']['slug'] == person.slug
    assert person_updates['New sponsorships']['bills'][0]['slug'] == new_bill.slug

    assert subscriptions['person'].seen_sponsorship_ids == [spon.id]


@pytest.mark.django_db
def test_find_committee_action_updates(new_bill, new_bill_actions, subscriptions):
    """
    Test finding new BillActions for a committee.
    """
    organization = new_bill.from_organization
    assert subscriptions['committee_action'].seen_bills.count() == 0

    committee_action_updates = subscriptions['committee_action'].get_updates()
    assert committee_action_updates['slug'] == organization.slug

    assert len(committee_action_updates['bills']) == 1
    assert committee_action_updates['bills'][0]['slug'] == new_bill.slug

    assert len(committee_action_updates['bills'][0]['actions']) == 2
    assert committee_action_updates['bills'][0]['actions'][0]['description'] == new_bill_actions[1].description
    assert committee_action_updates['bills'][0]['actions'][1]['description'] == new_bill_actions[0].description

    assert subscriptions['committee_action'].seen_bills.count() == 1
    assert subscriptions['committee_action'].seen_bills.first().last_seen_order == new_bill_actions[1].order


@pytest.mark.django_db
def test_find_committee_action_existing_updates(new_bill, new_bill_actions, subscriptions):
    """
    Test finding updates to existing Bills for a committee.
    """
    organization = new_bill.from_organization
    subscriptions['committee_action'].seen_bills.add(
        notifications_models.CommitteeActionSubscriptionBill.objects.create(
           bill=new_bill,
           last_seen_order=0
        )
    )

    committee_action_updates = subscriptions['committee_action'].get_updates()
    assert committee_action_updates['slug'] == organization.slug

    assert len(committee_action_updates['bills']) == 1
    assert committee_action_updates['bills'][0]['slug'] == new_bill.slug

    assert len(committee_action_updates['bills'][0]['actions']) == 2

    assert subscriptions['committee_action'].seen_bills.count() == 1
    assert subscriptions['committee_action'].seen_bills.first().last_seen_order == new_bill_actions[1].order


@pytest.mark.django_db
def test_find_committee_event_updates(new_events, subscriptions):
    organization = councilmatic_models.Organization.objects.first()
    event = new_events[0]
    ocd_legislative_models.EventParticipant.objects.create(
        event=event,
        organization=organization
    )

    committee_event_updates = subscriptions['committee_event'].get_updates()
    assert committee_event_updates['slug'] == organization.slug

    assert len(committee_event_updates['events']) == 1
    assert committee_event_updates['events'][0]['name'] == event.name


@pytest.mark.django_db
def test_user_has_subscriptions(user, subscriptions):
    notifications_user = notifications_models.NotificationsUser.objects.get(
        id=user.id
    )
    assert notifications_user.has_subscriptions

    new_user = notifications_models.NotificationsUser.objects.create(
        username='test_no_subscriptions',
        password='foobar',
        is_superuser=False
    )
    assert not new_user.has_subscriptions

    notifications_models.BillActionSubscription.objects.create(
        user=new_user,
        bill=subscriptions['bill_action'].bill
    )
    assert new_user.has_subscriptions


@pytest.mark.django_db
def test_send_notification_email(db, setup, new_bill_actions, user,
                                 subscriptions, mocker, mock_bill_search):
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
def test_dont_send_notification_email_no_subscriptions(mocker, user):
    """
    Test that users won't be sent emails when they have no subscriptions.
    """
    send_notification_email = mocker.patch(
        'notifications.management.commands.send_notifications.send_notification_email.delay',
        autospec=True
    )
    call_command('send_notifications')
    assert send_notification_email.call_count == 0


@pytest.mark.django_db
def test_dont_send_notification_email_no_updates(mocker, user, setup):
    """
    Test that users won't be sent emails when their subscriptions have no updates.
    """
    # Create a new subscription that should have no updates.
    notifications_models.CommitteeEventSubscription.objects.create(
        user=user,
        committee=councilmatic_models.Organization.objects.first()
    )
    send_notification_email = mocker.patch(
        'notifications.management.commands.send_notifications.send_notification_email.delay',
        autospec=True
    )
    call_command('send_notifications')
    assert send_notification_email.call_count == 0
