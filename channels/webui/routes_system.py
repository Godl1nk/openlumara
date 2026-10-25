"""
System API routes: misc data, context size, logs and restart.
"""

import core

import channels.webui.utils as utils

def register(app, channel):
    # ----------------------------
    # System.. stuff
    # ----------------------------
    # -- GET
    @app.get("/api/system/data")
    async def get_data():
        """returns any relevant data for the webUI to use"""
        data = {
            "max_context": core.config.get("api", "max_context")
        }

        return utils.api_result(data)

    @app.get("/api/system/context_size")
    async def get_context_size():
        """returns a detailed breakdown of the current context window usage"""
        try:
            size = await channel.context.get_size()
        except Exception as e:
            return utils.api_result(core.detail_error(e), success=False)

        threshold = core.config.get("model", "context_compression_threshold") or 0
        size["compression_threshold"] = round(float(threshold) * 100, 1)
        size["auto_compress"] = bool(core.config.get("model", "automatically_compress_context"))

        return utils.api_result(size)

    @app.get("/api/system/logs")
    async def get_logs():
        return utils.api_result(channel.logs)

    # -- POST
    @app.post("/api/system/restart")
    async def restart_server():
        await channel.manager.restart()
