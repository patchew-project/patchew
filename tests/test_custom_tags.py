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
from patchew.tags import tail_lines, grep_A, grep_B, grep_C, grep
import unittest

class CustomTagsTest(unittest.TestCase):
    def assertTemplate(self, template, expected, **kwargs):
        context = Context(kwargs)
        self.assertEqual(Template(template).render(context), expected)

    def test_template_filters(self):
        self.assertTemplate('{{s|ansi2text}}', 'dbc', s='abc\rd')
        self.assertTemplate('{{s|grep:"[0-9]"}}', '0\n9', s='0\na\n9')
        self.assertTemplate('{{s|grep_A:"b"}}',
                            'b\nc\nd\ne\n---\nb',
                             s='a\nb\nc\nd\ne\nf\nx\ny\nz\nb')
        self.assertTemplate('{{s|grep_B:"b"}}',
                            'a\nb\n---\nx\ny\nz\nb',
                             s='a\nb\nc\nd\ne\nf\nx\ny\nz\nb')
        self.assertTemplate('{{s|grep_C:"b"}}',
                            'a\nb\nc\nd\ne\n---\nx\ny\nz\nb',
                             s='a\nb\nc\nd\ne\nf\nx\ny\nz\nb')
        self.assertTemplate('{{s|tail_lines:3}}', 'b\nc\nd', s='a\nb\nc\nd')

    def test_template_tags(self):
        self.assertTemplate('{% ansi2text s %}', 'dbc', s='abc\rd')
        self.assertTemplate('{% grep s "[0-9]" %}', '0\n9', s='0\na\n9')
        self.assertTemplate('{% grep_A s regex="[bc]" n=1 %}', 'b\nc\nd', s='a\nb\nc\nd')
        self.assertTemplate('{% grep_B s regex="[bc]" n=1 %}', 'a\nb\nc', s='a\nb\nc\nd')
        self.assertTemplate('{% grep_C s "b" n=1 %}', 'a\nb\nc', s='a\nb\nc\nd')
        self.assertTemplate('{% tail_lines s n=3 %}', 'b\nc\nd', s='a\nb\nc\nd')

    def test_grep(self):
        self.assertEqual(grep('0\na\n9', '[0-9]'), '0\n9')
        self.assertEqual(grep('0\na\n9', '[0-9]', '---'), '0\n---\n9')

    def test_grep_A(self):
        self.assertEqual(grep_A('a\nb\nc\nd', 'b', 1, None), 'b\nc')
        self.assertEqual(grep_A('a\nb\nc\nd', 'b', 2, None), 'b\nc\nd')
        self.assertEqual(grep_A('a\nb\nc\nd\nb\ne', 'b', 1, None), 'b\nc\nb\ne')
        self.assertEqual(grep_A('a\nb\nc\nd\nb\ne', 'b', 2, None), 'b\nc\nd\nb\ne')
        self.assertEqual(grep_A('a\nb\nc\nd\nz\nb\ne', 'b', 1, None), 'b\nc\nb\ne')
        self.assertEqual(grep_A('a\nb\nc\nd\nz\nb\ne', 'b', 2, None), 'b\nc\nd\nb\ne')
        self.assertEqual(grep_A('a\nb\nc\nz\nb\nb\ne', 'b', 1, None), 'b\nc\nb\nb\ne')
        self.assertEqual(grep_A('b\nc\nz\nb\nb\ne', 'b', 1, None), 'b\nc\nb\nb\ne')
        self.assertEqual(grep_A('b\n', 'b', 1, None), 'b')

    def test_grep_A_sep(self):
        self.assertEqual(grep_A('a\nb\nc\nd', 'b', 1), 'b\nc')
        self.assertEqual(grep_A('a\nb\nc\nd', 'b', 2), 'b\nc\nd')
        self.assertEqual(grep_A('a\nb\nc\nd\nb\ne', 'b', 1), 'b\nc\n---\nb\ne')
        self.assertEqual(grep_A('a\nb\nc\nd\nb\ne', 'b', 2), 'b\nc\nd\nb\ne')
        self.assertEqual(grep_A('a\nb\nc\nd\nz\nb\ne', 'b', 1), 'b\nc\n---\nb\ne')
        self.assertEqual(grep_A('a\nb\nc\nd\nz\nb\nb\ne', 'b', 1), 'b\nc\n---\nb\nb\ne')
        self.assertEqual(grep_A('b\nc\nz\nb\nb\ne', 'b', 1), 'b\nc\n---\nb\nb\ne')
        self.assertEqual(grep_A('b\n', 'b', 1), 'b')

    def test_grep_B(self):
        self.assertEqual(grep_B('a\nb\nc\nd', 'b', 1, None), 'a\nb')
        self.assertEqual(grep_B('a\nb\nc\nd', 'b', 2, None), 'a\nb')
        self.assertEqual(grep_B('a\nb\nc\nd\nb\ne', 'b', 1, None), 'a\nb\nd\nb')
        self.assertEqual(grep_B('a\nb\nc\nd\nz\nb\ne', 'b', 1, None), 'a\nb\nz\nb')
        self.assertEqual(grep_B('a\nb\nc\nd\nz\nb\ne', 'b', 2, None), 'a\nb\nd\nz\nb')
        self.assertEqual(grep_B('a\nb\nc\nz\nb\nb\ne', 'b', 1, None), 'a\nb\nz\nb\nb')
        self.assertEqual(grep_B('b\nc\nz\nb\nb\ne', 'b', 1, None), 'b\nz\nb\nb')
        self.assertEqual(grep_B('b\n', 'b', 1, None), 'b')

    def test_grep_B_sep(self):
        self.assertEqual(grep_B('a\nb\nc\nd', 'b', 1), 'a\nb')
        self.assertEqual(grep_B('a\nb\nc\nd', 'b', 2), 'a\nb')
        self.assertEqual(grep_B('a\nb\nc\nd\nb\ne', 'b', 1), 'a\nb\n---\nd\nb')
        self.assertEqual(grep_B('a\nb\nc\nd\nz\nb\ne', 'b', 1), 'a\nb\n---\nz\nb')
        self.assertEqual(grep_B('a\nb\nc\nd\nz\nb\ne', 'b', 2), 'a\nb\n---\nd\nz\nb')
        self.assertEqual(grep_B('a\nb\nc\nz\nb\nb\ne', 'b', 1), 'a\nb\n---\nz\nb\nb')
        self.assertEqual(grep_B('b\nc\nz\nb\nb\ne', 'b', 1), 'b\n---\nz\nb\nb')
        self.assertEqual(grep_B('b\n', 'b', 1), 'b')

    def test_grep_C(self):
        self.assertEqual(grep_C('a\nb\nc\nd', 'b', 1, None), 'a\nb\nc')
        self.assertEqual(grep_C('a\nb\nc\nd', 'b', 2, None), 'a\nb\nc\nd')
        self.assertEqual(grep_C('a\nb\nc\nd\nb\ne', 'b', 1, None), 'a\nb\nc\nd\nb\ne')
        self.assertEqual(grep_C('a\nb\nc\nd\nz\nb\ne', 'b', 1, None), 'a\nb\nc\nz\nb\ne')
        self.assertEqual(grep_C('a\nb\nc\nd\nz\nb\ne', 'b', 2, None), 'a\nb\nc\nd\nz\nb\ne')
        self.assertEqual(grep_C('a\nb\nc\nz\nb\nb\ne', 'b', 1, None), 'a\nb\nc\nz\nb\nb\ne')
        self.assertEqual(grep_C('b\nc\nz\nb\nb\ne', 'b', 1, None), 'b\nc\nz\nb\nb\ne')
        self.assertEqual(grep_C('b\n', 'b', 1, None), 'b')

    def test_grep_C_sep(self):
        self.assertEqual(grep_C('a\nb\nc\nd', 'b', 1), 'a\nb\nc')
        self.assertEqual(grep_C('a\nb\nc\nd', 'b', 2), 'a\nb\nc\nd')
        self.assertEqual(grep_C('a\nb\nc\nd\nb\ne', 'b', 1), 'a\nb\nc\nd\nb\ne')
        self.assertEqual(grep_C('a\nb\nc\nd\nz\nb\ne', 'b', 1), 'a\nb\nc\n---\nz\nb\ne')
        self.assertEqual(grep_C('a\nb\nc\nd\nz\nb\ne', 'b', 2), 'a\nb\nc\nd\nz\nb\ne')
        self.assertEqual(grep_C('a\nb\nc\nz\nb\nb\ne', 'b', 1), 'a\nb\nc\nz\nb\nb\ne')
        self.assertEqual(grep_C('b\nc\nz\nb\nb\ne', 'b', 1), 'b\nc\nz\nb\nb\ne')
        self.assertEqual(grep_C('b\n', 'b', 1), 'b')

    def test_tail_lines(self):
        self.assertEqual(tail_lines('', 0), '')
        self.assertEqual(tail_lines('', 1), '')
        self.assertEqual(tail_lines('', 2), '')
        self.assertEqual(tail_lines('', 4), '')

        self.assertEqual(tail_lines('a\nb\n', 0), '')
        self.assertEqual(tail_lines('a\nb\n', 1), 'b')
        self.assertEqual(tail_lines('a\nb\n', 2), 'a\nb')

        self.assertEqual(tail_lines('a\nb\nc\n', 2), 'b\nc')
        self.assertEqual(tail_lines('a\nb\nc\n', 4), 'a\nb\nc')

        self.assertEqual(tail_lines('a\nb\nc\nd\n', 2), 'c\nd')

        self.assertEqual(tail_lines('\n\n\n', 2), '\n')
        self.assertEqual(tail_lines('\n\n\nbc', 2), '\nbc')
        self.assertEqual(tail_lines('\n\nbc', 3), '\n\nbc')
        self.assertEqual(tail_lines('\n\n\n\nbc', 3), '\n\nbc')

if __name__ == '__main__':
    unittest.main()
