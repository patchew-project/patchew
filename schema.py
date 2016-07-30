#!/usr/bin/env python3
#
# Copyright 2016 Red Hat, Inc.
#
# Authors:
#     Fam Zheng <famz@redhat.com>
#
# This work is licensed under the MIT License.  Please see the LICENSE file or
# http://opensource.org/licenses/MIT.

"""Data schema classes"""

class Schema(object):
    def __init__(self, name, title=None, desc=None, required=False):
        self.name = name
        self.title = title or name
        self.desc = desc
        self.required = required

class StringSchema(Schema):
    def __init__(self, name, title=None, desc=None, required=False, default="",
                 multiline=False):
        super(StringSchema, self).__init__(name, title, desc, required)
        self.multiline = multiline
        self.default = default

class IntegerSchema(Schema):
    def __init__(self, name, title=None, desc=None, required=False, default=0):
        super(IntegerSchema, self).__init__(name, title, desc, required)
        self.default = default

class EnumSchema(Schema):
    def __init__(self, name, title=None, desc=None, required=False,
                 enums=lambda: []):
        super(EnumSchema, self).__init__(name, title, desc, required)
        self.enums = enums

class BooleanSchema(Schema):
    def __init__(self, name, title=None, desc=None, required=False, default=0):
        super(BooleanSchema, self).__init__(name, title, desc, required)
        self.default = default

class MapSchema(Schema):
    """Homogeneous map from string to items"""
    def __init__(self, name, title=None, desc=None, required=False,
                 item=None):
        super(MapSchema, self).__init__(name, title, desc, required)
        self.item = item

class ArraySchema(Schema):
    """A fixed array of items"""
    def __init__(self, name, title=None, desc=None, required=False, members=[]):
        super(ArraySchema, self).__init__(name, title, desc, required)
        self.members = members

