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
