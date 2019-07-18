import datetime

import pytest
import pytz
from pytest_django.fixtures import db
from django.contrib.auth.models import User
from django.core.management import call_command
from django.conf import settings

from councilmatic_core.models import Bill, BillAction, Event, Organization
from opencivicdata.legislative.models import EventLocation, LegislativeSession


@pytest.fixture(scope='module')
def setup(django_db_blocker):
    with django_db_blocker.unblock():
        call_command('loaddata', 'tests/fixtures/test_data.json')

    yield

    django_db_blocker.restore()


@pytest.fixture
@pytest.mark.django_db
def user(db):
    user = {
        'username': 'testuser',
        'password': 'foobar',
        'is_superuser': False
    }
    return User.objects.create(**user)


@pytest.fixture
@pytest.mark.django_db
def new_bill(db, setup):
    return Bill.objects.create(
        legislative_session=LegislativeSession.objects.first(),
        from_organization=Organization.objects.first(),
        identifier='test bill'
    )


@pytest.fixture
@pytest.mark.django_db
def new_bill_actions(new_bill):
    first_action = BillAction.objects.create(
        bill=new_bill,
        organization=new_bill.from_organization.councilmatic_organization,
        description='test action 1',
        date=(
            datetime.datetime.now(pytz.timezone(settings.TIME_ZONE)) +
            datetime.timedelta(minutes=1)
        ).strftime('%Y-%m-%d %H:%M:%S%z'),
        order=2
    )
    second_action = BillAction.objects.create(
        bill=new_bill,
        organization=new_bill.from_organization.councilmatic_organization,
        description='test action 2',
        date=(
            datetime.datetime.now(pytz.timezone(settings.TIME_ZONE)) +
            datetime.timedelta(minutes=2)
        ).strftime('%Y-%m-%d %H:%M:%S%z'),
        order=3
    )
    return first_action, second_action


@pytest.fixture
@pytest.mark.django_db
def new_events(db, setup):
    organization = Organization.objects.first()
    location = EventLocation.objects.first()
    first_event = Event.objects.create(
        name='test event 1',
        start_date=(
            datetime.datetime.now(pytz.timezone(settings.TIME_ZONE)) +
            datetime.timedelta(minutes=15)
        ).strftime('%Y-%m-%d %H:%M:%S%z'),
        end_date=(
            datetime.datetime.now(pytz.timezone(settings.TIME_ZONE)) +
            datetime.timedelta(minutes=16)
        ).strftime('%Y-%m-%d %H:%M:%S%z'),
        jurisdiction=organization.jurisdiction,
        location=location
    )
    second_event = Event.objects.create(
        name='test event 2',
        start_date=(
            datetime.datetime.now(pytz.timezone(settings.TIME_ZONE)) +
            datetime.timedelta(minutes=17)
        ).strftime('%Y-%m-%d %H:%M:%S%z'),
        end_date=(
            datetime.datetime.now(pytz.timezone(settings.TIME_ZONE)) +
            datetime.timedelta(minutes=18)
        ).strftime('%Y-%m-%d %H:%M:%S%z'),
        jurisdiction=organization.jurisdiction,
        location=location
    )
    return first_event, second_event
