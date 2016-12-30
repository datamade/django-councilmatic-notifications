from django.conf.urls import include, url
from django.views.decorators.cache import never_cache
from django.contrib.auth.views import password_change, password_change_done

from notifications.views import notifications_login, notifications_logout, \
    notifications_signup, notifications_activation, notifications_account_settings, \
    SubscriptionsManageView, person_subscribe, person_unsubscribe, bill_subscribe, \
    bill_unsubscribe, committee_events_subscribe, committee_events_unsubscribe, \
    committee_actions_subscribe, committee_actions_unsubscribe, search_check_subscription, \
    search_subscribe, search_unsubscribe, events_subscribe, events_unsubscribe, \
    send_notifications

import django_rq


urlpatterns = [
    url(r'^login/$', notifications_login, name='notifications_login'),
    url(r'^logout/$', notifications_logout, name='notifications_logout'),
    url(r'^signup/$', notifications_signup, name='notifications_signup'),
    url(r'^activation/(?P<activation_key>[^/]+)/$', notifications_activation, name='notifications_activation'),
    url(r'^account/settings/$', notifications_account_settings, name='notifications_account_settings'),
    url(r'^account/subscriptions/$', never_cache(SubscriptionsManageView.as_view()), name='subscriptions_manage'),
    # url(r'^notification_loaddata$', notification_loaddata, name='notification_loaddata'),
    # list of things to subscribe/unsubscribe to:
    # - people
    # - committee actions
    # - committee events
    # - bill searches
    # - bill actions
    # - all events
    url(r'^person/(?P<slug>[^/]+)/subscribe/$', person_subscribe, name='person_subscribe'),
    url(r'^person/(?P<slug>[^/]+)/unsubscribe/$', person_unsubscribe, name='person_unsubscribe'),
    url(r'^legislation/(?P<slug>[^/]+)/subscribe/$', bill_subscribe, name='bill_subscribe'),
    url(r'^legislation/(?P<slug>[^/]+)/unsubscribe/$', bill_unsubscribe, name='bill_unsubscribe'),
    url(r'^committee/(?P<slug>[^/]+)/events/subscribe/$',
        committee_events_subscribe, name='committee_events_subscribe'),
    url(r'^committee/(?P<slug>[^/]+)/events/unsubscribe/$',
        committee_events_unsubscribe, name='committee_events_unsubscribe'),
    url(r'^committee/(?P<slug>[^/]+)/actions/subscribe/$',
        committee_actions_subscribe, name='committee_actions_subscribe'),
    url(r'^committee/(?P<slug>[^/]+)/actions/unsubscribe/$',
        committee_actions_unsubscribe, name='committee_actions_unsubscribe'),
    url(r'^search_check_subscription/$', search_check_subscription, name='search_check_subscription'),
    url(r'^search_subscribe/$', search_subscribe, name='search_subscribe'),
    url(r'^search_unsubscribe/(?P<subscription_id>[^/]+)/$', search_unsubscribe, name='search_unsubscribe'),
    url(r'^events/subscribe/$',
        events_subscribe, name='events_subscribe'),
    url(r'^events/unsubscribe/$',
        events_unsubscribe, name='events_unsubscribe'),
    url(r'^send-notifications/$',
        send_notifications, name='send-notifications'),
    # django-rq: https://github.com/ui/django-rq
    url(r'^django-rq/', include('django_rq.urls')),

    # URLs for password resets and changes.
    url(r'', include('password_reset.urls')),
    url(r'^password/change/$', password_change, {
        'template_name': 'password_change_form.html'},
        name='password_change'),
    url(r'^password/change/done/$', password_change_done,
        {'template_name': 'password_change_done.html'},
        name='password_change_done'),
]
