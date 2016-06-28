from django.shortcuts import render
from django.views.generic import View
from django.contrib.auth import authenticate, login, logout
from django.shortcuts import get_object_or_404
from django.http import HttpResponse
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

    def _api_response(self, succeeded, message, data=None):
        r = {"succeeded": succeeded}
        if message:
            r["message"] = message
        r["data"] = data
        return HttpResponse(json.dumps(r))

    def error_response(self, msg):
        return self._api_response(False, msg)

    def response(self, data=None):
        return self._api_response(True, "ok", data)

    def get(self, request):
        return self.error_response("API must use POST method")

    def handle(self, request, **params):
        return self.error_response("unrecognized command")

    def check_request(self, request):
        pass

    def post(self, request):
        p = request.POST.get("params")
        if p:
            params = json.loads(p)
        else:
            params = {}
        self.check_request(request)
        return self.handle(request, **params)

class APILoginRequiredView(APIView):
    def check_request(self, request):
        if not request.user.is_authenticated():
            raise PermissionDenied()

class VersionView(APIView):
    name = "version"

    def handle(self, request):
        return self.response(settings.VERSION)

class ProjectListView(APIView):
    name = "project-list"

    def handle(self, request):
        r = [x.name for x in Project.objects.all()]
        return self.response(r)

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
        return self.response([render_series(x) for x in r])

class ImportView(APILoginRequiredView):
    name = "import"

    def handle(self, request, mboxes):
        for mbox in mboxes:
            try:
                Message.objects.add_message_from_mbox(mbox.encode("utf8"), request.user)
            except Message.objects.DuplicateMessageError:
                pass
        return self.response()

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
        return self.response()

class Logout(APIView):
    name = "logout"

    def handle(self, request):
        logout(request)
        return self.response()

class LoginComand(APIView):
    name = "login"

    def handle(self, request, username, password):
        user = authenticate(username=username, password=password)
        if user is not None:
            # the password verified for the user
            if user.is_active:
                login(request, user)
                return self.response()
            else:
                return self.error_response("User is disabled")
        else:
                return self.error_response("Wrong user name or password")

