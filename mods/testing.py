from django.conf.urls import url
from django.http import HttpResponse, HttpResponseForbidden, Http404, \
                        HttpResponseRedirect
from django.core.urlresolvers import reverse
from django.template import Template, Context
from mod import PatchewModule
import time
import smtplib
import email
import traceback
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
                        StringSchema("users", "Users",
                                     desc="List of allowed users to run this test"),
                        StringSchema("testers", "Testers",
                                     desc="List of allowed testers to run this test"),
                        StringSchema("requirements", "Requirements",
                                     desc="List of requirements of the test"),
                        IntegerSchema("timeout", "Timeout",
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
        declare_event("SeriesTestingReport",
                      user="the user's name that runs this tester",
                      tester="the name of the tester",
                      project="the project's name in which the test is for",
                      series="the series object this test was run against",
                      passed="True if the test is passed",
                      test="test name",
                      log="test log")
        declare_event("ProjectTestingReport",
                      user="the user's name that runs this tester",
                      tester="the name of the tester",
                      project="the project's name in which the test is for",
                      passed="True if the test is passed",
                      test="test name",
                      log="test log")

    def www_view_testing_reset(self, request, message_id):
        if not request.user.is_authenticated():
            return HttpResponseForbidden()
        m = Message.objects.find_series(message_id)
        if not m:
            raise Http404("Series not found: " + message_id)
        for k in m.get_properties().keys():
            if k.startswith("testing."):
                m.set_property(k, None)
        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

    def www_url_hook(self, urlpatterns):
        urlpatterns.append(url(r"^testing-reset/(?P<message_id>.*)/",
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
        reports = filter(lambda x: x.startswith("testing.report."),
                        obj.get_properties())
        done_tests = set(map(lambda x: x[len("testing.report."):], reports))
        all_tests = set(self.get_tests(project).keys())
        if all_tests.issubset(done_tests):
            obj.set_property("testing.done", True)
        if all_tests.issubset(done_tests):
            obj.set_property("testing.tested-head", head)
        if is_proj_report:
            emit_event("SeriesTestingReport", tester=tester, user=user.username,
                                              project=project,
                                              series=obj, passed=passed,
                                              test=test,
                                              log=log)
        else:
            emit_event("ProjectTestingReport", tester=tester, user=user.username,
                                               project=project,
                                               passed=passed,
                                               test=test,
                                               log=log)

    def get_tests(self, project):
        ret = {}
        for k, v in project.get_properties().iteritems():
            if not k.startswith("testing.test."):
                continue
            tn = k[len("testing.test."):]
            ret[tn] = v
        return ret

    def get_requirements(self, project):
        ret = {}
        for k, v in project.get_properties().iteritems():
            if not k.startswith("testing.requirement."):
                continue
            tn = k[len("testing.requirement."):]
            ret[tn] = v
        return ret

    def prepare_testing_report(self, obj):
        for pn, p in obj.get_properties().iteritems():
            if not pn.startswith("testing.report."):
                continue
            tn = pn[len("testing.report."):]
            log = obj.get_property("testing.log." + tn)
            failed = not p["passed"]
            passed_str = "failed" if failed else "passed"
            obj.extra_info.append({"title": "Test %s: %s" % (passed_str, tn),
                                  "class": 'danger' if failed else 'success',
                                  "content": '<pre class="body-full">%s</pre>' % log})

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

    def prepare_project_hook(self, request, project):
        if not project.maintained_by(request.user):
            return
        project.extra_info.append({"title": "Tests",
                                   "content": self.build_config_html(request,
                                                                     project)})

    def get_capability_probes(self, project):
        ret = {}
        conf = self.get_config_obj()
        for sec in filter(lambda x: x.lower().startswith("capability "),
                          conf.sections()):
            if conf.get(sec, "project") and conf.get(sec, "project") != project:
                continue
            try:
                name = sec[len("capability "):]
                ret[name] = dict(conf.items(sec))
            except Exception as e:
                print "Error while parsing capability config:"
                traceback.print_exc(e)
        return ret

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
        all_tests = set()
        done_tests = set()
        for tn, t in _instance.get_tests(project).iteritems():
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
            for r in t.get("requirements", []):
                if r not in capabilities:
                    ok = False
                    break
            if not ok:
                continue
            return t
        if all_tests.issubset(done_tests):
            obj.set_property("testing.done", True)

    def _handle_project(self, request, project, tester, capabilities):
        po = Project.objects.get(name=project)
        test = self._find_applicable_test(request.user, project,
                                          tester, capabilities, po)
        if not test:
            return
        head = po.get_property("git.head")
        repo = po.get_property("git.repo")
        tested = po.get_property("testing.tested-head")
        td = self._generate_project_test_data(project, repo, head, tested, test)
        return td

    def handle(self, request, project, tester, capabilities):
        # Try project head test first
        r = self._handle_project(request, project, tester, capabilities)
        if r:
            return r
        se = SearchEngine()
        q = se.search_series("is:applied", "not:old", "not:tested", "project:" + project)
        candidate = None
        for s in q:
            test = self._find_applicable_test(request.user, project,
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
        if candidate:
            s.set_property("testing.started", True)
            s.set_property("testing.start-time", time.time())
            return self._generate_series_test_data(candidate[0], candidate[1])
        else:
            return

class TestingReportView(APILoginRequiredView):
    name = "testing-report"
    allowed_groups = ["testers"]

    def handle(self, request, tester, project, test, head, base, passed, log, identity):
        _instance.add_test_report(request.user, project, tester, test, head, base, identity, passed, log)

class TestingCapabilitiesView(APILoginRequiredView):
    name = "testing-capabilities"
    allowed_groups = ["testers"]

    def handle(self, request, tester, project):
        probes = _instance.get_capability_probes(project)
        return probes
