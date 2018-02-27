# Test conversion of ANSI sequences into HTML
#
# Copyright (C) 2018 Red Hat, Inc.
#
# Author: Paolo Bonzini <pbonzini@redhat.com>

import unittest

from patchew.logviewer import ansi2html, ansi2text, ANSI2TextConverter

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

    # basic style formatting and bold
    def test_basic_styles(self):
        self.assertBlackBg('\x1b[0m', '')
        self.assertWhiteBg('\x1b[0m', '')
        self.assertBlackBg('A\x1b[0mBC', 'ABC')
        self.assertWhiteBg('A\x1b[0mBC', 'ABC')
        self.assertBlackBg('\x1b[30;41m', '')
        self.assertWhiteBg('\x1b[30;41m', '')
        self.assertBlackBg('\x1b[1mABC', '<span class="HIW BOLD">ABC</span>')
        self.assertWhiteBg('\x1b[1mABC', '<span class="BOLD">ABC</span>')
        self.assertBlackBg('A\x1b[1mBC', 'A<span class="HIW BOLD">BC</span>')
        self.assertWhiteBg('A\x1b[1mBC', 'A<span class="BOLD">BC</span>')
        self.assertBlackBg('\x1b[1mAB\x1b[0mC', '<span class="HIW BOLD">AB</span>C')
        self.assertWhiteBg('\x1b[1mAB\x1b[0mC', '<span class="BOLD">AB</span>C')
        self.assertBlackBg('A\x1b[1mB\x1b[0mC', 'A<span class="HIW BOLD">B</span>C')
        self.assertWhiteBg('A\x1b[1mB\x1b[0mC', 'A<span class="BOLD">B</span>C')
        self.assertBlackBg('A\x1b[1mB\x1b[0m\x1b[1mC', 'A<span class="HIW BOLD">BC</span>')
        self.assertWhiteBg('A\x1b[1mB\x1b[0m\x1b[1mC', 'A<span class="BOLD">BC</span>')

    # basic dim and dim+bold tests
    def test_dim_bold(self):
        self.assertBlackBg('\x1b[2mABC', '<span class="HIK">ABC</span>')
        self.assertWhiteBg('\x1b[2mABC', '<span class="HIK">ABC</span>')
        self.assertBlackBg('\x1b[2;1mABC', '<span class="HIK BOLD">ABC</span>')
        self.assertWhiteBg('\x1b[2;1mABC', '<span class="HIK BOLD">ABC</span>')
        self.assertBlackBg('\x1b[1;21mABC', 'ABC')
        self.assertWhiteBg('\x1b[1;21mABC', 'ABC')
        self.assertBlackBg('\x1b[2;21mABC', 'ABC')
        self.assertWhiteBg('\x1b[2;21mABC', 'ABC')
        self.assertBlackBg('\x1b[1;22mABC', 'ABC')
        self.assertWhiteBg('\x1b[1;22mABC', 'ABC')
        self.assertBlackBg('\x1b[2;22mABC', 'ABC')
        self.assertWhiteBg('\x1b[2;22mABC', 'ABC')

    # background and foreground colors
    def test_colors(self):
        self.assertBlackBg('\x1b[31mABC', '<span class="HIR">ABC</span>')
        self.assertWhiteBg('\x1b[31mABC', '<span class="HIR">ABC</span>')
        self.assertBlackBg('\x1b[31;1mABC', '<span class="HIR BOLD">ABC</span>')
        self.assertWhiteBg('\x1b[31;1mABC', '<span class="HIR BOLD">ABC</span>')
        self.assertBlackBg('\x1b[31;2mABC', '<span class="RED">ABC</span>')
        self.assertWhiteBg('\x1b[31;2mABC', '<span class="RED">ABC</span>')
        self.assertBlackBg('\x1b[31;2;1mABC', '<span class="RED BOLD">ABC</span>')
        self.assertWhiteBg('\x1b[31;2;1mABC', '<span class="RED BOLD">ABC</span>')
        self.assertBlackBg('\x1b[31mAB\x1b[39mC', '<span class="HIR">AB</span>C')
        self.assertWhiteBg('\x1b[31mAB\x1b[39mC', '<span class="HIR">AB</span>C')
        self.assertBlackBg('\x1b[30mABC', '<span class="BLK">ABC</span>')
        self.assertWhiteBg('\x1b[30mABC', 'ABC')
        self.assertBlackBg('\x1b[30;1mABC', '<span class="BLK BOLD">ABC</span>')
        self.assertWhiteBg('\x1b[30;1mABC', '<span class="BOLD">ABC</span>')
        self.assertBlackBg('\x1b[30;2mABC', '<span class="BLK">ABC</span>')
        self.assertWhiteBg('\x1b[30;2mABC', '<span class="HIK">ABC</span>')
        self.assertBlackBg('\x1b[30;2;1mABC', '<span class="BLK BOLD">ABC</span>')
        self.assertWhiteBg('\x1b[30;2;1mABC', '<span class="HIK BOLD">ABC</span>')
        self.assertBlackBg('\x1b[37mABC', 'ABC')
        self.assertWhiteBg('\x1b[37mABC', '<span class="WHI">ABC</span>')
        self.assertBlackBg('\x1b[37;1mABC', '<span class="HIW BOLD">ABC</span>')
        self.assertWhiteBg('\x1b[37;1mABC', '<span class="HIW BOLD">ABC</span>')
        self.assertBlackBg('\x1b[37;2mABC', '<span class="HIK">ABC</span>')
        self.assertWhiteBg('\x1b[37;2mABC', '<span class="WHI">ABC</span>')
        self.assertBlackBg('\x1b[37;2;1mABC', '<span class="HIK BOLD">ABC</span>')
        self.assertWhiteBg('\x1b[37;2;1mABC', '<span class="WHI BOLD">ABC</span>')
        self.assertBlackBg('\x1b[46mABC', '<span class="BHIC">ABC</span>')
        self.assertWhiteBg('\x1b[46mABC', '<span class="BHIC">ABC</span>')
        self.assertBlackBg('\x1b[46mAB\x1b[49mC', '<span class="BHIC">AB</span>C')
        self.assertWhiteBg('\x1b[46mAB\x1b[49mC', '<span class="BHIC">AB</span>C')
        self.assertBlackBg('\x1b[46;31mABC', '<span class="HIR BHIC">ABC</span>')
        self.assertWhiteBg('\x1b[46;31mABC', '<span class="HIR BHIC">ABC</span>')
        self.assertBlackBg('\x1b[46;31;1mABC', '<span class="HIR BHIC BOLD">ABC</span>')
        self.assertWhiteBg('\x1b[46;31;1mABC', '<span class="HIR BHIC BOLD">ABC</span>')
        self.assertBlackBg('\x1b[46;31;2mABC', '<span class="RED BHIC">ABC</span>')
        self.assertWhiteBg('\x1b[46;31;2mABC', '<span class="RED BHIC">ABC</span>')
        self.assertBlackBg('\x1b[46;31;2;1mABC', '<span class="RED BHIC BOLD">ABC</span>')
        self.assertWhiteBg('\x1b[46;31;2;1mABC', '<span class="RED BHIC BOLD">ABC</span>')
        self.assertBlackBg('\x1b[46;37mABC', '<span class="BHIC">ABC</span>')
        self.assertWhiteBg('\x1b[46;37mABC', '<span class="WHI BHIC">ABC</span>')
        self.assertBlackBg('\x1b[46;37;1mABC', '<span class="HIW BHIC BOLD">ABC</span>')
        self.assertWhiteBg('\x1b[46;37;1mABC', '<span class="HIW BHIC BOLD">ABC</span>')
        self.assertBlackBg('\x1b[46;37;2mABC', '<span class="HIK BHIC">ABC</span>')
        self.assertWhiteBg('\x1b[46;37;2mABC', '<span class="WHI BHIC">ABC</span>')
        self.assertBlackBg('\x1b[46;37;2;1mABC', '<span class="HIK BHIC BOLD">ABC</span>')
        self.assertWhiteBg('\x1b[46;37;2;1mABC', '<span class="WHI BHIC BOLD">ABC</span>')

    # more colors
    def test_colors_extra(self):
        self.assertBlackBg('\x1b[90mABC', '<span class="HIK">ABC</span>')
        self.assertWhiteBg('\x1b[90mABC', '<span class="HIK">ABC</span>')
        self.assertBlackBg('\x1b[90;1mABC', '<span class="HIK BOLD">ABC</span>')
        self.assertWhiteBg('\x1b[90;1mABC', '<span class="HIK BOLD">ABC</span>')
        self.assertBlackBg('\x1b[90;2mABC', '<span class="HIK">ABC</span>')
        self.assertWhiteBg('\x1b[90;2mABC', '<span class="HIK">ABC</span>')
        self.assertBlackBg('\x1b[90;2;1mABC', '<span class="HIK BOLD">ABC</span>')
        self.assertWhiteBg('\x1b[90;2;1mABC', '<span class="HIK BOLD">ABC</span>')
        self.assertBlackBg('\x1b[97;1mABC', '<span class="HIW BOLD">ABC</span>')
        self.assertWhiteBg('\x1b[97;1mABC', '<span class="HIW BOLD">ABC</span>')
        self.assertBlackBg('\x1b[97;2mABC', 'ABC')
        self.assertWhiteBg('\x1b[97;2mABC', '<span class="WHI">ABC</span>')
        self.assertBlackBg('\x1b[97;2;1mABC', '<span class="BOLD">ABC</span>')
        self.assertWhiteBg('\x1b[97;2;1mABC', '<span class="WHI BOLD">ABC</span>')
        self.assertBlackBg('\x1b[100mABC', '<span class="BHIK">ABC</span>')
        self.assertWhiteBg('\x1b[100mABC', '<span class="BHIK">ABC</span>')
        self.assertBlackBg('\x1b[38;5;120mABC', '<span class="f120">ABC</span>')
        self.assertWhiteBg('\x1b[38;5;120mABC', '<span class="f120">ABC</span>')
        self.assertBlackBg('\x1b[38;5;120;2mABC', '<span class="df120">ABC</span>')
        self.assertWhiteBg('\x1b[38;5;120;2mABC', '<span class="df120">ABC</span>')
        self.assertBlackBg('\x1b[48;5;120mABC', '<span class="b120">ABC</span>')
        self.assertWhiteBg('\x1b[48;5;120mABC', '<span class="b120">ABC</span>')
        self.assertBlackBg('\x1b[48;5;120;2mABC', '<span class="HIK b120">ABC</span>')
        self.assertWhiteBg('\x1b[48;5;120;2mABC', '<span class="HIK b120">ABC</span>')

    # italic, underline, strikethrough
    def test_text_variants(self):
        self.assertBlackBg('\x1b[3mABC', '<span class="ITA">ABC</span>')
        self.assertWhiteBg('\x1b[3mABC', '<span class="ITA">ABC</span>')
        self.assertBlackBg('\x1b[3;31mABC', '<span class="HIR ITA">ABC</span>')
        self.assertWhiteBg('\x1b[3;31mABC', '<span class="HIR ITA">ABC</span>')
        self.assertBlackBg('\x1b[3mAB\x1b[23mC', '<span class="ITA">AB</span>C')
        self.assertWhiteBg('\x1b[3mAB\x1b[23mC', '<span class="ITA">AB</span>C')
        self.assertBlackBg('\x1b[3;31mAB\x1b[23mC', '<span class="HIR ITA">AB</span><span class="HIR">C</span>')
        self.assertWhiteBg('\x1b[3;31mAB\x1b[23mC', '<span class="HIR ITA">AB</span><span class="HIR">C</span>')
        self.assertBlackBg('\x1b[4mABC', '<span class="UND">ABC</span>')
        self.assertWhiteBg('\x1b[4mABC', '<span class="UND">ABC</span>')
        self.assertBlackBg('\x1b[4;31mABC', '<span class="HIR UND">ABC</span>')
        self.assertWhiteBg('\x1b[4;31mABC', '<span class="HIR UND">ABC</span>')
        self.assertBlackBg('\x1b[4mAB\x1b[24mC', '<span class="UND">AB</span>C')
        self.assertWhiteBg('\x1b[4mAB\x1b[24mC', '<span class="UND">AB</span>C')
        self.assertBlackBg('\x1b[4;31mAB\x1b[24mC', '<span class="HIR UND">AB</span><span class="HIR">C</span>')
        self.assertWhiteBg('\x1b[4;31mAB\x1b[24mC', '<span class="HIR UND">AB</span><span class="HIR">C</span>')
        self.assertBlackBg('\x1b[9mABC', '<span class="STR">ABC</span>')
        self.assertWhiteBg('\x1b[9mABC', '<span class="STR">ABC</span>')
        self.assertBlackBg('\x1b[9mAB\x1b[29mC', '<span class="STR">AB</span>C')
        self.assertWhiteBg('\x1b[9mAB\x1b[29mC', '<span class="STR">AB</span>C')
        self.assertBlackBg('\x1b[9;31mAB\x1b[29mC', '<span class="HIR STR">AB</span><span class="HIR">C</span>')
        self.assertWhiteBg('\x1b[9;31mAB\x1b[29mC', '<span class="HIR STR">AB</span><span class="HIR">C</span>')
        self.assertBlackBg('\x1b[9;31mABC', '<span class="HIR STR">ABC</span>')
        self.assertWhiteBg('\x1b[9;31mABC', '<span class="HIR STR">ABC</span>')
        self.assertBlackBg('\x1b[4;9mABC', '<span class="UNDSTR">ABC</span>')
        self.assertWhiteBg('\x1b[4;9mABC', '<span class="UNDSTR">ABC</span>')
        self.assertBlackBg('\x1b[4;9;31mABC', '<span class="HIR UNDSTR">ABC</span>')
        self.assertWhiteBg('\x1b[4;9;31mABC', '<span class="HIR UNDSTR">ABC</span>')
        self.assertBlackBg('\x1b[4;9mAB\x1b[24mC', '<span class="UNDSTR">AB</span><span class="STR">C</span>')
        self.assertWhiteBg('\x1b[4;9mAB\x1b[24mC', '<span class="UNDSTR">AB</span><span class="STR">C</span>')
        self.assertBlackBg('\x1b[4;9mAB\x1b[29mC', '<span class="UNDSTR">AB</span><span class="UND">C</span>')
        self.assertWhiteBg('\x1b[4;9mAB\x1b[29mC', '<span class="UNDSTR">AB</span><span class="UND">C</span>')

    # invert
    def test_invert(self):
        self.assertBlackBg('\x1b[7mABC', '<span class="BLK BWHI">ABC</span>')
        self.assertWhiteBg('\x1b[7mABC', '<span class="WHI BBLK">ABC</span>')
        self.assertBlackBg('\x1b[7mABC\r', '<span class="BLK BWHI">ABC</span>')
        self.assertWhiteBg('\x1b[7mABC\r', '<span class="WHI BBLK">ABC</span>')
        self.assertBlackBg('\x1b[30;7mABC', '<span class="BLK">ABC</span>')
        self.assertWhiteBg('\x1b[30;7mABC', '<span class="WHI BBLK">ABC</span>')
        self.assertBlackBg('\x1b[30;1;7mABC', '<span class="BLK BOLD">ABC</span>')
        self.assertWhiteBg('\x1b[30;1;7mABC', '<span class="HIW BBLK BOLD">ABC</span>')
        self.assertBlackBg('\x1b[37;7mABC', '<span class="BLK BWHI">ABC</span>')
        self.assertWhiteBg('\x1b[37;7mABC', '<span class="WHI">ABC</span>')
        self.assertBlackBg('\x1b[37;1;7mABC', '<span class="BLK BWHI BOLD">ABC</span>')
        self.assertWhiteBg('\x1b[37;1;7mABC', '<span class="HIW BOLD">ABC</span>')
        self.assertBlackBg('\x1b[46;7mABC', '<span class="HIC BWHI">ABC</span>')
        self.assertWhiteBg('\x1b[46;7mABC', '<span class="HIC BBLK">ABC</span>')
        self.assertBlackBg('\x1b[46;1;7mABC', '<span class="HIC BWHI BOLD">ABC</span>')
        self.assertWhiteBg('\x1b[46;1;7mABC', '<span class="HIC BBLK BOLD">ABC</span>')
        self.assertBlackBg('\x1b[46;31;7mABC', '<span class="HIC BHIR">ABC</span>')
        self.assertWhiteBg('\x1b[46;31;7mABC', '<span class="HIC BHIR">ABC</span>')
        self.assertBlackBg('\x1b[46;31;7mAB\x1b[27mC', '<span class="HIC BHIR">AB</span><span class="HIR BHIC">C</span>')
        self.assertWhiteBg('\x1b[46;31;7mAB\x1b[27mC', '<span class="HIC BHIR">AB</span><span class="HIR BHIC">C</span>')
        self.assertBlackBg('\x1b[36;47;1;7mABC', '<span class="HIW BHIC BOLD">ABC</span>')
        self.assertWhiteBg('\x1b[36;47;1;7mABC', '<span class="HIW BHIC BOLD">ABC</span>')
        self.assertBlackBg('\x1b[36;47;2;7mABC', '<span class="BCYN">ABC</span>')
        self.assertWhiteBg('\x1b[36;47;2;7mABC', '<span class="WHI BCYN">ABC</span>')
        self.assertBlackBg('\x1b[36;47;2;1;7mABC', '<span class="BCYN BOLD">ABC</span>')
        self.assertWhiteBg('\x1b[36;47;2;1;7mABC', '<span class="WHI BCYN BOLD">ABC</span>')
        self.assertBlackBg('\x1b[90;7mABC', '<span class="BLK BHIK">ABC</span>')
        self.assertWhiteBg('\x1b[90;7mABC', '<span class="WHI BHIK">ABC</span>')
        self.assertBlackBg('\x1b[90;1;7mABC', '<span class="BLK BHIK BOLD">ABC</span>')
        self.assertWhiteBg('\x1b[90;1;7mABC', '<span class="HIW BHIK BOLD">ABC</span>')
        self.assertBlackBg('\x1b[100;7mABC', '<span class="HIK BWHI">ABC</span>')
        self.assertWhiteBg('\x1b[100;7mABC', '<span class="HIK BBLK">ABC</span>')
        self.assertBlackBg('\x1b[100;1;7mABC', '<span class="HIK BWHI BOLD">ABC</span>')
        self.assertWhiteBg('\x1b[100;1;7mABC', '<span class="HIK BBLK BOLD">ABC</span>')
        self.assertBlackBg('\x1b[38;5;120;7mABC', '<span class="BLK b120">ABC</span>')
        self.assertWhiteBg('\x1b[38;5;120;7mABC', '<span class="WHI b120">ABC</span>')
        self.assertBlackBg('\x1b[38;5;120;2;7mABC', '<span class="BLK db120">ABC</span>')
        self.assertWhiteBg('\x1b[38;5;120;2;7mABC', '<span class="WHI db120">ABC</span>')
        self.assertBlackBg('\x1b[48;5;120;7mABC', '<span class="f120 BWHI">ABC</span>')
        self.assertWhiteBg('\x1b[48;5;120;7mABC', '<span class="f120 BBLK">ABC</span>')
        self.assertBlackBg('\x1b[48;5;120;2;7mABC', '<span class="f120 BHIK">ABC</span>')
        self.assertWhiteBg('\x1b[48;5;120;2;7mABC', '<span class="f120 BHIK">ABC</span>')
        # vte uses BHIK here??
        self.assertBlackBg('\x1b[47;30;1;7mABC', '<span class="HIW BOLD">ABC</span>')
        self.assertWhiteBg('\x1b[47;30;1;7mABC', '<span class="HIW BBLK BOLD">ABC</span>')

    # combining cursor movement and formatting
    def test_movement_and_formatting(self):
        self.assertBlackBg('\x1b[42m\tabc', '        <span class="BHIG">abc</span>')
        self.assertWhiteBg('\x1b[42m\tabc', '        <span class="BHIG">abc</span>')
        self.assertBlackBg('abc\x1b[42m\x1b[1Kabc', '   <span class="BHIG">abc</span>')
        self.assertWhiteBg('abc\x1b[42m\x1b[1Kabc', '   <span class="BHIG">abc</span>')
        self.assertBlackBg('\x1b[7m\tabc', '        <span class="BLK BWHI">abc</span>')
        self.assertWhiteBg('\x1b[7m\tabc', '        <span class="WHI BBLK">abc</span>')
        self.assertBlackBg('abc\x1b[7m\x1b[1Kabc', '   <span class="BLK BWHI">abc</span>')
        self.assertWhiteBg('abc\x1b[7m\x1b[1Kabc', '   <span class="WHI BBLK">abc</span>')


class ANSI2TextTest(unittest.TestCase):
    def assertAnsi(self, test, expected, **kwargs):
        self.assertEqual(''.join(ansi2text(test, **kwargs)), expected,
                         repr(test))

    # basic formatting tests
    def test_basic(self):
        self.assertAnsi('\tb', '        b')
        self.assertAnsi('\t\ta', '                a')
        self.assertAnsi('a\tb', 'a       b')
        self.assertAnsi('ab\tc', 'ab      c')
        self.assertAnsi('a\nbc', 'a\nbc')
        self.assertAnsi('a\f', 'a\n' + ANSI2TextConverter.FF)
        self.assertAnsi('a\n\f', 'a\n\n' + ANSI2TextConverter.FF)
        self.assertAnsi('<', '<')
        self.assertAnsi('\x07', '\U00001F514')

    # backspace and carriage return
    def test_set_pos(self):
        self.assertAnsi('abc\b\bBC', 'aBC')
        self.assertAnsi('a\b<', '<')
        self.assertAnsi('<\ba', 'a')
        self.assertAnsi('a\b\bbc', 'bc')
        self.assertAnsi('a\rbc', 'bc')
        self.assertAnsi('a\nb\bc', 'a\nc')
        self.assertAnsi('a\t\bb', 'a      b')
        self.assertAnsi('a\tb\b\bc', 'a      cb')
        self.assertAnsi('01234567\r\tb', '01234567b')

    # Escape sequences
    def test_esc_parsing(self):
        self.assertAnsi('{\x1b%}', '{}')
        self.assertAnsi('{\x1b[0m}', '{}')
        self.assertAnsi('{\x1b[m}', '{}')
        self.assertAnsi('{\x1b[0;1;7;0m}', '{}')
        self.assertAnsi('{\x1b[1;7m\x1b[m}', '{}')
        self.assertAnsi('{\x1b]test\x1b\\}', '{}')
        self.assertAnsi('{\x1b]test\x07}', '{}')
        self.assertAnsi('{\x1b]test\x1b[0m\x07}', '{}')
        self.assertAnsi('{\x1b]test\x1b[7m\x07}', '{}')

    # ESC [C and ESC [D
    def test_horiz_movement(self):
        self.assertAnsi('abc\x1b[2DB', 'aBc')
        self.assertAnsi('abc\x1b[3CD', 'abc   D')
        self.assertAnsi('abcd\x1b[3DB\x1b[1CD', 'aBcD')
        self.assertAnsi('abc\x1b[0CD', 'abc D')
        self.assertAnsi('abc\x1b[CD', 'abc D')

    # ESC [K
    def test_clear_line(self):
        self.assertAnsi('\x1b[Kabcd', 'abcd')
        self.assertAnsi('abcd\r\x1b[K', '')
        self.assertAnsi('abcd\b\x1b[K', 'abc')
        self.assertAnsi('abcd\r\x1b[KDef', 'Def')
        self.assertAnsi('abcd\b\x1b[KDef', 'abcDef')
        self.assertAnsi('abcd\r\x1b[0K', '')
        self.assertAnsi('abcd\b\x1b[0K', 'abc')
        self.assertAnsi('abcd\r\x1b[1K', 'abcd')
        self.assertAnsi('abcd\b\x1b[1K', '   d')
        self.assertAnsi('abcd\r\x1b[2K', '')
        self.assertAnsi('abcd\b\x1b[2K', '   ')
        self.assertAnsi('abcd\r\x1b[2KDef', 'Def')
        self.assertAnsi('abcd\b\x1b[2KDef', '   Def')

    # combining cursor movement and formatting
    def test_movement_and_formatting(self):
        self.assertAnsi('\x1b[42m\tabc', '        abc')
        self.assertAnsi('abc\x1b[42m\x1b[1Kabc', '   abc')
        self.assertAnsi('\x1b[7m\tabc', '        abc')
        self.assertAnsi('abc\x1b[7m\x1b[1Kabc', '   abc')


if __name__ == '__main__':
    unittest.main()
