from django.conf.urls import url

from . import views

def _build_urls(base=None, r=[]):
    for cls in (base or views.APIView).__subclasses__():
        if cls.name:
            # API views should handle the authentication explicitly, disable
            # csrf check to simplify client code
            r.append(url(cls.name + "/", cls.as_view()))
        else:
            _build_urls(cls, r)
    return r

urlpatterns = _build_urls() + [
        # Use the base class's handler by default
        url(r".*", views.APIView.as_view())
    ]


