# -*- coding: utf-8 -*-
# Generated by Django 1.9 on 2016-02-25 20:48
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('random2', '0002_workerconfig'),
    ]

    operations = [
        migrations.AddField(
            model_name='workerconfig',
            name='project',
            field=models.SmallIntegerField(default=1),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='workerconfig',
            name='requester',
            field=models.SmallIntegerField(default=1),
            preserve_default=False,
        ),
    ]