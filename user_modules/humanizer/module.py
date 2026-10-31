import json
import urllib.parse

import aiohttp

import core
import channels.webui.api as webui


DEFAULT_INSTRUCTION = """Rewrite the text below so it reads like a person wrote it, not a language model.

Reorganize it as you see fit. Vary sentence length on purpose. Cut hedging,
throat-clearing, and any sentence that only announces what comes next.
Prefer the concrete word over the abstract one. It is fine to sound uneven.

Every fact, number, unit, date, name and quotation must survive unchanged."""

DEFAULT_SEPARATOR = "\n\n### Rewritten:\n\n"


class Humanizer(core.module.Module):
    """Rewrite AI-sounding drafts with jialinyyzz/humanizer while preserving facts."""

    category = "writing"

    settings = {
        "model": {
            "type": "model_select",
            "default": "",
            "description": "Model to use, picked from the models configured in OpenLumara. For `jialinyyzz/humanizer`, add its server as a provider in Settings → API, then select the model here. Leave empty to use the active chat model."
        },
        "api_style": {
            "type": "select",
            "default": "openai",
            "options": {
                "openai": "OpenAI-compatible `/v1/completions` endpoint (llama-swap, vLLM, etc.)",
                "llama_cpp": "llama.cpp native `/completion` endpoint",
                "ollama": "Ollama `/api/generate` endpoint"
            },
            "description": "Completion API exposed by the selected model's provider. Humanizer models use text completion, not chat completions."
        },
        "base_url": {
            "type": "text",
            "default": "",
            "description": "Fallback endpoint used only when the selected model is not listed under any OpenLumara provider. Leave empty to use the core API URL."
        },
        "api_key": {
            "type": "text",
            "default": "",
            "description": "Fallback key for the fallback endpoint. Leave empty to use the core API key."
        },
        "request_timeout": {
            "type": "number",
            "default": 900,
            "min": 10,
            "step": 10,
            "description": "Maximum seconds to wait for a rewrite. Long local generations can take several minutes. AI tool calls are also capped by Core → Tool Timeout; use `/humanize` for long drafts or raise that limit."
        },
        "max_input_chars": {
            "type": "number",
            "default": 20000,
            "min": 1,
            "step": 1000,
            "description": "Reject drafts longer than this before sending them to the model. The default stays within the model's 8192-token context when combined with the default output limit."
        },
        "max_output_tokens": {
            "type": "number",
            "default": 2048,
            "min": 1,
            "step": 128,
            "description": "Maximum number of tokens generated for the rewritten text."
        },
        "temperature": {
            "type": "number",
            "default": 1.0,
            "min": 0.0,
            "max": 2.0,
            "step": 0.05,
            "description": "The model card recommends 1.0."
        },
        "top_p": {
            "type": "number",
            "default": 0.95,
            "min": 0.0,
            "max": 1.0,
            "step": 0.01,
            "description": "The model card recommends 0.95."
        },
        "top_k": {
            "type": "number",
            "default": 0,
            "min": 0,
            "step": 1,
            "description": "The model card requires top-k to be disabled (0)."
        },
        "min_p": {
            "type": "number",
            "default": 0.0,
            "min": 0.0,
            "max": 1.0,
            "step": 0.01,
            "description": "The model card requires min-p to be disabled (0)."
        },
        "repeat_penalty": {
            "type": "number",
            "default": 1.0,
            "min": 0.0,
            "step": 0.05,
            "description": "The model card recommends no repetition penalty (1.0)."
        },
        "prompt_instruction": {
            "type": "long_text",
            "default": DEFAULT_INSTRUCTION,
            "description": "Instruction prepended to every draft. The default is the exact instruction from the model repository."
        },
        "prompt_separator": {
            "type": "long_text",
            "default": DEFAULT_SEPARATOR,
            "description": "Text inserted after the draft. The default `### Rewritten:` marker comes from the model repository."
        }
    }

    def _setting_number(self, key, default, cast=float):
        try:
            return cast(self.config.get(key, default))
        except (TypeError, ValueError):
            return default

    def _active_model(self):
        try:
            return str(self.manager.API.get_model() or "").strip()
        except Exception:
            return str(core.config.get("model", "name", default="") or "").strip()

    def _resolve_target(self):
        """Resolve model, endpoint and key from OpenLumara's provider config."""
        model = str(self.config.get("model", default="") or "").strip() or self._active_model()
        if not model:
            raise ValueError("No model selected. Pick one in the Humanizer settings or configure an active chat model.")

        provider = None
        try:
            provider, entry = self.manager.API.find_provider_for_model(model)
            if provider and isinstance(entry, dict) and entry.get("id"):
                model = str(entry["id"]).strip()
        except Exception:
            provider = None

        # a model listed in a configured provider always uses that provider;
        # the URL/key settings are only a fallback for uncatalogued models
        if provider and provider.get("url"):
            base_url = str(provider["url"]).strip().rstrip("/")
            api_key = str(provider.get("key") or "").strip()
        else:
            base_url = str(self.config.get("base_url", default="") or "").strip().rstrip("/")
            api_key = str(self.config.get("api_key", default="") or "").strip()
            if not base_url:
                base_url = str(core.config.get("api", "url", default="") or "").strip().rstrip("/")
                if not api_key:
                    api_key = str(core.config.get("api", "key", default="") or "").strip()

        parsed = urllib.parse.urlparse(base_url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ValueError("No usable provider URL found. Add the model's provider in Settings → API, or set a Humanizer base URL override.")

        return model, base_url, api_key

    def _completion_url(self, base_url, style):
        if style == "llama_cpp":
            if base_url.endswith("/v1"):
                base_url = base_url[:-3]
            return base_url + "/completion"
        if style == "ollama":
            if base_url.endswith("/v1"):
                base_url = base_url[:-3]
            elif base_url.endswith("/api"):
                base_url = base_url[:-4]
            return base_url + "/api/generate"
        if base_url.endswith("/v1"):
            return base_url + "/completions"
        return base_url + "/v1/completions"

    def _sampling(self):
        return {
            "temperature": self._setting_number("temperature", 1.0),
            "top_p": self._setting_number("top_p", 0.95),
            "top_k": self._setting_number("top_k", 0, int),
            "min_p": self._setting_number("min_p", 0.0),
            "repeat_penalty": self._setting_number("repeat_penalty", 1.0),
            "max_output_tokens": self._setting_number("max_output_tokens", 2048, int),
        }

    def _build_prompt(self, draft):
        instruction = str(self.config.get("prompt_instruction", default=DEFAULT_INSTRUCTION) or DEFAULT_INSTRUCTION).strip()
        separator = str(self.config.get("prompt_separator", default=DEFAULT_SEPARATOR) or DEFAULT_SEPARATOR)
        return instruction + "\n\n" + draft.strip() + separator

    def _request_body(self, style, model, prompt, sampling):
        if style == "llama_cpp":
            return {
                "prompt": prompt,
                "temperature": sampling["temperature"],
                "top_p": sampling["top_p"],
                "top_k": sampling["top_k"],
                "min_p": sampling["min_p"],
                "repeat_penalty": sampling["repeat_penalty"],
                "n_predict": sampling["max_output_tokens"],
                "stream": False,
            }
        if style == "ollama":
            return {
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": sampling["temperature"],
                    "top_p": sampling["top_p"],
                    "top_k": sampling["top_k"],
                    "min_p": sampling["min_p"],
                    "repeat_penalty": sampling["repeat_penalty"],
                    "num_predict": sampling["max_output_tokens"],
                },
            }
        return {
            "model": model,
            "prompt": prompt,
            "temperature": sampling["temperature"],
            "top_p": sampling["top_p"],
            "top_k": sampling["top_k"],
            "min_p": sampling["min_p"],
            "repetition_penalty": sampling["repeat_penalty"],
            "max_tokens": sampling["max_output_tokens"],
            "stream": False,
        }

    @staticmethod
    def _extract_text(style, payload):
        if style == "llama_cpp":
            return payload.get("content")
        if style == "ollama":
            return payload.get("response")
        choices = payload.get("choices") or []
        if choices:
            return choices[0].get("text")
        return None

    async def _humanize(self, draft):
        draft = str(draft or "").strip()
        if not draft:
            raise ValueError("Draft cannot be empty.")

        max_input_chars = self._setting_number("max_input_chars", 20000, int)
        if max_input_chars > 0 and len(draft) > max_input_chars:
            raise ValueError(f"Draft is too long ({len(draft)} characters); the configured limit is {max_input_chars}.")

        style = str(self.config.get("api_style", default="openai") or "openai").strip().lower()
        if style not in ("llama_cpp", "openai", "ollama"):
            raise ValueError(f"Unsupported Humanizer API style: {style}")

        model, base_url, api_key = self._resolve_target()
        url = self._completion_url(base_url, style)
        sampling = self._sampling()
        body = self._request_body(style, model, self._build_prompt(draft), sampling)

        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        timeout = self._setting_number("request_timeout", 900, int)
        client_timeout = aiohttp.ClientTimeout(total=max(10, timeout), connect=min(10, max(10, timeout)))
        async with aiohttp.ClientSession(timeout=client_timeout) as session:
            async with session.post(url, json=body, headers=headers) as response:
                text = await response.text()
                if response.status != 200:
                    raise RuntimeError(f"Humanizer server returned HTTP {response.status}: {text[:500]}")

        try:
            payload = json.loads(text)
        except (TypeError, ValueError) as exc:
            raise RuntimeError(f"Humanizer server returned invalid JSON: {text[:500]}") from exc

        output = self._extract_text(style, payload)
        output = str(output or "").strip()
        if not output:
            raise RuntimeError("Humanizer server returned an empty completion.")
        return output

    @core.module.tool
    async def humanize(self, draft: str):
        """
        Rewrite an AI-generated draft so it sounds naturally human while preserving every fact.
        Use this when the user explicitly asks to humanize text, remove AI-sounding phrasing,
        or make an email, essay, report, or forum post feel less machine-written.

        Args:
            draft: The complete text to rewrite.
        """
        try:
            output = await self._humanize(draft)
        except Exception as exc:
            return self.result(f"Humanization failed: {core.detail_error(exc)}", success=False)
        return self.result(output, success=True)

    @webui.route("humanize", method="POST", admin_only=True)
    async def _route_humanize(self, body=None, query=None):
        """Rewrite a draft submitted from Humanizer Studio."""
        draft = str((body or {}).get("draft", "") or "").strip()
        if not draft:
            return self.result("Draft cannot be empty.", success=False)
        try:
            output = await self._humanize(draft)
        except Exception as exc:
            self.log(self.name, f"Humanizer Studio request failed: {core.detail_error(exc)}")
            return self.result(f"Humanization failed: {core.detail_error(exc)}", success=False)
        return self.result({"humanized": output}, success=True)

    @core.module.command("humanize", help={
        "<text>": "Rewrite the given draft so it reads naturally while preserving its facts"
    })
    async def humanize_command(self, args: list):
        """Rewrite a draft from the command line."""
        draft = " ".join(args).strip()
        if not draft:
            return "Usage: `/humanize <text>`."
        try:
            return await self._humanize(draft)
        except Exception as exc:
            return f"Humanization failed: {core.detail_error(exc)}"
