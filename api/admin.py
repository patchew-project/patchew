#!/usr/bin/env python3
#
# Copyright 2016 Red Hat, Inc.
#
# Authors:
#     Fam Zheng <famz@redhat.com>
#
# This work is licensed under the MIT License.  Please see the LICENSE file or
# http://opensource.org/licenses/MIT.

from django.contrib import admin
from .models import *
from mod import get_module

class ProjectPropertyInline(admin.TabularInline):
    model = ProjectProperty
    extra = 0

class ProjectAdmin(admin.ModelAdmin):
    filter_horizontal = ('maintainers',)
    inlines = [
            ProjectPropertyInline
        ]

class MessagePropertyInline(admin.TabularInline):
    model = MessageProperty
    extra = 0

class MessageAdmin(admin.ModelAdmin):
    inlines = [
            MessagePropertyInline
        ]
    list_filter = [('is_series_head')]
    search_fields = [
            'message_id',
            'subject',
            'sender',
        ]

class ModuleAdmin(admin.ModelAdmin):
    inlines = [
        ]

    def get_fieldsets(self, request, obj=None):
        fs = super(ModuleAdmin, self).get_fieldsets(request, obj)
        if obj:
            po = get_module(obj.name)
            if po:
                a, b = fs[0]
                b["fields"].remove("name")
                doc = type(po).__doc__
                if doc:
                    from markdown import markdown
                    b["description"] = markdown(doc)
        return fs

    def has_add_permission(self, request):
        return False

    def change_view(self, request, object_id, form_url='', extra_context=None):
        extra_context = extra_context or {}
        q = Module.objects.filter(pk=object_id).first()
        if q:
            extra_context['title'] = "%s Module " % q.name.capitalize()
        return super(ModuleAdmin, self).change_view(
            request, object_id, form_url, extra_context=extra_context,
        )

admin_site = admin.site

admin_site.site_header = 'Patchew admin'
admin_site.site_title = 'Patchew admin'
admin_site.index_title = 'Patchew administration'

admin_site.register(Project, ProjectAdmin)
admin_site.register(Message, MessageAdmin)
admin_site.register(Module, ModuleAdmin)
