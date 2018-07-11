# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.conf import settings
from django.db import migrations
from django.db.models import Count
from api.migrations import get_property, set_property, delete_property_blob

import datetime
import lzma

# For Result's constant status values
import api.models

def result_from_properties(apps, schema_editor):
    # We can't import the models directly as they may be a newer
    # version than this migration expects. We use the historical version.
    # The code is mostly based on the implementation of the old
    # "rest_results_hook" method in GitModule, which used to build
    # a Result namedtuple from the properties
    Message = apps.get_model('api', 'Message')
    MessageProperty = apps.get_model('api', 'MessageProperty')
    MessageResult = apps.get_model('api', 'MessageResult')
    LogEntry = apps.get_model('api', 'LogEntry')
    messages = Message.objects.filter(properties__name__startswith='git.').distinct()
    for m in messages:
        need_apply = get_property(MessageProperty, 'git.need-apply', message=m)
        if need_apply is None:
            continue
        log = get_property(MessageProperty, "git.apply-log", message=m)
        r = MessageResult(name='git', message=m)
        if log:
            log_xz = lzma.compress(log.encode("utf-8"))
            log_entry = LogEntry(data_xz=log_xz)
            log_entry.save()
            r.log_entry = log_entry
            data = {}
            if get_property(MessageProperty, "git.apply-failed", message=m):
                r.status = api.models.Result.FAILURE
            else:
                git_repo = get_property(MessageProperty, "git.repo", message=m)
                git_tag = get_property(MessageProperty, "git.tag", message=m)
                git_url = get_property(MessageProperty, "git.url", message=m)
                git_base = get_property(MessageProperty, "git.base", message=m)
                if git_repo and git_tag:
                    data['repo'] = git_repo
                    data['tag'] = 'refs/tags/' + git_tag
                    if git_url:
                        data['url'] = git_url
                    if git_base:
                        data['base'] = git_base
                r.status = api.models.Result.SUCCESS
            r.data = data
        else:
            status = api.models.Result.PENDING
        r.last_update = datetime.datetime.utcnow()
        r.save()
    messages = Message.objects.filter(properties__name='git.apply-log', properties__blob=True)
    for m in messages:
        delete_property_blob(MessageProperty, "git.apply-log", message=m)
    MessageProperty.objects.filter(name__startswith='git.').delete()

def result_to_properties(apps, schema_editor):
    # We can't import the models directly as they may be a newer
    # version than this migration expects. We use the historical version.
    Message = apps.get_model('api', 'Message')
    MessageProperty = apps.get_model('api', 'MessageProperty')
    MessageResult = apps.get_model('api', 'MessageResult')
    LogEntry = apps.get_model('api', 'LogEntry')
    messages = Message.objects.filter(results__name='git')
    for m in messages:
        r = MessageResult.objects.get(name='git', message=m)
        if not r:
            continue
        if r.status == api.models.Result.PENDING:
            set_property(MessageProperty, 'git.need-apply', True, message=m)
        else:
            log = lzma.decompress(r.log_entry.data_xz).decode("utf-8")
            set_property(MessageProperty, 'git.need-apply', False, message=m)
            set_property(MessageProperty, 'git.apply-log', log, message=m)
            if r.status == api.models.Result.FAILURE:
                set_property(MessageProperty, "git.apply-failed", True, message=m)
            else:
                set_property(MessageProperty, "git.apply-failed", False, message=m)
                if 'repo' in r.data:
                    set_property(MessageProperty, "git.repo", r.data['repo'], message=m)
                if 'tag' in r.data:
                    set_property(MessageProperty, "git.tag", r.data['repo'][len('refs/tags/'):], message=m)
                if 'url' in r.data:
                    set_property(MessageProperty, "git.url", r.data['url'], message=m)
                if 'base' in r.data:
                    set_property(MessageProperty, "git.base", r.data['base'], message=m)
    MessageResult.objects.filter(message=m, name='git').delete()

class Migration(migrations.Migration):

    dependencies = [
        ('api', '0027_auto_20180521_0152'),
    ]

    operations = [
        migrations.RunPython(result_from_properties,
                             reverse_code=result_to_properties),
    ]
