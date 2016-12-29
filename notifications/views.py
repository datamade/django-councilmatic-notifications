import json
import datetime
import pytz
import sys
import random
import hashlib

from io import StringIO

from django.shortcuts import render, get_object_or_404
from django.http import HttpResponseRedirect, HttpResponse
from django.conf import settings
from django import forms
from django.utils import timezone

from django.core.urlresolvers import reverse
from django.core.exceptions import ObjectDoesNotExist
from django.core.mail import EmailMessage
from django.core.cache import cache
from django.core import management

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm, PasswordResetForm
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User # XXX TODO: migrate to custom User model https://docs.djangoproject.com/en/1.9/topics/auth/customizing/ http://blog.mathandpencil.com/replacing-django-custom-user-models-in-an-existing-application/ https://www.caktusgroup.com/blog/2013/08/07/migrating-custom-user-model-django/

from django.views.decorators.csrf import csrf_exempt
from django.views.generic import TemplateView, ListView, DetailView

from django.template.loader import get_template
from django.template import Context

from django.db.models import Q
from django.db import IntegrityError

from councilmatic_core.models import Bill, Organization, Person, Event
from notifications.models import PersonSubscription, BillActionSubscription, \
    CommitteeActionSubscription, CommitteeEventSubscription, \
    BillSearchSubscription, EventsSubscription, SubscriptionProfile

from notifications.utils import send_signup_email

app_timezone = pytz.timezone(settings.TIME_ZONE)

class CouncilmaticUserCreationForm(UserCreationForm):
    email = forms.EmailField(label="Email address", required=True,
        help_text="Required.")

    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2")

    def save(self, commit=True):
        user = super().save(commit=False) # this should set the password
        user.email = self.cleaned_data["email"]
        user.is_active = False
        if commit:
            user.save()

        profile = SubscriptionProfile()
        profile.user = user

        salt = hashlib.sha1(str(random.random()).encode('utf-8')).hexdigest()[:5]
        activation_key = hashlib.sha1((salt + user.username).encode('utf-8')).hexdigest()

        profile.activation_key = activation_key

        now = timezone.now()
        expiration = now + datetime.timedelta(days=1)
        profile.key_expires = expiration

        profile.save()

        return user


def notifications_activation(request, activation_key):

    profile = get_object_or_404(SubscriptionProfile,
                                activation_key=activation_key)

    message_level = 'INFO'
    redirect = reverse('index')

    next_url = request.GET.get('next')

    if next_url:
        redirect = next_url

    if not profile.user.is_active:

        if timezone.now() > profile.key_expires:

            salt = hashlib.sha1(str(random.random()).encode('utf-8')).hexdigest()[:5]
            activation_key = hashlib.sha1((salt + profile.user.username).encode('utf-8')).hexdigest()

            profile.activation_key = activation_key
            profile.save()

            send_signup_email(profile.user, request.get_host())

            message = 'Your activation link has expired. A new link has been sent to your email.'
            message_level = 'ERROR'

        else:
            profile.user.is_active = True
            profile.user.save()

            redirect = reverse('notifications_login')

            if next_url:
                redirect = '{0}?next={1}'.format(redirect, next_url)

            message = 'Your account has been activated! Login to continue.'

    else:
        message = 'Your account has already been activated.'

    messages.add_message(request,
                         getattr(messages, message_level),
                         message)

    return HttpResponseRedirect(redirect)

def notifications_signup(request):
    form = None
    if request.method == 'POST':
        form = CouncilmaticUserCreationForm(data=request.POST)
        if form.is_valid():
            try:
                user = form.save()

                redirect = reverse('index')
                if request.GET.get('next'):
                    redirect = request.GET['next']

                host = '{0}://{1}'.format(request.scheme, request.get_host())
                send_signup_email(user, host, redirect)
                messages.add_message(request, messages.INFO, 'Check your email for a link to confirm your account!')

                return HttpResponseRedirect(redirect)
            except IntegrityError:
                response = HttpResponse('Not able to save form.')
                response.status_code = 500
                return response
        else:
            return render(request, 'notifications_signup.html', {'form': form}, status=500)
    if not form:
        form = CouncilmaticUserCreationForm()
    return render(request, 'notifications_signup.html', {'form': form})

def notifications_login(request):
    form = None
    if request.method == 'POST':
        form = AuthenticationForm(data=request.POST)
        if form.is_valid():
            try:
                user = form.get_user()
                login(request, user)

                redirect = reverse('index')
                if request.GET.get('next'):
                    redirect = request.GET['next']

                return HttpResponseRedirect(redirect)
            except IntegrityError:
                response = HttpResponse('Not able to find or login user.')
                response.status_code = 500
                return response
        else:
            return render(request, 'notifications_login.html', {'form': form}, status=500)
    if not form:
        form = AuthenticationForm()
    return render(request, 'notifications_login.html', {'form': form})

def notifications_logout(request):
    logout(request)
    return HttpResponseRedirect('/')

@login_required(login_url='/login/')
def notifications_account_settings(request):
    return HttpResponse('notifications_account_settings')

class SubscriptionsManageView(LoginRequiredMixin, TemplateView):
    template_name = 'subscriptions_manage.html'

    def get_context_data(self, *args, **kwargs):
        context = super(SubscriptionsManageView, self).get_context_data(*args, **kwargs)

        context['person_subscriptions'] = self.request.user.personsubscriptions.all()
        context['committee_action_subscriptions'] = self.request.user.committeeactionsubscriptions.all()
        context['committee_event_subscriptions'] = self.request.user.committeeeventsubscriptions.all()
        context['bill_search_subscriptions'] = self.request.user.billsearchsubscriptions.all()
        context['bill_action_subscriptions'] = self.request.user.billactionsubscriptions.all()
        context['events_subscriptions'] = self.request.user.eventssubscriptions.all()

        obj_copy = context.copy()
        del obj_copy['view']
        if any([len(s) != 0 for s in obj_copy.values()]):
            context['subscriptions'] = 'Yes, subscriptions.'
        else:
            context['subscriptions'] = None

        return context

@login_required(login_url='/login/')
def bill_subscribe(request, slug):
    bill = Bill.objects.get(slug=slug)
    (bill_action_subscription, created) = BillActionSubscription.objects.get_or_create(user=request.user, bill=bill)

    cache.delete('subscriptions_manage')

    return HttpResponse('Subscribed to bill %s.' % str(bill))

@login_required(login_url='/login/')
def bill_unsubscribe(request, slug):
    bill = Bill.objects.get(slug=slug)

    try:
        bill_action_subscription = BillActionSubscription.objects.get(user=request.user, bill=bill)
    except ObjectDoesNotExist:
        response = HttpResponse('This bill subscription does not exist.')
        response.status_code = 500
        return response

    bill_action_subscription.delete()

    return HttpResponse('Unsubscribed from bill %s.' % str(bill))

@login_required(login_url='/login/')
def person_subscribe(request, slug):
    person = Person.objects.get(slug=slug)

    (person_subscription, created) = PersonSubscription.objects.get_or_create(user=request.user, person=person)

    return HttpResponse('Subscribed to person %s.' % str(person))

@login_required(login_url='/login/')
def person_unsubscribe(request, slug):
    person = Person.objects.get(slug=slug)

    try:
        person_subscription = PersonSubscription.objects.get(user=request.user, person=person)
    except ObjectDoesNotExist:
        response = HttpResponse('This person subscription does not exist.')
        response.status_code = 500
        return response

    person_subscription.delete()

    return HttpResponse('Unsubscribed from person %s.' % str(person))

@login_required(login_url='/login/')
def committee_events_subscribe(request, slug):
    committee = Organization.objects.get(slug=slug)
    (committee_events_subscription, created) = CommitteeEventSubscription.objects.get_or_create(user=request.user, committee=committee)

    return HttpResponse('Subscribed to events of %s.' % str(committee))

@login_required(login_url='/login/')
def committee_events_unsubscribe(request, slug):
    committee = Organization.objects.get(slug=slug)
    try:
        committee_events_subscription = CommitteeEventSubscription.objects.get(user=request.user, committee=committee)
    except ObjectDoesNotExist:
        response = HttpResponse('This committee event subscription does not exist.')
        response.status_code = 500
        return response

    committee_events_subscription.delete()
    return HttpResponse('Unsubscribed from events of %s.' % str(committee))

@login_required(login_url='/login/')
def committee_actions_subscribe(request, slug):
    committee = Organization.objects.get(slug=slug)
    (committee_actions_subscription, created) = CommitteeActionSubscription.objects.get_or_create(user=request.user, committee=committee)

    return HttpResponse('Subscribed to actions of %s.' % str(committee))

@login_required(login_url='/login/')
def committee_actions_unsubscribe(request, slug):
    committee = Organization.objects.get(slug=slug)

    try:
        committee_actions_subscription = CommitteeActionSubscription.objects.get(user=request.user, committee=committee)
    except ObjectDoesNotExist:
        response = HttpResponse('This committee action subscription does not exist.')
        response.status_code = 500
        return response

    committee_actions_subscription.delete()

    return HttpResponse('Unsubscribed from actions of %s.' % str(committee))

@login_required(login_url='/login/')
def search_subscribe(request):
    q = request.POST.get('query')
    selected_facets = request.POST.get('selected_facets')
    search_params = {'term': q, 'facets': json.loads(selected_facets)}
    (bss, created) = BillSearchSubscription.objects.get_or_create(user=request.user,
                                                                  search_params=search_params)

    return HttpResponse('Subscribed to search for: %s.' % q)

@login_required(login_url='/login/')
def search_unsubscribe(request, subscription_id):
    try:
        bss = BillSearchSubscription.objects.get(user=request.user,
                                                 id=subscription_id)
    except ObjectDoesNotExist:
        response = HttpResponse('This search subscription does not exist.')
        response.status_code = 500
        return response

    bss.delete()
    return HttpResponse('Unsubscribed from bill search')

@login_required(login_url='/login/')
def search_check_subscription(request):
    q = request.POST.get('query')
    selected_facets = request.POST.get('selected_facets')
    selected_facets_json = json.loads(selected_facets)
    search_params = {'term': q, 'facets': selected_facets_json}

    try:
        bss = BillSearchSubscription.objects.get(user=request.user,
                                                 search_params__exact=search_params)

    except ObjectDoesNotExist:
        response = HttpResponse('This bill search subscription does not exist.')
        response.status_code = 500
        return response

    return HttpResponse('true')

# TODO: Make these do something
@login_required(login_url='/login/')
def events_subscribe(request):
    (events_subscription, created) = EventsSubscription.objects.get_or_create(user=request.user)

    return HttpResponse('%s unsubscribed from all events.' % request.user)

@login_required(login_url='/login/')
def events_unsubscribe(request):
    try:
        events_subscription = EventsSubscription.objects.get(user=request.user)
    except ObjectDoesNotExist:
        response = HttpResponse('This event subscription does not exist.')
        response.status_code = 500
        return response

    events_subscription.delete()

    return HttpResponse('%s unsubscribed from all events.' % str(request.user))

@login_required(login_url='/login/')
def send_notifications(request):
    notify_output = StringIO()
    management.call_command('send_notifications', users=request.user.username, stdout=notify_output)
    results = notify_output.getvalue()

    timestamp = json.dumps(datetime.datetime.now().isoformat())

    # TODO: Make this more refined, using json.loads(), to show count of each subscription.
    if 'no email' in results:
        return HttpResponse(json.dumps({'status': 'ok', 'email_sent': 'false', 'date': timestamp}), content_type='application/json')
    else:
        return HttpResponse(json.dumps({'status': 'ok', 'email_sent': 'true', 'date': timestamp}), content_type='application/json')
# The function worker_handle_notification_email() is invoked when the 'notifications_emails' queue (notification_emails_queue)
# is woken up.


