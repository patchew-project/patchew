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
from schema import *

class PatchewModule(object):
    """ Module base class """
    name = None # The name of the module, must be unique
    default_config = "" # The default config string
    project_property_schema = None

    def get_model(self):
        # ALways read from DB to accept configuration update in-flight
        from api.models import Module as PC
        _module_init_config(self.__class__)
        return PC.objects.get(name=self.name)

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

    def _build_map_scm(self, request, project, prefix, scm):
        prefix = prefix + scm.name + "."
        def _build_map_items():
            r = {}
            for p, v in project.get_properties().items():
                if not p.startswith(prefix):
                    continue
                name = p[len(prefix):]
                name = name[:name.rfind(".")]
                if name in r:
                    continue
                pref = prefix + name + "."
                r[name] = {
                          "name": name,
                          "html": self._build_one(request, project,
                                                  pref, scm.item)
                          }
            return list(r.values())

        schema_html = self._build_one(request, project, prefix,
                                      scm.item)
        item = {"html": schema_html}
        items = _build_map_items()
        return self._render_template(request, project, TMPL_MAP,
                                     schema=scm,
                                     item_schema=scm.item,
                                     prefix=prefix,
                                     items=items,
                                     item=item)

    def _build_array_scm(self, request, project, prefix, scm):
        members = [self._build_one(request, project,
                                                prefix, x) for x in scm.members]
        show_save_button = False
        for m in scm.members:
            if type(m) == StringSchema:
                show_save_button = True
                break
        return self._render_template(request, project, TMPL_ARRAY,
                                     schema=scm,
                                     members=members,
                                     show_save_button=show_save_button,
                                     prefix=prefix)

    def _build_string_scm(self, request, project, prefix, scm):
        prop_name = prefix + scm.name
        prop_value = project.get_property(prop_name)
        return self._render_template(request, project, TMPL_STRING,
                                     schema=scm,
                                     name=scm.name,
                                     prefix=prefix,
                                     value=prop_value)

    def _build_integer_scm(self, request, project, prefix, scm):
        prop_name = prefix + scm.name
        prop_value = project.get_property(prop_name)
        return self._render_template(request, project, TMPL_INTEGER,
                                     schema=scm,
                                     name=scm.name,
                                     prefix=prefix,
                                     value=prop_value)

    def _build_boolean_scm(self, request, project, prefix, scm):
        prop_name = prefix + scm.name
        prop_value = project.get_property(prop_name)
        return self._render_template(request, project, TMPL_BOOLEAN,
                                     schema=scm,
                                     name=scm.name,
                                     prefix=prefix,
                                     value=prop_value)

    def _build_enum_scm(self, request, project, prefix, scm):
        prop_name = prefix + scm.name
        prop_value = project.get_property(prop_name)
        return self._render_template(request, project, TMPL_ENUM,
                                     schema=scm,
                                     name=scm.name,
                                     prefix=prefix,
                                     value=prop_value)

    def _build_one(self, request, project, prefix, scm):
        if type(scm) == MapSchema:
            return self._build_map_scm(request, project, prefix, scm)
        elif type(scm) == StringSchema:
            return self._build_string_scm(request, project, prefix, scm)
        elif type(scm) == IntegerSchema:
            return self._build_integer_scm(request, project, prefix, scm)
        elif type(scm) == BooleanSchema:
            return self._build_boolean_scm(request, project, prefix, scm)
        elif type(scm) == EnumSchema:
            return self._build_enum_scm(request, project, prefix, scm)
        elif type(scm) == ArraySchema:
            return self._build_array_scm(request, project, prefix, scm)
        assert False

    def build_config_html(self, request, project):
        assert not isinstance(self.project_property_schema, StringSchema)
        assert not isinstance(self.project_property_schema, IntegerSchema)
        scm = self.project_property_schema
        tmpl = self._build_one(request, project, scm.name + ".", scm)
        tmpl += self._render_template(request, project, TMPL_END)
        return tmpl

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
    if not pc.enabled:
        return None
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
            except:
                traceback.print_exc()
    for cls in PatchewModule.__subclasses__():
        try:
            i = _init_module(cls)
            if not i:
                continue
            _loaded_modules[cls.name] = i
            print("Loaded module:", cls.name)
        except Exception as e:
            print("Cannot load module '%s':" % cls, e)

def dispatch_module_hook(hook_name, **params):
    for i in [x for x in list(_loaded_modules.values()) if x.enabled]:
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
    <div class="form-group" id="enum-desc">
    {% for opt, desc in schema.enums.items %}
      {% if opt == value %}
""" + TMPL_ENUM_DESC + """
      {% endif %}
    {% endfor %}
    </div>
    {% for opt, desc in schema.enums.items %}
        <div class="hidden" id="enum-desc-{{ opt }}">
""" + TMPL_ENUM_DESC + """
        </div>
    {% endfor %}
</div>
"""

TMPL_ARRAY = """
<input type="hidden" name="property-prefix" id="property-prefix" value="{{ prefix }}">
{% for schema in members %}
    {{ schema }}
{% endfor %}
{% if show_save_button %}
    <div class="form-group">
        <button type="button" class="btn btn-info" onclick="properties_save(this)">
             Save
         </button>
    </div>
{% endif %}
"""

TMPL_MAP_ITEM = """
<div class="item panel panel-default">
    <div class="panel-heading panel-toggler" onclick="patchew_toggler_onclick(this)">
        {{ item_schema.title }}
        <strong id="item-name">{{ item.name }}</strong>
        <input type="hidden" value="{{ prefix }}{{ item.name }}." id="prefix" />
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
<div id="{{ schema.name }}-container">
    <script id="item-template" type="text/x-custom-template">
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

TMPL_END = """
<script type="text/javascript">
function save_done(btn, succeeded, error) {
    $(btn).text("Save");
    $(btn).removeClass("disabled");
    info = $("<div class=\\"alert save-message\\"></div>");
    if (succeeded) {
        info.addClass("alert-success");
        info.html("Saved");
    } else {
        info.addClass("alert-danger");
        info.html("Error: " + error);
    }
    info.insertBefore($(btn));
}

function collect_properties(btn, check_required) {
    prefix = $(btn).parent().parent().find("#property-prefix").val();
    properties = {};
    $(btn).parent().parent().find(".project-property").each(function () {
        if (check_required && this.required && !this.value) {
            alert($(this).parent().find("label").html() + " is required!");
            $(this).focus();
            properties = false;
            return false;
        }
        if (this.type == "number") {
            val = parseInt(this.value);
            if (isNaN(val)) {
                alert("Invalid number for " + this.name);
                $(this).focus();
                properties = false;
                return false;
            }
        } else if (this.type == "checkbox") {
            if (this.checked) {
                val = true;
            } else {
                val = false;
            }
        } else {
            val = this.value;
        }
        properties[prefix + this.name] = val;
    });
    return properties;
}

function properties_save(btn) {
    if ($(btn).hasClass("disabled")) {
        return;
    }
    props = collect_properties(btn, true);
    if (!props) {
        return;
    }
    $(btn).addClass("disabled");
    $(btn).text("Saving...");
    $(btn).parent().find(".save-message").remove();
    patchew_api_do("set-project-properties",
                   { project: "{{ project.name }}",
                     properties: props })
        .done(function (data) {
            save_done(btn, true);
        })
        .fail(function (data, text, error) {
            save_done(btn, false, error);
        });
}

function collect_items(btn) {
    $(btn).parent().parent().find(".map-item");
    return {};
}

function map_add_item(btn) {
    name = window.prompt("Please input a name");
    if (!name || name == 'null') {
        return;
    }
    if (name in collect_items(btn)) {
        alert(test_name + " already exists.");
        return;
    }
    if (name.indexOf(".") >= 0) {
        alert("Invalid name, no dot is allowed.");
        return;
    }
    container = $(btn).parent().parent();
    tmpl = container.find("#item-template").html();
    nt = $(tmpl)
    nt.find("#item-name").html(name);
    old = nt.find("#property-prefix").val();
    nt.find("#property-prefix").val(old + name + ".");
    container.find(".items").append(nt);
}
function map_delete_item(btn) {
    name = $(btn).parent().parent().parent().find("#item-name").html();
    prefix = $(btn).parent().parent().parent().find("#prefix").val();
    if (!window.confirm("Really delete '" + name +"'?")) {
        return;
    }
    $(btn).addClass("disabled");
    $(btn).text("Deleting...");
    $(btn).parent().find(".delete-message").remove();
    patchew_api_do("delete-project-properties-by-prefix",
                   { project: "{{ project.name }}",
                     prefix: prefix })
        .done(function (data) {
            container = $(btn).parent().parent().parent();
            container.remove();
        })
        .fail(function (data, text, error) {
            $(btn).removeClass("disabled");
            $(btn).text("Delete");
            info = $("<div class=\\"alert alert-danger delete-message\\"></div>");
            info.html("Error: " + error);
            info.insertBefore($(btn));
        });
}
function enum_change(which) {
    val = $(which).val();
    desc = $(which).parent().find("#enum-desc-" + val).html();
    $(which).parent().find("#enum-desc").html(desc);
}
</script>
"""
