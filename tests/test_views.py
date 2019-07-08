import pytest
from django.urls import reverse

from councilmatic_core import models as councilmatic_models


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


@pytest.mark.django_db
def test_person_subscribe(client, user, setup):
    client.force_login(user)
    person = councilmatic_models.Person.objects.first()
    subscription_res = client.get(
        reverse('person_subscribe', kwargs={'slug': person.slug})
    )
    assert subscription_res.status_code == 200
    assert 'Subscribed to person' in subscription_res.content.decode('utf-8')
