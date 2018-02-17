import abc

from django.views import View
from django.http import HttpResponse

class LogView(View, metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def content(request, **kwargs):
        return None

    def get(self, request, **kwargs):
        self.text = self.content(request, **kwargs)
        return HttpResponse(self.text, content_type='text/plain')
