from django.shortcuts import render
from django.views.generic import View
from django.contrib.auth import authenticate, login, logout
from django.http import HttpResponse, Http404
from django.core.exceptions import PermissionDenied
from django.conf import settings
from .models import Project, Message
import json
from search import SearchEngine
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
        if r:
            return HttpResponse(json.dumps(r))
        else:
            return HttpResponse()

class APILoginRequiredView(APIView):

    allowed_groups = []

    def check_permission(self, request):
        return False

    def check_request(self, request):
        if not request.user.is_authenticated():
            raise PermissionDenied()
        if request.user.is_superuser:
            return
        for grp in request.user.groups.all():
            if grp.is_superuser or grp.name in self.allowed_groups or \
                    self.check_permission(request):
                return
        raise PermissionDenied()

class VersionView(APIView):
    name = "version"

    def handle(self, request):
        return settings.VERSION

class ListProjectView(APIView):
    name = "list-projects"

    def handle(self, request):
        r = [x.name for x in Project.objects.all()]
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

def render_series(s):
    r = {"subject": s.subject,
         "project": s.project.name,
         "message-id": s.message_id,
         "patches": [x.get_mbox() for x in s.get_patches()],
         "properties": s.get_properties(),
         }
    return r

class SearchView(APIView):
    name = "search"

    def handle(self, request, terms):
        se = SearchEngine()
        r = se.search_series(*terms)
        return [render_series(x) for x in r]

class ImportView(APILoginRequiredView):
    name = "import"
    allowed_groups = ["importers"]

    def handle(self, request, mboxes):
        for mbox in mboxes:
            try:
                Message.objects.add_message_from_mbox(mbox.encode("utf8"), request.user)
            except Message.objects.DuplicateMessageError:
                pass

class DeletreView(APILoginRequiredView):
    """ Delete messages """
    name = "delete"

    def handle(self, request, terms=[]):
        if not terms:
            Message.objects.all().delete()
        else:
            se = SearchEngine()
            for r in se.search_series(*terms):
                Message.objects.delete_subthread(r)

class Logout(APIView):
    name = "logout"

    def handle(self, request):
        logout(request)

class LoginComand(APIView):
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

