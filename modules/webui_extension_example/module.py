import core

class WebuiExtensionExample(core.module.Module):
    """
    Example module for the webui extension system. Read its source code (or have your AI read it) to learn how to make webui extensions. This example module renders a bright canary widget in
    every extension slot, so you can see where you can insert content, and to verify that it all works."""

    category = "development"

    async def on_ready(self):
        pass
