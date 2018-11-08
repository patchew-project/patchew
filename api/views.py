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
from django.http import HttpResponse, Http404
from django.core.exceptions import PermissionDenied
from django.conf import settings
from .models import Project, Message
import json
from .search import SearchEngine
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator


class APIView(View):
    name = None

    @method_decorator(csrf_exempt)
    def dispatch(self, request, *args, **kwargs):
        return super(APIView, self).dispatch(request, *args, **kwargs)

    def get(self, request):
        raise PermissionDenied("API must use POST method")

    def handle(self, request, **params):
        raise Http404("unknown command")

    def check_request(self, request):
        pass

    def post(self, request):
        p = request.POST.get("params")
        if p:
            params = json.loads(p)
        else:
            params = {}
        self.check_request(request)
        r = self.handle(request, **params)
        if r is not None:
            return HttpResponse(json.dumps(r))
        else:
            return HttpResponse()


class APILoginRequiredView(APIView):

    allowed_groups = []

    def check_permission(self, request):
        return False

    def check_request(self, request):
        if not request.user.is_authenticated:
            raise PermissionDenied()
        if request.user.is_superuser:
            return
        for grp in request.user.groups.all():
            if grp.name in self.allowed_groups or \
                    self.check_permission(request):
                return
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
        "properties": p.get_properties(),
    }
    return ret


class ListProjectView(APIView):
    name = "get-projects"

    def handle(self, request, name=None):
        r = [prepare_project(x) for x in Project.objects.all()
             if name is None or name == x.name]
        return r


class AddProjectView(APILoginRequiredView):
    name = "add-project"

    def handle(self, request, name, mailing_list, url, git, description):
        if Project.objects.filter(name=name):
            raise Exception("Project already exists")
        p = Project(name=name,
                    mailing_list=mailing_list,
                    url=url,
                    git=git,
                    description=description)
        p.save()


class GetProjectPropertiesView(APILoginRequiredView):
    name = "get-project-properties"

    def handle(self, request, project):
        po = Project.objects.get(name=project)
        if not po.maintained_by(request.user):
            raise PermissionDenied("Access denied to this project")
        return po.get_properties()


class UpdateProjectHeadView(APILoginRequiredView):
    name = "update-project-head"
    allowed_groups = ["importers"]

    def handle(self, request, project, old_head, new_head, message_ids):
        po = Project.objects.get(name=project)
        old_head_0 = po.project_head
        if old_head_0 and old_head_0 != old_head:
            raise Exception("wrong old head")
        ret = po.series_update(message_ids)
        po.project_head = new_head
        return ret


class SetPropertyView(APILoginRequiredView):
    name = "set-properties"
    allowed_groups = ["importers"]

    def handle(self, request, project, message_id, properties):
        mo = Message.objects.filter(project__name=project,
                                    message_id=message_id).first()
        if not mo:
            raise Http404("Message not found")
        for k, v in properties.items():
            mo.set_property(k, v)


class SetProjectPropertiesView(APILoginRequiredView):
    name = "set-project-properties"
    allowed_groups = ["maintainers"]

    def handle(self, request, project, properties):
        po = Project.objects.get(name=project)
        if not po.maintained_by(request.user):
            raise PermissionDenied("Access denied to this project")
        for k, v in properties.items():
            po.set_property(k, v)


def get_properties(m):
    r = m.get_properties()
    # for compatibility with patchew-cli's applier mode
    if m.tags:
        r['tags'] = m.tags
    return r


class DeleteProjectPropertiesByPrefixView(APILoginRequiredView):
    name = "delete-project-properties-by-prefix"
    allowed_groups = ["maintainers"]

    def handle(self, request, project, prefix):
        po = Project.objects.get(name=project)
        if not po.maintained_by(request.user):
            raise PermissionDenied("Access denied to this project")
        for k in [x for x in po.get_properties().keys() if x.startswith(prefix)]:
            po.set_property(k, None)


def prepare_patch(p):
    r = {"subject": p.subject,
         "message-id": p.message_id,
         "mbox": p.get_mbox(),
         "properties": get_properties(p)
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
        r["properties"] = get_properties(s)
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
        se = SearchEngine()
        r = se.search_series(user=request.user, *terms)
        return [prepare_series(request, x, fields) for x in r]


class ImportView(APILoginRequiredView):
    name = "import"
    allowed_groups = ["importers"]

    def handle(self, request, mboxes):
        projects = set()
        for mbox in mboxes:
            try:
                projects = projects.union([
                    x.name for x in
                    Message.objects.add_message_from_mbox(mbox, request.user)
                ])
            except Message.objects.DuplicateMessageError:
                pass
        return list(projects)


class DeleteView(APILoginRequiredView):
    """ Delete messages """
    name = "delete"

    def handle(self, request, terms=[]):
        if not terms:
            Message.objects.all().delete()
        else:
            se = SearchEngine()
            for r in se.search_series(user=request.user, *terms):
                Message.objects.delete_subthread(r)


class Logout(APIView):
    name = "logout"

    def handle(self, request):
        logout(request)


class LoginCommand(APIView):
    name = "login"

    def handle(self, request, username, password):
        user = authenticate(username=username, password=password)
        if user is not None:
            # the password verified for the user
            if user.is_active:
                login(request, user)
                return
            else:
                raise Exception("User is disabled")
        else:
                raise PermissionDenied("Wrong user name or password")
