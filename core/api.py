import core
import core.http_sse as http_sse
import aiohttp
import asyncio
import copy
import json
import math
import ssl
import time
import urllib.parse
import ulid

# -- AI GENERATED CODE (GPT-6.2-Sol) :: 2026-11-24 09:29 +08:00 harness:Codex
def _positive_number(value):
    if isinstance(value, bool):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return value if math.isfinite(value) and value > 0 else None


def _generation_timings(packet):
    raw = packet.get("timings")
    timings = dict(raw) if isinstance(raw, dict) else {}
    rate = _positive_number(timings.pop("predicted_per_second", None))
    if rate is None:
        count = _positive_number(timings.get("predicted_n"))
        elapsed = _positive_number(timings.get("predicted_ms"))
        if count and elapsed:
            rate = _positive_number(count / elapsed * 1000)

    metrics, usage = packet.get("metrics"), packet.get("usage")
    if rate is None and isinstance(metrics, dict) and isinstance(usage, dict):
        elapsed = _positive_number(metrics.get("generation_time_ms"))
        count = usage.get("completion_tokens")
        # vLLM measures from the first token to the last, so there are count - 1 intervals.
        intervals = _positive_number(count - 1) if type(count) is int else None
        if elapsed and intervals:
            rate = _positive_number(intervals / elapsed * 1000)
            if rate is not None:
                timings["predicted_ms"] = elapsed

    if rate is not None:
        timings["predicted_per_second"] = rate
    return timings


# -- AI GENERATED CODE (GPT-6.2-Sol) :: 2026-11-23 21:59 +08:00 harness:Codex
MODEL_OPTION_DEFAULTS = {
    "context_length": ("8192", "16384", "32768", "65536", "128000", "131072", "180000", "200000", "1000000"),
    "thinking_effort": ("low", "medium", "high", "xhigh", "max"),
}
_MODEL_OPTION_MODES = {"context_length": ("auto",), "thinking_effort": ("default", "none")}
_MAX_SAFE_TOKEN_COUNT = 2**53 - 1


def _model_option_value(field, value):
    label = field.replace("_", " ").capitalize()
    if value is not None and type(value) not in (str, int):
        raise ValueError(f"{label} must be a name or a whole number.")
    text = str(value).strip() if value is not None else ""
    modes = _MODEL_OPTION_MODES[field]
    if not text:
        return modes[0]
    folded = text.lower()
    if folded in modes or folded in MODEL_OPTION_DEFAULTS[field]:
        return folded
    if text.isascii() and text.isdecimal():
        digits = text.lstrip("0") or "0"
        if len(digits) <= 16 and int(digits) <= _MAX_SAFE_TOKEN_COUNT and (digits != "0" or field == "thinking_effort"):
            return digits
        raise ValueError(f"{label} is outside the supported token count range.")
    if field == "context_length":
        raise ValueError("Context length must be a positive whole number or Auto.")
    if isinstance(value, int) or len(text.splitlines()) != 1:
        raise ValueError("Thinking effort must be a single name or a non-negative whole number.")
    return text


def _saved_model_option(field, value):
    try:
        return _model_option_value(field, value)
    except ValueError:
        return _MODEL_OPTION_MODES[field][0]


def _model_option_updates(model, settings):
    updates = dict(settings)
    for field, defaults in MODEL_OPTION_DEFAULTS.items():
        options_key = f"{field}_options"
        if field not in settings and options_key not in settings:
            continue

        modes = _MODEL_OPTION_MODES[field]
        active = _saved_model_option(field, model.get(field))
        selected = _model_option_value(field, settings[field]) if field in settings else active
        previous = _saved_model_option(field, model.get("previous_thinking_effort")) if field == "thinking_effort" else modes[0]
        stored = model.get(options_key)
        if options_key in settings:
            submitted = settings[options_key]
            if not isinstance(submitted, list):
                raise ValueError(f"{field.replace('_', ' ').capitalize()} options must be a list.")
            options = [_model_option_value(field, value) for value in submitted]
            if selected not in modes and selected not in options:
                if field in settings:
                    raise ValueError("Add the selected value to the list of options first.")
                selected = modes[0]
        else:
            options = [_saved_model_option(field, value) for value in stored] if isinstance(stored, list) else list(defaults)
            options.extend((active, previous, selected))
        options = list(dict.fromkeys(value for value in options if value not in modes))
        if options_key in settings or isinstance(stored, list) or options != list(defaults):
            updates[options_key] = options
        updates[field] = selected
        if field == "thinking_effort":
            if selected == "none" and active != "none":
                previous = active
            if selected == "none" or "previous_thinking_effort" in model:
                updates["previous_thinking_effort"] = previous if previous in options else "default"
    return updates


class APIError(Exception):
    """Holds an error message, used for passing on to channels as a value, and raisable as an exception"""
    def __init__(self, message: str = None, exc = None):
        self.message = message
        
        # store exception if relevant
        self.exc = None
        if exc:
            self.exc = exc

    def __str__(self):
        err_str = ""
        if self.message:
            err_str += self.message
        if self.exc:
            if self.message:
                err_str += ": "
            err_str += core.detail_error(self.exc)

        return err_str

class APIHTTPError(Exception):
    """a HTTP response with a non-200 status"""
    def __init__(self, status: int, body: str = ""):
        self.status = status
        self.body = body or ""
        super().__init__(f"HTTP {status}: {self.body[:500]}")

class APIClient():
    """
    wrapper around an OpenAI-compatible chat completions API
    """

    MAX_API_ATTEMPTS = 3
    RETRY_BASE_DELAY = 0.5
    RETRYABLE_STATUS_CODES = (408, 409, 425, 429, 500, 502, 503, 504)

    def __init__(self, manager):
        # store a reference to the manager
        self.manager = manager

        self.connected = False
        self.is_streaming = False

        self._messages = []
        self._legacy_model_cache = None

        self.cancel_request = False

        # active low-level HTTP request task, used for reliable cancellation
        self._request_task = None

        # guards session lifecycle against concurrent connect/disconnect calls
        self._connect_lock = asyncio.Lock()

        # active streamed HTTP response, so cancel() can sever the SSE connection immediately
        self._stream_response = None

        # the aiohttp session is the one HTTP client for everything
        self._session = None
        self._ssl_ctx = None # only set when TLS verification is disabled

        # origin of the API when it's a llama.cpp router. enables the model load progress feed.
        self._router_origin = None

        # -- AI GENERATED CODE (GPT-6.2-Sol) :: 2026-11-24 07:36 +08:00 harness:Codex
        self._extras_rejected = set()
        self._live_timings_base = None
        self._live_timings_rejected = set()

    # -------------------
    # HTTP plumbing
    # -------------------
    def _api_headers(self):
        """auth headers for calls to the API"""
        key = core.config.get("api", "key")
        if key:
            return {"Authorization": f"Bearer {key}"}
        return {}

    def _json_headers(self):
        headers = self._api_headers()
        headers["Content-Type"] = "application/json"
        return headers

    def _make_session(self):
        """create the shared aiohttp session"""
        # infinite read timeout (long generations and model loads must not be cut off)
        timeout = aiohttp.ClientTimeout(total=None, connect=5.0)
        return aiohttp.ClientSession(timeout=timeout)

    async def _http_get(self, url, timeout_total=None):
        """GET a url and return (status, body_text)"""
        kwargs = {"headers": self._api_headers()}
        if self._ssl_ctx is not None:
            kwargs["ssl"] = self._ssl_ctx
        if timeout_total is not None:
            kwargs["timeout"] = aiohttp.ClientTimeout(total=timeout_total)

        async with self._session.get(url, **kwargs) as resp:
            return resp.status, await resp.text()

    async def _probe_connection(self):
        """lightweight connection probe by doing a GET request to /models"""
        base = core.config.get("api", "url").rstrip("/")
        return await self._http_get(f"{base}/models", timeout_total=15)

    async def _probe_chat_completions(self):
        """fallback probe for servers without GET /models,
        by sending a chat completions request"""
        api_config = core.config.get("api", {})
        
        probe_body = {
            "messages": [{"role": "user", "content": "ping"}],
            "stream": False,
            "max_completion_tokens": 1,
        }
        model_name = core.config.get("model", "name")
        if model_name:
            probe_body["model"] = model_name

        kwargs = {"headers": self._json_headers(), "json": probe_body}
        if self._ssl_ctx is not None:
            kwargs["ssl"] = self._ssl_ctx

        async with self._session.post(
            f"{api_config.get('url')}/chat/completions",
            timeout=aiohttp.ClientTimeout(total=60, connect=15),
            **kwargs,
        ) as resp:
            return resp.status, await resp.text()

    def _error_for_status(self, status, body, prefix=""):
        """maps an HTTP error response onto a APIError"""
        e = APIHTTPError(status, body)
        error_str = (body or "").lower()

        if status == 400:
            # check if the error message specifically mentions the model is not found
            if "model" in error_str and ("not found" in error_str or "missing" in error_str):
                return APIError("Model with that name does not exist!", e)
            return APIError("Bad request", e)

        if status in (401, 403):
            return APIError("Authentication failed. Check whether your API key is valid!", e)

        if status == 404:
            return APIError("Model with that name does not exist!", e)

        if status == 429:
            return APIError("Rate limit exceeded", e)

        return APIError("API Status Error", e)

    # -------------------
    # Connection management
    # -------------------
    async def connect(self, silent=False):
        if self.connected:
            return True

        async with self._connect_lock:
            # dont allow concurrent connect() calls
            if self.connected:
                return True

            return await self._connect_setup(silent=silent)

    async def _connect_setup(self, silent=False):
        # Resolve active endpoint from active model or configured providers
        target_model = core.config.get("model", "name")
        prov, _ = self.find_provider_for_model(target_model)
        if not prov and core.config.get("model", "provider_id"):
            raise APIError("Selected chat model or provider is unavailable. Choose an enabled model.")
        if prov and not prov.get("url"):
            raise APIError("Selected provider has no endpoint URL.")
        if not prov:
            # only fall back to another provider when the API is still unconfigured,
            # so a manually configured api.url is never clobbered
            current_url = core.config.get("api", "url")
            if not current_url or current_url == "http://API_URL_HERE/v1":
                for p in self.get_providers():
                    if p.get("enabled", True) and p.get("url") and p.get("url") != "http://API_URL_HERE/v1":
                        prov = p
                        break

        if prov and prov.get("url"):
            if "api" not in core.config.config:
                core.config.config["api"] = {}
            core.config.config["api"]["url"] = prov["url"]
            # always assign, so a key from a previous provider can never leak to this one
            core.config.config["api"]["key"] = prov.get("key") or ""
            # Sync max_context for the active model
            core.config.config["api"]["max_context"] = self.get_max_context(target_model)
            core.config.config.save()

        api_config = core.config.get("api", {})

        if api_config.get("url") == "http://API_URL_HERE/v1":
            raise APIError("The API connection has not been set up yet! Please set up your API connection by either using the WebUI, the /config command, or editing the config file")

        # close any session left over from a previous failed connect attempt
        await self._close_session()

        use_secure_connection = not getattr(getattr(self.manager, "args", None), "insecure_tls", False)
        if not use_secure_connection and self.manager:
            self.manager.log("API", "WARNING: TLS certificate and hostname verification are disabled")

        try:
            self._session = self._make_session()

            if not use_secure_connection:
                self._ssl_ctx = ssl.create_default_context()
                self._ssl_ctx.check_hostname = False
                self._ssl_ctx.verify_mode = ssl.CERT_NONE

            # validate the connection with a cheap GET /models request
            status, body = await self._probe_connection()
            model_listing = body if status == 200 else None
            connection_error = None

            if status in (404, 405):
                # server does not implement GET /models: fall back to the
                # old chat-completions probe
                status, body = await self._probe_chat_completions()

                if status in (400, 404):
                    error_str = body.lower()
                    if "model" in error_str and ("not found" in error_str or "missing" in error_str):
                        connection_error = APIError("Model not found.")
                    elif status != 400:
                        connection_error = APIError("Unknown error", APIHTTPError(status, body))
                    # status 400 without a model complaint: accept the connection

                elif status in (401, 403):
                    connection_error = APIError("Authentication failed. Check if your API key is valid.", APIHTTPError(status, body))

                elif status == 405:
                    connection_error = APIError("The URL does not look like a chat-completions API.", APIHTTPError(status, body))

                elif status != 200:
                    connection_error = APIError("Failed to connect to the API", APIHTTPError(status, body))

            elif status in (401, 403):
                connection_error = APIError("Authentication failed. Check if your API key is valid.", APIHTTPError(status, body))

            elif status != 200:
                connection_error = APIError("Failed to connect to the API", APIHTTPError(status, body))

            if connection_error is not None:
                await self._close_session()
                raise connection_error

        except aiohttp.ClientError as e:
            await self._close_session()
            raise APIError("Failed to connect to the API", e) from e

        except Exception as e:
            await self._close_session()
            import traceback
            if core.debug:
                traceback.print_exc()
            raise APIError(None, e) from e

        self.connected = True

        await self._detect_router(model_listing)

        if not silent and self.manager:
            self.manager.log("API", "Successfully connected to AI")

        return True
    
    async def attempt_connect(self):
        if not self.connected:
            return await self.connect()
        
        return True

    def get_status(self):
        api_config = core.config.get("api", {})
        model_config = core.config.get("model", {})

        return {
            "connected": self.connected,
            "url": api_config.get("url"),
            "model": core.config.get("model", "name")
        }

    async def _close_session(self):
        if self._session:
            await self._session.close()
            self._session = None

    async def disconnect(self):
        """disconnect from the API"""
        # dont allow concurrent disconnect() calls
        async with self._connect_lock:
            await self._close_session()

            # clear per-session state
            self._ssl_ctx = None
            self._router_origin = None
            self._extras_rejected.clear()
            self._live_timings_base = None
            self._live_timings_rejected.clear()

            self.connected = False

        return True

    async def reconnect(self):
        """disconnect and reconnect to the API"""
        await self.disconnect()
        return await self.connect()

    # -------------------
    # llama.cpp router support
    # -------------------
    async def _detect_router(self, model_listing=None):
        """
        probe the API to detect if it's a llamacpp instance that's in router mode
        (to support features exclusive to llamacpp, such as
        model loading progress bars, prompt progress, and so on)
        """
        self._router_origin = None
        self._live_timings_base = None

        try:
            api_url = core.config.get("api", "url") or ""
            parsed = urllib.parse.urlsplit(api_url)

            if not parsed.scheme or not parsed.netloc:
                return

            # The management endpoints omit /v1, including behind a path prefix.
            router_path = parsed.path.rstrip("/").removesuffix("/v1")
            origin = f"{parsed.scheme}://{parsed.netloc}{router_path}"
            if model_listing is None:
                status, model_listing = await self._http_get(f"{origin}/models", timeout_total=5.0)
                if status != 200:
                    return

            body = json.loads(model_listing)
            entries = body.get("data") if isinstance(body, dict) else None
            if not isinstance(entries, list):
                return
            entries = [entry for entry in entries if isinstance(entry, dict)]
            if any(entry.get("owned_by") in ("llamacpp", "llama-swap") for entry in entries):
                self._live_timings_base = api_url.rstrip("/")
            if any(isinstance(entry.get("status"), dict) and entry["status"].get("value") for entry in entries):
                self._router_origin = origin

        except (ValueError, TypeError, aiohttp.ClientError, asyncio.TimeoutError):
            pass

    async def _wait_for_model_loaded(self, timeout=240.0):
        """Wait until the router reports the chat model as loaded.

        Only used before retrying an empty completion: the first request is what
        triggers the swap, so polling afterwards is safe. No-ops for providers
        that don't expose model status.
        """
        if not self._router_origin:
            return

        model_name = core.config.get("model", "name")
        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            if self.cancel_request:
                return
            try:
                status, body = await self._http_get(f"{self._router_origin}/models", timeout_total=5.0)
                if status == 200:
                    for entry in (json.loads(body).get("data") or []):
                        if entry.get("id") != model_name:
                            continue
                        state = (entry.get("status") or {}).get("value")
                        if state in (None, "", "loaded"):
                            return
                        break
                else:
                    return
            except Exception:
                return
            await asyncio.sleep(1.0)

    async def _watch_model_load(self, model_name, queue):
        """reads the llamacpp router's /models/sse feed while a model loads"""
        try:
            url = f"{self._router_origin}/models/sse"
            kwargs = {"headers": self._api_headers()}
            if self._ssl_ctx is not None:
                kwargs["ssl"] = self._ssl_ctx

            async with self._session.get(url, **kwargs) as feed:
                async for event in http_sse.iter_events(feed):
                    # the SSE parser merges the event/id fields into the
                    # parsed data payload
                    if event.get("event") not in ("status_change", "model_status"):
                        continue

                    # the payload IS the event data (status/model/progress live
                    # at the top level of the parsed JSON)
                    data = event
                    status = data.get("status") or ""
                    name = data.get("model") or ""

                    if status in ("loaded", "unloaded"):
                        # let the prompt/content tokens take over the progress indicator
                        if name == model_name:
                            return
                        continue

                    if status not in ("loading", "queued", "downloading"):
                        continue

                    progress = data.get("progress") or {}
                    value = progress.get("value")

                    await queue.put({
                        "model": name,
                        "status": status,
                        "stage": progress.get("current") or "",
                        "percent": round(value * 100) if isinstance(value, (int, float)) else None,
                    })

        except asyncio.CancelledError:
            raise
        except Exception:
            pass

    # -------------------
    # Model config
    # -------------------
    def get_model(self):
        return core.config.get("model", "name")

    # -- AI GENERATED CODE (GPT-6) :: 2026-11-21 18:22:00 +08:00 harness:Codex
    def set_model(self, name: str, provider_id=None):
        selection = self.resolve_model_selection(name, provider_id)
        if selection is None:
            return False
        name, p = selection
        core.config.config["model"]["name"] = name
        core.config.config["model"]["provider_id"] = p["id"] if p else ""

        # Sync api.url and api.key with the provider hosting this model
        if p and p.get("url"):
            if "api" not in core.config.config:
                core.config.config["api"] = {}
            core.config.config["api"]["url"] = p["url"]
            # always assign, so a key from a previous provider can never leak to this one
            core.config.config["api"]["key"] = p.get("key") or ""
            self._router_origin = None
            self.connected = False

        # Sync effective max context for this model into api.max_context
        eff_ctx = self.get_max_context(name)
        if "api" not in core.config.config:
            core.config.config["api"] = {}
        core.config.config["api"]["max_context"] = eff_ctx

        core.config.config.save()
        return True

    def get_max_context(self, model_name: str = None) -> int:
        """Returns the effective max context length for the given model (or currently active model)."""
        target = model_name or core.config.get("model", "name")
        p, m = self.find_provider_for_model(target)
        if m:
            ctx_val = m.get("context_length")
            if ctx_val and str(ctx_val).strip().lower() != "auto":
                try:
                    parsed = int(ctx_val)
                    if parsed > 0:
                        return parsed
                except (ValueError, TypeError, OverflowError):
                    pass
            return int(self.detect_model_context(target))

        # legacy single-endpoint setups have no provider model to configure
        try:
            configured = int(core.config.get("api", "max_context", default=0) or 0)
            if configured > 0:
                return configured
        except (ValueError, TypeError):
            pass

        detected = self.detect_model_context(target)
        if detected:
            return int(detected)
        return 16768
    def get_model_option(self, key, default=None, model_name=None):
        """Resolve a per-model request option. Provider models don't inherit the
        hidden legacy globals; single-endpoint setups still use them."""
        target = model_name or self.get_model()
        _, model = self.find_provider_for_model(target)
        if model:
            value = model.get(key)
            if value is not None and not (isinstance(value, str) and value.strip().lower() in ("", "default")):
                return value
            return default
        return core.config.get("api", key, default=default)

    @property
    def supports_developer_role(self):
        value = self.get_model_option("use_developer_role", default=False)
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "yes", "on")
        return bool(value)

    def get_image_model(self):
        return core.config.get("model", "image_model", default="dall-e-3")

    def get_image_edit_model_setting(self):
        return str(core.config.get("model", "image_edit_model", default="") or "").strip()

    def get_image_edit_model(self):
        configured = self.get_image_edit_model_setting()
        if not configured or configured.casefold() == str(self.get_model()).strip().casefold():
            return self.get_image_model()
        _, model = self.find_provider_for_model(configured)
        if model and not model.get("is_image"):
            return self.get_image_model()
        return configured

    def set_image_edit_model(self, name: str):
        clean_name = str(name or "").strip()
        if clean_name:
            if clean_name.casefold() == str(self.get_model()).strip().casefold():
                return False
            _, model = self.find_provider_for_model(clean_name)
            if model and not model.get("is_image"):
                return False
        if "model" not in core.config.config:
            core.config.config["model"] = {}
        core.config.config["model"]["image_edit_model"] = clean_name
        core.config.config.save()
        return True

    def set_image_model(self, name: str, provider_id=None):
        selection = self.resolve_model_selection(name, provider_id, image=True)
        if selection is None:
            return False
        clean_name, provider = selection
        core.config.config.setdefault("model", {})
        core.config.config["model"]["image_model"] = clean_name
        core.config.config["model"]["image_provider_id"] = provider["id"] if provider else ""
        core.config.config.save()
        return True

    def get_disabled_models(self) -> list:
        return list(core.config.get("model", "disabled_models", default=[]))

    def set_model_disabled(self, name: str, disabled: bool):
        name_clean, provider_id = self._split_model_selector(name)
        if provider_id:
            matches = self._model_matches(name_clean, provider_id)
            if not matches:
                return None
            self.update_model_settings(provider_id, matches[0][1]["id"], {"enabled": not disabled})
            return self.get_disabled_models()
        if "model" not in core.config.config:
            core.config.config["model"] = {}
        disabled_list = list(core.config.get("model", "disabled_models", default=[]))
        disabled_list = [item for item in disabled_list if item.casefold() != name_clean.casefold()]
        providers = self.get_providers()
        for provider in providers:
            for model in provider["models"]:
                if model["id"].casefold() == name_clean.casefold():
                    model["enabled"] = not disabled
        if disabled:
            disabled_list.append(name_clean)
        core.config.config["model"]["disabled_models"] = disabled_list
        self.save_providers(providers)
        return disabled_list

    def set_reasoning_effort(self, effort: str = None, custom: str = None):
        if "model" not in core.config.config:
            core.config.config["model"] = {}
        if effort is not None:
            core.config.config["model"]["reasoning_effort"] = str(effort).strip()
        if custom is not None:
            core.config.config["model"]["custom_reasoning_effort"] = str(custom).strip()
        core.config.config.save()
        return True
    # -------------------
    # Multi-Provider & Model Config
    # -------------------
    def get_providers(self) -> list:
        """Returns all configured API providers, auto-seeding a default provider if empty."""
        providers = core.config.get("api", "providers", default=[])
        if not providers and core.config.get("api", "url"):
            # only seed legacy configs that never had a providers list. an
            # explicitly emptied list must stay empty (deleting the last
            # provider should not resurrect a ghost provider on the next read)
            api_section = core.config.config.get("api") or {}
            if "providers" in api_section:
                return []
            default_url = core.config.get("api", "url")
            parsed = urllib.parse.urlparse(default_url)
            host_label = parsed.netloc or "default-provider"
            default_p = {
                "id": "p_default",
                "name": host_label,
                "url": default_url,
                "key": core.config.get("api", "key", default=""),
                "type": "llm",
                "api_format": "auto",
                "enabled": True,
                "is_image_provider": False,
                "models": []
            }
            if "api" not in core.config.config:
                core.config.config["api"] = {}
            core.config.config["api"]["providers"] = [default_p]
            core.config.config.save()
            providers = [default_p]
        disabled = {name.casefold() for name in self.get_disabled_models()}
        model_config = core.config.config.get("model") or {}
        normalized = []
        for provider in providers or []:
            models = []
            for entry in provider.get("models", []):
                model = dict(entry) if isinstance(entry, dict) else {"id": str(entry)}
                if not model.get("id"):
                    continue
                model["enabled"] = model.get("enabled", True) and model["id"].casefold() not in disabled
                if model["id"] == model_config.get("image_model") and model_config.get("image_provider_id") in (None, "", provider["id"]):
                    model.setdefault("is_image", True)
                models.append(model)
            normalized.append({**provider, "enabled": provider.get("enabled", True), "models": models})
        return normalized

    def save_providers(self, providers: list):
        if "api" not in core.config.config:
            core.config.config["api"] = {}
        core.config.config["api"]["providers"] = providers
        core.config.config.save()
        return True

    def _model_matches(self, name, provider_id=None):
        name = str(name or "").strip().casefold()
        return [(provider, model) for provider in self.get_providers()
                if not provider_id or provider["id"] == provider_id
                for model in provider["models"] if model["id"].casefold() == name]

    def find_provider_for_model(self, model_name: str, provider_id=None):
        if provider_id is None and model_name == self.get_model():
            provider_id = core.config.get("model", "provider_id")
        matches = [(provider, model) for provider, model in self._model_matches(model_name, provider_id)
                   if provider["enabled"] and model["enabled"]]
        if not matches:
            return None, None
        # Older configs identify the selected server only by its endpoint.
        url = core.config.get("api", "url")
        return next((pair for pair in matches if pair[0].get("url") == url), matches[0])

    def selected_provider_id(self, image=False):
        key = "image_provider_id" if image else "provider_id"
        pinned = core.config.get("model", key)
        if pinned:
            return pinned
        name = self.get_image_model() if image else self.get_model()
        provider, _ = self.find_provider_for_model(name, "")
        return provider["id"] if provider else ""

    def is_selected_model(self, name, provider_id, image=False):
        current = self.get_image_model() if image else self.get_model()
        return name == current and (not provider_id or provider_id == self.selected_provider_id(image))

    # -- AI GENERATED CODE (GPT-6) :: 2026-11-21 21:10:18 +08:00 harness:Codex
    def _split_model_selector(self, name, provider_id=None):
        name = str(name or "").strip()
        if not provider_id and "::" in name and not self._model_matches(name):
            provider_id, name = name.split("::", 1)
        return name, provider_id

    def resolve_model_selection(self, name, provider_id=None, image=False):
        name, provider_id = self._split_model_selector(name, provider_id)
        if not name or name.casefold() in {item.casefold() for item in self.get_disabled_models()}:
            return None
        matches = self._model_matches(name, provider_id)
        if not matches and not provider_id:
            other = self.get_model() if image else self.get_image_model()
            return None if name.casefold() == str(other).casefold() else (name, None)
        eligible = [(provider, model) for provider, model in matches if provider["enabled"] and model["enabled"]
                    and not self.is_selected_model(model["id"], provider["id"], image=not image)]
        choices = [(model["id"], provider) for provider, model in eligible if bool(model.get("is_image")) == image]
        if image and not choices:
            # Older catalogs have model names without capability flags.
            choices = [(model["id"], provider) for provider, model in eligible if "is_image" not in model]
        return choices[0] if len(choices) == 1 else None

    def get_image_model_provider(self):
        """Finds the designated image model and its provider."""
        img_model = self.get_image_model()
        pinned = core.config.get("model", "image_provider_id")
        p, m = self.find_provider_for_model(img_model, pinned or "")
        if p:
            return p, img_model
        if pinned:
            raise APIError("Selected image model or provider is unavailable.")
        for prov in self.get_providers():
            if prov.get("enabled", True) and prov.get("is_image_provider"):
                return prov, img_model
        return None, img_model

    async def test_provider_connection(self, url: str, key: str = ""):
        """Tests connectivity and latency to an endpoint without persisting."""
        url_clean = str(url).strip().rstrip("/")
        if not url_clean:
            return {"success": False, "error": "URL cannot be empty"}

        parsed = urllib.parse.urlparse(url_clean)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return {"success": False, "error": "URL must be a valid http:// or https:// endpoint"}

        endpoint = f"{url_clean}/models"
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        headers["Accept"] = "application/json"

        t0 = time.time()
        try:
            timeout = aiohttp.ClientTimeout(total=8.0, connect=4.0)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(endpoint, headers=headers, ssl=self._ssl_ctx) as resp:
                    latency = round((time.time() - t0) * 1000)
                    body_text = await resp.text()

                    if resp.status != 200:
                        return {
                            "success": False,
                            "status": resp.status,
                            "latency_ms": latency,
                            "error": f"HTTP {resp.status}: {body_text[:200]}"
                        }

                    data = json.loads(body_text)
                    raw_models = data.get("data", [])
                    models = [m["id"] for m in raw_models if isinstance(m, dict) and m.get("id")]
                    return {
                        "success": True,
                        "latency_ms": latency,
                        "model_count": len(models),
                        "models": models
                    }
        except Exception as e:
            latency = round((time.time() - t0) * 1000)
            return {
                "success": False,
                "latency_ms": latency,
                "error": str(e)
            }

    async def add_provider(self, name: str, url: str, key: str = "", type: str = "llm", api_format: str = "auto", is_image_provider: bool = False):
        """Adds a new provider and queries its initial models."""
        url_clean = str(url).strip().rstrip("/")
        name_clean = str(name).strip() or urllib.parse.urlparse(url_clean).netloc or "provider"
        pid = f"p_{str(ulid.ULID()).lower()[-8:]}"

        new_provider = {
            "id": pid,
            "name": name_clean,
            "url": url_clean,
            "key": str(key).strip(),
            "type": type or "llm",
            "api_format": api_format or "auto",
            "enabled": True,
            "is_image_provider": bool(is_image_provider),
            "models": []
        }
        providers = self.get_providers()
        providers.append(new_provider)
        self.save_providers(providers)

        # Sync default api.url if still placeholder
        if "api" not in core.config.config:
            core.config.config["api"] = {}
        if core.config.get("api", "url") in ("http://API_URL_HERE/v1", "", None):
            core.config.config["api"]["url"] = url_clean
            core.config.config["api"]["key"] = str(key or "").strip()
            core.config.config.save()

        await self.refresh_provider_models(pid)
        for p in self.get_providers():
            if p["id"] == pid:
                return p
        return new_provider

    async def refresh_provider_models(self, provider_id: str):
        """Re-queries {url}/models and merges model customizations."""
        target = next((provider for provider in self.get_providers() if provider["id"] == provider_id), None)
        if not target:
            return []

        endpoint = target["url"], target.get("key", "")
        res = await self.test_provider_connection(*endpoint)
        if not res.get("success"):
            return None

        # -- AI GENERATED CODE (GPT-6.2-Sol) :: 2026-11-23 21:59 +08:00 harness:Codex
        # A model's settings may have changed while the provider was being probed.
        providers = self.get_providers()
        target = next((provider for provider in providers if provider["id"] == provider_id), None)
        if not target or (target["url"], target.get("key", "")) != endpoint:
            return None

        discovered_ids = res.get("models", [])
        existing_map = {}
        for m in target.get("models", []):
            mid = m["id"] if isinstance(m, dict) else str(m)
            existing_map[mid] = m if isinstance(m, dict) else {"id": mid}

        merged = []
        for mid in discovered_ids:
            if mid in existing_map:
                merged.append(existing_map[mid])
            else:
                is_img = any(k in mid.lower() for k in ("image", "flux", "dall-e", "stable-diffusion", "sdxl", "diffusion"))
                merged.append({
                    "id": mid,
                    "enabled": True,
                    "is_image": is_img,
                    "context_length": "auto",
                    "temperature": "default",
                    "thinking_effort": "default",
                    "max_output_tokens": "default",
                    "max_messages": "default",
                    "evict_block": "default",
                    "use_developer_role": "default",
                    "custom_fields": "default"
                })

        target["models"] = merged
        self.save_providers(providers)
        return merged

    def update_provider(self, provider_id: str, updates: dict):
        providers = self.get_providers()
        for p in providers:
            if p["id"] == provider_id:
                for k, v in updates.items():
                    if k != "id":
                        p[k] = v
                self.save_providers(providers)

                # if this provider serves the active model, keep the connection
                # config in sync so an edited url/key takes effect immediately
                active_model = core.config.get("model", "name")
                active_provider, _ = self.find_provider_for_model(active_model)
                if active_provider and active_provider.get("id") == provider_id:
                    core.config.config.setdefault("api", {})
                    core.config.config["api"]["url"] = p.get("url") or ""
                    core.config.config["api"]["key"] = p.get("key") or ""
                    core.config.config.save()
                    self._router_origin = None
                    self.connected = False
                return p
        return None

    def delete_provider(self, provider_id: str):
        providers = self.get_providers()
        new_list = [p for p in providers if p["id"] != provider_id]
        self.save_providers(new_list)
        return True

    def update_model_settings(self, provider_id: str, model_id: str, settings: dict):
        providers = self.get_providers()
        for p in providers:
            if p["id"] == provider_id:
                for m in p.get("models", []):
                    if m.get("id") == model_id:
                        if settings.get("is_image") and self.is_selected_model(model_id, provider_id):
                            return None
                        if settings.get("is_image") is False and self.is_selected_model(model_id, provider_id, image=True):
                            return None
                        settings = _model_option_updates(m, settings)
                        for k, v in settings.items():
                            if k != "id":
                                m[k] = v

                        # Sync active model parameters immediately
                        if "enabled" in settings:
                            disabled = self.get_disabled_models()
                            core.config.config["model"]["disabled_models"] = [
                                name for name in disabled if name.casefold() != model_id.casefold()
                            ]
                        self.save_providers(providers)
                        if "context_length" in settings and self.is_selected_model(model_id, provider_id):
                            core.config.config["api"]["max_context"] = self.get_max_context(model_id)
                            core.config.config.save()
                        return m
        return None

    def detect_model_context(self, model_id: str):
        """Heuristic context length detection."""
        mid = str(model_id).lower()
        if "deepresearch" in mid or "30b" in mid:
            return 131072
        if "qwen3.8-27b" in mid or "qwen3.8" in mid or "qwen2.5" in mid:
            return 180000
        if "gpt-4o" in mid or "o1" in mid or "o3" in mid:
            return 128000
        if "claude" in mid or "sonnet" in mid:
            return 200000
        if "gemini" in mid:
            return 1000000
        if "llama-3" in mid:
            return 131072
        if "mistral" in mid or "nemo" in mid:
            return 128000
        return 32768

    # -------------------
    # Requests
    # -------------------
    async def _post_chat_completion(self, payload, stream=False, api_url=None, api_key=None):
        """
        sends the chat completions request over HTTP.
        returns a parsed JSON dict when not streaming,
        or an open aiohttp ClientResponse (to be consumed by _recv_stream) when streaming.
        """
        base = api_url.rstrip("/") if api_url else core.config.get('api', 'url').rstrip("/")
        url = f"{base}/chat/completions"

        headers = self._json_headers()
        if api_key is not None:
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            else:
                headers.pop("Authorization", None)

        kwargs = {"json": payload, "headers": headers}
        if self._ssl_ctx is not None:
            kwargs["ssl"] = self._ssl_ctx

        if stream:
            resp = await self._session.post(url, **kwargs)

            if resp.status != 200:
                body = await resp.text()
                await resp.release()
                raise APIHTTPError(resp.status, body)

            return resp

        async with self._session.post(url, **kwargs) as resp:
            body = await resp.text()

            if resp.status != 200:
                raise APIHTTPError(resp.status, body)

            return json.loads(body)

    # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-24) harness:openlumara status:reviewed
	# ROSE22: i mean, this is just an exception parser.
    def _is_retryable_error(self, exc):
        """whether a failed request may be retried"""
        if isinstance(exc, APIHTTPError):
            return exc.status in self.RETRYABLE_STATUS_CODES
        if isinstance(exc, aiohttp.ClientSSLError):
            return False
        if isinstance(exc, aiohttp.ClientConnectionError):
            return True
        if isinstance(exc, asyncio.TimeoutError):
            return True
        return False

    async def _request(self, context, tools=None, stream=False, use_thinking=True, **kwargs):
        """send a request to the LLM and return the response (dict, or an open SSE response when streaming)"""

        if not context:
            # this should never happen..
            # so if it does, always print a traceback, since it's bad news!
            import traceback
            traceback.print_stack()

            return APIError("Tried to send a blank request for some reason! This should NEVER happen. Notify the developer.")

        try:
            await self.attempt_connect()
        except APIError as e:
            return e

        if not core.config.get("model", {}).get("use_tools"):
            # allow switching tools off globally
            tools = None

        target_model = kwargs.get("model") or core.config.get("model", "name")
        provider, model_entry = self.find_provider_for_model(target_model)
        if target_model == self.get_model() and core.config.get("model", "provider_id") and not provider:
            return APIError("Selected chat model or provider is unavailable. Choose an enabled model.")
        api_url = provider.get("url") if provider else core.config.get("api", "url")
        if provider and not api_url:
            return APIError("Selected provider has no endpoint URL.")
        api_key = (provider.get("key") if provider else core.config.get("api", "key")) or ""
        endpoint = ((api_url or "").rstrip("/"), target_model)

        req = {
            "model": target_model,
            "messages": context,
            "stream": stream,
            "temperature": kwargs.get("temperature", core.config.get("model", {}).get("temperature", 0.7)),
            "max_completion_tokens": core.config.get("api", {}).get("max_output_tokens", 8192),
            "chat_template_kwargs": {
                "enable_thinking": core.config.get("model", "enable_thinking", default=use_thinking)
            },
            "return_progress": True
        }

        # add kwargs to the request
        for key, value in kwargs.items():
            if key in ("tools", "stream", "use_thinking"): continue
            # None means "not set": never let it overwrite a resolved default
            # (e.g. compression passes model=None when no compression model is configured)
            if value is None: continue
            req[key] = value

        if model_entry:
            # Provider models own these parameters. "default" sends no override,
            # so the host server decides; the hidden globals only cover legacy
            # single-endpoint setups with no provider model entry.
            m_effort = str(model_entry.get("thinking_effort") or "default").strip()
            if m_effort and m_effort.lower() != "default":
                if m_effort.lower() == "none":
                    req.pop("reasoning_effort", None)
                    req.setdefault("chat_template_kwargs", {})["enable_thinking"] = False
                else:
                    req.setdefault("chat_template_kwargs", {})["enable_thinking"] = True
                    if m_effort.isascii() and m_effort.isdecimal():
                        req["reasoning_effort"] = int(m_effort)
                    else:
                        req["reasoning_effort"] = m_effort
        else:
            custom_effort = core.config.get("model", {}).get("custom_reasoning_effort")
            reasoning_effort = core.config.get("model", {}).get("reasoning_effort")
            effective_effort = custom_effort if (custom_effort and str(custom_effort).strip()) else reasoning_effort
            if effective_effort and str(effective_effort).strip().lower() != "none":
                eff_str = str(effective_effort).strip()
                if eff_str.isdigit():
                    req["reasoning_effort"] = int(eff_str)
                else:
                    req["reasoning_effort"] = eff_str

        if model_entry and kwargs.get("temperature") is None:
            model_temp = model_entry.get("temperature")
            if model_temp in (None, "", "default"):
                req.pop("temperature", None)
            else:
                try:
                    temperature = float(model_temp)
                    if 0.0 <= temperature <= 2.0:
                        req["temperature"] = temperature
                except (ValueError, TypeError):
                    pass

        if model_entry:
            output_limit = model_entry.get("max_output_tokens")
            if output_limit in (None, "", "default"):
                req.pop("max_completion_tokens", None)
            else:
                try:
                    output_limit = int(output_limit)
                    if output_limit > 0:
                        req["max_completion_tokens"] = output_limit
                except (ValueError, TypeError):
                    pass

        # allow inserting custom request fields (per-model, legacy fallback)
        custom_fields = model_entry.get("custom_fields") if model_entry else core.config.get("api", "custom_fields", default={})
        if isinstance(custom_fields, dict):
            for key, value in custom_fields.items():
                if key == "chat_template_kwargs" and isinstance(value, dict):
                    req[key] = {**value, **req[key]}
                elif key == "reasoning_effort":
                    if req["chat_template_kwargs"]["enable_thinking"]:
                        req.setdefault(key, value)
                elif key not in ("tools", "model", "chat_template_kwargs"):
                    req[key] = value

        if tools:
            req["tools"] = tools

        if stream:
            # request token usage from the API
            req["stream_options"] = {"include_usage": True}
        auto_timings = (stream and endpoint[0] == self._live_timings_base
                        and endpoint not in self._live_timings_rejected and "timings_per_token" not in req)
        if auto_timings:
            req["timings_per_token"] = True

        # -- AI GENERATED CODE (GPT-6.2-Sol) :: 2026-11-24 07:36 +08:00 harness:Codex
        llama_extras = ("return_progress", "chat_template_kwargs")
        if endpoint in self._extras_rejected:
            for field in llama_extras:
                req.pop(field, None)

        #import rich
        #rich.print(req)

        if core.debug:
            message_summary = []
            api_config = core.config.get("api", {})

            for message in context:
                summary = {
                    "role": message.get("role")
                }

                content = message.get("content")
                if isinstance(content, str):
                    summary["content_chars"] = len(content)
                elif isinstance(content, list):
                    summary["content_items"] = len(content)

                if message.get("tool_calls"):
                    summary["tool_calls"] = len(message.get("tool_calls") or [])

                message_summary.append(summary)

            tool_count = len(tools or [])
            custom_field_keys = sorted(list(custom_fields.keys())) if isinstance(custom_fields, dict) else []

#             self.manager.log(
#                 "debug:request",
#                 json.dumps({
#                     "base_url": api_config.get("url"),
#                     "model": core.config.get("model", "name"),
#                     "stream": stream,
#                     "use_thinking": use_thinking,
#                     "message_count": len(context),
#                     "tool_count": tool_count,
#                     "max_completion_tokens": req.get("max_completion_tokens"),
#                     "temperature": req.get("temperature"),
#                     "reasoning_effort": req.get("reasoning_effort"),
#                     "custom_field_keys": custom_field_keys,
#                     "messages": message_summary,
#                 }, ensure_ascii=True, sort_keys=True)
#             )

        response = None
        attempt = 1
        retried_without_extras = False
        retried_without_timings = False
        try:
            # retry loop
            while True:
                try:
                    # if at this point a cancel was already requested,
                    # it was likely from a toolcalling chain, so abort EVERYTHING
                    if self.cancel_request:
                        raise asyncio.CancelledError("Request cancelled")

                    request_task = asyncio.create_task(self._post_chat_completion(req, stream=stream, api_url=api_url, api_key=api_key))
                    # keep a reference so cancel() can abort a request that
                    # is still in-flight (before streaming started)
                    self._request_task = request_task

                    # wrap the request in a task that we can poll for cancellation,
                    # so a cancel aborts no matter what
                    try:
                        while not request_task.done():
                            if self.cancel_request:
                                request_task.cancel()
                            await asyncio.sleep(0.1)

                        response = await request_task
                    except asyncio.CancelledError:
                        if not request_task.done():
                            request_task.cancel()
                        raise
                    finally:
                        self._request_task = None

                    if retried_without_extras:
                        self._extras_rejected.add(endpoint)
                    if retried_without_timings:
                        self._live_timings_rejected.add(endpoint)
                    break

                except (APIHTTPError, aiohttp.ClientError, asyncio.TimeoutError) as e:
                    if isinstance(e, APIHTTPError) and e.status == 400 and not self.cancel_request:
                        # A proxy can forward to engines that reject live timings.
                        if auto_timings and "timings_per_token" in req:
                            req.pop("timings_per_token")
                            retried_without_timings = True
                            continue
                        if any(field in req for field in llama_extras):
                            for field in llama_extras:
                                req.pop(field, None)
                            retried_without_extras = True
                            continue

                    if attempt >= self.MAX_API_ATTEMPTS or not self._is_retryable_error(e) or self.cancel_request:
                        raise

                    delay = self.RETRY_BASE_DELAY * attempt
                    self.manager.log(
                        "API",
                        f"request failed ({type(e).__name__}), retrying in {delay:.1f}s "
                        f"(attempt {attempt + 1}/{self.MAX_API_ATTEMPTS})"
                    )

                    # wait with backoff, while staying responsive to cancellation
                    waited = 0.0
                    while waited < delay:
                        if self.cancel_request:
                            raise asyncio.CancelledError("Request cancelled")
                        await asyncio.sleep(0.1)
                        waited += 0.1
                    attempt += 1

        except asyncio.CancelledError as e:
            self.cancel_request = False

            # and propagate it up for any other stuff to handle
            raise

        except APIHTTPError as e:
            return self._error_for_status(e.status, e.body)

        except aiohttp.ClientError as e:
            return APIError("Failed to connect to API", e)

        except Exception as e:
            return APIError(None, e)

        finally:
            self.cancel_request = False
            self._request_task = None

#         if core.debug:
#             self.manager.log("debug:response", str(response))

        if isinstance(response, dict) and (timings := _generation_timings(response)):
            response["timings"] = timings
        return response

    async def send(self, context: list, system_prompt=True, use_tools=True, tools=None, use_thinking=True, **kwargs):
        """send a message to the LLM."""

        self.cancel_request = False

        # attempt auto-reconnect once
        await self.attempt_connect()

        # use default tools if not specified. allow overrides
        if tools is None:
            tools = self.manager.tools

        try:
            response = await self._request(context, tools=(tools if use_tools else None), use_thinking=use_thinking, **kwargs)
        except Exception as e:
            raise APIError("While sending request to AI", e) from e

        if isinstance(response, APIError):
            raise response

        try:
            result = await self._recv(response, use_tools=use_tools and bool(tools))
            return result
        except Exception as e:
            raise APIError("While processing response from AI", e) from e

    async def send_stream(self, context: list, use_tools=True, tools=None, use_thinking=True, **kwargs):
        """send a message to the LLM. is an iterable async generator"""

        self.cancel_request = False
        # Each model call, including a tool follow-up, starts with an empty decode rate.
        yield {"type": "timings", "content": None}

        # attempt auto-reconnect once
        try:
            await self.attempt_connect()
        except APIError as e:
            yield {"type": "error", "content": str(e)}
            return

        # use default tools if not specified. allow overrides
        if tools is None:
            tools = self.manager.tools

        # against a llama.cpp router, the request below blocks while a model
        # is swapped in. run the SSE load watcher alongside it and yield
        # model_load_progress tokens until the request resolves.
        load_task = None
        load_queue = None

        if self._router_origin:
            load_queue = asyncio.Queue()
            load_task = asyncio.create_task(self._watch_model_load(core.config.get("model", "name"), load_queue))

        request_task = asyncio.create_task(self._request(context, tools=(tools if use_tools else None), stream=True, use_thinking=use_thinking, **kwargs))

        response = None
        try:
            while True:
                while load_queue and not load_queue.empty():
                    yield {"type": "model_load_progress", "content": load_queue.get_nowait()}

                if request_task.done():
                    break

                await asyncio.wait([request_task], timeout=0.25)

            response = await request_task

        finally:
            if load_task and not load_task.done():
                load_task.cancel()

            # if we bailed out before the request resolved (cancel, generator
            # closed early, etc.), make sure the request itself is aborted too
            if response is None and not request_task.done():
                request_task.cancel()

        # return errors if applicable
        if isinstance(response, APIError):
            yield {"type": "error", "content": str(response)}
            return

        try:
            self.is_streaming = True
            # expose the live SSE response so cancel() can abort the blocked read
            self._stream_response = response

            # a router swapping the model in can end the request right after its
            # load banner, yielding no real tokens at all; one retry then hits
            # the loaded model and returns the actual answer
            for attempt in (0, 1):
                saw_output = False

                async for token in self._recv_stream(response, use_tools=use_tools and bool(tools)):
                    if self.cancel_request:
                        # cancel the entire stream
                        raise asyncio.CancelledError("Request cancelled")

                    if token.get("type") in ("content", "reasoning", "tool_calls", "tool_call_delta"):
                        saw_output = True

                    if core.debug_stream:
                        self.manager.log("debug:stream", json.dumps(token, ensure_ascii=True))

                    # let the channel calling send_stream() handle token processing
                    yield token

                if saw_output or attempt:
                    break

                if response is not None and hasattr(response, "close"):
                    response.close()

                # the failed attempt started the swap; wait for it to finish so
                # the retry doesn't just collect another load banner
                await self._wait_for_model_loaded()
                if self.cancel_request:
                    break

                response = await self._request(context, tools=(tools if use_tools else None), stream=True, use_thinking=use_thinking, **kwargs)
                if isinstance(response, APIError):
                    yield {"type": "error", "content": str(response)}
                    break
        except asyncio.CancelledError:
            self.cancel_request = False
            raise  # let callers handle cancellation
        except Exception as e:
            if self.cancel_request:
                self.cancel_request = False
                raise asyncio.CancelledError("Request cancelled")
            yield {"type": "error", "content": f"While sending request to AI: {core.detail_error(e)}"}
        finally:
            self.is_streaming = False
            self._stream_response = None

            # make sure the SSE connection is always released
            if response is not None and not isinstance(response, APIError) and hasattr(response, "close"):
                response.close()

    async def cancel(self):
        """
        cancel a request that's been sent to the AI.
        safe to call at any time, also when nothing is active.
        """
        self.cancel_request = True

        request_task = self._request_task
        if request_task and not request_task.done():
            # request is in-flight but not streaming yet
            request_task.cancel()

        if self._stream_response is not None:
            try:
                self._stream_response.close()
            except Exception:
                pass

        if not self.is_streaming and not (request_task and not request_task.done()):
            # nothing was active, so clear the flag
            self.cancel_request = False
            return False

        # wait for the cancellation to complete
        waited = 0.0
        while self.cancel_request and waited < 2.0:
            await asyncio.sleep(0.05)
            waited += 0.05

        return not self.cancel_request

    async def _recv(self, response, use_tools=True):
        """takes a response dict and extracts the message from it, handling tool calls if needed"""

        try:
            # normal non-streaming mode
            response_main = response["choices"][0]
        except Exception as e:
            raise e # raise it so send() can catch it

        message = response_main.get("message") or {}

        reasoning_content = message.get("reasoning_content") or message.get("reasoning") or ""

        if reasoning_content and core.debug:
            self.manager.log("debug:reasoning", reasoning_content)

        # extract message content
        final_content = message.get("content") or ""

        # handle tool calls, if any
        tool_calls = None
        if use_tools and core.config.get("model").get("use_tools", False) and message.get("tool_calls"):
            tool_calls = [copy.deepcopy(tc) for tc in message.get("tool_calls")]

        result = {}

        if final_content:
            result["content"] = final_content
        if reasoning_content:
            result["reasoning_content"] = reasoning_content
        if tool_calls:
            result["tool_calls"] = tool_calls

        # role is always assistant, so we force it if for some reason its not present
        result["role"] = "assistant"

        return result

    async def _recv_stream(self, response, use_tools=True):
        """
        Takes a HTTP SSE response object and yields tokens from it,
        handling tool calls if needed. Streaming version.
        """
        final_tool_calls = []
        tool_call_buffer = {}

        token_usage = None
        total_prompt_tokens = 0
        total_completion_tokens = 0
        last_timing_at = -math.inf

        # llama.cpp router load-banner detection (see the reasoning branch below)
        loader_probe = ""
        loader_stream = False
        content_seen = False

        if not response:
            return

        response_started = False
        try:
            async for chunk in http_sse.iter_events(response):
                if not response_started:
                    # mark it as started so that we can detect if the API has returned a blank message
                    # (for example due to an error the inference server, i.e. llamacpp, failed to send)
                    response_started = True

                if self.cancel_request:
                    # closing the response severs the HTTP connection immediately
                    response.close()
                    raise asyncio.CancelledError("Request cancelled")

                if chunk.get("error") is not None or chunk.get("event") == "error":
					# surface errors if they appear
                    err = chunk.get("error")
                    message = None
                    if isinstance(err, dict):
                        inner = err.get("error")
                        message = err.get("message")
                        if message is None and isinstance(inner, dict):
                            message = inner.get("message")
                        elif message is None and isinstance(inner, str):
                            message = inner
                        if message is None:
                            message = json.dumps(err)
                    elif err is not None:
                        message = str(err)
                    if not message:
                        message = "The API reported an error while streaming the response."

                    yield {"type": "error", "content": str(message)}
                    return

                # uncomment if trying to see token stream chunks
                #print(chunk)

                if chunk.get("prompt_progress") is not None:
                    yield {
                        "type": "prompt_progress",
                        "content": chunk.get("prompt_progress")
                    }

                choices = chunk.get("choices") or []
                if choices:
                    streamed_token = choices[0].get("delta") or {}

                    content_part = streamed_token.get("content")
                    reason_part = streamed_token.get("reasoning_content") or streamed_token.get("reasoning")

                    # llama.cpp routers stream their own "loading model" banner as
                    # reasoning tokens while swapping a model in (e.g. after an
                    # image tool used another model). it is not model output, so
                    # detect it once and drop the reasoning for that response
                    if reason_part and not loader_stream and not content_seen:
                        loader_probe = (loader_probe + reason_part)[:200]
                        if loader_probe.lstrip().startswith("━") or "llama-swap loading model" in loader_probe:
                            loader_stream = True
                    if reason_part and loader_stream:
                        reason_part = None
                    if content_part:
                        content_seen = True

                    # a single chunk can carry both (servers often batch the last
                    # reasoning delta with the first content delta), so emit each
                    # separately instead of letting reasoning overwrite content
                    # reasoning logically precedes content: servers batch the
                    # last reasoning delta with the first content delta, and
                    # emitting content first would split the reply's first
                    # token into a separate segment
                    emitted = []
                    if reason_part:
                        emitted.append({"type": "reasoning", "content": reason_part})
                    if content_part:
                        emitted.append({"type": "content", "content": content_part})

                    # and finally, yield the content token
                    for token in emitted:
                        yield token

                    # extract tool calls, if any
                    if streamed_token.get("tool_calls") and use_tools:
                        for tool_call in streamed_token["tool_calls"]:
                            index = tool_call.get("index", 0)

                            if index not in tool_call_buffer:
                                tool_call_buffer[index] = copy.deepcopy(tool_call)
                                # ensure arguments is always a string
                                if tool_call_buffer[index].get("function", {}).get("arguments") is None:
                                    tool_call_buffer[index].setdefault("function", {})["arguments"] = ""

                                yield {
                                    "type": "tool_call_delta",
                                    "tool_calls": [copy.deepcopy(tool_call_buffer[index])]
                                }
                            else:
                                # it seems these properties will only show up in one chunk,
                                # and the rest of the stream won't have them anymore..
                                # so the AI decided we should set these if they show up
                                # and then just assume it won't happen again
                                # i guess if it does, it just overwrites it..
                                if tool_call.get("id"):
                                    tool_call_buffer[index]["id"] = tool_call["id"]

                                incoming_fn = tool_call.get("function") or {}
                                buffer_fn = tool_call_buffer[index].setdefault("function", {})

                                if incoming_fn.get("name"):
                                    buffer_fn["name"] = incoming_fn["name"]

                                # function arguments seem to be the part that actually gets streamed
                                # and which we must accumulate to get the full toolcall
                                if incoming_fn.get("arguments"):
                                    buffer_fn["arguments"] = buffer_fn.get("arguments", "") + incoming_fn["arguments"]

                                    # the magic sauce that allows streaming toolcall arguments
                                    yield {
                                        "type": "tool_call_delta",
                                        "tool_calls": [copy.deepcopy(tool_call_buffer[index])]
                                    }

                if chunk.get("timings") or chunk.get("metrics"):
                    now = time.monotonic()
                    final = not choices or choices[0].get("finish_reason") is not None
                    if final or now - last_timing_at >= 0.25:
                        if timings := _generation_timings(chunk):
                            yield {"type": "timings", "content": timings}
                            last_timing_at = now

                # Keep the existing context count and forward the provider's usage breakdown.
                usage = chunk.get("usage")
                if isinstance(usage, dict):
                    if usage.get("prompt_tokens") is not None:
                        total_prompt_tokens = usage["prompt_tokens"]
                    if usage.get("completion_tokens") is not None:
                        total_completion_tokens = usage["completion_tokens"]

                    token_usage = 0
                    if total_prompt_tokens > 0:
                        token_usage = total_prompt_tokens
                    elif total_completion_tokens > 0:
                        # API gave us no prompt count, fall back to what we have
                        token_usage = total_completion_tokens

                    if token_usage > 0:
                        yield {"type": "token_usage", "content": token_usage, "source": "API", "usage": usage}

            if use_tools:
                for index in sorted(tool_call_buffer.keys()):
                    # filter out blank tool calls (rare model glitch)
                    tool_call = tool_call_buffer[index]
                    if not (tool_call.get("function") or {}).get("name"):
                        continue

                    final_tool_calls.append(tool_call)

                if final_tool_calls and core.config.get("model").get("use_tools", False):
                    # yield the full toolcall object as a single token to be interpreted by the function that is iterating through _recv_stream()
                    tool_call_dicts = [copy.deepcopy(tc) for tc in final_tool_calls]
                    yield {"type": "tool_calls", "tool_calls": tool_call_dicts}

        except Exception as e:
            raise e # Re-raise so send_stream can catch it and yield the error type

        finally:
            # release the connection back to the pool (or close it if the stream ended early)
            if hasattr(response, "close"):
                response.close()

        if not response_started:
            # this means the inference server (such as llamacpp) failed to report an error
            # for user friendliness, we just display a message that explains what happened
            raise Exception("The API returned a blank response. This likely means an error happened on the API end, but that API failed to report the error. Check your AI server's logs if you're using local AI, or if not, contact your cloud AI service. Also, try turning off `Use Developer Role` in the api settings, as some models don't support it.")

    async def model_choices(self, cached=False):
        """Provider catalog, with endpoint discovery only for legacy configurations."""
        providers = self.get_providers()
        if any(provider["models"] for provider in providers) or (providers and not any(p["enabled"] for p in providers)):
            choices = [{"id": model["id"], "provider_id": provider["id"], "enabled": model["enabled"],
                        "is_image": bool(model.get("is_image"))}
                       for provider in providers if provider["enabled"] for model in provider["models"]]
        else:
            endpoint = (core.config.get("api", "url"), core.config.get("api", "key"))
            if not cached or not self._legacy_model_cache or self._legacy_model_cache[0] != endpoint:
                names = await self.list_models()
                self._legacy_model_cache = (endpoint, names) if names else None
            else:
                names = self._legacy_model_cache[1]
            disabled = {name.casefold() for name in self.get_disabled_models()}
            image_model = self.get_image_model()
            choices = [{"id": name, "provider_id": "", "enabled": name.casefold() not in disabled,
                        "is_image": name == image_model} for name in names]
        return choices

    async def list_models(self):
        if not self.connected:
            await self.attempt_connect()

        try:
            # get alphabetically sorted model list
            status, body = await self._http_get(f"{core.config.get('api', 'url')}/models")

            if status != 200:
                raise APIHTTPError(status, body)

            body = json.loads(body)

            model_list = [model["id"] for model in body.get("data", []) if isinstance(model, dict) and model.get("id")]
            model_list.sort()

        except Exception as e:
            self.manager.log_error("error while retrieving model list", e)
            return []

        return model_list
