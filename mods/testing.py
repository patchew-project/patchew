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
from django.http import HttpResponseForbidden, Http404, HttpResponseRedirect
from django.core.exceptions import PermissionDenied
from django.urls import reverse
from django.utils.html import format_html
from mod import PatchewModule
import time
import math
from api.views import APILoginRequiredView
from api.models import Message, Project, MessageProperty
from api.search import SearchEngine
from event import emit_event, declare_event, register_handler
from patchew.logviewer import LogView
from schema import *

_instance = None

TESTING_SCRIPT_DEFAULT = """#!/bin/bash
# Testing script will be invoked under the git checkout with
# HEAD pointing to a commit that has the patches applied on top of "base"
# branch
exit 0
"""

class TestingLogViewer(LogView):
    def content(self, request, **kwargs):
        project_or_series = kwargs['project_or_series']
        testing_name = kwargs['testing_name']
        if request.GET.get("type") == "project":
            obj = Project.objects.filter(name=project_or_series).first()
        else:
            obj = Message.objects.find_series(project_or_series)
        if not obj:
            raise Http404("Object not found: " + project_or_series)
        log = obj.get_property("testing.log." + testing_name)
        if log is None:
            raise Http404("Testing log not found: " + testing_name)
        return log


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
                                     default=TESTING_SCRIPT_DEFAULT,
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
                      log="test log",
                      log_url="URL to test log (text)",
                      html_log_url="URL to test log (HTML)",
                      is_timeout="whether the test has timeout")
        register_handler("SetProperty", self.on_set_property)

    def on_set_property(self, evt, obj, name, value, old_value):
        if ((isinstance(obj, Message) and obj.is_series_head) \
            or isinstance(obj, Project)) \
            and name in ("git.tag", "git.repo") \
            and old_value is None \
            and obj.get_property("git.tag") and obj.get_property("git.repo"):
                self.remove_testing_properties(obj)
                obj.set_property("testing.ready", 1)
        elif isinstance(obj, Project) and name == "git.head" \
            and old_value != value:
            self.remove_testing_properties(obj)
            obj.set_property("testing.ready", 1)

    def remove_testing_properties(self, obj, test=""):
        for k in list(obj.get_properties().keys()):
            if (not test and k == "testing.started") or \
               (not test and k == "testing.start-time") or \
               (not test and k == "testing.failed") or \
               k == "testing.done" or \
               k == "testing.tested-head" or \
               k.startswith("testing.report." + test) or \
               k.startswith("testing.log." + test):
                obj.set_property(k, None)

    def www_view_testing_reset(self, request, project_or_series):
        if not request.user.is_authenticated:
            return HttpResponseForbidden()
        if request.GET.get("type") == "project":
            obj = Project.objects.filter(name=project_or_series).first()
            if not obj.maintained_by(request.user):
                raise PermissionDenied()
        else:
            obj = Message.objects.find_series(project_or_series)
        if not obj:
            raise Http404("Not found: " + project_or_series)
        self.remove_testing_properties(obj, request.GET.get("test", ""))
        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

    def www_url_hook(self, urlpatterns):
        urlpatterns.append(url(r"^testing-reset/(?P<project_or_series>.*)/",
                               self.www_view_testing_reset,
                               name="testing-reset"))
        urlpatterns.append(url(r"^logs/(?P<project_or_series>.*)/testing.(?P<testing_name>.*)/",
                               TestingLogViewer.as_view(),
                               name="testing-log"))

    def reverse_testing_log(self, obj, test, request=None, html=False):
        if isinstance(obj, Message):
            log_url = reverse("testing-log",
                              kwargs={"project_or_series": obj.message_id,
                                      "testing_name": test}) + "?type=message"
        else:
            assert(isinstance(obj, Project))
            log_url = reverse("testing-log",
                              kwargs={"project_or_series": obj.name,
                                      "testing_name": test}) + "?type=project"
        if html:
            log_url += "&html=1"
        # Generate a full URL, including the host and port, for use in email
        # notifications and REST API responses.
        if request:
            log_url = request.build_absolute_uri(log_url)
        return log_url

    def add_test_report(self, request, project, tester, test, head,
                        base, identity, passed, log, is_timeout):
        # Find a project or series depending on the test type and assign it to obj
        if identity["type"] == "project":
            obj = Project.objects.get(name=project)
            project = obj.name
        elif identity["type"] == "series":
            message_id = identity["message-id"]
            obj = Message.objects.find_series(message_id, project)
            if not obj:
                raise Exception("Series doesn't exist")
            project = obj.project.name
        user = request.user
        log_url = self.reverse_testing_log(obj, test, request=request)
        html_log_url = self.reverse_testing_log(obj, test, request=request, html=True)
        obj.set_property("testing.report." + test,
                         {"passed": passed,
                          "is_timeout": is_timeout,
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
            obj.set_property("testing.ready", None)
        if all_tests.issubset(done_tests):
            obj.set_property("testing.tested-head", head)
        emit_event("TestingReport", tester=tester, user=user.username,
                    obj=obj, passed=passed, test=test, log=log, log_url=log_url,
                    html_log_url=html_log_url, is_timeout=is_timeout)

    def get_tests(self, obj):
        ret = {}
        if isinstance(obj, Message):
            obj = obj.project
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
            failed = not p["passed"]
            log_url = self.reverse_testing_log(obj, tn, html=False)
            html_log_url = self.reverse_testing_log(obj, tn, html=True)
            passed_str = "failed" if failed else "passed"
            html = format_html('Test <b>{}</b> <a class="cbox-log" data-link="{}" href="{}">{}</a>',
                               tn, html_log_url, log_url, passed_str)
            obj.extra_status.append({
                "kind": "alert" if failed else "good",
                "html": html,
            })

    def _build_reset_ops(self, obj):
        if isinstance(obj, Message):
            typearg = "type=message"
            url = reverse("testing-reset",
                          kwargs={"project_or_series": obj.message_id})
        else:
            assert(isinstance(obj, Project))
            url = reverse("testing-reset",
                          kwargs={"project_or_series": obj.name})
            typearg = "type=project"
        url += "?" + typearg
        ret = [{"url": url,
                "title": "Reset all testing states",
                "class": "warning",
                "icon": "refresh",
               }]
        for pn, p in obj.get_properties().items():
            if not pn.startswith("testing.report."):
                continue
            tn = pn[len("testing.report."):]
            failed = not p["passed"]
            ret.append({"url": url + "&test=" + tn,
                        "title": format_html("Reset <b>{}</b> testing state", tn),
                        "class": "warning",
                        "icon": "refresh",
                        })
        return ret

    def _build_message_prop_url(message, prop):
        return reverse("testing-get-prop",
                       kwargs={"project_or_series": obj.message_id})

    def rest_results_hook(self, request, message, results):
        for pn, p in message.get_properties().items():
            if not pn.startswith("testing.report."):
                continue
            tn = pn[len("testing.report."):]
            failed = not p["passed"]
            log_url = self.reverse_testing_log(message, tn, request=request, html=False)
            passed_str = "failure" if failed else "success"
            result = {
                'status': passed_str,
                'log_url': log_url
            }
            results['testing.' + tn] = result

    def prepare_message_hook(self, request, message, detailed):
        if not message.is_series_head:
            return
        self.prepare_testing_report(message)
        if message.project.maintained_by(request.user) \
                and message.get_property("testing.started"):
            message.extra_ops += self._build_reset_ops(message)

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

    def check_active_testers(self, project):
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
        project.extra_status.append({
            "kind": "running",
            "html":  "Active testers: " + ", ".join(at)
        })

    def prepare_project_hook(self, request, project):
        if not project.maintained_by(request.user):
            return
        project.extra_info.append({"title": "Testing configuration",
                                   "class": "info",
                                   "content_html": self.build_config_html(request,
                                                                          project)})
        self.check_active_testers(project)
        self.prepare_testing_report(project)

        if project.maintained_by(request.user) \
                and project.get_property("testing.started"):
            project.extra_ops += self._build_reset_ops(project)

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
            if t.get("tester") and tester != t["tester"]:
                continue
            if t.get("user") and user.username != t["user"]:
                continue
            # TODO: group?
            ok = True
            reqs = t.get("requirements", "")
            for r in [x.strip() for x in reqs.split(",") if x]:
                if r not in capabilities:
                    ok = False
                    break
            if not ok:
                continue
            return t
        if len(all_tests) and all_tests.issubset(done_tests):
            obj.set_property("testing.done", True)

    def _find_project_test(self, request, po, tester, capabilities):
        if not po.get_property("testing.ready"):
            return
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
        q = MessageProperty.objects.filter(name="testing.ready",
                                           value=1,
                                           message__project=po)
        candidate = None
        for prop in q:
            s = prop.message
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

    def handle(self, request, tester, project, test,
               head, base, passed, log, identity,
               is_timeout=False):
        _instance.tester_check_in(project, tester or request.user.username)
        _instance.add_test_report(request, project, tester,
                                  test, head, base, identity, passed, log,
                                  is_timeout)

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
    allowed_groups = ["testers"]

    def handle(self, request, terms):
        se = SearchEngine()
        q = se.search_series(*terms)
        for s in q:
            _instance.remove_testing_properties(s)
