# -- AI GENERATED CODE (GPT-6) :: 2026-11-21 16:39:24 +08:00 harness:Codex
import core
from collections import Counter

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
        },
        "allow_ai_to_switch": {
            "description": "Whether to allow the AI to switch its model",
            "default": True
        }
    }

    async def on_ready(self):
        self.disabled_tools[:] = [name for name in self.disabled_tools if name not in ("get_available", "switch")]

        if self.config.get("insert_available_models_into_system_prompt") or not self.config.get("allow_ai_to_switch"):
            self.disabled_tools.append("get_available")

        if not self.config.get("allow_ai_to_switch"):
            self.disabled_tools.append("switch")

    async def on_system_prompt(self):
        output = ""

        if self.config.get("insert_current_model_into_system_prompt"):
            current_model = self.manager.API.get_model()
            output += f"Current model: {current_model}"

        if self.config.get("insert_available_models_into_system_prompt"):
            choices = await self._load_models()
            available = [item["selector"] for item in choices if item["enabled"] and not item["is_image"]]
            if len(available) > 1:
                output += "\n\nModels you can switch to using the models_switch() toolcall: "
                output += ", ".join(available)

        return output or None

    async def _load_models(self):
        try:
            choices = await self.manager.API.model_choices(cached=True)
        except core.api.APIError:
            return []
        counts = Counter(item["id"].casefold() for item in choices)
        for item in choices:
            name = item["id"]
            item["selector"] = f"{item['provider_id']}::{name}" if counts[name.casefold()] > 1 else name
        return choices

    @core.module.tool
    async def get_available(self):
        """Returns a list of AI/LLM models available to switch to, along with current model, image model, and reasoning efforts."""
        choices = await self._load_models()

        current_model = self.manager.API.get_model()
        image_model = self.manager.API.get_image_model()
        disabled_models = self.manager.API.get_disabled_models()
        reasoning_effort = core.config.get("model", "reasoning_effort", default="none")
        custom_effort = core.config.get("model", "custom_reasoning_effort", default="")

        return self.result({
            "models": [item["selector"] for item in choices if item["enabled"] and not item["is_image"]],
            "current": current_model,
            "image_model": image_model,
            "disabled_models": disabled_models,
            "reasoning_effort": reasoning_effort,
            "custom_reasoning_effort": custom_effort
        })

    @core.module.tool
    async def switch(self, name: str):
        """Switches the active chat model."""
        choices = await self._load_models()
        if not choices:
            return self.result("No models available or API connection error.", success=False)

        target = name.strip().casefold()
        matches = [item for item in choices if item["enabled"] and not item["is_image"]
                   and target in (item["id"].casefold(), item["selector"].casefold())]
        if len(matches) > 1:
            return self.result("Choose a provider: " + ", ".join(item["selector"] for item in matches), success=False)
        if not matches or not self.manager.API.set_model(matches[0]["id"], matches[0]["provider_id"]):
            return self.result(f"Chat model '{name}' unavailable. Use /models to list choices.", success=False)
        return self.result(f"Model has been switched to {matches[0]['selector']}", success=True)

    @core.module.tool
    async def set_image_model(self, name: str):
        """Sets the image generation model."""
        name_clean = str(name).strip()
        if not name_clean:
            return self.result("Image model name cannot be empty.", success=False)

        if not self.manager.API.set_image_model(name_clean):
            return self.result("Choose an enabled image model. Use /models for provider-qualified names.", success=False)
        return self.result(f"Image model has been set to '{name_clean}'.", success=True)

    @core.module.tool
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

    @core.module.tool
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
        if updated is None:
            return self.result(f"Unknown model '{name_clean}'. Use /models to list choices.", success=False)
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
            return f"**Active Chat Model**: `{curr}`\n**Image Generation Model**: `{img}`\n**Reasoning Effort**: `{eff_display}`"

        sub = args[0].lower()
        if sub == "image" and len(args) > 1:
            img_target = " ".join(args[1:]).strip()
            if not self.manager.API.set_image_model(img_target):
                return "Choose an enabled image model. Use /models for provider-qualified names."
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
        elif sub in ("enable", "disable") and len(args) > 1:
            target = " ".join(args[1:]).strip()
            result = await self.toggle_model(target, enable=sub == "enable")
            return result["content"]

        target_name = " ".join(args).strip()
        res = await self.switch(target_name)
        return res.get("content") if isinstance(res, dict) else str(res)

    @core.module.command("models", help={
        "": "Lists all available models with their current status"
    })
    async def models(self, args: list):
        """Lists available models."""
        choices = await self._load_models()
        if not choices:
            return "No models available or API connection error."

        curr = self.manager.API.get_model()
        img = self.manager.API.get_image_model()
        chat_provider = self.manager.API.selected_provider_id()
        image_provider = self.manager.API.selected_provider_id(image=True)

        lines = ["**Available Models**:"]
        for item in choices:
            tags = []
            if item["id"] == curr and item["provider_id"] == chat_provider:
                tags.append("ACTIVE CHAT")
            if item["id"] == img and item["provider_id"] == image_provider:
                tags.append("IMAGE GEN")
            if not item["enabled"]:
                tags.append("DISABLED")

            tag_str = f" *[{', '.join(tags)}]*" if tags else ""
            lines.append(f"- `{item['selector']}`{tag_str}")

        lines.append("\n*Commands: `/model <name>`, `/model image <name>`, `/model effort <level>`, `/model disable <name>`*")
        return "\n".join(lines)
