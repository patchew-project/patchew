from __future__ import unicode_literals

from django.apps import AppConfig
import mod

class ApiConfig(AppConfig):
    name = 'api'
    verbose_name = "Patchew Core"
    def ready(self):
        try:
            mod.load_modules()
        except Exception, e:
            print "Error while loading modules:", e
