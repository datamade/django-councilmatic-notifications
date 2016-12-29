from django.contrib import admin
from notifications.models import *

admin.site.register(PersonSubscription)
admin.site.register(CommitteeActionSubscription)
admin.site.register(CommitteeEventSubscription)
admin.site.register(BillSearchSubscription)
admin.site.register(BillActionSubscription)
admin.site.register(EventsSubscription)