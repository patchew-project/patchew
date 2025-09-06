#!/usr/bin/env python3
#
# Copyright 2016 Red Hat, Inc.
#
# Authors:
#     Fam Zheng <famz@redhat.com>
#
# This work is licensed under the MIT License.  Please see the LICENSE file or
# http://opensource.org/licenses/MIT.

from django.views.generic import View
from django.contrib.auth import authenticate, login, logout
from django.http import HttpResponse, Http404, JsonResponse
from django.core.exceptions import PermissionDenied
from django.conf import settings
from .models import Project, Message
import json
from .search import SearchEngine
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from mod import dispatch_module_hook
from django.db import transaction
import logging

logger = logging.getLogger(__name__)


class APIView(View):
    name = None

    @method_decorator(csrf_exempt)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        raise PermissionDenied("API must use POST method")

    def handle(self, request, **params):
        raise Http404("unknown command")

    def check_request(self, request):
        pass

    def _parse_params(self, request):
        """
        Parse params from either:
         - JSON body (Content-Type: application/json)
         - form POST param named 'params' (JSON encoded)
         - empty dict otherwise
        """
        # Try application/json (or any body that parses as JSON)
        try:
            if request.body:
                # Some clients may send form-encoded data but still put JSON in body
                raw = request.body.decode("utf-8")
                # If there is a body and it's JSON, parse it
                try:
                    parsed = json.loads(raw)
                    # If the top-level is a dict, return it as params. If clients send {"params": {...}},
                    # allow that too.
                    if isinstance(parsed, dict):
                        # If parsed contains top-level keys for this API, assume it's the params dict
                        # Otherwise, support {"params": {...}} format
                        if "params" in parsed and isinstance(parsed["params"], dict):
                            return parsed["params"]
                        return parsed
                    # If parsed is not dict (e.g., list) return as {"_data": parsed}
                    return {"_data": parsed}
                except json.JSONDecodeError:
                    # Not valid JSON in body — fall back to form POST below
                    pass
        except Exception:
            # decoding issues — fall back
            pass

        # Fallback: look for form field 'params' which contains JSON string
        p = request.POST.get("params")
        if p:
            try:
                return json.loads(p)
            except json.JSONDecodeError:
                raise Http404("Malformed JSON in 'params'")
        return {}

    def post(self, request):
        params = self._parse_params(request)
        self.check_request(request)
        r = self.handle(request, **params)
        if r is not None:
            # use JsonResponse so lists and dicts are returned correctly
            return JsonResponse(r, safe=False, json_dumps_params={"ensure_ascii": False})
        else:
            return HttpResponse()


class APILoginRequiredView(APIView):

    allowed_groups = []

    def check_permission(self, request):
        """
        override in subclasses to provide custom additional permission checks
        """
        return False

    def check_request(self, request):
        if not request.user.is_authenticated:
            raise PermissionDenied()
        # superusers bypass other checks
        if request.user.is_superuser:
            return
        # explicit permission method can allow
        if self.check_permission(request):
            return
        # allowed_groups membership can allow
        user_group_names = {g.name for g in request.user.groups.all()}
        if any(g in user_group_names for g in self.allowed_groups):
            return
        # otherwise deny
        raise PermissionDenied()


class VersionView(APIView):
    name = "version"

    def handle(self, request):
        return settings.VERSION


def prepare_project(p):
    ret = {
        "name": p.name,
        "mailing_list": p.mailing_list,
        "url": p.url,
        "git": p.git,
        "description": p.description,
        "properties": {},
    }
    dispatch_module_hook(
        "get_projects_prepare_hook", project=p, response=ret["properties"]
    )

    return ret


class ListProjectView(APIView):
    name = "get-projects"

    def handle(self, request, name=None):
        r = [
            prepare_project(x)
            for x in Project.objects.all()
            if name is None or name == x.name
        ]
        return r


class AddProjectView(APILoginRequiredView):
    name = "add-project"

    def handle(self, request, name, mailing_list, url, git, description):
        # use exists() for efficient check
        if Project.objects.filter(name=name).exists():
            raise Exception("Project already exists")
        p = Project(
            name=name,
            mailing_list=mailing_list,
            url=url,
            git=git,
            description=description,
        )
        p.save()
        # Return created project summary for convenience
        return prepare_project(p)


class UpdateProjectHeadView(APILoginRequiredView):
    name = "update-project-head"
    allowed_groups = ["importers"]

    def handle(self, request, project, old_head, new_head, message_ids):
        # Use select_for_update to avoid race conditions; wrap in transaction
        try:
            with transaction.atomic():
                po = Project.objects.select_for_update().get(name=project)
                old_head_0 = po.project_head
                if old_head_0 and old_head_0 != old_head:
                    raise Exception("wrong old head")
                ret = po.series_update(message_ids)
                po.project_head = new_head
                po.save()
                return ret
        except Project.DoesNotExist:
            raise Http404("Project not found")


def prepare_patch(p):
    r = {
        "subject": p.subject,
        "message-id": p.message_id,
        "mbox": p.get_mbox(),
        # For backwards compatibility with old clients
        "properties": {},
    }
    return r


def prepare_series(request, s, fields=None):
    r = {}

    def want_field(f):
        return not fields or f in fields

    if want_field("subject"):
        r["subject"] = s.subject
    if want_field("project"):
        r["project"] = s.project.name
    if want_field("message-id"):
        r["message-id"] = s.message_id
    if want_field("patches"):
        r["patches"] = [prepare_patch(x) for x in s.get_patches()]
    if want_field("properties"):
        # For backwards compatibility with old clients
        r["properties"] = {}
    if want_field("tags"):
        r["tags"] = s.tags
    if want_field("is_complete"):
        r["is_complete"] = s.is_complete
    if fields:
        r = dict([(k, v) for k, v in r.items() if k in fields])
    return r


class SearchView(APIView):
    name = "search"

    def handle(self, request, terms, fields=None):
        se = SearchEngine(terms, request.user)
        r = se.search_series()
        return [prepare_series(request, x, fields) for x in r]


class ImportView(APILoginRequiredView):
    name = "import"
    allowed_groups = ["importers"]

    def handle(self, request, mboxes):
        projects = set()
        for mbox in mboxes:
            try:
                projects = projects.union(
                    [
                        x.name
                        for x in Message.objects.add_message_from_mbox(
                            mbox, request.user
                        )
                    ]
                )
            except Message.objects.DuplicateMessageError:
                # keep going on duplicates
                logger.info("Duplicate messages found while importing mbox: %s", mbox)
                pass
        return list(projects)


class DeleteView(APILoginRequiredView):
    """Delete messages"""

    name = "delete"

    def handle(self, request, terms=None, confirm=False):
        """
        terms: list of search terms; if empty or None and confirm is True => delete all
        confirm: boolean, must be True to allow deletion of ALL messages
        """
        if not terms:
            # require explicit confirmation to delete everything
            if not confirm:
                raise PermissionDenied(
                    "Deleting all messages requires explicit confirm=True"
                )
            logger.warning("User %s requested full message delete", request.user)
            Message.objects.all().delete()
            return {"deleted_all": True}
        else:
            se = SearchEngine(terms, request.user)
            deleted = []
            for r in se.search_series():
                Message.objects.delete_subthread(r)
                deleted.append(r.message_id if hasattr(r, "message_id") else str(r))
            return {"deleted": deleted}


class Logout(APIView):
    name = "logout"

    def handle(self, request):
        logout(request)
        return {"logged_out": True}


class LoginCommand(APIView):
    name = "login"

    MAX_FAILED = 10

    def handle(self, request, username, password):
        """
        Simple session-backed failed-login mitigation: increments a counter in session.
        This is intentionally small and local — for production use a shared/central rate-limit store.
        """
        # initialize session counter
        failed = request.session.get("failed_logins", 0)
        if failed >= self.MAX_FAILED:
            logger.warning("Too many failed login attempts for session: %s", request.session.session_key)
            raise PermissionDenied("Too many failed login attempts")

        user = authenticate(username=username, password=password)
        if user is not None:
            # reset counter on success
            request.session["failed_logins"] = 0
            if user.is_active:
                login(request, user)
                logger.info("User %s logged in", username)
                return {"logged_in": True}
            else:
                raise Exception("User is disabled")
        else:
            # increment counter
            request.session["failed_logins"] = failed + 1
            logger.info("Failed login attempt for username: %s (count=%d)", username, failed + 1)
            raise PermissionDenied("Wrong user name or password")
