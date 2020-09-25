#!/usr/bin/env python3
#
# Copyright 2018 Red Hat, Inc.
#
# Authors:
#     Paolo Bonzini <pbonzini@redhat.com>
#
# This work is licensed under the MIT License.  Please see the LICENSE file or
# http://opensource.org/licenses/MIT.

from collections import OrderedDict
from django.contrib.auth.models import User
from django.http import Http404, HttpResponseRedirect
from django.template import loader

from mod import dispatch_module_hook
from .models import Project, ProjectResult, Message, MessageResult, Result
from .search import SearchEngine
from rest_framework import (
    permissions,
    serializers,
    generics,
    viewsets,
    filters,
    mixins,
    renderers,
    status,
)
from rest_framework.decorators import action
from rest_framework.fields import (
    SerializerMethodField,
    CharField,
    JSONField,
    EmailField,
    ListField,
)
from rest_framework.relations import HyperlinkedIdentityField
from rest_framework.response import Response
from rest_framework.views import APIView
import rest_framework
from mbox import addr_db_to_rest, MboxMessage
from rest_framework.parsers import BaseParser

SEARCH_PARAM = "q"


class StaticTextRenderer(renderers.BaseRenderer):
    media_type = "text/plain"
    charset = "utf-8"
    format = "mbox"

    def render(self, data, accepted_media_type=None, renderer_context=None):
        renderer_context = renderer_context or {}
        response = renderer_context.get("response")
        if response and response.exception:
            return "%d %s" % (response.status_code, response.status_text.title())
        else:
            return data


# patchew-specific permission classes


class PatchewPermission(permissions.BasePermission):
    """
    Generic code to lookup for permissions based on message and project
    objects.  If the view has a "project" property, it should return an
    api.models.Project, and has_permission will check that property too.

    Subclasses can override the methods, or specify a set of groups that
    are granted authorization independent of object permissions.
    """

    allowed_groups = ()

    def is_superuser(self, request):
        return request.user and request.user.is_superuser

    def is_safe_method(self, request):
        return request.method in permissions.SAFE_METHODS

    def has_project_permission(self, request, view, obj):
        return obj.maintained_by(request.user)

    def has_group_permission(self, request, view, groups):
        for grp in request.user.groups.all():
            if grp.name in groups:
                return True
        return False

    def has_generic_permission(self, request, view):
        return (
            self.is_safe_method(request)
            or self.is_superuser(request)
            or self.has_group_permission(request, view, self.allowed_groups)
        )

    def has_permission(self, request, view):
        # The user can get permissions to operate on an object or a list from one of:
        # - the HTTP method (has_generic_permission)
        # - the groups that are allowed for the view (has_generic_permission)
        # - the parent project of an object (view.project + has_project_permission)
        # - the groups that are allowed for a result
        #   (view.result_renderer + has_group_permission)
        conditions = [self.has_generic_permission(request, view)]

        if hasattr(view, "project"):
            conditions.append(
                view.project
                and self.has_project_permission(request, view, view.project)
            )

        if hasattr(view, "result_renderer"):
            conditions.append(
                view.result_renderer
                and self.has_group_permission(
                    request, view, view.result_renderer.allowed_groups
                )
            )

        return any(conditions)

    def has_object_permission(self, request, view, obj):
        # For non-project objects, has_project_permission has been evaluated
        # already in has_permission, based on the primary key included in the
        # URL.
        return (
            self.has_generic_permission(request, view)
            or not isinstance(obj, Project)
            or self.has_project_permission(request, view, obj)
        )


class MaintainerPermission(PatchewPermission):
    def is_safe_method(self, request):
        return False


class ImportPermission(PatchewPermission):
    allowed_groups = ("importers",)


class TestPermission(PatchewPermission):
    allowed_groups = ("testers",)


# utility function to generate REST API URLs


def reverse_detail(obj, request):
    if isinstance(obj, Project):
        return rest_framework.reverse.reverse(
            "project-detail", request=request, kwargs={"pk": obj.id}
        )
    if isinstance(obj, Message):
        assert obj.is_series_head
        return rest_framework.reverse.reverse(
            "series-detail",
            request=request,
            kwargs={"projects_pk": obj.project.id, "message_id": obj.message_id},
        )
    if isinstance(obj, ProjectResult):
        po = obj.obj
        return rest_framework.reverse.reverse(
            "results-detail",
            request=request,
            kwargs={"projects_pk": po.id, "name": obj.name},
        )
    if isinstance(obj, MessageResult):
        m = obj.obj
        return rest_framework.reverse.reverse(
            "results-detail",
            request=request,
            kwargs={
                "projects_pk": m.project.id,
                "series_message_id": m.message_id,
                "name": obj.name,
            },
        )
    raise Exception("unhandled object type")


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
        request = self.context["request"]
        format = self.context.get("format", None)
        return method(value, request, format)


# Users

# TODO: include list of projects maintained by the user, login
class UserSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = User
        fields = ("resource_uri", "username")


class UsersViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all().order_by("id")
    serializer_class = UserSerializer
    permission_classes = (PatchewPermission,)


# Projects

# TODO: include list of maintainers, connect plugins
class ProjectSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Project
        fields = (
            "resource_uri",
            "name",
            "mailing_list",
            "prefix_tags",
            "url",
            "git",
            "description",
            "display_order",
            "logo",
            "parent_project",
            "messages",
            "results",
            "series",
        )

    messages = HyperlinkedIdentityField(
        view_name="messages-list", lookup_field="pk", lookup_url_kwarg="projects_pk"
    )
    results = HyperlinkedIdentityField(
        view_name="results-list", lookup_field="pk", lookup_url_kwarg="projects_pk"
    )
    series = HyperlinkedIdentityField(
        view_name="series-list", lookup_field="pk", lookup_url_kwarg="projects_pk"
    )

    def get_fields(self):
        fields = super(ProjectSerializer, self).get_fields()
        request = self.context["request"]
        dispatch_module_hook("rest_project_fields_hook", request=request, fields=fields)
        return fields


class ProjectsViewSet(viewsets.ModelViewSet):
    queryset = Project.objects.all().order_by("id")
    serializer_class = ProjectSerializer
    permission_classes = (PatchewPermission,)

    @action(
        methods=["get", "put"], detail=True, permission_classes=[MaintainerPermission]
    )
    def config(self, request, pk=None):
        project = self.get_object()
        if request.method == "PUT":
            project.config = request.data
            project.save()
        return Response(project.config)

    @action(methods=["post"], detail=True, permission_classes=[ImportPermission])
    def update_project_head(self, request, pk=None):
        """
        updates the project head and message_id which are matched are merged.
        Data input format:
        {
            "old_head": "..",
            "new_head": "..",
            "message_ids": []
        }
        """
        project = self.get_object()
        head = project.project_head
        old_head = request.data["old_head"]
        message_ids = request.data["message_ids"]
        if head and head != old_head:
            return Response("Wrong old head", status_code=status.HTTP_409_CONFLICT)
        ret = project.series_update(message_ids)
        project.project_head = request.data["new_head"]
        return Response({"new_head": project.project_head, "count": ret})


class ProjectsByNameView(generics.GenericAPIView):
    serializer_class = ProjectSerializer
    queryset = Project.objects.all()
    lookup_field = "name"

    def _redirect(self, request, *args, **kwargs):
        instance = self.get_object()
        url = reverse_detail(instance, request)
        if kwargs["tail"]:
            tail = kwargs["tail"]
            if kwargs["tail"][0] == "/" and url[-1] == "/":
                tail = tail[1:]
            url += tail
        params = request.query_params.urlencode()
        if params:
            url += "?" + params
        return HttpResponseRedirect(url, status=status.HTTP_307_TEMPORARY_REDIRECT)

    delete = _redirect
    get = _redirect
    head = _redirect
    options = _redirect
    patch = _redirect
    post = _redirect
    put = _redirect


# Common classes for series and messages


class HyperlinkedMessageField(HyperlinkedIdentityField):
    lookup_field = "message_id"

    def get_url(self, obj, view_name, request, format):
        kwargs = {"projects_pk": obj.project_id, self.lookup_field: obj.message_id}
        return self.reverse(view_name, kwargs=kwargs, request=request, format=format)


class AddressSerializer(serializers.Serializer):
    name = CharField(required=False)
    address = EmailField()

    def to_representation(self, obj):
        return addr_db_to_rest(obj)

    def create(self, validated_data):
        try:
            return [validated_data["name"], validated_data["address"]]
        except Exception:
            return [validated_data["address"], validated_data["address"]]


class BaseMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        read_only_fields = (
            "resource_uri",
            "message_id",
            "subject",
            "date",
            "sender",
            "recipients",
        )
        fields = read_only_fields + ("tags",)

    resource_uri = HyperlinkedMessageField(view_name="messages-detail")
    recipients = AddressSerializer(many=True)
    sender = AddressSerializer()
    tags = ListField(child=CharField(), required=False)

    def create(self, validated_data):
        validated_data["recipients"] = self.fields["recipients"].create(
            validated_data["recipients"]
        )
        validated_data["sender"] = self.fields["sender"].create(
            validated_data["sender"]
        )
        if "project" in validated_data:
            project = validated_data.pop("project")
            return Message.objects.create(project=project, **validated_data)
        return Message.objects.create(project=self.context["project"], **validated_data)


# a message_id is *not* unique, so we can only list
class BaseMessageViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = BaseMessageSerializer
    queryset = Message.objects.all()
    permission_classes = (ImportPermission,)
    lookup_field = "message_id"
    lookup_value_regex = "[^/]+"


# a (project, message_id) tuple is unique, so we can always retrieve an object
class ProjectMessagesViewSetMixin(mixins.RetrieveModelMixin, mixins.UpdateModelMixin):
    def get_queryset(self):
        return self.queryset.filter(project=self.kwargs["projects_pk"])

    @property
    def project(self):
        if hasattr(self, "__project"):
            return self.__project
        try:
            self.__project = Project.objects.get(id=self.kwargs["projects_pk"])
        except Exception:
            self.__project = None
        return self.__project

    def get_serializer_context(self):
        if "projects_pk" in self.kwargs and not self.project:
            raise Http404("Project not found")
        context = super(ProjectMessagesViewSetMixin, self).get_serializer_context()
        context["project"] = self.project
        return context


# Series
class ReplySerializer(BaseMessageSerializer):
    class Meta:
        model = Message
        fields = BaseMessageSerializer.Meta.fields + ("in_reply_to",)


class PatchSerializer(BaseMessageSerializer):
    class Meta:
        model = Message
        fields = BaseMessageSerializer.Meta.fields + (
            "stripped_subject",
            "last_comment_date",
            "patch_num",
        )


class SeriesSerializer(BaseMessageSerializer):
    class Meta:
        model = Message
        subclass_read_only_fields = (
            "message",
            "stripped_subject",
            "num_patches",
            "total_patches",
            "results",
            "mbox_uri",
        )
        fields = (
            BaseMessageSerializer.Meta.fields
            + subclass_read_only_fields
            + (
                "last_comment_date",
                "last_reply_date",
                "is_complete",
                "is_merged",
                "is_obsolete",
                "is_tested",
                "is_reviewed",
                "maintainers",
            )
        )
        read_only_fields = (
            BaseMessageSerializer.Meta.read_only_fields + subclass_read_only_fields
        )

    resource_uri = HyperlinkedMessageField(view_name="series-detail")
    mbox_uri = HyperlinkedMessageField(view_name="series-mbox")
    message = HyperlinkedMessageField(view_name="messages-detail")
    results = HyperlinkedMessageField(
        view_name="results-list", lookup_field="series_message_id"
    )
    total_patches = SerializerMethodField()
    maintainers = ListField(child=CharField(), required=False)

    def __init__(self, *args, **kwargs):
        self.detailed = kwargs.pop("detailed", False)
        super(SeriesSerializer, self).__init__(*args, **kwargs)

    def get_fields(self):
        fields = super(SeriesSerializer, self).get_fields()
        request = self.context["request"]
        dispatch_module_hook(
            "rest_series_fields_hook",
            request=request,
            fields=fields,
            detailed=self.detailed,
        )
        return fields

    def get_total_patches(self, obj):
        return obj.get_total_patches()


class SeriesSerializerFull(SeriesSerializer):
    class Meta:
        model = Message
        fields = SeriesSerializer.Meta.fields + ("patches", "replies")

    patches = PatchSerializer(many=True)
    replies = ReplySerializer(many=True)

    def __init__(self, *args, **kwargs):
        if "detailed" not in kwargs:
            kwargs["detailed"] = True
        super(SeriesSerializerFull, self).__init__(*args, **kwargs)


class PatchewSearchFilter(filters.BaseFilterBackend):
    search_param = SEARCH_PARAM
    search_title = "Search"
    search_description = "A search term."
    template = "rest_framework/filters/search.html"

    def filter_queryset(self, request, queryset, view):
        search = request.query_params.get(self.search_param) or ""
        terms = [x.strip() for x in search.split(" ") if x]
        se = SearchEngine()
        query = se.search_series(queryset=queryset, user=request.user, *terms)
        return query

    def to_html(self, request, queryset, view):
        if not getattr(view, "search_fields", None):
            return ""

        term = request.query_params.get(self.search_param) or ""
        context = {"param": self.search_param, "term": term}
        template = loader.get_template(self.template)
        return template.render(context)


class SeriesViewSet(BaseMessageViewSet):
    serializer_class = SeriesSerializer
    queryset = Message.objects.filter(topic__isnull=False).order_by("-last_reply_date")
    filter_backends = (PatchewSearchFilter,)
    search_fields = (SEARCH_PARAM,)


class ProjectSeriesViewSet(
    ProjectMessagesViewSetMixin,
    SeriesViewSet,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
):
    def collect_patches(self, series):
        if series.is_patch:
            patches = [series]
        else:
            patches = Message.objects.filter(
                in_reply_to=series.message_id,
                project=self.kwargs["projects_pk"],
                is_patch=True,
            ).order_by("patch_num")
        return patches

    def collect_replies(self, parent, result):
        replies = Message.objects.filter(
            in_reply_to=parent.message_id,
            project=self.kwargs["projects_pk"],
            is_patch=False,
        ).order_by("date")
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

    def perform_destroy(self, instance):
        Message.objects.delete_subthread(instance)

    @action(detail=True, renderer_classes=[StaticTextRenderer])
    def mbox(self, request, *args, **kwargs):
        message = self.get_object()
        mbox = message.get_mbox_with_tags()
        if not mbox:
            raise Http404("Series not complete")
        return Response(mbox)


# Messages


class MessageSerializer(BaseMessageSerializer):
    class Meta:
        model = Message
        fields = BaseMessageSerializer.Meta.fields + ("mbox",)
        read_only_fields = BaseMessageSerializer.Meta.read_only_fields + ("mbox",)

    mbox = CharField()

    def get_fields(self):
        fields = super(MessageSerializer, self).get_fields()
        try:
            # When called from the CoreAPI schema generator, there is no context defined?
            request = self.context["request"]
        except TypeError:
            request = None

        dispatch_module_hook("rest_message_fields_hook", request=request, fields=fields)
        return fields


class MessageCreationSerializer(BaseMessageSerializer):
    class Meta:
        model = Message
        fields = BaseMessageSerializer.Meta.fields + ("mbox",)
        read_only_fields = []

    mbox = CharField()


class MessagePlainTextParser(BaseParser):
    media_type = "message/rfc822"

    def parse(self, stream, media_type=None, parser_context=None):
        data = stream.read().decode("utf-8")
        return MboxMessage(data).get_json()


class ProjectMessagesViewSet(
    ProjectMessagesViewSetMixin,
    BaseMessageViewSet,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
):
    parser_classes = APIView.parser_classes + [MessagePlainTextParser]

    def get_serializer_class(self, *args, **kwargs):
        if self.request.method == "POST":
            return MessageCreationSerializer
        else:
            return MessageSerializer

    @action(detail=True, renderer_classes=[StaticTextRenderer])
    def mbox(self, request, *args, **kwargs):
        message = self.get_object()
        return Response(message.get_mbox())

    @action(detail=True)
    def replies(self, request, *args, **kwargs):
        message = self.get_object()
        replies = Message.objects.filter(
            in_reply_to=message.message_id, project=self.kwargs["projects_pk"]
        ).order_by("date")
        page = self.paginate_queryset(replies)
        serializer = BaseMessageSerializer(
            page, many=True, context=self.get_serializer_context()
        )
        return self.get_paginated_response(serializer.data)


class MessagesViewSet(BaseMessageViewSet):
    permission_classes = (permissions.IsAuthenticatedOrReadOnly,)
    parser_classes = APIView.parser_classes + [MessagePlainTextParser]

    def get_serializer_class(self, *args, **kwargs):
        if self.request.method == "POST":
            return MessageCreationSerializer
        else:
            return MessageSerializer

    def create(self, request, *args, **kwargs):
        m = MboxMessage(request.data["mbox"])
        projects = [p for p in Project.objects.all() if p.recognizes(m)]
        grps = request.user.groups.all()
        grps_name = [grp.name for grp in grps]
        if "importers" not in grps_name:
            projects = (p for p in projects if p.maintained_by(self.request.user))
        results = []
        for project in projects:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            serializer.save(project=project)
            results.append(serializer.data)
        # Fake paginator response.  Note that there is no Location header.
        return Response(
            OrderedDict([("count", len(results)), ("results", results)]),
            status=status.HTTP_201_CREATED,
        )


# Results
class HyperlinkedResultField(HyperlinkedIdentityField):
    def get_url(self, result, view_name, request, format):
        obj = result.obj
        kwargs = {"name": result.name}
        if isinstance(obj, Message):
            kwargs["projects_pk"] = obj.project_id
            kwargs["series_message_id"] = obj.message_id
        else:
            kwargs["projects_pk"] = obj.id
        return self.reverse(view_name, kwargs=kwargs, request=request, format=format)


class ResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = Result
        fields = ("resource_uri", "name", "status", "last_update", "data", "log_url")
        read_only_fields = ("name", "last_update")

    resource_uri = HyperlinkedResultField(view_name="results-detail")
    log_url = SerializerMethodField(required=False)
    data = JSONField(required=False)

    def get_log_url(self, obj):
        request = self.context["request"]
        return obj.get_log_url(request)

    def validate(self, data):
        if "data" in data:
            data_serializer_class = self.context[
                "renderer"
            ].result_data_serializer_class
            data_serializer_class(data=data["data"], context=self.context).is_valid(
                raise_exception=True
            )
        return data


class ResultSerializerFull(ResultSerializer):
    class Meta:
        model = Result
        fields = ResultSerializer.Meta.fields + ("log",)
        read_only_fields = ResultSerializer.Meta.read_only_fields

    # The database field is log_xz, so this is needed here
    log = CharField(required=False, allow_null=True, allow_blank=True)


class ResultsViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    lookup_field = "name"
    lookup_value_regex = "[^/]+"
    filter_backends = (filters.OrderingFilter,)
    ordering_fields = ("name",)
    ordering = ("name",)
    permission_classes = (PatchewPermission,)

    # for permissions
    @property
    def project(self):
        if hasattr(self, "__project"):
            return self.__project
        try:
            self.__project = Project.objects.get(id=self.kwargs["projects_pk"])
        except Exception:
            self.__project = None
        return self.__project

    @property
    def result_renderer(self):
        if "name" in self.kwargs:
            return Result.renderer_from_name(self.kwargs["name"])
        return None

    def get_serializer_context(self):
        context = super(ResultsViewSet, self).get_serializer_context()
        if "name" in self.kwargs:
            context["renderer"] = self.result_renderer
        return context

    def get_serializer_class(self, *args, **kwargs):
        if self.lookup_field in self.kwargs:
            return ResultSerializerFull
        return ResultSerializer


class ProjectResultsViewSet(ResultsViewSet):
    def get_queryset(self):
        return ProjectResult.objects.filter(project=self.kwargs["projects_pk"])


class SeriesResultsViewSet(ResultsViewSet):
    def get_queryset(self):
        return MessageResult.objects.filter(
            message__project=self.kwargs["projects_pk"],
            message__message_id=self.kwargs["series_message_id"],
        )
