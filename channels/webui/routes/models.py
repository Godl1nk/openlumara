"""Model selection and multi-provider management routes"""

import fastapi

import core

import channels.webui.utils as utils

def register(app, channel):
    @app.get("/api/models")
    async def models_get():
        """Returns available models plus current chat/image selection metadata"""
        result = await channel.manager.API.list_models()
        if isinstance(result, core.api.APIError):
            return utils.api_result(str(result), success=False)

        return utils.api_result({
            "models": result,
            "current": channel.manager.API.get_model(),
            "image_model": channel.manager.API.get_image_model(),
            "disabled_models": channel.manager.API.get_disabled_models(),
            "reasoning_effort": core.config.get("model", "reasoning_effort", default="none"),
            "custom_reasoning_effort": core.config.get("model", "custom_reasoning_effort", default="")
        })

    @app.post("/api/model/set")
    async def model_set(request: fastapi.Request):
        """Switches the active chat model"""
        data = await request.json()
        name = (data.get("name") or "").strip()
        if not name:
            return utils.api_result("Model name cannot be empty", success=False)

        if not channel.manager.API.set_model(name):
            return utils.api_result("An image model cannot be used as the default chat model", success=False)
        connected = await channel.manager.API.connect(silent=True)
        if isinstance(connected, core.api.APIError):
            return utils.api_result(str(connected), success=False)

        await channel.websocket_manager.push_context_update()
        return utils.api_result({
            "name": name,
            "max_context": channel.manager.API.get_max_context(name)
        }, success=True)

    @app.post("/api/model/image/set")
    async def model_image_set(request: fastapi.Request):
        """Sets the default image model"""
        data = await request.json()
        name = (data.get("name") or "").strip()
        if not name:
            return utils.api_result("Image model name cannot be empty", success=False)

        if not channel.manager.API.set_image_model(name):
            return utils.api_result("The default chat model cannot also be the default image model", success=False)
        return utils.api_result({"image_model": name}, success=True)

    @app.post("/api/model/effort/set")
    async def model_effort_set(request: fastapi.Request):
        """Sets legacy global reasoning effort defaults"""
        data = await request.json()
        channel.manager.API.set_reasoning_effort(effort=data.get("effort"), custom=data.get("custom"))
        return utils.api_result({
            "reasoning_effort": core.config.get("model", "reasoning_effort", default="none"),
            "custom_reasoning_effort": core.config.get("model", "custom_reasoning_effort", default="")
        }, success=True)

    @app.post("/api/model/toggle")
    async def model_toggle(request: fastapi.Request):
        """Enables or disables a model in the switcher"""
        data = await request.json()
        name = (data.get("name") or "").strip()
        if not name:
            return utils.api_result("Model name cannot be empty", success=False)

        disabled = bool(data.get("disabled", False))
        updated = channel.manager.API.set_model_disabled(name, disabled)
        return utils.api_result({
            "name": name,
            "disabled": disabled,
            "disabled_models": updated
        }, success=True)

    @app.get("/api/providers")
    async def providers_get():
        """Returns configured providers, models, and current selections"""
        return utils.api_result({
            "providers": channel.manager.API.get_providers(),
            "current_model": channel.manager.API.get_model(),
            "image_model": channel.manager.API.get_image_model()
        }, success=True)

    @app.post("/api/provider/test")
    async def provider_test(request: fastapi.Request):
        """Tests an endpoint connection and measures latency"""
        data = await request.json()
        res = await channel.manager.API.test_provider_connection(data.get("url", ""), data.get("key", ""))
        if isinstance(res.get("models"), list) and len(res["models"]) > 60:
            res["models"] = res["models"][:60]
        return utils.api_result(res, success=res.get("success", False))

    @app.post("/api/provider/add")
    async def provider_add(request: fastapi.Request):
        """Adds a provider and queries its models"""
        data = await request.json()
        if not data.get("url"):
            return utils.api_result("Base URL cannot be empty", success=False)

        provider = await channel.manager.API.add_provider(
            name=data.get("name", ""),
            url=data.get("url", ""),
            key=data.get("key", ""),
            type=data.get("type", "llm"),
            api_format=data.get("api_format", "auto"),
            is_image_provider=bool(data.get("is_image_provider", False)),
        )
        await channel.manager.API.connect(silent=True)
        return utils.api_result(provider, success=True)

    @app.post("/api/provider/update")
    async def provider_update(request: fastapi.Request):
        """Updates provider fields"""
        data = await request.json()
        pid = data.get("id")
        if not pid:
            return utils.api_result("Missing provider ID", success=False)
        provider = channel.manager.API.update_provider(pid, data.get("updates", {}))
        return utils.api_result(provider, success=bool(provider))

    @app.post("/api/provider/delete")
    async def provider_delete(request: fastapi.Request):
        """Deletes a provider"""
        data = await request.json()
        pid = data.get("id")
        if not pid:
            return utils.api_result("Missing provider ID", success=False)
        channel.manager.API.delete_provider(pid)
        return utils.api_result("Deleted", success=True)

    @app.post("/api/provider/refresh")
    async def provider_refresh(request: fastapi.Request):
        """Re-queries models for a provider"""
        data = await request.json()
        pid = data.get("id")
        if not pid:
            return utils.api_result("Missing provider ID", success=False)
        models = await channel.manager.API.refresh_provider_models(pid)
        if models is None:
            return utils.api_result("Could not fetch models from the provider. Check the URL and API key.", success=False)
        return utils.api_result(models, success=True)

    @app.post("/api/provider/model/update")
    async def provider_model_update(request: fastapi.Request):
        """Updates settings for a provider model"""
        data = await request.json()
        pid = data.get("provider_id")
        mid = data.get("model_id")
        settings = data.get("settings", {})
        if not pid or not mid:
            return utils.api_result("Missing provider_id or model_id", success=False)
        if settings.get("is_image") and mid == channel.manager.API.get_model():
            return utils.api_result("The default chat model cannot also be image-capable", success=False)
        if settings.get("is_image") is False and mid == channel.manager.API.get_image_model():
            return utils.api_result("The default image model must remain image-capable", success=False)

        model = channel.manager.API.update_model_settings(pid, mid, settings)
        return utils.api_result({
            "model": model,
            "max_context": channel.manager.API.get_max_context()
        }, success=bool(model))
