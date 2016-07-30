#!/usr/bin/env python3
#
# Copyright 2016 Red Hat, Inc.
#
# Authors:
#     Fam Zheng <famz@redhat.com>
#
# This work is licensed under the MIT License.  Please see the LICENSE file or
# http://opensource.org/licenses/MIT.

from django.conf.urls import url
from django.http import HttpResponse, HttpResponseForbidden, Http404, \
                        HttpResponseRedirect
from django.core.exceptions import PermissionDenied
from django.core.urlresolvers import reverse
from django.template import Template, Context
from mod import PatchewModule
import time
import smtplib
import email
import traceback
import math
from api.views import APILoginRequiredView
from api.models import Message, Project
from api.search import SearchEngine
from event import emit_event, declare_event
from schema import *

_instance = None

class TestingModule(PatchewModule):
    """Testing module"""

    name = "testing"

    test_schema = \
        ArraySchema("{name}", "Test", desc="Test spec",
                    members=[
                        BooleanSchema("enabled", "Enabled",
                                      desc="Whether this test is enabled",
                                      default=True),
                        StringSchema("users", "Users",
                                     desc="List of allowed users to run this test"),
                        StringSchema("testers", "Testers",
                                     desc="List of allowed testers to run this test"),
                        StringSchema("requirements", "Requirements",
                                     desc="List of requirements of the test"),
                        IntegerSchema("timeout", "Timeout",
                                      default=3600,
                                      desc="Timeout for the test"),
                        StringSchema("script", "Test script",
                                     desc="The testing script",
                                     default="#!/bin/bash\ntrue",
                                     multiline=True,
                                     required=True),
                    ])

    requirement_schema = \
        ArraySchema("{name}", "Requirement", desc="Test requirement spec",
                    members=[
                        StringSchema("script", "Probe script",
                                     desc="The probing script for this requirement",
                                     default="#!/bin/bash\ntrue",
                                     multiline=True,
                                     required=True),
                    ])

    project_property_schema = \
        ArraySchema("testing", desc="Configuration for testing module",
                    members=[
                        MapSchema("tests", "Tests",
                                   desc="Testing specs",
                                   item=test_schema),
                        MapSchema("requirements", "Requirements",
                                   desc="Requirement specs",
                                   item=requirement_schema),
                   ])

    def __init__(self):
        global _instance
        assert _instance == None
        _instance = self
        declare_event("TestingReport",
                      user="the user's name that runs this tester",
                      tester="the name of the tester",
                      obj="the object (series or project) which the test is for",
                      passed="True if the test is passed",
                      test="test name",
                      log="test log")

    def remove_testing_properties(self, obj):
        for k in list(obj.get_properties().keys()):
            if k == "testing.started" or \
               k == "testing.start-time" or \
               k == "testing.failed" or \
               k == "testing.done" or \
               k == "testing.tested-head" or \
               k.startswith("testing.report.") or \
               k.startswith("testing.log."):
                obj.set_property(k, None)

    def www_view_testing_reset(self, request, project_or_series):
        if not request.user.is_authenticated():
            return HttpResponseForbidden()
        if request.GET.get("type") == "project":
            obj = Project.objects.filter(name=project_or_series).first()
            if not obj.maintained_by(request.user):
                raise PermissionDenied()
        else:
            obj = Message.objects.find_series(project_or_series)
        if not obj:
            raise Http404("Not found: " + project_or_series)
        self.remove_testing_properties(obj)
        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

    def www_url_hook(self, urlpatterns):
        urlpatterns.append(url(r"^testing-reset/(?P<project_or_series>.*)/",
                               self.www_view_testing_reset,
                               name="testing-reset"))

    def add_test_report(self, user, project, tester, test, head, base, identity, passed, log):
        # Find a project or series depending on the test type and assign it to obj
        if identity["type"] == "project":
            obj = Project.objects.get(name=project)
            is_proj_report = True
            project = obj.name
        elif identity["type"] == "series":
            message_id = identity["message-id"]
            obj = Message.objects.find_series(message_id, project)
            if not obj:
                raise Exception("Series doesn't exist")
            is_proj_report = False
            project = obj.project.name
        obj.set_property("testing.report." + test,
                         {"passed": passed,
                          "user": user.username,
                          "tester": tester or user.username,
                         })
        obj.set_property("testing.log." + test, log)
        if not passed:
            obj.set_property("testing.failed", True)
        reports = [x for x in obj.get_properties() if x.startswith("testing.report.")]
        done_tests = set([x[len("testing.report."):] for x in reports])
        all_tests = set([k for k, v in self.get_tests(obj).items() if v["enabled"]])
        if all_tests.issubset(done_tests):
            obj.set_property("testing.done", True)
        if all_tests.issubset(done_tests):
            obj.set_property("testing.tested-head", head)
        emit_event("TestingReport", tester=tester, user=user.username,
                    obj=obj, passed=passed, test=test, log=log)

    def get_tests(self, obj):
        ret = {}
        for k, v in obj.get_properties().items():
            if not k.startswith("testing.tests."):
                continue
            tn = k[len("testing.tests."):]
            if "." not in tn:
                continue
            an = tn[tn.find(".") + 1:]
            tn = tn[:tn.find(".")]
            ret.setdefault(tn, {})
            ret[tn][an] = v
            ret[tn]["name"] = tn
        return ret

    def prepare_testing_report(self, obj):
        for pn, p in obj.get_properties().items():
            if not pn.startswith("testing.report."):
                continue
            tn = pn[len("testing.report."):]
            log = obj.get_property("testing.log." + tn)
            failed = not p["passed"]
            passed_str = "failed" if failed else "passed"
            obj.extra_info.append({"title": "Test %s: %s" % (passed_str, tn),
                                  "class": 'danger' if failed else 'success',
                                  "content": '<pre>%s</pre>' % log})

    def prepare_message_hook(self, request, message):
        if not message.is_series_head:
            return
        self.prepare_testing_report(message)

        if message.project.maintained_by(request.user) \
                and message.get_property("testing.started"):
            url = reverse("testing-reset",
                          kwargs={"project_or_series": message.message_id})
            url += "?type=message"
            message.extra_ops.append({"url": url,
                                      "title": "Reset testing states",
                                     })

        if message.get_property("testing.failed"):
            message.status_tags.append({
                "title": "Testing failed",
                "url": reverse("series_detail",
                                kwargs={"project": message.project.name,
                                        "message_id":message.message_id}),
                "type": "danger",
                "char": "T",
                })
        elif message.get_property("testing.done"):
            message.status_tags.append({
                "title": "Testing passed",
                "url": reverse("series_detail",
                                kwargs={"project": message.project.name,
                                        "message_id":message.message_id}),
                "type": "success",
                "char": "T",
                })

    def _testers_info(self, project):
        at = []
        for k, v in project.get_properties().items():
            prefix = "testing.check_in."
            if not k.startswith(prefix):
                continue
            age = time.time() - v
            if age > 10 * 60:
                continue
            tn = k[len(prefix):]
            at.append("%s (%dmin)" % (tn, math.ceil(age / 60)))
        if not at:
            return
        return "Active testers: " + ", ".join(at)

    def prepare_project_hook(self, request, project):
        if not project.maintained_by(request.user):
            return
        project.extra_info.append({"title": "Testing configuration",
                                   "class": "info",
                                   "content": self.build_config_html(request,
                                                                     project)})
        ti = self._testers_info(project)
        if ti:
            project.extra_headers.append(ti)
        self.prepare_testing_report(project)

        if project.maintained_by(request.user) \
                and project.get_property("testing.started"):
            url = reverse("testing-reset",
                          kwargs={"project_or_series": project.name})
            url += "?type=project"
            project.extra_ops.append({"url": url,
                                      "title": "Reset testing states"})

    def get_capability_probes(self, project):
        ret = {}
        for k, v in project.get_properties().items():
            prefix = "testing.requirements."
            if not k.startswith(prefix):
                continue
            name = k[len(prefix):]
            name = name[:name.find(".")]
            ret[name] = v
        return ret

    def tester_check_in(self, project, tester):
        assert project
        assert tester
        po = Project.objects.filter(name=project).first()
        if not po:
            return
        po.set_property('testing.check_in.' + tester, time.time())

class TestingGetView(APILoginRequiredView):
    name = "testing-get"
    allowed_groups = ["testers"]

    def _generate_test_data(self, project, repo, head, base, identity, test):
        r = {"project": project,
             "repo": repo,
             "head": head,
             "base": base,
             "test": test,
             "identity": identity
             }
        return r

    def _generate_series_test_data(self, s, test):
        return self._generate_test_data(project=s.project.name,
                                        repo=s.get_property("git.repo"),
                                        head=s.get_property("git.tag"),
                                        base=s.get_property("git.base"),
                                        identity={
                                            "type": "series",
                                            "message-id": s.message_id,
                                            "subject": s.subject,
                                        },
                                        test=test)

    def _generate_project_test_data(self, project, repo, head, base, test):
        return self._generate_test_data(project=project,
                                        repo=repo, head=head, base=base,
                                        identity={
                                            "type": "project",
                                            "head": head,
                                        },
                                        test=test)

    def _find_applicable_test(self, user, project, tester, capabilities, obj):
        all_tests = set([k for k, v in _instance.get_tests(obj).items() if v["enabled"]])
        done_tests = set()
        for tn, t in _instance.get_tests(project).items():
            if not t.get("enabled"):
                continue
            all_tests.add(tn)
            if obj.get_property("testing.report." + tn):
                done_tests.add(tn)
                continue
            if "tester" in t and tester != t["tester"]:
                continue
            if "user" in t and user.username != t["user"]:
                continue
            # TODO: group?
            ok = True
            reqs = t.get("requirements", "")
            for r in [x.strip() for x in reqs.split(",")]:
                if r not in capabilities:
                    ok = False
                    break
            if not ok:
                continue
            return t
        if len(all_tests) and all_tests.issubset(done_tests):
            obj.set_property("testing.done", True)

    def _find_project_test(self, request, po, tester, capabilities):
        head = po.get_property("git.head")
        repo = po.git
        tested = po.get_property("testing.tested-head")
        if not head or not repo:
            return
        test = self._find_applicable_test(request.user, po,
                                          tester, capabilities, po)
        if not test:
            return
        td = self._generate_project_test_data(po.name, repo, head, tested, test)
        return po, td

    def _find_series_test(self, request, po, tester, capabilities):
        se = SearchEngine()
        q = se.search_series("is:applied", "not:old", "not:tested",
                             "project:" + po.name)
        candidate = None
        for s in q:
            test = self._find_applicable_test(request.user, po,
                                              tester, capabilities, s)
            if not test:
                continue
            if not s.get_property("testing.started"):
                candidate = s, test
                break
            # Pick one series that started test the earliest
            if not candidate or \
                    s.get_property("testing.start-time") < \
                    candidate[0].get_property("testing.start-time"):
                candidate = s, test
        if not candidate:
            return None
        return candidate[0], \
               self._generate_series_test_data(candidate[0], candidate[1])

    def handle(self, request, project, tester, capabilities):
        # Try project head test first
        _instance.tester_check_in(project, tester or request.user.username)
        po = Project.objects.get(name=project)
        candidate = self._find_project_test(request, po, tester, capabilities)
        if not candidate:
            candidate = self._find_series_test(request, po, tester, capabilities)
        if not candidate:
            return
        obj, test_data = candidate
        obj.set_property("testing.started", True)
        obj.set_property("testing.start-time", time.time())
        return test_data

class TestingReportView(APILoginRequiredView):
    name = "testing-report"
    allowed_groups = ["testers"]

    def handle(self, request, tester, project, test, head, base, passed, log, identity):
        _instance.tester_check_in(project, tester or request.user.username)
        _instance.add_test_report(request.user, project, tester,
                                  test, head, base, identity, passed, log)

class TestingCapabilitiesView(APILoginRequiredView):
    name = "testing-capabilities"
    allowed_groups = ["testers"]

    def handle(self, request, tester, project):
        _instance.tester_check_in(project, tester or request.user.username)
        po = Project.objects.filter(name=project).first()
        if not po:
            raise Http404("Project '%s' not found" % project)
        probes = _instance.get_capability_probes(po)
        return probes

class UntestView(APILoginRequiredView):
    name = "untest"

    def handle(self, request, terms):
        se = SearchEngine()
        q = se.search_series(*terms)
        for s in q:
            _instance.remove_testing_properties(s)
