import core

class Tutorial(core.module.Module):
    """
    Guides you through openlumara if you're new!

    -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
    the getting-started instructions used to be injected into the system
    prompt on every conversation. they now live on the webui's welcome page
    instead (see webui/templates/chat/welcome.html), which costs zero tokens.
    disabling this module removes the welcome panel as well.
    """

    category = "core"

    async def on_ready(self):
        pass
