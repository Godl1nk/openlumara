import core
import inspect
import json_repair
import regex as re

META_TOOL_NAMES = {"tools_load", "tools_call"}

_TYPE_MAP = {str: "string", int: "integer", bool: "boolean", list: "array", dict: "object"}
_ARG_SECTION = "Args:"
_END_SECTIONS = ("Returns:", "Raises:", "Note:", "Example:")
_ALL_SECTIONS = (_ARG_SECTION,) + _END_SECTIONS
_PARAM_RE = re.compile(r"(\w+)(?:\s*\([^)]*\))?\s*:\s*(.+)")


class ToolLoader:
    """Manages dynamic tool loading: catalog, active set, the tools_load meta tool,
    and the cache-stable tool bridge (tools_call)."""

    def __init__(self, channel):
        self.channel = channel
        self.catalog = {}  # name -> {"tool": dict, "module": str, "method": str, "description": str}
        self.active_tools = []  # tool dicts sent to the API
        self.active_names = []  # active tool names
        self._meta_def = None  # tools_load meta tool dict (part of the baseline)
        self._bridge_defs = []  # tools_call bridge defs (part of the baseline)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def parse_tool_docstring(self, docstring):
        """Parse a Google-style docstring into (param_descriptions, clean_description)."""
        if not docstring:
            return {}, ""

        lines = docstring.split("\n")

        # clean description: drop section headers and their indented bodies
        clean_lines = []
        skip = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith(_ALL_SECTIONS):
                skip = True
            elif skip and (not stripped or not line[:1].isspace()):
                skip = False
                if stripped:
                    clean_lines.append(line)
            elif not skip:
                clean_lines.append(line)

        # param descriptions from the Args: section
        descriptions = {}
        in_args = False
        current_param = None
        current_desc = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith(_ARG_SECTION):
                in_args = True
            elif in_args and stripped in _END_SECTIONS:
                break
            elif in_args and stripped:
                match = _PARAM_RE.match(stripped)
                if match:
                    if current_param and current_desc:
                        descriptions[current_param] = " ".join(current_desc)
                    current_param = match.group(1)
                    current_desc = [match.group(2)]
                elif current_param:
                    current_desc.append(stripped)
        if current_param and current_desc:
            descriptions[current_param] = " ".join(current_desc)

        return descriptions, "\n".join(clean_lines).strip()

    def _tool_dict_from_func(self, func, tool_name):
        """Build an API tool dict from a callable."""
        param_descriptions, docstring = self.parse_tool_docstring(func.__doc__)

        properties = {}
        required = []
        for name, param in inspect.signature(func).parameters.items():
            prop = {"type": _TYPE_MAP.get(param.annotation, "string")}
            desc = param_descriptions.get(name)
            if desc:
                prop["description"] = desc
            properties[name] = prop
            if param.default == inspect.Parameter.empty:
                required.append(name)

        tool = {
            "type": "function",
            "function": {
                "name": tool_name,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                    "additionalProperties": False,
                },
                "strict": False,
            },
        }
        if docstring:
            tool["function"]["description"] = docstring
        return tool

    def _loadable_entry(self, name):
        """Return the catalog entry for a tool if loadable, else None.

        Loadable means: in the catalog, its module is enabled, and the tool
        itself is not disabled.
        """
        entry = self.catalog.get(name)
        if entry is None:
            return None
        module = self.channel.manager.modules.get(entry["module"])
        if module is None or entry["method"] in module.disabled_tools:
            return None
        return entry

    def _preloaded_modules(self):
        """Module names whose tools are preloaded at startup (model.preloaded_modules)."""
        modules = core.config.get("model", "preloaded_modules", default=[])
        return {str(m).lower() for m in modules} if isinstance(modules, list) else set()

    def _default_tools(self):
        """Cataloged tools belonging to the preloaded modules, as {name: entry}."""
        preloaded = self._preloaded_modules()
        return {
            name: entry for name, entry in self.catalog.items()
            if entry["module"] in preloaded
        }

    # ------------------------------------------------------------------
    # Catalog management
    # ------------------------------------------------------------------

    def register_module(self, module):
        """Scan a module for tool methods and add them to the catalog."""
        for func_name in type(module).__dict__:
            if func_name.startswith("_") or func_name in module.disabled_tools:
                continue
            if func_name == "result" or func_name.startswith("on_"):
                continue
            func_obj = getattr(module, func_name, None)
            if not callable(func_obj) or getattr(func_obj, "_is_command", False):
                continue

            tool_name = f"{module.name}_{func_name}"
            tool_dict = self._tool_dict_from_func(func_obj, tool_name)
            self.catalog[tool_name] = {
                "tool": tool_dict,
                "module": module.name,
                "method": func_name,
                "description": tool_dict["function"].get("description", ""),
            }

    def unregister_module(self, module):
        """Remove all catalog entries and active tools for a module."""
        prefix = f"{module.name}_"
        removed = [k for k in self.catalog if k.startswith(prefix)]
        for k in removed:
            del self.catalog[k]

        self.active_tools = [
            t for t in self.active_tools
            if not t["function"]["name"].startswith(prefix)
        ]
        self.active_names = [n for n in self.active_names if not n.startswith(prefix)]

    # ------------------------------------------------------------------
    # Meta tool
    # ------------------------------------------------------------------

    @property
    def meta_tool_names(self):
        return META_TOOL_NAMES

    def _enabled_module_names(self):
        """Names of all currently enabled (loaded) modules that have tools"""
        modules_with_tools = {entry["module"] for entry in self.catalog.values()}
        return sorted(
            name for name in self.channel.manager.modules
            if name in modules_with_tools
        )

    def _build_meta_def(self):
        """Build the tools_load meta tool definition."""
        modules = ", ".join(self._enabled_module_names()) or "(none currently enabled)"
        return {
            "type": "function",
            "function": {
                "name": "tools_load",
                "description": (
                    "Returns full schemas of all tools in the modules you request"
                    ", as array. Tools are NOT added to your tool list: call "
                    "them with tools_call using returned schemas."
                    f"Currently enabled modules: {modules}"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "module_names": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Names of the modules whose tool schemas to return",
                        }
                    },
                    "required": ["module_names"],
                    "additionalProperties": False,
                },
                "strict": False,
            },
        }

    # ------------------------------------------------------------------
    # Tool bridge (cache-stable dynamic invocation)
    # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-15) harness:openlumara
    # -- REDESIGNED (Qwen3.8 Flash Next) :: (2026-10-21) harness:openlumara
    # Progressive disclosure without ever touching the active tools array
    # (any change to it invalidates the request prefix and blows the
    # provider prompt cache): tools_load returns the schemas of a module's
    # tools as a tool result (append-only, so the cache survives) and the
    # model invokes them through the generic tools_call bridge. The model
    # only ever needs module names (listed in the tools_load description);
    # no per-tool catalog is embedded anywhere. The active array holds
    # exactly: the meta tools, the preloaded modules' tools, and (legacy)
    # tools restored from the chat's persisted modules. With
    # dynamic_tool_loading off the whole system is bypassed and every tool
    # registers natively.
    # ------------------------------------------------------------------

    def _build_bridge_defs(self):
        """Build the tools_call bridge tool definition."""
        call = {
            "type": "function",
            "function": {
                "name": "tools_call",
                "description": (
                    "Calls tool directly by name. If do not know tool's "
                    "params, call tools_load with module name first to get "
                    "schemas. Arguments are validated against tool's schema before it "
                    "runs; invalid calls are rejected with valid parameter "
                    "list."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Exact tool name to call"},
                        # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-21) harness:openlumara
                        # arguments is TRANSPORTED as a JSON-encoded string on purpose:
                        # string-typed fields stream token by token, while object-typed
                        # nested values arrive as one atomic chunk from the model server
                        # (verified in the bridge debug log) - which made long bridged
                        # args pop in all at once instead of streaming. execution-side
                        # coercion of str -> dict already exists in tools_call(), and a
                        # model that emits a raw object anyway keeps working.
                        "arguments": {
                            "type": "string",
                            "description": (
                                "JSON-encoded arguments object for the tool, matching "
                                "its schema. Example: {\"path\": \"foo.py\", \"content\": \"...\"}"
                            ),
                        },
                    },
                    "required": ["name", "arguments"],
                    "additionalProperties": False,
                },
                "strict": False,
            },
        }
        return [call]

    def _replace_def_in_active(self, tool_def):
        """Swap a tool def into the active list in place (order-preserving)."""
        for i, tool in enumerate(self.active_tools):
            if tool["function"]["name"] == tool_def["function"]["name"]:
                self.active_tools[i] = tool_def
                return
        self.active_tools.append(tool_def)

    def register_meta_tools(self):
        """Register the tools_load meta tool and the tool bridge."""
        if not core.config.get("model", "dynamic_tool_loading", default=True):
            return
        if self._meta_def:
            return

        self._meta_def = self._build_meta_def()
        self._bridge_defs = self._build_bridge_defs()
        self.active_tools = [self._meta_def] + self._bridge_defs
        self.active_names = ["tools_load", "tools_call"]

    def refresh_meta_tool_descriptions(self):
        """Rebuild the dynamic meta tool and bridge descriptions with the current catalog."""
        if not self._meta_def:
            return
        self._meta_def = self._build_meta_def()
        self._bridge_defs = self._build_bridge_defs()
        self._replace_def_in_active(self._meta_def)
        for tool_def in self._bridge_defs:
            self._replace_def_in_active(tool_def)

    def get_meta_callable(self, tool_name):
        """Return the bound method for a meta tool name."""
        if tool_name == "tools_load":
            return self.tools_load
        if tool_name == "tools_call":
            return self.tools_call
        return None

    # ------------------------------------------------------------------
    # Active set management
    # ------------------------------------------------------------------

    def _baseline_tools(self):
        """(tools, names) for the baseline: meta tool + bridge + loadable default-module tools."""
        tools, names = [], []
        if self._meta_def:
            tools.append(self._meta_def)
            names.append("tools_load")
            for tool_def in self._bridge_defs:
                tools.append(tool_def)
                names.append(tool_def["function"]["name"])
        for name, entry in self._default_tools().items():
            if name in names or self._loadable_entry(name) is None:
                continue
            tools.append(entry["tool"])
            names.append(name)
        return tools, names

    def load_default_tools(self):
        """Preload all tools of the preloaded modules"""
        if not core.config.get("model", "dynamic_tool_loading", default=True):
            return
        if not self._meta_def:
            return

        loaded = []
        for name, entry in self._default_tools().items():
            if name in self.active_names or self._loadable_entry(name) is None:
                continue
            self.active_tools.append(entry["tool"])
            self.active_names.append(name)
            loaded.append(name)

        if loaded:
            # keep the meta tool descriptions in sync with the active set
            self.refresh_meta_tool_descriptions()

    def reset_for_new_chat(self):
        """Reset active tools to the baseline (meta tool + bridge + default tools)."""
        if core.config.get("model", "dynamic_tool_loading", default=True):
            self.active_tools, self.active_names = self._baseline_tools()
            # refresh meta tool descriptions to reflect the reset active set
            self.refresh_meta_tool_descriptions()
        else:
            self.active_tools = []
            self.active_names = []
            self.load_all_tools()

    def load_all_tools(self):
        """Load every loadable tool from the catalog into the active set."""
        for name in self.catalog:
            entry = self._loadable_entry(name)
            if entry is None or name in self.active_names:
                continue
            self.active_tools.append(entry["tool"])
            self.active_names.append(name)

    # ------------------------------------------------------------------
    # Per-chat tool persistence
    # ------------------------------------------------------------------

    def get_active_non_baseline_modules(self):
        """Modules whose tools are active but that are NOT part of the baseline.

        This is the set of modules the AI explicitly loaded for this chat; it
        gets persisted per-chat so it can be restored on load.
        """
        baseline_modules = self._preloaded_modules()
        modules = set()
        for name in self.active_names:
            entry = self.catalog.get(name)
            if entry is None or entry["module"] in baseline_modules:
                continue
            modules.add(entry["module"])
        return sorted(modules)

    def persist_active_tools(self):
        """Persist active non-baseline modules to the chat's metadata (no-op if no chat)."""
        chat = self.channel.context.chat
        if chat is None or chat.current is None:
            return
        chat.set_loaded_modules(self.get_active_non_baseline_modules())

    def restore_chat_tools(self):
        """Load the modules persisted in the chat's metadata (call after reset_for_new_chat)."""
        chat = self.channel.context.chat
        if chat is None or chat.current is None:
            return
        for module_name in chat.get_loaded_modules():
            self.activate_module_tools(module_name)

    # ------------------------------------------------------------------
    # Meta tool implementation
    # ------------------------------------------------------------------

    def activate_module_tools(self, module_name):
        """Load all cataloged tools of an enabled module (legacy: kept only to
        restore chats persisted under the pre-2026-10-21 native-loading design;
        tools_load itself now returns schemas instead of activating)"""
        module_name = str(module_name).lower().strip()
        module = self.channel.manager.modules.get(module_name)
        if module is None:
            return {
                "status": "error",
                "unknown_module": module_name,
                "enabled_modules": self._enabled_module_names(),
            }

        loaded = []
        already_loaded = []
        disabled = []
        for name, entry in self.catalog.items():
            if entry["module"] != module_name:
                continue
            if entry["method"] in module.disabled_tools:
                disabled.append(name)
            elif name in self.active_names:
                already_loaded.append(name)
            else:
                self.active_tools.append(entry["tool"])
                self.active_names.append(name)
                loaded.append(name)

        result = {"loaded": loaded, "already_loaded": already_loaded}
        if disabled:
            result["disabled"] = disabled
        if loaded:
            # the active array changed; keep the meta tool descriptions in sync
            self.refresh_meta_tool_descriptions()
        return result

    # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-21) harness:openlumara
    # tools_load no longer mutates the active tools array (a prefix change that
    # blows the provider prompt cache): it returns the schemas of the modules'
    # tools directly, and the model invokes them via the tools_call bridge.
    async def tools_load(self, module_names: list):
        """Returns the full parameter schemas of all tools in the given modules.

        The tools are not added to your tool list; call them with tools_call
        using the returned schemas.

        Args:
        module_names (list): Names of the modules whose tool schemas to return
        """
        if isinstance(module_names, str):
            module_names = [module_names]
        if not isinstance(module_names, list):
            return {"status": "error", "content": "module_names must be a list of module names"}

        tools = []
        unknown = []
        disabled = []
        for module_name in module_names:
            name = str(module_name).lower().strip()
            module = self.channel.manager.modules.get(name)
            if module is None:
                unknown.append(name)
                continue
            for tool_name, entry in sorted(self.catalog.items()):
                if entry["module"] != name:
                    continue
                if entry["method"] in module.disabled_tools:
                    disabled.append(tool_name)
                    continue
                func = entry["tool"]["function"]
                tools.append({
                    "name": tool_name,
                    "description": func.get("description", ""),
                    "parameters": func.get("parameters", {}),
                })

        if not tools:
            if unknown:
                return {
                    "status": "error",
                    "content": (
                        f"No enabled module named '{unknown[0]}'"
                        + (f" (also unknown: {', '.join(unknown[1:])})" if len(unknown) > 1 else "")
                        + f". Enabled modules: {', '.join(self._enabled_module_names())}."
                    ),
                }
            return {
                "status": "error",
                "content": "None of those modules have loadable tools.",
            }

        result = {
            "status": "success",
            "tools": tools,
            "note": "These tools are not in your tool list; call them with tools_call(name, arguments).",
        }
        if unknown:
            result["not_found"] = unknown
            result["enabled_modules"] = self._enabled_module_names()
        if disabled:
            result["disabled"] = disabled
        return result

    # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-21) harness:openlumara
    # Schema pre-validation for the bridge. Without it, a bad kwarg survives
    # until the real method call and blows up deep inside the tool with a raw
    # TypeError, which toolcalls.py can only report as a generic execution
    # error. Pre-binding against the target signature rejects unknown/missing
    # arguments and type mismatches before any side effects happen, and the
    # error lists the valid parameters so the model can recover in one retry.
    # Simple annotated types are coerced leniently (stringified numbers are a
    # common model slip) to skip even that retry; unannotated or exotic
    # annotations are left unchecked so previously-working calls never break.

    _NAME_TO_TYPE = {"str": str, "int": int, "bool": bool, "list": list, "dict": dict}

    def _simple_annotation(self, annotation):
        """Return the raw type for simple annotations (incl. stringized ones), else None."""
        if isinstance(annotation, str):
            return self._NAME_TO_TYPE.get(annotation)
        try:
            if annotation in _TYPE_MAP:
                return annotation
        except TypeError:  # unhashable annotation
            return None
        return None

    @staticmethod
    def _coerce_arg(value, target):
        """Leniently coerce a JSON value to a simply-annotated parameter type. Returns (value, ok)."""
        if target is int and isinstance(value, bool):
            return value, False
        if isinstance(value, target):
            return value, True
        if target is int:
            if isinstance(value, str) and re.fullmatch(r"[+-]?\d+", value.strip()):
                return int(value.strip()), True
            if isinstance(value, float) and value.is_integer():
                return int(value), True
        elif target is bool:
            if isinstance(value, int):
                return bool(value), True
            if isinstance(value, str) and value.strip().lower() in ("true", "false"):
                return value.strip().lower() == "true", True
        elif target is str:
            if isinstance(value, (int, float)):
                return str(value), True
        return value, False

    def _param_summary(self, sig):
        """Render 'name: type (required)' for each parameter of a signature."""
        parts = []
        for name, param in sig.parameters.items():
            target = self._simple_annotation(param.annotation)
            label = _TYPE_MAP[target] if target else "any"
            marker = "" if param.default is not inspect.Parameter.empty else " (required)"
            parts.append(f"{name}: {label}{marker}")
        return ", ".join(parts) if parts else "(none)"

    def _preflight_args(self, func, tool_name, arguments):
        """Check arguments against the target function's signature before dispatch.

        Returns (clean_arguments, None) if the call can proceed (possibly with
        coerced values), or (None, error_message) if it would raise before
        reaching the tool body.
        """
        try:
            sig = inspect.signature(func)
        except (TypeError, ValueError):
            return arguments, None  # exotic callable; don't block on introspection
        try:
            sig.bind(**arguments)
        except TypeError as exc:
            return None, (
                f"Invalid arguments for '{tool_name}': {exc}. "
                f"Valid parameters: {self._param_summary(sig)}. "
                "Call tools_load with this tool's module name to get the full schema."
            )

        coerced = {}
        mismatches = []
        for key, value in arguments.items():
            param = sig.parameters.get(key)
            target = self._simple_annotation(param.annotation) if param is not None else None
            if target is None or value is None:
                # unknown extra keys already rejected by sig.bind; anything
                # consumed by *args/**kwargs, unannotated, or an explicit None
                # (Optional-style params) passes through untouched
                coerced[key] = value
                continue
            new_value, ok = self._coerce_arg(value, target)
            if ok:
                coerced[key] = new_value
            else:
                mismatches.append(
                    f"'{key}' expects {_TYPE_MAP[target]}, got {type(value).__name__}: {value!r}"
                )
        if mismatches:
            return None, (
                f"Invalid arguments for '{tool_name}': " + "; ".join(mismatches)
                + f". Expected: {self._param_summary(sig)}."
            )
        return coerced, None

    async def tools_call(self, name: str, arguments=None):
        """Calls a cataloged tool directly by name without loading it into your toolset.

        Args:
        name (str): Exact name of the tool to call
        arguments (str): JSON-encoded arguments object for the tool, matching its schema (a raw object is accepted too)
        """
        if isinstance(arguments, str):
            # transport format: JSON-encoded string (streams token by token)
            try:
                arguments = json_repair.loads(arguments)
            except Exception:
                return {"status": "error", "content": "arguments is not valid JSON"}
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            return {"status": "error", "content": "arguments must be an object"}

        name = str(name).strip()
        if name in META_TOOL_NAMES:
            return {"status": "error", "content": f"'{name}' is a meta tool; call it directly."}

        entry = self._loadable_entry(name)
        if entry is None:
            if name in self.catalog:
                return {"status": "error", "content": f"Tool '{name}' is disabled (module or tool setting)."}
            return {
                "status": "error",
                "content": (
                    f"No tool named '{name}'. Call tools_load with a module name to get its "
                    f"tools' schemas. Enabled modules: {', '.join(self._enabled_module_names())}."
                ),
            }

        module = self.channel.manager.modules.get(entry["module"])
        if module is None:
            return {"status": "error", "content": f"Module '{entry['module']}' is not enabled."}

        func = getattr(module, entry["method"])
        arguments, preflight_error = self._preflight_args(func, name, arguments)
        if preflight_error:
            self.channel.log("toolcall", f"bridge rejected '{name}': {preflight_error}")
            return {"status": "error", "content": preflight_error}

        result = func(**arguments)
        if inspect.isawaitable(result):
            result = await result
        return result
