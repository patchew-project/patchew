#!/usr/bin/env python3
#
# Copyright 2016 Red Hat, Inc.
#
# Authors:
#     Fam Zheng <famz@redhat.com>
#
# This work is licensed under the MIT License.  Please see the LICENSE file or
# http://opensource.org/licenses/MIT.

from mod import PatchewModule

_default_config = """
<!-- your HTML here -->

"""

class FooterModule(PatchewModule):
    """

Documentation
-------------

This is a simple module to inject any HTML code into the page bottom. Can be
useful to add statistic code, etc..

The config is the raw HTML code to inject.

"""
    name = "footer"
    default_config = _default_config

    def render_page_hook(self, context_data):
        context_data.setdefault("footer", "")
        context_data["footer"] += self.get_config_raw()
