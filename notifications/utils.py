from django.template.loader import get_template
from django.conf import settings
from django.core.mail import EmailMultiAlternatives

def send_signup_email(user, host, redirect):

    context = {
        'user': user,
        'SITE_META': settings.SITE_META,
        'host': host,
        'redirect': redirect,
    }

    html = "signup_email.html"
    txt = "signup_email.txt"
    html_template = get_template(html)
    text_template = get_template(txt)
    html_content = html_template.render(context)
    text_content = text_template.render(context)
    subject = 'Activate your account with {0}'.format(settings.SITE_META['site_name'])

    # send email confirmation to info@largelots.org
    msg = EmailMultiAlternatives(subject,
                                 text_content,
                                 settings.EMAIL_HOST_USER,
                                 [user.email])

    msg.attach_alternative(html_content, 'text/html')
    msg.send()
