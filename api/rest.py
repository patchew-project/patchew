#!/usr/bin/env python3
#
# Copyright 2018 Red Hat, Inc.
#
# Authors:
#     Paolo Bonzini <pbonzini@redhat.com>
#
# This work is licensed under the MIT License.  Please see the LICENSE file or
# http://opensource.org/licenses/MIT.

from django.contrib.auth.models import User
from django.template import loader

from mod import dispatch_module_hook
from .models import Project, Message
from .search import SearchEngine
from rest_framework import permissions, serializers, viewsets, filters, mixins, renderers
from rest_framework.decorators import detail_route
from rest_framework.fields import SerializerMethodField
from rest_framework.relations import HyperlinkedIdentityField
from rest_framework.response import Response

SEARCH_PARAM = 'q'

# patchew-specific permission classes

class IsAdminUserOrReadOnly(permissions.BasePermission):
    """
    Allows access only to admin users.
    """
    def has_permission(self, request, view):
        return request.method in permissions.SAFE_METHODS or \
               (request.user and request.user.is_superuser)

class IsMaintainerOrReadOnly(permissions.BasePermission):
    """
    Allows access only to admin users or maintainers.
    """
    def has_object_permission(self, request, view, obj):
        return request.method in permissions.SAFE_METHODS or \
               obj.maintained_by(request.user)

# pluggable field for plugin support

class PluginMethodField(SerializerMethodField):
    """
    A read-only field that get its representation from calling a method on
    the plugin class. The method called will be of the form
    "get_{field_name}", and should take a single argument, which is the
    object being serialized.

    For example:

        fields['extra_info'] = api.rest.PluginMethodField(obj=self)

        def get_extra_info(self, obj):
            return ...  # Calculate some data to return.
    """

    def __init__(self, obj=None, method_name=None, **kwargs):
        self.obj = obj
        super(PluginMethodField, self).__init__(method_name=method_name, **kwargs)

    def to_representation(self, value):
        method = getattr(self.obj, self.method_name)
        request = self.context['request']
        format = self.context.get('format', None)
        return method(value, request, format)

# Users

# TODO: include list of projects maintained by the user, login

class UserSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = User
        fields = ('resource_uri', 'username')

class UsersViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all().order_by('id')
    serializer_class = UserSerializer
    permission_classes = (IsAdminUserOrReadOnly,)

# Projects

# TODO: include list of maintainers, connect plugins

class ProjectSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Project
        fields = ('resource_uri', 'name', 'mailing_list', 'prefix_tags', 'url', 'git', \
                  'description', 'display_order', 'logo', 'parent_project')

class ProjectsViewSet(viewsets.ModelViewSet):
    queryset = Project.objects.all().order_by('id')
    serializer_class = ProjectSerializer
    permission_classes = (IsMaintainerOrReadOnly,)

# Common classes for series and messages

class HyperlinkedMessageField(HyperlinkedIdentityField):
    def get_url(self, obj, view_name, request, format):
        kwargs = {'projects_pk': obj.project_id, 'message_id': obj.message_id}
        return self.reverse(view_name, kwargs=kwargs, request=request, format=format)

class BaseMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = ('resource_uri', 'message_id', 'subject', 'date', 'sender', 'recipients')

    resource_uri = HyperlinkedMessageField(view_name='messages-detail')

    recipients = SerializerMethodField()
    sender = SerializerMethodField()

    def format_name_addr(self, name, addr):
        d = {}
        if name != addr:
            d['name'] = name
        d['address'] = addr
        return d

    def get_recipients(self, obj):
        return [self.format_name_addr(*x) for x in obj.get_recipients()]

    def get_sender(self, obj):
        name, addr = obj.get_sender()
        return self.format_name_addr(*obj.get_sender())

# a message_id is *not* unique, so we can only list
class BaseMessageViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = BaseMessageSerializer
    queryset = Message.objects.all()
    permission_classes = ()
    lookup_field = 'message_id'
    lookup_value_regex = '[^/]+'

# a (project, message_id) tuple is unique, so we can always retrieve an object
class ProjectMessagesViewSetMixin(mixins.RetrieveModelMixin):
    def get_queryset(self):
        return self.queryset.filter(project=self.kwargs['projects_pk'])

# Series

class ReplySerializer(BaseMessageSerializer):
    class Meta:
        model = Message
        fields = BaseMessageSerializer.Meta.fields + ('in_reply_to', )

class PatchSerializer(BaseMessageSerializer):
    class Meta:
        model = Message
        fields = BaseMessageSerializer.Meta.fields + ('stripped_subject',
            'last_comment_date', 'patch_num')

class SeriesSerializer(BaseMessageSerializer):
    class Meta:
        model = Message
        fields = ('resource_uri',) + BaseMessageSerializer.Meta.fields + (
             'message', 'stripped_subject', 'last_comment_date', 'last_reply_date',
             'is_complete', 'is_merged', 'num_patches', 'total_patches', 'results')

    resource_uri = HyperlinkedMessageField(view_name='series-detail')
    message = HyperlinkedMessageField(view_name='messages-detail')
    total_patches = SerializerMethodField()
    results = SerializerMethodField()

    def __init__(self, *args, **kwargs):
        self.detailed = kwargs.pop('detailed', False)
        super(SeriesSerializer, self).__init__(*args, **kwargs)

    def get_fields(self):
        fields = super(SeriesSerializer, self).get_fields()
        request = self.context['request']
        dispatch_module_hook("rest_series_fields_hook", request=request,
                             fields=fields, detailed=self.detailed)
        return fields

    def get_results(self, message):
        results = {}
        request = self.context['request']
        dispatch_module_hook("rest_results_hook", request=request,
                             message=message, results=results)
        return results

    def get_total_patches(self, obj):
        return obj.get_total_patches()

class SeriesSerializerFull(SeriesSerializer):
    class Meta:
        model = Message
        fields = SeriesSerializer.Meta.fields + ('patches', 'replies')

    patches = PatchSerializer(many=True)
    replies = ReplySerializer(many=True)

    def __init__(self, *args, **kwargs):
        if not 'detailed' in kwargs:
            kwargs['detailed'] = True
        super(SeriesSerializerFull, self).__init__(*args, **kwargs)

class PatchewSearchFilter(filters.BaseFilterBackend):
    search_param = SEARCH_PARAM
    search_title = 'Search'
    search_description = 'A search term.'
    template = 'rest_framework/filters/search.html'

    def filter_queryset(self, request, queryset, view):
        search = request.query_params.get(self.search_param) or ''
        terms = [x.strip() for x in search.split(" ") if x]
        se = SearchEngine()
        query = se.search_series(queryset=queryset, *terms)
        return query

    def to_html(self, request, queryset, view):
        if not getattr(view, 'search_fields', None):
            return ''

        term = request.query_params.get(self.search_param) or ''
        context = {
            'param': self.search_param,
            'term': term
        }
        template = loader.get_template(self.template)
        return template.render(context)

class SeriesViewSet(BaseMessageViewSet):
    serializer_class = SeriesSerializer
    queryset = Message.objects.filter(is_series_head=True).order_by('-last_reply_date')
    filter_backends = (PatchewSearchFilter,)
    search_fields = (SEARCH_PARAM,)

class ProjectSeriesViewSet(ProjectMessagesViewSetMixin,
                           SeriesViewSet):
    def collect_patches(self, series):
        if series.is_patch:
            patches = [series]
        else:
            patches = Message.objects.filter(in_reply_to=series.message_id,
                                             project=self.kwargs['projects_pk'],
                                             is_patch=True).order_by('patch_num')
        return patches

    def collect_replies(self, parent, result):
        replies = Message.objects.filter(in_reply_to=parent.message_id,
                                         project=self.kwargs['projects_pk'],
                                         is_patch=False).order_by('date')
        for m in replies:
            result.append(m)
        for m in replies:
            self.collect_replies(m, result)
        return result

    def get_serializer_class(self, *args, **kwargs):
        if self.lookup_field in self.kwargs:
            return SeriesSerializerFull
        return SeriesSerializer

    def get_object(self):
        series = super(ProjectSeriesViewSet, self).get_object()
        series.patches = self.collect_patches(series)
        series.replies = self.collect_replies(series, [])
        if not series.is_patch:
            for i in series.patches:
                self.collect_replies(i, series.replies)
        return series

# Messages

# TODO: add POST endpoint connected to email plugin?

class MessageSerializer(BaseMessageSerializer):
    class Meta:
        model = Message
        fields = BaseMessageSerializer.Meta.fields + ('mbox', )

    def get_mbox(self, obj):
        return obj.get_mbox()
    mbox = SerializerMethodField()

    def get_fields(self):
        fields = super(MessageSerializer, self).get_fields()
        request = self.context['request']
        dispatch_module_hook("rest_message_fields_hook", request=request,
                             fields=fields)
        return fields

class StaticTextRenderer(renderers.BaseRenderer):
    media_type = 'text/plain'
    format = 'mbox'

    def render(self, data, accepted_media_type=None, renderer_context=None):
        renderer_context = renderer_context or {}
        response = renderer_context.get('response')
        if response and response.exception:
            return '%d %s' % (response.status_code, response.status_text.title())
        else:
            return data

class MessagesViewSet(ProjectMessagesViewSetMixin,
                      BaseMessageViewSet):
    serializer_class = MessageSerializer

    @detail_route(renderer_classes=[StaticTextRenderer])
    def mbox(self, request, *args, **kwargs):
        message = self.get_object()
        return Response(message.get_mbox())

    @detail_route()
    def replies(self, request, *args, **kwargs):
        message = self.get_object()
        replies = Message.objects.filter(in_reply_to=message.message_id,
                                         project=self.kwargs['projects_pk']).order_by('date')
        page = self.paginate_queryset(replies)
        serializer = BaseMessageSerializer(page, many=True,
                                           context=self.get_serializer_context())
        return self.get_paginated_response(serializer.data)
