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
        self.assertBlackBg('\tb', '        b')
        self.assertBlackBg('\t\ta', '                a')
        self.assertBlackBg('a\tb', 'a       b')
        self.assertBlackBg('ab\tc', 'ab      c')
        self.assertBlackBg('a\nbc', 'a\nbc')
        self.assertBlackBg('a\f', 'a\n<hr>')
        self.assertBlackBg('a\n\f', 'a\n\n<hr>')
        self.assertBlackBg('<', '&lt;')
        self.assertBlackBg('\x07', '&#x1F514;')

    # backspace and carriage return
    def test_set_pos(self):
        self.assertBlackBg('abc\b\bBC', 'aBC')
        self.assertBlackBg('a\b<', '&lt;')
        self.assertBlackBg('<\ba', 'a')
        self.assertBlackBg('a\b\bbc', 'bc')
        self.assertBlackBg('a\rbc', 'bc')
        self.assertBlackBg('a\nb\bc', 'a\nc')
        self.assertBlackBg('a\t\bb', 'a      b')
        self.assertBlackBg('a\tb\b\bc', 'a      cb')
        self.assertBlackBg('01234567\r\tb', '01234567b')

    # Escape sequences
    def test_esc_parsing(self):
        self.assertBlackBg('{\x1b%}', '{}')
        self.assertBlackBg('{\x1b[0m}', '{}')
        self.assertBlackBg('{\x1b[m}', '{}')
        self.assertBlackBg('{\x1b[0;1;7;0m}', '{}')
        self.assertBlackBg('{\x1b[1;7m\x1b[m}', '{}')
        self.assertBlackBg('{\x1b]test\x1b\\}', '{}')
        self.assertBlackBg('{\x1b]test\x07}', '{}')
        self.assertBlackBg('{\x1b]test\x1b[0m\x07}', '{}')
        self.assertBlackBg('{\x1b]test\x1b[7m\x07}', '{}')

    # ESC [2J
    def test_clear_screen(self):
        self.assertBlackBg('a\n\x1b[2Jb', 'a\n<hr>b')
        self.assertBlackBg('a\x1b[2J', 'a<hr> ')
        self.assertBlackBg('a\x1b[2Jb', 'a<hr> b')

    # ESC [C and ESC [D
    def test_horiz_movement(self):
        self.assertBlackBg('abc\x1b[2DB', 'aBc')
        self.assertBlackBg('abc\x1b[3CD', 'abc   D')
        self.assertBlackBg('abcd\x1b[3DB\x1b[1CD', 'aBcD')
        self.assertBlackBg('abc\x1b[0CD', 'abc D')
        self.assertBlackBg('abc\x1b[CD', 'abc D')

    # ESC [K
    def test_clear_line(self):
        self.assertBlackBg('\x1b[Kabcd', 'abcd')
        self.assertBlackBg('abcd\r\x1b[K', '')
        self.assertBlackBg('abcd\b\x1b[K', 'abc')
        self.assertBlackBg('abcd\r\x1b[KDef', 'Def')
        self.assertBlackBg('abcd\b\x1b[KDef', 'abcDef')
        self.assertBlackBg('abcd\r\x1b[0K', '')
        self.assertBlackBg('abcd\b\x1b[0K', 'abc')
        self.assertBlackBg('abcd\r\x1b[1K', 'abcd')
        self.assertBlackBg('abcd\b\x1b[1K', '   d')
        self.assertBlackBg('abcd\r\x1b[2K', '')
        self.assertBlackBg('abcd\b\x1b[2K', '   ')
        self.assertBlackBg('abcd\r\x1b[2KDef', 'Def')
        self.assertBlackBg('abcd\b\x1b[2KDef', '   Def')


if __name__ == '__main__':
    unittest.main()
