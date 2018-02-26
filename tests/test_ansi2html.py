# Test conversion of ANSI sequences into HTML
#
# Copyright (C) 2018 Red Hat, Inc.
#
# Author: Paolo Bonzini <pbonzini@redhat.com>

import unittest

from patchew.logviewer import ansi2html

class ANSI2HTMLTest(unittest.TestCase):
    def assertAnsi(self, test, expected, **kwargs):
        self.assertEqual(''.join(ansi2html(test, **kwargs)),
                         '<pre class="ansi">%s</pre>' % expected,
                         repr(test))

    def assertBlackBg(self, test, expected):
        self.assertAnsi(test, expected)

    def assertWhiteBg(self, test, expected):
        self.assertAnsi(test, expected, white_bg=True)

    # basic formatting tests
    def test_basic(self):
        self.assertBlackBg('a\nbc', 'a\nbc')
        self.assertBlackBg('<', '&lt;')


if __name__ == '__main__':
    unittest.main()
