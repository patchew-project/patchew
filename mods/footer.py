from mod import PatchewModule

_default_config = """
<!-- your HTML here -->

"""

class FooterModule(PatchewModule):
    name = "footer"
    default_config = _default_config

    def render_page_hook(self, context_data):
        context_data.setdefault("footer", "")
        context_data["footer"] += self.get_config_raw()
