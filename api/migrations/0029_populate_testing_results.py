# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.conf import settings
from django.db import migrations
from django.db.models import Count
from api.migrations import (get_property, get_property_raw,
        load_property, set_property, delete_property_blob)

import abc
from collections import defaultdict
from copy import copy
import datetime
import lzma

# For Result's constant status values
import api.models

class Converter(object, metaclass=abc.ABCMeta):
    def __init__(self, apps, schema_editor):
        # We can't import the models directly as they may be a newer
        # version than this migration expects. We use the historical version.
        self.Project = apps.get_model('api', 'Project')
        self.Message = apps.get_model('api', 'Message')
        self.MessageProperty = apps.get_model('api', 'MessageProperty')
        self.ProjectProperty = apps.get_model('api', 'ProjectProperty')
        self.MessageResult = apps.get_model('api', 'MessageResult')
        self.ProjectResult = apps.get_model('api', 'ProjectResult')
        self.LogEntry = apps.get_model('api', 'LogEntry')

    @abc.abstractmethod
    def get_objects_for_project(self, po):
        pass

    @abc.abstractmethod
    def set_property(self, obj, name, value):
        pass

    @abc.abstractmethod
    def get_property(self, obj, name):
        pass

    @abc.abstractmethod
    def get_properties(self, obj, **kwargs):
        pass

    @abc.abstractmethod
    def delete_property(self, obj, name):
        pass

    @abc.abstractmethod
    def create_result(self, obj, **kwargs):
        pass

    def get_projects_with_tests(self):
        return self.Project.objects.filter(
                projectproperty__name__startswith='testing.').distinct()

    def get_tests(self, po):
        # Based on TestingModule.get_tests
        ret = {}
        props = self.ProjectProperty.objects.filter(name__startswith='testing.tests.',
                                                    project=po)
        for p in props:
            k = p.name
            v = load_property(p)
            tn = k[len("testing.tests."):]
            if "." not in tn:
                continue
            an = tn[tn.find(".") + 1:]
            tn = tn[:tn.find(".")]
            ret.setdefault(tn, {})
            ret[tn][an] = v
        return ret

    def do_result_from_properties(self):
        for po in self.Project.objects.all():
            tests = self.get_tests(po)
            for obj in self.get_objects_for_project(po):
                pending_status = api.models.Result.RUNNING \
                        if self.get_property(obj, "testing.started") \
                        else api.models.Result.PENDING
                done_tests = set()
                results = []
                for prop in self.get_properties(obj, name__startswith='testing.report.'):
                    tn = prop.name[len('testing.report.'):]
                    done_tests.add(tn)
                    r = self.create_result(obj)
                    report = load_property(prop)
                    passed = report["passed"]
                    del report["passed"]
                    log = self.get_property(obj, "testing.log." + tn)
                    r.name = 'testing.' + tn
                    r.status = api.models.Result.SUCCESS if passed else api.models.Result.FAILURE
                    r.last_update = datetime.datetime.utcnow()
                    r.data = report
                    if log:
                        log_xz = lzma.compress(log.encode("utf-8"))
                        log_entry = self.LogEntry(data_xz=log_xz)
                        log_entry.save()
                        r.log_entry = log_entry
                        self.delete_property(obj, "testing.log." + tn)
                    r.save()
                    results.append(r)
                    self.delete_property(obj, "testing.report." + tn)
                if self.get_property(obj, "testing.ready"):
                    for tn, test in tests.items():
                        if tn in done_tests:
                            continue
                        r = self.create_result(obj)
                        r.name = 'testing.' + tn
                        r.status = pending_status
                        r.last_update = datetime.datetime.utcnow()
                        r.save()
                        results.append(r)
                    self.delete_property(obj, "testing.ready")
                #print(obj, len(done_tests), len(tests) - len(done_tests))
                obj.results.add(*results)
                try:
                    self.delete_property(obj, "testing.started")
                    self.delete_property(obj, "testing.failed")
                    self.delete_property(obj, "testing.start-time")
                except:
                    pass

    def do_result_to_properties(self):
        for po in self.Project.objects.all():
            for obj in self.get_objects_for_project(po):
                by_status = defaultdict(lambda: 0)
                start_time = datetime.datetime.utcnow()
                for r in obj.results.filter(name__startswith='testing.'):
                    by_status[r.status] += 1
                    if r.status in (api.models.Result.SUCCESS, api.models.Result.FAILURE):
                        tn = r.name[len('testing.'):]
                        report = copy(r.data)
                        report['passed'] = (r.status == api.models.Result.SUCCESS)
                        self.set_property(obj, "testing.report." + tn, report)
                        if r.log_entry:
                            log = lzma.decompress(r.log_entry.data_xz).decode("utf-8")
                            self.set_property(obj, "testing.log." + tn, log)
                    else:
                        started = started or r.status == api.models.Result.RUNNING
                        if r.last_update < start_time:
                            start_time = r.last_update
                #print(obj, dict(by_status))
                if by_status[api.models.Result.FAILURE]:
                    self.set_property(obj, "testing.failed", True)
                if by_status[api.models.Result.RUNNING]:
                    self.set_property(obj, "testing.started", True)
                    self.set_property(obj, "testing.start-time", d.timestamp())
                if by_status[api.models.Result.RUNNING] + by_status[api.models.Result.PENDING]:
                    self.set_property(obj, "testing.ready", 1)
                else:
                    self.set_property(obj, "testing.done", True)
                obj.results.filter(name__startswith='testing.').delete()

class ProjectConverter(Converter):
    def get_objects_for_project(self, po):
        yield po

    def set_property(self, obj, name, value):
        set_property(self.ProjectProperty, name, value, project=obj)

    def get_property(self, obj, name):
        try:
            return get_property(self.ProjectProperty, name, project=obj)
        except:
            return None

    def get_properties(self, obj, **kwargs):
        return self.ProjectProperty.objects.filter(project=obj, **kwargs)

    def delete_property(self, obj, name):
        delete_property_blob(self.ProjectProperty, name, project=obj)
        get_property_raw(self.ProjectProperty, name, project=obj).delete()

    def create_result(self, obj, **kwargs):
        return self.ProjectResult(project=obj, **kwargs)

class MessageConverter(Converter):
    def get_objects_for_project(self, po):
        yield from self.Message.objects.filter(is_series_head=True, project=po)

    def set_property(self, obj, name, value):
        set_property(self.MessageProperty, name, value, message=obj)

    def get_property(self, obj, name):
        try:
            return get_property(self.MessageProperty, name, message=obj)
        except:
            return None

    def get_properties(self, obj, **kwargs):
        return self.MessageProperty.objects.filter(message=obj, **kwargs)

    def delete_property(self, obj, name):
        delete_property_blob(self.MessageProperty, name, message=obj)
        get_property_raw(self.MessageProperty, name, message=obj).delete()

    def create_result(self, obj, **kwargs):
        return self.MessageResult(message=obj, **kwargs)

def result_from_properties(apps, schema_editor):
    ProjectConverter(apps, schema_editor).do_result_from_properties()
    MessageConverter(apps, schema_editor).do_result_from_properties()

def result_to_properties(apps, schema_editor):
    ProjectConverter(apps, schema_editor).do_result_to_properties()
    MessageConverter(apps, schema_editor).do_result_to_properties()

class Migration(migrations.Migration):

    dependencies = [
        ('api', '0028_populate_git_results'),
    ]

    operations = [
        migrations.RunPython(result_from_properties,
                             reverse_code=result_to_properties),
    ]
