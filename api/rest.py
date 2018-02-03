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
from .models import Project
from rest_framework import permissions, serializers, viewsets

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
                  'description', 'display_order', 'logo')

class ProjectsViewSet(viewsets.ModelViewSet):
    queryset = Project.objects.all().order_by('id')
    serializer_class = ProjectSerializer
    permission_classes = (IsMaintainerOrReadOnly,)
