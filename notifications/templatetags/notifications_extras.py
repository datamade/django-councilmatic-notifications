import json
import urllib

from django import template
from django.db.models.query import QuerySet
from django.utils.safestring import mark_safe

register = template.Library()

# Used in subscriptions_manage.html. XXX: potential (?) site of concern for
# injecting JSON in search facet dicts and re-jsonifying it there (From
# https://stackoverflow.com/questions/4698220/django-template-convert-a-python-list-into-a-javascript-object
# ) Open ticket in Django (with discussion of problematic aspects)
# https://code.djangoproject.com/ticket/17419
@register.filter
def jsonify(object):
    if isinstance(object, QuerySet):
        return mark_safe(serialize('json', object))
    return mark_safe(json.dumps(object))
jsonify.is_safe = True

# Given a search subscription object, successfully reconstruct the
# URL representing it
@register.filter
def custom_reverse_search_url(subscription):
    url = '/search/'
    d = [('q',subscription.search_params['term'])]
    
    for k,vs in subscription.search_params['facets'].items():
        
        for v in vs:
            d.append(("selected_facets","%s_exact:%s" % (k,v)))
    
    url += "?" + urllib.parse.urlencode(d)
    
    return url
