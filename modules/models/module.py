import core

class Models(core.module.Module):
    """Lets you or the AI switch between AI models"""

    category = "core"

    settings = {
        "insert_current_model_into_system_prompt": {
            "description" :"Whether to make the AI aware of what model it's currently running on. Can help it stay grounded!",
            "default": True
        },
        "insert_available_models_into_system_prompt": {
            "description": "Whether to make the AI aware of what models are available for it to switch to. Allows you to simply ask the AI to switch to whatever model you want (example: `switch to Qwen3.5-9B`) and it'll just do it ",
            "default": False
        }
    }

    async def on_ready(self):
        self._models_cache = None

        if self.config.get("insert_available_models_into_system_prompt"):
            self.disabled_tools.append("get_available")

    async def on_system_prompt(self):
        output = ""

        if self.config.get("insert_current_model_into_system_prompt"):
            current_model = self.manager.API.get_model()
            output += f"Current model: {current_model}"

        current_model = self.manager.API.get_model()
        
        if self.config.get("insert_available_models_into_system_prompt"):
            if not self._models_cache:
                models = await self.manager.API.list_models()
                if not models or isinstance(models, core.api.APIError):
                    return output if output else None
                self._models_cache = models

            if len(self._models_cache) > 1:
                output += f"\n\nModels you can switch to using the models_switch() toolcall: "
                output += ", ".join(self._models_cache)
        else:
            self.header = "current model"
            output = current_model

        return output

    async def _load_models(self):
        if not self._models_cache:
            models = await self.manager.API.list_models()
            if not models or isinstance(models, core.api.APIError):
                return None
            self._models_cache = models

    async def get_available(self):
        """Returns a list of AI/LLM models available to switch to, along with current model, image model, and reasoning efforts."""
        await self._load_models()

        current_model = self.manager.API.get_model()
        image_model = self.manager.API.get_image_model()
        disabled_models = self.manager.API.get_disabled_models()
        reasoning_effort = core.config.get("model", "reasoning_effort", default="none")
        custom_effort = core.config.get("model", "custom_reasoning_effort", default="")

        return self.result({
            "models": list(self._models_cache or []),
            "current": current_model,
            "image_model": image_model,
            "disabled_models": disabled_models,
            "reasoning_effort": reasoning_effort,
            "custom_reasoning_effort": custom_effort
        })

    async def switch(self, name: str):
        """Switches the active chat model."""
        await self._load_models()
        if not self._models_cache:
            return self.result("No models available or API connection error.", success=False)

        found_id = None
        for model_id in self._models_cache:
            if model_id.strip().lower() == name.strip().lower():
                found_id = model_id
                break

        if not found_id:
            return self.result(f"Model '{name}' does not exist on the server. Use models() to see available models.", success=False)

        disabled_models = self.manager.API.get_disabled_models()
        if found_id in disabled_models:
            return self.result(f"Model '{found_id}' is currently disabled. Enable it first with `/model enable {found_id}`.", success=False)

        if not self.manager.API.set_model(found_id):
            return self.result("An image model cannot be used as the active chat model.", success=False)
        return self.result(f"Model has been switched to {found_id}", success=True)

    async def set_image_model(self, name: str):
        """Sets the designated model to be used for image generation and editing."""
        name_clean = str(name).strip()
        if not name_clean:
            return self.result("Image model name cannot be empty.", success=False)

        if not self.manager.API.set_image_model(name_clean):
            return self.result("The active chat model cannot also be the default image model.", success=False)
        return self.result(f"Image model has been set to '{name_clean}'.", success=True)

    async def set_reasoning_effort(self, effort: str, custom: bool = False):
        """
        Sets the model's reasoning effort level (preset or custom).

        Args:
            effort: Effort value (e.g. 'none', 'low', 'medium', 'high', or custom string/number).
            custom: If True, sets this as a custom reasoning effort overriding presets.
        """
        eff = str(effort).strip()
        if custom:
            self.manager.API.set_reasoning_effort(effort=None, custom=eff)
            return self.result(f"Custom reasoning effort set to '{eff}'.", success=True)
        else:
            self.manager.API.set_reasoning_effort(effort=eff, custom="")
            return self.result(f"Reasoning effort set to '{eff}'.", success=True)

    async def toggle_model(self, name: str, enable: bool = True):
        """
        Enables or disables an AI model in the switcher.

        Args:
            name: Model identifier.
            enable: True to enable, False to disable.
        """
        name_clean = str(name).strip()
        if not name_clean:
            return self.result("Model name cannot be empty.", success=False)

        updated = self.manager.API.set_model_disabled(name_clean, not enable)
        status = "enabled" if enable else "disabled"
        return self.result(f"Model '{name_clean}' has been {status}.", success=True)

    @core.module.command("model", help={
        "": "Shows current active model, image model, and reasoning effort",
        "<name>": "Switches the active chat model to <name>",
        "image <name>": "Sets the designated image model to <name>",
        "effort <level>": "Sets reasoning effort (e.g. low, medium, high, max, or custom value)",
        "enable <name>": "Enables a model in the model switcher",
        "disable <name>": "Disables a model in the model switcher"
    })
    async def model(self, args: list):
        """Model configuration and switching command."""
        if not args:
            curr = self.manager.API.get_model() or "None"
            img = self.manager.API.get_image_model() or "None"
            preset_effort = core.config.get("model", "reasoning_effort", default="none")
            custom_effort = core.config.get("model", "custom_reasoning_effort", default="")
            eff_display = f"Custom ({custom_effort})" if custom_effort else preset_effort
            return f"**Active Chat Model**: `{curr}`\n**Image Model**: `{img}`\n**Reasoning Effort**: `{eff_display}`"

        sub = args[0].lower()
        if sub == "image" and len(args) > 1:
            img_target = " ".join(args[1:]).strip()
            if not self.manager.API.set_image_model(img_target):
                return "The active chat model cannot also be the default image model."
            return f"Image model set to `{img_target}`"
        elif sub == "effort" and len(args) > 1:
            eff_val = " ".join(args[1:]).strip()
            presets = ("none", "low", "medium", "high", "xhigh", "max")
            if eff_val.lower() in presets:
                self.manager.API.set_reasoning_effort(effort=eff_val.lower(), custom="")
                return f"Reasoning effort preset set to `{eff_val}`"
            else:
                self.manager.API.set_reasoning_effort(effort="none", custom=eff_val)
                return f"Custom reasoning effort set to `{eff_val}`"
        elif sub == "enable" and len(args) > 1:
            target = " ".join(args[1:]).strip()
            self.manager.API.set_model_disabled(target, False)
            return f"Model `{target}` is now enabled."
        elif sub == "disable" and len(args) > 1:
            target = " ".join(args[1:]).strip()
            self.manager.API.set_model_disabled(target, True)
            return f"Model `{target}` is now disabled."

        target_name = " ".join(args).strip()
        res = await self.switch(target_name)
        return res.get("content") if isinstance(res, dict) else str(res)

    @core.module.command("models", help={
        "": "Lists all available models with their current status"
    })
    async def models(self, args: list):
        """Lists available models."""
        await self._load_models()
        if not self._models_cache:
            return "No models available or API connection error."

        curr = self.manager.API.get_model()
        img = self.manager.API.get_image_model()
        disabled = set(self.manager.API.get_disabled_models())

        lines = ["**Available Models**:"]
        for m in self._models_cache:
            tags = []
            if m == curr:
                tags.append("ACTIVE CHAT")
            if m == img:
                tags.append("IMAGE")
            if m in disabled:
                tags.append("DISABLED")

            tag_str = f" *[{', '.join(tags)}]*" if tags else ""
            lines.append(f"- `{m}`{tag_str}")

        lines.append("\n*Commands: `/model <name>`, `/model image <name>`, `/model effort <level>`, `/model disable <name>`*")
        return "\n".join(lines)
