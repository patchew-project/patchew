from django.conf.urls import url
from django.http import HttpResponse, HttpResponseForbidden, Http404, \
                        HttpResponseRedirect
from django.core.urlresolvers import reverse
from mod import PatchewModule
import time
import smtplib
import email
import traceback
from api.views import APILoginRequiredView
from api.models import Message
from api.search import SearchEngine
from event import emit_event, declare_event

_default_config = """
[test a]
project = QEMU
command = true

[test b]
project = QEMU
command-asset = test_b
requirements = docker
user = fam
tester = debug

"""

_instance = None

class TestingModule(PatchewModule):
    """

Documentation
-------------

This module is configured in "INI" style.

Each section named like 'test FOO' is a test case
that will be distributed to testers. For example:

    [test a]
    project = BAR
    command = true
    timeout = 1000

defines a test called "a" that will be run against each new series of project
BAR. The testing command to run is 'true' which will already pass. The timeout
specifies for how long the tester should wait for the command to execute,
before aborting and reporting a timeout error.

Other supported options are:

  * **command-asset**: Instead of using a one liner command as given in "command"
    option, this option refers to a named "module asset" and treat it as a
    script in any format.

  * **user**: Limit the accepted user name that can run this test.

  * **tester**: Limit the accepted tester name that can run this test.

  * **requirements**: Limit the accepted tester to those that has these
    capabilities. Multiple requirements are delimit with comma.

"""

    name = "testing"
    default_config = _default_config

    def __init__(self):
        global _instance
        assert _instance == None
        _instance = self
        declare_event("TestingReport",
                      user="the user's name that runs this tester",
                      tester="the name of the tester",
                      project="the project's name in which the test is for",
                      series="the series object this test was run against",
                      passed="True if the test is passed",
                      test="test name",
                      log="test log")

    def www_view_testing_reset(self, request, message_id):
        if not request.user:
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

    def www_series_operations_hook(self, request, series, operations):
        if request.user and series.get_property("testing.started"):
            operations.append({"url": reverse("testing-reset",
                              kwargs={"message_id": series.message_id}),
                              "title": "Reset testing states"})

    def add_test_report(self, user, tester, series, test, passed, log):
        series.set_property("testing.report." + test,
                            {"passed": passed,
                             "user": user.username,
                             "tester": tester or user.username,
                            })
        series.set_property("testing.log." + test, log)
        if not passed:
            series.set_property("testing.failed", True)
        reports = filter(lambda x: x.startswith("testing.report."),
                        series.get_properties())
        done_tests = set(map(lambda x: x[len("testing.report."):], reports))
        all_tests = set(self.get_tests(series.project.name).keys())
        if all_tests.issubset(done_tests):
            series.set_property("testing.done", True)
        emit_event("TestingReport", tester=tester, user=user.username,
                                    project=series.project.name,
                                    series=series, passed=passed,
                                    test=test,
                                    log=log)

    def get_tests(self, project):
        ret = {}
        conf = self.get_config_obj()
        for sec in filter(lambda x: x.lower().startswith("test "),
                          conf.sections()):
            if conf.get(sec, "project") != project:
                continue
            try:
                name = sec[len("test "):]
                t = {"name": name}
                fields = [x for x, y in conf.items(sec)]
                if "command" in fields:
                    t["commands"] = "#!/bin/bash\n" + conf.get(sec, "command")
                elif "command-asset" in fields:
                    t["commands"] = self.get_asset(conf.get(sec, "command-asset")).\
                                    replace("\r\n", "\n")
                if "requirements" in fields:
                    t["requirements"] = [x.strip() for x in conf.get(sec, "requirements").split()]
                if "timeout" in fields:
                    t["timeout"] = conf.getint(sec, "timeout")
                else:
                    t["timeout"] = 3600
                if "tester" in fields:
                    t["tester"] = conf.get(sec, "tester")
                ret[name] = t
            except Exception as e:
                print "Error while parsing test config:"
                traceback.print_exc(e)
        return ret

    def prepare_message_hook(self, message):
        if not message.is_series_head:
            return
        for pn, p in message.get_properties().iteritems():
            if not pn.startswith("testing.report."):
                continue
            tn = pn[len("testing.report."):]
            log = message.get_property("testing.log." + tn)
            failed = not p["passed"]
            passed_str = "failed" if failed else "passed"
            message.extra_info.append({"title": "Test %s: %s" % (passed_str, tn),
                                       "is_error": failed,
                                       "content": log})

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

class TestingGetView(APILoginRequiredView):
    name = "test-get"
    allowed_groups = ["testers"]

    def _generate_test_data(self, s, test):
        r = {"project": s.project.name,
             "repo": s.get_property("git.repo"),
             "tag": s.get_property("git.tag"),
             "base": s.get_property("git.base"),
             "test": test,
             "identity": {
                 "message-id": s.message_id,
                 "subject": s.subject,
                 },
             }
        return r

    def _find_applicable_test(self, user, project, tester, capabilities, s):
        all_tests = set()
        done_tests = set()
        for tn, t in _instance.get_tests(project).iteritems():
            all_tests.add(tn)
            if s.get_property("testing.report." + tn):
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
            s.set_property("testing.done", True)

    def handle(self, request, project, tester, capabilities):
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
            return self.response(self._generate_test_data(candidate[0], candidate[1]))
        else:
            return self.response()

class TestingReportView(APILoginRequiredView):
    name = "test-report"
    allowed_groups = ["testers"]

    def handle(self, request, tester, project, message_id, test, passed, log):
        m = Message.objects.find_series(message_id, project)
        if not m:
            return self.error_response("Series doesn't exist")
        _instance.add_test_report(request.user, tester, m, test, passed, log)
        return self.response()
