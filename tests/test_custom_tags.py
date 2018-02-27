#!/usr/bin/env python3
#
# Copyright 2018 Red Hat, Inc.
#
# Authors:
#     Paolo Bonzini <pbonzini@redhat.com>
#
# This work is licensed under the MIT License.  Please see the LICENSE file or
# http://opensource.org/licenses/MIT.

from django.template import Context, Template
import patchewtest
import unittest

class CustomTagsTest(unittest.TestCase):
    def assertTemplate(self, template, expected, **kwargs):
        context = Context(kwargs)
        self.assertEqual(Template(template).render(context), expected)

    def test_template_filters(self):
        self.assertTemplate('{{s|ansi2text}}', 'dbc', s='abc\rd')

    def test_template_tags(self):
        self.assertTemplate('{% ansi2text s %}', 'dbc', s='abc\rd')

if __name__ == '__main__':
    unittest.main()
