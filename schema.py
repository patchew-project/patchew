
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
    def __init__(self, name, title=None, desc=None, required=False):
        super(IntegerSchema, self).__init__(name, title, desc, required)

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

