#!/usr/bin/env python3
#
# Copyright 2018 Red Hat, Inc.
#
# Authors:
#     Paolo Bonzini <pbonzini@redhat.com>
#
# This work is licensed under the MIT License.  Please see the LICENSE file or
# http://opensource.org/licenses/MIT.

from django import template
from patchew import logviewer

register = template.Library()

@register.simple_tag
@register.filter
def ansi2text(value):
    return ''.join(logviewer.ansi2text(value))
