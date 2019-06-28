import pytest
from django.urls import reverse

@pytest.mark.django_db
def test_signup(client, mocker):
    send_signup_email = mocker.patch(
        'notifications.utils.send_signup_email',
        autospec=True
    )
    data = {
        'username': 'test',
        'email': 'test@example.com',
        'password1': 'foobar',
        'password2': 'foobar',
    }
    signup_response = client.post(reverse('notifications_signup'), data=data)
    assert signup_response.status_code == 302
    assert signup_response.url == reverse('index')
    assert send_signup_email.call_count == 1


def test_login():
    assert False


def test_account_settings():
    assert False


def test_subscriptions_list():
    assert False


def test_person_subscribe():
    assert False


def test_person_unsubscribe():
    assert False


def test_legislation_subscribe():
    assert False


def test_legislation_unsubscribe():
    assert False


def test_committee_events_subscribe():
    assert False


def test_committee_events_unsubscribe():
    assert False


def test_committee_actions_subscribe():
    assert False


def test_committee_actions_unsubscribe():
    assert False


def test_search_check_subscription():
    assert False


def test_search_subscribe():
    assert False


def test_search_unsubscribe():
    assert False


def test_events_subscribe():
    assert False


def test_events_unsubscribe():
    assert False


def test_send_notifications():
    assert False


def test_password_change():
    assert False
