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
from django.db.models import Q
from django.urls import reverse
from django.utils.html import format_html
from mod import PatchewModule
import datetime
import time
import math
from api.views import APILoginRequiredView
from api.models import Message, MessageResult, Project, ProjectResult, Result
from api.rest import PluginMethodField, TestPermission, reverse_detail
from api.search import SearchEngine
from event import emit_event, declare_event, register_handler
from patchew.logviewer import LogView
import schema
from rest_framework import serializers, generics
from rest_framework.fields import CharField, BooleanField
from rest_framework.response import Response

_instance = None

TESTING_SCRIPT_DEFAULT = """#!/bin/bash
# Testing script will be invoked under the git checkout with
# HEAD pointing to a commit that has the patches applied on top of "base"
# branch
exit 0
"""


class TestingLogViewer(LogView):
    def get_result(self, request, **kwargs):
        project_or_series = kwargs["project_or_series"]
        testing_name = kwargs["testing_name"]
        if request.GET.get("type") == "project":
            obj = Project.objects.filter(name=project_or_series).first()
        else:
            obj = Message.objects.find_series(project_or_series)
        if not obj:
            raise Http404("Object not found: " + project_or_series)
        return _instance.get_testing_result(obj, testing_name)


class ResultDataSerializer(serializers.Serializer):
    # TODO: is_timeout should be present iff the result is a failure
    is_timeout = BooleanField(required=False)
    head = CharField()
    tester = CharField(default=serializers.CurrentUserDefault())


class TestingModule(PatchewModule):
    """Testing module"""

    name = "testing"
    allowed_groups = ("testers",)
    result_data_serializer_class = ResultDataSerializer

    test_schema = schema.ArraySchema(
        "{name}",
        "Test",
        desc="Test spec",
        members=[
            schema.BooleanSchema(
                "enabled", "Enabled", desc="Whether this test is enabled", default=True
            ),
            schema.StringSchema(
                "requirements", "Requirements", desc="List of requirements of the test"
            ),
            schema.IntegerSchema(
                "timeout", "Timeout", default=3600, desc="Timeout for the test"
            ),
            schema.StringSchema(
                "script",
                "Test script",
                desc="The testing script",
                default=TESTING_SCRIPT_DEFAULT,
                multiline=True,
                required=True,
            ),
        ],
    )

    requirement_schema = schema.ArraySchema(
        "{name}",
        "Requirement",
        desc="Test requirement spec",
        members=[
            schema.StringSchema(
                "script",
                "Probe script",
                desc="The probing script for this requirement",
                default="#!/bin/bash\ntrue",
                multiline=True,
                required=True,
            )
        ],
    )

    project_config_schema = schema.ArraySchema(
        "testing",
        desc="Configuration for testing module",
        members=[
            schema.MapSchema("tests", "Tests", desc="Testing specs", item=test_schema),
            schema.MapSchema(
                "requirements",
                "Requirements",
                desc="Requirement specs",
                item=requirement_schema,
            ),
        ],
    )

    def __init__(self):
        global _instance
        assert _instance == None
        _instance = self
        declare_event(
            "TestingReport",
            user="the user's name that runs this tester",
            tester="the name of the tester",
            obj="the object (series or project) which the test is for",
            passed="True if the test is passed",
            test="test name",
            log="test log",
            log_url="URL to test log (text)",
            html_log_url="URL to test log (HTML)",
            is_timeout="whether the test has timeout",
        )
        register_handler("SetProperty", self.on_set_property)
        register_handler("SetProjectConfig", self.on_set_config)
        register_handler("ResultUpdate", self.on_result_update)

    def on_set_property(self, evt, obj, name, value, old_value):
        if isinstance(obj, Project) and name == "git.head" and old_value != value:
            self.clear_and_start_testing(obj)

    def on_set_config(self, evt, obj):
        self.project_recalc_pending_tests(obj)

    def get_msg_base_tags(self, msg):
        return [t for t in msg.tags if t.lower().startswith("based-on:")]

    def on_result_update(self, evt, obj, old_status, result):
        if result.name.startswith("testing.") and result.status != old_status:
            if "tester" in result.data:
                po = obj if isinstance(obj, Project) else obj.project
                _instance.tester_check_in(po, result.data["tester"])
            if not self.get_testing_results(
                obj, status__in=(Result.PENDING, Result.RUNNING)
            ).exists():
                obj.set_property("testing.tested-head", result.data["head"])
                if isinstance(obj, Message):
                    obj.is_tested = True
                    obj.save()
                    obj.set_property("testing.tested-base", self.get_msg_base_tags(obj))
            if isinstance(obj, Project):
                # cache the last result so that badges are not affected by RUNNING state
                failures = obj.get_property("testing.failures", [])
                if result.status == result.SUCCESS and result.name in failures:
                    failures.remove(result.name)
                    obj.set_property("testing.failures", list(failures))
                if result.status == result.FAILURE and result.name not in failures:
                    failures.append(result.name)
                    obj.set_property("testing.failures", list(failures))

        if result.name != "git":
            return
        if (
            isinstance(obj, Message)
            and obj.is_series_head
            and result.status == result.SUCCESS
            and result.data.get("tag")
            and result.data.get("repo")
        ):
            tested_base = obj.get_property("testing.tested-base")
            if tested_base is None or tested_base != self.get_msg_base_tags(obj):
                self.clear_and_start_testing(obj)

    def filter_testing_results(self, queryset, *args, **kwargs):
        return queryset.filter(name__startswith="testing.", *args, **kwargs)

    def get_testing_results(self, obj, *args, **kwargs):
        return self.filter_testing_results(obj.results, *args, **kwargs)

    def get_testing_result(self, obj, name):
        try:
            return obj.results.get(name="testing." + name)
        except:
            raise Http404("Test doesn't exist")

    def get_test_name(self, result):
        return result.name[len("testing.") :]

    def recalc_pending_tests(self, obj):
        test_dict = self.get_tests(obj)
        all_tests = set((k for k, v in test_dict.items() if v.get("enabled", False)))
        for r in self.get_testing_results(obj, status=Result.PENDING):
            r.delete()
        if len(all_tests):
            done_tests = [self.get_test_name(r) for r in self.get_testing_results(obj)]
            for tn in all_tests:
                if not tn in done_tests:
                    obj.create_result(
                        name="testing." + tn, status=Result.PENDING
                    ).save()
        if isinstance(obj, Message):
            is_tested = len(all_tests) and len(done_tests) == len(all_tests)
            if is_tested != obj.is_tested:
                obj.is_tested = is_tested
                obj.save()

    def project_recalc_pending_tests(self, project):
        self.recalc_pending_tests(project)

        # Only operate on messages for which testing has not completed yet.
        message_ids = self.filter_testing_results(
            MessageResult.objects, message__project=project, status=Result.PENDING
        ).values("message_id")
        messages = Message.objects.filter(id__in=message_ids)
        for obj in messages:
            self.recalc_pending_tests(obj)

    def clear_and_start_testing(self, obj, test=""):
        obj.set_property("testing.tested-head", None)
        if isinstance(obj, Message):
            obj.is_tested = False
            obj.save()
        if test:
            r = self.get_testing_result(obj, test)
            if r:
                r.delete()
        else:
            for r in self.get_testing_results(obj):
                r.delete()
        self.recalc_pending_tests(obj)

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
        self.clear_and_start_testing(obj, request.GET.get("test", ""))
        return HttpResponseRedirect(request.META.get("HTTP_REFERER"))

    def www_view_badge(self, request, project, ext):
        po = Project.objects.filter(name=project).first()
        if po.get_property("testing.failures"):
            return HttpResponseRedirect(
                "https://img.shields.io/badge/patchew-failing-critical." + ext
            )
        else:
            return HttpResponseRedirect(
                "https://img.shields.io/badge/patchew-passing-success." + ext
            )

    def www_url_hook(self, urlpatterns):
        urlpatterns.append(
            url(
                r"^testing-reset/(?P<project_or_series>.*)/",
                self.www_view_testing_reset,
                name="testing-reset",
            )
        )
        urlpatterns.append(
            url(
                r"^logs/(?P<project_or_series>.*)/testing.(?P<testing_name>.*)/",
                TestingLogViewer.as_view(),
                name="testing-log",
            )
        )
        urlpatterns.append(
            url(
                r"^(?P<project>[^/]*)/badge.(?P<ext>svg|png)$",
                self.www_view_badge,
                name="testing-badge",
            )
        )

    def api_url_hook(self, urlpatterns):
        urlpatterns.append(
            url(
                r"^v1/projects/(?P<pk>[^/]*)/get-test/$",
                GetTestView.as_view(),
                name="get-test",
            )
        )

    def reverse_testing_log(self, obj, test, request=None, html=False):
        if isinstance(obj, Message):
            log_url = (
                reverse(
                    "testing-log",
                    kwargs={"project_or_series": obj.message_id, "testing_name": test},
                )
                + "?type=message"
            )
        else:
            assert isinstance(obj, Project)
            log_url = (
                reverse(
                    "testing-log",
                    kwargs={"project_or_series": obj.name, "testing_name": test},
                )
                + "?type=project"
            )
        if html:
            log_url += "&html=1"
        # Generate a full URL, including the host and port, for use in
        # email notifications
        if request:
            log_url = request.build_absolute_uri(log_url)
        return log_url

    def add_test_report(
        self,
        request,
        project,
        tester,
        test,
        head,
        base,
        identity,
        passed,
        log,
        is_timeout,
    ):
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

        r = self.get_testing_result(obj, test)
        r.data = {
            "is_timeout": is_timeout,
            "user": user.username,
            "head": head,
            "tester": tester or user.username,
        }
        r.log = log
        r.status = Result.SUCCESS if passed else Result.FAILURE
        r.save()

        log_url = self.reverse_testing_log(obj, test, request=request)
        html_log_url = self.reverse_testing_log(obj, test, request=request, html=True)
        emit_event(
            "TestingReport",
            tester=tester,
            user=user.username,
            obj=obj,
            passed=passed,
            test=test,
            log=log,
            log_url=log_url,
            html_log_url=html_log_url,
            is_timeout=is_timeout,
        )

    def get_tests(self, obj):
        if isinstance(obj, Message):
            obj = obj.project
        return self.get_project_config(obj).get("tests", {})

    def _build_reset_ops(self, obj):
        if isinstance(obj, Message):
            typearg = "type=message"
            url = reverse("testing-reset", kwargs={"project_or_series": obj.message_id})
        else:
            assert isinstance(obj, Project)
            url = reverse("testing-reset", kwargs={"project_or_series": obj.name})
            typearg = "type=project"
        url += "?" + typearg
        ret = [
            {
                "url": url,
                "title": "Reset all testing states",
                "class": "warning",
                "icon": "refresh",
            }
        ]
        for r in self.get_testing_results(obj, ~Q(status=Result.PENDING)):
            tn = self.get_test_name(r)
            ret.append(
                {
                    "url": url + "&test=" + tn,
                    "title": format_html("Reset <b>{}</b> testing state", tn),
                    "class": "warning",
                    "icon": "refresh",
                }
            )
        return ret

    def prepare_message_hook(self, request, message, detailed):
        if not message.is_series_head:
            return
        if (
            message.project.maintained_by(request.user)
            and self.get_testing_results(message, ~Q(status=Result.PENDING)).exists()
        ):
            message.extra_ops += self._build_reset_ops(message)

        if self.get_testing_results(message, status=Result.FAILURE).exists():
            message.status_tags.append(
                {
                    "title": "Testing failed",
                    "url": reverse(
                        "series_detail",
                        kwargs={
                            "project": message.project.name,
                            "message_id": message.message_id,
                        },
                    ),
                    "type": "danger",
                    "char": "T",
                }
            )
        elif message.is_tested:
            message.status_tags.append(
                {
                    "title": "Testing passed",
                    "url": reverse(
                        "series_detail",
                        kwargs={
                            "project": message.project.name,
                            "message_id": message.message_id,
                        },
                    ),
                    "type": "success",
                    "char": "T",
                }
            )

    def get_result_log_url(self, result):
        tn = result.name[len("testing.") :]
        return self.reverse_testing_log(result.obj, tn, html=False)

    def render_result(self, result):
        if not result.is_completed():
            return None
        pn = result.name
        tn = pn[len("testing.") :]
        log_url = result.get_log_url()
        html_log_url = log_url + "&html=1"
        passed_str = "failed" if result.is_failure() else "passed"
        return format_html(
            'Test <b>{}</b> <a class="cbox-log" data-link="{}" href="{}">{}</a>',
            tn,
            html_log_url,
            log_url,
            passed_str,
        )

    def check_active_testers(self, project):
        at = []
        for tn, v in project.get_property("testing.check_in", {}).items():
            age = time.time() - v
            if age > 10 * 60:
                continue
            at.append("%s (%dmin)" % (tn, math.ceil(age / 60)))
        if not at:
            return
        project.extra_status.append(
            {"icon": "fa-refresh fa-spin", "html": "Active testers: " + ", ".join(at)}
        )

    def prepare_project_hook(self, request, project):
        if not project.maintained_by(request.user):
            return
        project.extra_info.append(
            {
                "title": "Testing configuration",
                "class": "info",
                "content_html": self.build_config_html(request, project),
            }
        )
        self.check_active_testers(project)

        if (
            project.maintained_by(request.user)
            and self.get_testing_results(project, ~Q(status=Result.PENDING)).exists()
        ):
            project.extra_ops += self._build_reset_ops(project)

    def get_capability_probes(self, project):
        props = self.get_project_config(project).get("requirements", {})
        return {k: v["script"] for k, v in props.items()}

    def get_testing_probes(self, project, request, format):
        return self.get_capability_probes(project)

    def rest_project_fields_hook(self, request, fields):
        fields["testing_probes"] = PluginMethodField(obj=self)

    def tester_check_in(self, project, tester):
        assert project
        assert tester
        po = Project.objects.filter(name=project).first()
        if not po:
            return
        po.set_property("testing.check_in." + tester, time.time())


class GetTestViewMixin(object):
    def _generate_series_test_data(self, request, s, result, test):
        gr = s.git_result
        assert gr.is_success()
        return self._generate_test_data(
            project=s.project.name,
            repo=gr.data["repo"],
            head=gr.data["tag"],
            base=gr.data.get("base", None),
            identity={
                "type": "series",
                "message-id": s.message_id,
                "subject": s.subject,
            },
            result_uri=reverse_detail(result, request),
            test=test,
        )

    def _generate_project_test_data(
        self, request, project, repo, head, base, result, test
    ):
        return self._generate_test_data(
            project=project,
            repo=repo,
            head=head,
            base=base,
            identity={"type": "project", "head": head},
            result_uri=reverse_detail(result, request),
            test=test,
        )

    def _find_applicable_test(self, queryset, user, po, tester, capabilities):
        # Prefer non-running tests, or tests that started the earliest
        one_hour_ago = datetime.datetime.now() - datetime.timedelta(0, 3600)
        where = Q(status=Result.PENDING)
        where = where | Q(status=Result.RUNNING, last_update__lt=one_hour_ago)
        where = where & Q(name__startswith="testing.")
        q = queryset.filter(where).order_by("status", "last_update")
        tests = _instance.get_tests(po)
        for r in q:
            if isinstance(r, MessageResult) and not r.message.git_result.is_success():
                continue
            tn = _instance.get_test_name(r)
            t = tests.get(tn, None)
            # Shouldn't happen, but let's protect against it
            if not t:
                continue
            reqs = t.get("requirements", "")
            for req in [x.strip() for x in reqs.split(",") if x]:
                if req not in capabilities:
                    break
            else:
                t["name"] = tn
                yield r, t

    def _find_project_test(self, request, po, tester, capabilities):
        head = po.get_property("git.head")
        repo = po.git
        tested = po.get_property("testing.tested-head")
        if not head or not repo:
            return None
        candidates = self._find_applicable_test(
            ProjectResult.objects.filter(project=po),
            request.user,
            po,
            tester,
            capabilities,
        )
        for r, test in candidates:
            td = self._generate_project_test_data(
                request, po.name, repo, head, tested, r, test
            )
            return r, po, td
        return None

    def _find_series_test(self, request, po, tester, capabilities):
        candidates = self._find_applicable_test(
            MessageResult.objects.filter(message__project=po),
            request.user,
            po,
            tester,
            capabilities,
        )
        for r, test in candidates:
            s = r.message
            td = self._generate_series_test_data(request, s, r, test)
            return r, s, td
        return None

    def _do_testing_get(self, request, po, tester, capabilities):
        # Try project head test first
        _instance.tester_check_in(po.name, tester or request.user.username)
        candidate = self._find_project_test(request, po, tester, capabilities)
        if not candidate:
            candidate = self._find_series_test(request, po, tester, capabilities)
        if not candidate:
            return None
        r, obj, test_data = candidate
        r.status = Result.RUNNING
        r.save()
        return test_data


class TestingGetView(APILoginRequiredView, GetTestViewMixin):
    name = "testing-get"
    allowed_groups = ["testers"]

    def _generate_test_data(
        self, project, repo, head, base, identity, result_uri, test
    ):
        r = {
            "project": project,
            "repo": repo,
            "head": head,
            "base": base,
            "test": test,
            "identity": identity,
            "result_uri": result_uri,
        }
        return r

    def handle(self, request, project, tester, capabilities):
        po = Project.objects.get(name=project)
        return self._do_testing_get(request, po, tester, capabilities)

class TestSerializer(serializers.BaseSerializer):
    pass

class GetTestView(generics.GenericAPIView, GetTestViewMixin):
    queryset = Project.objects.all()
    permission_classes = (TestPermission,)
    serializer_class = TestSerializer

    def _generate_test_data(
        self, project, repo, head, base, identity, result_uri, test
    ):
        r = {
            "repo": repo,
            "head": head,
            "base": base,
            "test": test,
            "identity": identity,
            "result_uri": result_uri,
        }
        return r

    def post(self, request, *args, **kwargs):
        tester = request.data.get("tester", "")
        capabilities = request.data.get("capabilities", [])
        test_data = self._do_testing_get(
            request, self.get_object(), tester, capabilities
        )
        if test_data:
            return Response(test_data)
        else:
            return Response(status=204)


class TestingReportView(APILoginRequiredView):
    name = "testing-report"
    allowed_groups = ["testers"]

    def handle(
        self,
        request,
        tester,
        project,
        test,
        head,
        base,
        passed,
        log,
        identity,
        is_timeout=False,
    ):
        _instance.add_test_report(
            request,
            project,
            tester,
            test,
            head,
            base,
            identity,
            passed,
            log,
            is_timeout,
        )


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
        q = se.search_series(user=request.user, *terms)
        for s in q:
            _instance.clear_and_start_testing(s)
