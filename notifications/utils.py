from django.template.loader import get_template
from django.template import Context
from django.conf import settings

def send_signup_email(user):
    
    context = {
        'user': user, 
        'SITE_META': settings.SITE_META
    }

    context = Context(context)
    html = "signup_email.html"
    txt = "signup_email.txt"
    html_template = get_template(html)
    text_template = get_template(txt)
    html_content = html_template.render(context)
    text_content = text_template.render(context)
    subject = '{0} account activation' % (settings.SITE_META['site_name'])

    from_email = settings.EMAIL_HOST_USER
    to_email = user.email

    # send email confirmation to info@largelots.org
    msg = EmailMultiAlternatives(subject, text_content, from_email, to_email)
    msg.attach_alternative(html_content, 'text/html')
    msg.send()
