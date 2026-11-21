"""API routes that affect settings/config"""

import copy

import fastapi

import core

import channels.webui.utils as utils
import channels.webui.settings_structure as settings_structure

# -- AI GENERATED CODE (GPT-6) :: 2026-11-21 21:11:03 +08:00 harness:Codex
IMAGE_CARD_FIELDS = ("enabled", "ask_before_generate", "endpoint", "quality")

def register(app, channel):
    # --- Settings
    # -- GET
    @app.get("/api/settings/load")
    async def settings_load():
        """Returns the complete, render-ready settings structure (categories, field types, schemas and current values merged)"""
        module_info, core_sections = settings_structure.get_module_info()
        # the Your Skills tab only makes sense while the skills module is loaded
        skills_enabled = "skills" in channel.manager.modules
        structure = settings_structure.build_settings_structure(core.config.config, module_info, core_sections, skills_enabled=skills_enabled)
        image_module = channel.manager.modules.get("image_tools")
        if image_module and channel._ui_extension_enabled(image_module):
            fields = structure.get("modules", {}).get("settings", {}).get("image_tools", {}).get("value", {})
            for key in IMAGE_CARD_FIELDS:
                fields.pop(key, None)

        return utils.api_result({
            "categories": structure,
            "show_unsafe_settings": bool(channel.config.get("show_unsafe_settings"))
        })

    @app.get("/api/check_connection")
    async def check_connection():
        """returns True if the backend is connected to the AI API, else False"""
        if channel.manager.API.connected:
            return utils.api_result(True, success=True)
        else:
            return utils.api_result("not connected", success=False)

    @app.post("/api/settings/field")
    async def settings_field_set(request: fastapi.Request):
        """Sets a single core config field by key path, e.g. {"path": ["model", "enable_thinking"], "value": false}.
        The path is validated against the core settings schema, so only real, known fields can be written."""
        data = await request.json()
        keys = data.get("path")
        value = data.get("value")

        if not isinstance(keys, list) or not keys or not all(isinstance(k, str) and k for k in keys):
            return utils.api_result("path must be a non-empty list of strings", success=False)

        node = core.config.core_settings_schema
        for key in keys:
            if not isinstance(node, dict) or key not in node:
                return utils.api_result(f"unknown setting: {'.'.join(keys)}", success=False)
            node = node[key]

        if not isinstance(node, dict) or "default" not in node:
            return utils.api_result(f"{'.'.join(keys)} is not a setting field", success=False)

        if node.get("unsafe") and not core.config.get("channels", "settings", "webui", "show_unsafe_settings", default=False):
            return utils.api_result(f"{'.'.join(keys)} is unsafe and unsafe settings are hidden", success=False)

        default = node["default"]
        if isinstance(default, bool) != isinstance(value, bool) or isinstance(default, (int, float)) and not isinstance(default, bool) and not isinstance(value, (int, float)):
            return utils.api_result(f"value type does not match {'.'.join(keys)}", success=False)

        core.config.ConfigManager(core.config.config, base_path=keys[:-1]).set(keys[-1], value)
        return utils.api_result({"path": keys, "value": value}, success=True)

    # -- POST
    @app.post("/api/settings/save")
    async def settings_save(request: fastapi.Request):
        """Saves the (possibly edited) settings structure back to the backend. Accepts exactly what /api/settings/load returned, flattens it server-side and writes it to the config. Returns requires_restart/requires_reconnect if needed"""
        data = await request.json()

        changed_modules = list(data.get("changed_modules", []))

        # the frontend sends the category tree it got from settings/load,
        # with edited values, rebuild the raw config dict from it
        flattened = settings_structure.flatten_categories(data.get("categories", {}))
        new_webui = ((flattened.get("channels") or {}).get("settings") or {}).get("webui") or {}

        if new_webui.get("require_login"):
            blank = [f for f in ("username", "password") if not (new_webui.get(f) or "").strip()]
            if blank:
                if len(blank) == 2:
                    detail = "both username and password are still blank. Please fill in both fields"
                else:
                    detail = f"{blank[0]} is still blank. Please fill it in"
                return utils.api_result(
                    f"Logins are enabled but {detail}, or turn logins off.",
                    success=False,
                )

        new_mode = new_webui.get("network_mode", "local")
        if new_mode in ("internet", "custom"):
            login_ok = (
                bool(new_webui.get("require_login"))
                and bool((new_webui.get("username") or "").strip())
                and bool(new_webui.get("password"))
            )
            if not login_ok:
                return utils.api_result(
                    f"network mode '{new_mode}' exposes the WebUI beyond this machine, so a login is required. "
                    "Please enable 'Require login' and fill in a username and password, or switch the network mode back to local.",
                    success=False,
                )

        # provider/model controls save immediately. keep their live values
        # instead of writing back an older settings-modal snapshot.
        live_api = core.config.config.get("api") or {}
        flat_api = flattened.get("api")
        if isinstance(flat_api, dict):
            for live_key in ("url", "key", "providers", "max_context"):
                if live_key in live_api:
                    flat_api[live_key] = copy.deepcopy(live_api[live_key])

        live_model = core.config.config.get("model") or {}
        flat_model = flattened.get("model")
        if isinstance(flat_model, dict):
            for live_key in ("name", "provider_id", "image_model", "image_provider_id", "image_edit_model", "disabled_models"):
                if live_key in live_model:
                    flat_model[live_key] = copy.deepcopy(live_model[live_key])

        live_image = core.config.get("modules", "settings", "image_tools", {}) or {}
        flat_image = (flattened.get("modules", {}).get("settings", {}) or {}).get("image_tools")
        if isinstance(flat_image, dict):
            changed = data.get("changed_image_fields", [])
            for live_key in (*IMAGE_CARD_FIELDS, "model"):
                if live_key in live_image and (live_key not in changed or live_key not in flat_image):
                    flat_image[live_key] = copy.deepcopy(live_image[live_key])
            if "model" in changed and flat_image.get("model") and isinstance(flat_model, dict):
                selection = channel.manager.API.resolve_model_selection(flat_image["model"], image=True)
                if not selection:
                    return utils.api_result("Choose an enabled image model. Use /models for provider-qualified names.", success=False)
                name, provider = selection
                flat_image["model"] = flat_model["image_model"] = name
                flat_model["image_provider_id"] = provider["id"] if provider else ""

        # snapshot the pre-save config so we can tell the frontend whether
        # the changes need a server restart or an API reconnect
        old_config = copy.deepcopy(dict(core.config.config))

        result = core.config.config.load(data=flattened)
        core.config.config.save()

        if not result:
            return utils.api_result(success=False)

        # require a restart if any modules/channels were toggled
        requires_restart = any(
            {k: (old_config.get(key) or {}).get(k) for k in ("enabled", "disabled")} !=
            {k: (flattened.get(key) or {}).get(k) for k in ("enabled", "disabled")}
            for key in settings_structure.MODULE_CATEGORY_KEYS
        )
        # and a reconnect if the API settings got changed
        requires_reconnect = (not requires_restart) and (
            old_config.get("api") != flattened.get("api")
        )

        # reload modules that had their settings changed
        if changed_modules:
            for module_name in changed_modules:
                try:
                    await channel.manager.reload_module(module_name)
                except Exception as e:
                    channel.log(channel.name, f"Error reloading module {module_name}: {core.detail_error(e)}")

        # reload all webui extensions
        channel.setup_ui_extensions()

        # if the webui's own settings changed, tell every connected client to refresh the page
        old_webui = ((old_config.get("channels") or {}).get("settings") or {}).get("webui") or {}
        if old_webui != new_webui:
            await channel.websocket_manager.broadcast({"type": "refresh_page"})

        await channel.websocket_manager.push_context_update()

        return utils.api_result({
            "requires_restart": requires_restart,
            "requires_reconnect": requires_reconnect,
        }, success=True)
    
    @app.post("/api/reconnect")
    async def reconnect():
        """Disconnects and then reconnects the API."""
        try:
            await channel.manager.API.reconnect()
        except core.api.APIError as e:
            return utils.api_result(str(e), success=False)

        await channel.websocket_manager.push_context_update()

        return utils.api_result(success=True)
