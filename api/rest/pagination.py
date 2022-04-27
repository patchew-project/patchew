#!/usr/bin/env python3
#
# Copyright 2022 Red Hat, Inc.
#
# Authors:
#     Paolo Bonzini <pbonzini@redhat.com>
#
# This work is licensed under the MIT License.  Please see the LICENSE file or
# http://opensource.org/licenses/MIT.

from rest_framework.pagination import LimitOffsetPagination
from rest_framework.response import Response


# remove count from paginator

# This is referred to in settings.py, putting it with the rest of api/rest.py
# results in a circular dependency between modules.


class PatchewPagination(LimitOffsetPagination):
    def get_paginated_response(self, data):
        return Response(
            {
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                "results": data,
            }
        )

    def paginate_queryset(self, queryset, request, view=None):
        self.offset = self.get_offset(request)
        self.limit = self.get_limit(request)

        # Get one extra element to check if there is a "next" page
        q = list(queryset[self.offset : self.offset + self.limit + 1])
        self.count = self.offset + len(q) if len(q) else self.offset - 1
        if len(q) > self.limit:
            q.pop()

        self.request = request
        if self.count > self.limit and self.template is not None:
            self.display_page_controls = True

        return q

    def get_paginated_response_schema(self, schema):
        ret = super().get_paginated_response_schema(schema)
        del ret["properties"]["count"]
        return ret
