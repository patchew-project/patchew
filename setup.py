#!/usr/bin/env python2
#
# The MIT License (MIT)
#
# Copyright (c) 2014 Fam Zheng <fam@euphon.net>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of
# this software and associated documentation files (the "Software"), to deal in
# the Software without restriction, including without limitation the rights to
# use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
# the Software, and to permit persons to whom the Software is furnished to do so,
# subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
# FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
# COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
# IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

from glob import glob
from distutils.core import setup

setup(name='patchew',
      version='1.0',
      description="Patchew is a system to track and test patch series on mailing lists",
      author="Fam Zheng",
      author_email="fam@euphon.net",
      url="https://github.com/famz/patchew",
      packages=['libpatchew'],
      scripts=['patchew'] + glob('hook-scripts/*'),
      data_files=[('/usr/lib/systemd/system/', ['patchew.service']),
                  ('/etc/patchew', ['server.conf']),
                  ('/usr/share/patchew/static', glob('static/*')),
                  ('/usr/share/patchew/templates', glob('templates/*'))],
      )
