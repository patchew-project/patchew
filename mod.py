import imp
import os
import sys
from django.conf import settings
import traceback
import ConfigParser
import io

class PatchewModule(object):
    """ Module base class """
    name = None # The name of the module, must be unique
    default_config = "" # The default config string

    def get_model(self):
        # ALways read from DB to accept configuration update in-flight
        from api.models import Module as PC
        return PC.objects.get(name=self.name)

    def get_config_raw(self):
        return self.get_model().config

    def get_config_obj(self):
        config = ConfigParser.ConfigParser()
        config.readfp(io.BytesIO(str(self.get_config_raw())))
        return config

    def get_config(self, section, field, getmethod="get", default=None):
        cfg = self.get_config_obj()
        if field in dict(cfg.items(section)):
            return getattr(cfg, getmethod)(section, field)
        else:
            return default

    def get_asset(self, asset_name):
        from api.models import ModuleAsset as PA
        a = PA.objects.get(module__name=self.name, name=asset_name)
        if a.text:
            return a.text
        elif a.file:
            return a.file.file.read()

    def __init__(self):
        pass

_loaded_modules = {}

def _module_init_config(cls):
    from api.models import Module as PC
    pc, created = PC.objects.get_or_create(name=cls.name)
    if created:
        pc.config = cls.default_config.strip()
        pc.save()
    return pc

def _init_module(cls):
    name = cls.name
    if name in _loaded_modules:
        raise Exception("The module named '%s' is already loaded" % name)
    pc = _module_init_config(cls)
    i = cls()
    # TODO: let i.enabled follows pc.enabled
    i.enabled = pc.enabled
    return i

def load_modules():
    _module_path = settings.MODULE_DIR
    sys.path.append(_module_path)
    for f in os.listdir(_module_path):
        if f.endswith(".py"):
            pn = f[:-len(".py")]
            try:
                imp.load_source(pn, os.path.join(_module_path, f))
            except Exception as e:
                traceback.print_exc(e)
    for cls in PatchewModule.__subclasses__():
        try:
            i = _init_module(cls)
            _loaded_modules[cls.name] = i
            print "Loaded module:", cls.name
        except Exception as e:
            print "Cannot load module '%s':" % cls, e

def dispatch_module_hook(hook_name, **params):
    for i in filter(lambda x: x.enabled, _loaded_modules.values()):
        if hasattr(i, hook_name):
            try:
                getattr(i, hook_name)(**params)
            except Exception as e:
                print "Cannot invoke module hook: %s.%s" % (i, hook_name)
                traceback.print_exc(e)

def get_module(name):
    return _loaded_modules.get(name)
