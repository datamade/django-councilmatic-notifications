# Generated by Django 2.1.10 on 2019-07-18 21:28

import django.contrib.postgres.fields
import django.core.validators
from django.db import migrations, models
import django.db.models.deletion
import opencivicdata.core.models.base
import re


class Migration(migrations.Migration):

    dependencies = [
        ('councilmatic_core', '0049_alter_person_headshot'),
        ('notifications', '0005_auto_20161121_1208'),
    ]

    operations = [
        migrations.CreateModel(
            name='CommitteeActionSubscriptionBill',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('last_seen_order', models.PositiveIntegerField(default=0)),
                ('bill', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='committee_subscriptions', to='councilmatic_core.Bill')),
            ],
        ),
        migrations.AddField(
            model_name='billactionsubscription',
            name='last_seen_order',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='personsubscription',
            name='seen_sponsorship_ids',
            field=django.contrib.postgres.fields.ArrayField(base_field=opencivicdata.core.models.base.OCDIDField(ocd_type='bill', validators=[django.core.validators.RegexValidator(flags=re.RegexFlag(32), message='ID must match ^ocd-bill/[0-9a-f]{8}-([0-9a-f]{4}-){3}[0-9a-f]{12}$', regex='^ocd-bill/[0-9a-f]{8}-([0-9a-f]{4}-){3}[0-9a-f]{12}$')]), default=list, size=None),
        ),
        migrations.AddField(
            model_name='committeeactionsubscription',
            name='seen_bills',
            field=models.ManyToManyField(to='notifications.CommitteeActionSubscriptionBill'),
        ),
    ]
