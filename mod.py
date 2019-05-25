#!/usr/bin/env python3
#
# Copyright 2016 Red Hat, Inc.
#
# Authors:
#     Fam Zheng <famz@redhat.com>
#
# This work is licensed under the MIT License.  Please see the LICENSE file or
# http://opensource.org/licenses/MIT.

import imp
import os
import sys
from django.conf import settings
from django.template import Template, Context
import traceback
import configparser
import schema

class PatchewModule(object):
    """ Module base class """
    name = None # The name of the module, must be unique
    default_config = "" # The default config string
    project_config_schema = None

    def get_model(self):
        # ALways read from DB to accept configuration update in-flight
        return _module_init_config(self.__class__)

    def get_config_raw(self):
        return self.get_model().config or ""

    def get_config_obj(self):
        config = configparser.ConfigParser()
        config.read_string(self.get_config_raw())
        return config

    def get_config(self, section, field, getmethod="get", default=None):
        cfg = self.get_config_obj()
        if not section in cfg.sections():
            return default
        if field in dict(cfg.items(section)):
            return getattr(cfg, getmethod)(section, field)
        else:
            return default

    def _render_template(self, request, project, tmpl, **data):
        data["project"] = project
        data["module"] = self
        return Template(tmpl).render(Context(data))

    def _build_map_scm(self, request, project, prefix, config, scm):
        schema_html = self._build_one(request, project, "", {}, scm.item)
        item = {"html": schema_html}
        config = config or {}
        items = [{
            "name": name,
            "html": self._build_one(request, project, prefix + "." + name,
                                    value, scm.item)} for name, value in config.items()]
        return self._render_template(request, project, TMPL_MAP,
                                     schema=scm,
                                     item_schema=scm.item,
                                     prefix=prefix,
                                     items=items,
                                     item=item)

    def _build_array_scm(self, request, project, prefix, config, scm):
        config = config or {}
        members = [self._build_one(request, project,
                                   prefix + "." + x.name,
                                   config.get(x.name), x) for x in scm.members]
        return self._render_template(request, project, TMPL_ARRAY,
                                     schema=scm,
                                     members=members,
                                     prefix=prefix)

    def _build_string_scm(self, request, project, prefix, config, scm):
        return self._render_template(request, project, TMPL_STRING,
                                     schema=scm,
                                     name=scm.name,
                                     prefix=prefix,
                                     value=config or '')

    def _build_integer_scm(self, request, project, prefix, config, scm):
        return self._render_template(request, project, TMPL_INTEGER,
                                     schema=scm,
                                     name=scm.name,
                                     prefix=prefix,
                                     value=config or 0)

    def _build_boolean_scm(self, request, project, prefix, config, scm):
        return self._render_template(request, project, TMPL_BOOLEAN,
                                     schema=scm,
                                     name=scm.name,
                                     prefix=prefix,
                                     value=config or False)

    def _build_enum_scm(self, request, project, prefix, config, scm):
        return self._render_template(request, project, TMPL_ENUM,
                                     schema=scm,
                                     name=scm.name,
                                     prefix=prefix,
                                     value=config)

    def _build_one(self, request, project, prefix, config, scm):
        if type(scm) == schema.MapSchema:
            return self._build_map_scm(request, project, prefix, config, scm)
        elif type(scm) == schema.StringSchema:
            return self._build_string_scm(request, project, prefix, config, scm)
        elif type(scm) == schema.IntegerSchema:
            return self._build_integer_scm(request, project, prefix, config, scm)
        elif type(scm) == schema.BooleanSchema:
            return self._build_boolean_scm(request, project, prefix, config, scm)
        elif type(scm) == schema.EnumSchema:
            return self._build_enum_scm(request, project, prefix, config, scm)
        elif type(scm) == schema.ArraySchema:
            return self._build_array_scm(request, project, prefix, config, scm)
        assert False

    def build_config_html(self, request, project):
        assert isinstance(self.project_config_schema, schema.ArraySchema)
        scm = self.project_config_schema
        config = self.get_project_config(project)
        return self._build_one(request, project, scm.name, config, scm)

    def get_project_config(self, project):
        return project.config.get(self.project_config_schema.name, {})

_loaded_modules = {}

def _module_init_config(cls):
    from api.models import Module
    mod, _ = Module.objects.get_or_create(name=cls.name,
                 defaults={ 'config': cls.default_config.strip() })
    return mod

def load_modules():
    _module_path = settings.MODULE_DIR
    sys.path.append(_module_path)
    for f in os.listdir(_module_path):
        if f.endswith(".py"):
            pn = f[:-len(".py")]
            try:
                imp.load_source(pn, os.path.join(_module_path, f))
            except:
                traceback.print_exc()
    for cls in PatchewModule.__subclasses__():
        if cls.name not in _loaded_modules:
            _loaded_modules[cls.name] = cls()
            print("Loaded module:", cls.name)

def dispatch_module_hook(hook_name, **params):
    for i in _loaded_modules.values():
        if hasattr(i, hook_name):
            try:
                getattr(i, hook_name)(**params)
            except:
                print("Cannot invoke module hook: %s.%s" % (i, hook_name))
                traceback.print_exc()

def get_module(name):
    return _loaded_modules.get(name)

TMPL_STRING = """
<div class="form-group">
    <label for="{{ module.name }}-input-{{ schema.name }}">{{ schema.title }}</label>
    {% if schema.multiline %}
        <textarea rows="10"
    {% else %}
        <input
    {% endif %}
    type="text" class="form-control project-property"
    data-property-path="{{ prefix }}"
    id="{{ module.name }}-input-{{ schema.name }}" {% if schema.required %}required{%endif%}
    name="{{ name }}" placeholder="{{ schema.desc }}"
    {% if schema.multiline %}
        >{{ value | default_if_none:schema.default }}</textarea>
    {% else %}
        value="{{ value | default_if_none:"" }}">
    {% endif %}
</div>
"""

TMPL_INTEGER = """
<div class="form-group">
    <label for="{{ module.name }}-input-{{ schema.name }}">{{ schema.title }}</label>
    <input type="number" class="form-control project-property"
    data-property-path="{{ prefix }}"
    id="{{ module.name }}-input-{{ schema.name }}" {% if schema.required %}required{%endif%}
    name="{{ name }}" placeholder="{{ schema.desc }}"
    {% if schema.multiline %}
        >{{ value | default_if_none:schema.default }}</textarea>
    {% else %}
        value="{{ value | default_if_none:schema.default }}">
    {% endif %}
</div>
"""

TMPL_BOOLEAN = """
<div class="checkbox">
<label>
  <input class="project-property" type="checkbox" name="{{ name }}"
    data-property-path="{{ prefix }}"
  {% if value == None %}
    {% if schema.default %}
      checked
    {% endif %}
  {% elif value %}
      checked
  {% endif %}
  >
    <span title="{{ schema.desc }}">{{ schema.title }}</span>
</label>
</div>
"""
TMPL_ENUM_DESC = """
<div class="well" style="margin-top: 10px;">
    <h4>Available variables in template</h4>
    {% for k, v in desc.items %}
        <p><strong>{{ k }}</strong>: {{ v }}</p>
    {% endfor %}
</div>
"""

TMPL_ENUM = """
<div class="form-group">
    <label for="{{ module.name }}-input-{{ schema.name }}">{{ schema.title }}</label>
    <select class="form-control project-property"
    id="{{ module.name }}-input-{{ schema.name }}"
    data-property-path="{{ prefix }}"
    onchange="enum_change(this)"
    {% if schema.required %}required{%endif%}
    name="{{ name }}">
        <option disabled selected value=""> -- select an event type -- </option>
        {% for opt in schema.enums %}
          {% if opt == value %}
            <option selected value="{{ opt }}">{{ opt }}</option>
          {% else %}
            <option value="{{ opt }}">{{ opt }}</option>
          {% endif %}
        {% endfor %}
    </select>
    <div class="form-group enum-desc">
    {% for opt, desc in schema.enums.items %}
      {% if opt == value %}
""" + TMPL_ENUM_DESC + """
      {% endif %}
    {% endfor %}
    </div>
    {% for opt, desc in schema.enums.items %}
        <div class="hidden enum-desc-{{ opt }}">
""" + TMPL_ENUM_DESC + """
        </div>
    {% endfor %}
</div>
"""

TMPL_ARRAY = """
{% for schema in members %}
    {{ schema }}
{% endfor %}
"""

TMPL_MAP_ITEM = """
<div class="item panel panel-default" data-property-prefix="{{ prefix }}{% if item.name %}.{{ item.name }}{% endif %}">
    <div class="item-heading panel-heading panel-toggler" onclick="patchew_toggler_onclick(this)">
        {{ item_schema.title }}
        <strong class="item-name">{{ item.name }}</strong>
    </div>
    <div class="panel-body panel-collapse collapse">
        {{ item.html }}
        <div class="form-group">
            <button type="button"
             class="btn btn-danger" onclick="map_delete_item(this)">
                 Delete
             </button>
        </div>
    </div>
</div>
"""

TMPL_MAP = """
<div>
    <script class="item-template" type="text/x-custom-template">
    """ + TMPL_MAP_ITEM + """
    </script>
    <div class="items">
        {% for item in items %}
        """ + TMPL_MAP_ITEM + """
        {% endfor %}
    </div>
    <div class="form-group">
        <button type="button"
         class="btn btn-info" onclick="map_add_item(this)">
             Add {{ item_schema.title }}
         </button>
    </div>
</div>
"""
