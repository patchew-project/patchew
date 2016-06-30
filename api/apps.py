from __future__ import unicode_literals

from django.apps import AppConfig
import mod

_default_groups = ['maintainers', 'testers', 'importers']

def create_default_groups():
    from .models import Group
    for grp in _default_groups:
        Group.objects.get_or_create(name=grp)

class ApiConfig(AppConfig):
    name = 'api'
    verbose_name = "Patchew Core"
    def ready(self):
        try:
            mod.load_modules()
            create_default_groups()
        except Exception, e:
            print "Error while loading modules:", e
