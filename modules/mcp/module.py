# -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-11
"""
MCP (Model Context Protocol) client module.

How it works:
- Every configured server gets its own asyncio task that opens the transport,
  keeps the connection alive and cleans it up on shutdown. This is required:
  the MCP SDK's transports use anyio scopes that MUST be entered and exited
  from the same task.
- Each server's tools (via tools/list) are injected straight into every
  channel's ToolLoader catalog as normal OpenAI-format tool definitions.
  Execution works because the core tool executor resolves a catalog entry
  through getattr(module_instance, entry["method"]) - so for every MCP tool we
  simply attach a generated async closure to this module instance under the
  entry's method name. No core changes needed: injected tools behave exactly
  like class-scanned ones (dynamic loading via tools_load, disabled_tools,
  per-chat persistence, timeouts, all inherited for free).
- Tool names follow the pattern mcp_<server>_<tool>, sanitized to
  [a-zA-Z0-9_-] and capped at 64 characters.

State:
- self._servers maps a server name to a single record holding everything
  about that server: its config, connection task, live session, control
  events and status.
"""
import core
import asyncio
import contextlib
import json
import re
import shlex
import urllib.parse

import mcp
import mcp.client.stdio
import mcp.client.streamable_http
import mcp.client.sse


def _flatten_error(exc, depth=0):
    """
    The mcp SDK hides the real cause of failures twice over: anyio wraps
    transport errors in ExceptionGroups ("unhandled errors in a TaskGroup"),
    and MCPError keeps the server's actual JSON-RPC error on .error.
    This digs everything out, including the exception cause chain, so status
    reports say what actually went wrong.
    """
    # anyio ExceptionGroup: collect the sub-exceptions
    subexceptions = getattr(exc, "exceptions", None)
    if subexceptions and depth < 5:
        messages = []
        for sub in subexceptions:
            message = _flatten_error(sub, depth + 1)
            if message not in messages:
                messages.append(message)
        return "; ".join(messages)

    # MCPError: show the server's JSON-RPC error code, message and data
    rpc_error = getattr(exc, "error", None)
    if rpc_error is not None and getattr(rpc_error, "code", None) is not None:
        text = f"{type(exc).__name__} [{rpc_error.code}] {getattr(rpc_error, 'message', '')}".strip()
        if getattr(rpc_error, "data", None):
            text += f" | data: {rpc_error.data}"
    else:
        text = f"{type(exc).__name__}: {exc}"

    # chained causes often hold the true reason
    cause = exc.__cause__ if exc.__cause__ is not None else exc.__context__
    if cause is not None and cause is not exc and depth < 5:
        inner = _flatten_error(cause, depth + 1)
        if inner and inner not in text:
            text += f" <- {inner}"
    return text


def _new_server(cfg):
    """Everything we track about one MCP server lives in this single record."""
    return {
        "cfg": cfg,               # parsed config: type + command/args or url
        "task": None,             # asyncio task owning the connection
        "session": None,          # live ClientSession while connected
        "stop": asyncio.Event(),  # signals the task to shut down
        "ready": asyncio.Event(), # signals startup finished (success or failure)
        "state": "connecting",    # connecting / connected / timeout / error / stopped
        "tools": [],              # catalog names of the tools currently injected
        "error": None,            # last error, flattened to readable text
    }


class Mcp(core.module.Module):
    """Connects to MCP (Model Context Protocol) servers and exposes their tools to your AI as if they were native tools. Supports stdio, streamable HTTP and SSE transports."""

    dependencies = ["mcp>=2"]

    settings = {
        "servers_http": {
            "type": "list",
            "description": "MCP servers reachable over streamable HTTP. One URL per entry, e.g. http://localhost:8000/mcp",
            "default": []
        },
        "servers_sse": {
            "type": "list",
            "description": "MCP servers reachable over legacy SSE. One URL per entry, e.g. http://localhost:9000/sse",
            "default": []
        },
        "servers_stdio": {
            "type": "list",
            "description": "MCP servers launched as local processes. One command line per entry, e.g. uvx mcp-server-time",
            "default": []
        },
        "connect_timeout": {
            "type": "number",
            "description": "Seconds to wait for each MCP server to connect and initialize at startup.",
            "default": 30
        }
    }

    # -------------------------
    #   LIFECYCLE
    # -------------------------

    async def on_ready(self):
        self._servers = {}                  # server name -> record (see _new_server)
        self._parse_error = None
        self._used_names = {"mcp_status"}   # tool names already claimed

        await self._start_servers()

    async def on_shutdown(self):
        await self._stop_servers()

    # -------------------------
    #   CONFIG PARSING
    # -------------------------

    # hostname labels that say nothing about who runs the server
    _GENERIC_HOST_LABELS = ("mcp", "api", "www", "app", "server", "gateway")

    # package runners: for these, the package name is more telling than the runner
    _RUNNERS = ("uvx", "npx", "pnpx", "bunx", "deno", "node", "python", "python3", "py")

    def _set_parse_error(self, message):
        self._parse_error = message
        self.manager.log(self.name, message)

    def _build_server_configs(self):
        """
        Read the three server lists from settings and turn them into
        {name: cfg} entries, where cfg has a "type" plus either
        command/args (stdio) or url (http/sse).
        Malformed entries set self._parse_error but don't block the rest.
        """
        self._parse_error = None
        configs = {}

        sources = (
            ("servers_http", "http"),
            ("servers_sse", "sse"),
            ("servers_stdio", "stdio"),
        )
        for setting_name, transport in sources:
            entries = self.config.get(setting_name, default=[])
            if isinstance(entries, str):
                entries = [entries] if entries.strip() else []
            if not isinstance(entries, list):
                self._set_parse_error(f"'{setting_name}' must be a list")
                continue

            for entry in entries:
                parsed = self._parse_entry(entry, transport, setting_name)
                if parsed is None:
                    continue
                name, cfg = parsed
                configs[self._unique_name(name, configs)] = cfg

        return configs

    def _parse_entry(self, entry, transport, setting_name):
        """Turn one config line into a (name, cfg) tuple, or None if invalid."""
        if not isinstance(entry, str) or not entry.strip():
            return None
        entry = entry.strip()

        if transport == "stdio":
            try:
                argv = shlex.split(entry)
            except ValueError as e:
                self._set_parse_error(f"invalid command in '{setting_name}': '{entry}' ({e})")
                return None
            if not argv:
                return None
            cfg = {"type": "stdio", "command": argv[0], "args": argv[1:]}
            return self._derive_stdio_name(argv), cfg

        cfg = {"type": transport, "url": entry}
        return self._derive_url_name(entry), cfg

    @staticmethod
    def _unique_name(name, taken):
        """Append _2, _3, ... until the name no longer clashes."""
        unique, counter = name, 2
        while unique in taken:
            unique = f"{name}_{counter}"
            counter += 1
        return unique

    @staticmethod
    def _sanitize(text):
        """Reduce arbitrary text to characters that are legal in tool names."""
        text = re.sub(r"[^a-zA-Z0-9_-]", "_", str(text))
        return text.strip("_-") or "unnamed"

    @classmethod
    def _derive_url_name(cls, url):
        """Name a remote server after the first meaningful hostname label:
        mcp.exa.ai -> exa (not mcp, which would double up with the tool prefix)."""
        hostname = urllib.parse.urlparse(url).hostname or ""
        labels = [label for label in hostname.split(".") if label]
        for label in labels:
            if label.lower() not in cls._GENERIC_HOST_LABELS:
                return cls._sanitize(label)
        return "unnamed"

    @classmethod
    def _derive_stdio_name(cls, argv):
        """Name a stdio server after the package it runs, not the runner:
        'uvx mcp-server-time' -> mcp-server-time."""
        command = argv[0].replace("\\", "/").rsplit("/", 1)[-1]
        args = argv[1:]

        if command in cls._RUNNERS:
            if args and args[0] in ("-m", "--module") and len(args) > 1:
                return cls._sanitize(args[1].rsplit(".", 1)[-1])
            for arg in args:
                if not arg.startswith("-"):
                    return cls._sanitize(arg)

        return cls._sanitize(command)

    # -------------------------
    #   CONNECTIONS
    # -------------------------

    async def _start_servers(self):
        configs = self._build_server_configs()
        for name, cfg in configs.items():
            self._servers[name] = _new_server(cfg)

        # launch one connection task per server
        for name, srv in self._servers.items():
            srv["task"] = asyncio.create_task(self._connection_lifecycle(name))

        # ...then wait for them to settle
        timeout = float(self.config.get("connect_timeout", default=30))
        for name, srv in self._servers.items():
            try:
                await asyncio.wait_for(srv["ready"].wait(), timeout=timeout)
            except asyncio.TimeoutError:
                srv["state"] = "timeout"
                srv["error"] = f"did not connect within {timeout}s"
                self.manager.log(self.name, f"server '{name}' timed out while connecting")

    async def _stop_servers(self):
        # ask every connection task to shut down, give them time, then force
        for srv in self._servers.values():
            srv["stop"].set()
        for srv in self._servers.values():
            if srv["task"] is None:
                continue
            try:
                await asyncio.wait_for(srv["task"], timeout=10)
            except Exception:
                srv["task"].cancel()

        for name in list(self._servers):
            self._purge_server(name)

        self._servers = {}

    async def _connection_lifecycle(self, name):
        """
        Owns one server connection from birth to death. Because the SDK's
        transports must be entered and exited by the same task, this whole
        coroutine IS the connection: it opens everything, serves until the
        stop event fires, then unwinds cleanly.
        """
        srv = self._servers[name]
        try:
            async with contextlib.AsyncExitStack() as stack:
                read, write = await stack.enter_async_context(self._open_transport(srv["cfg"]))

                session = await stack.enter_async_context(
                    mcp.ClientSession(read, write, message_handler=self._make_message_handler(name))
                )
                await session.initialize()

                srv["session"] = session
                await self._resync_tools(name)
                srv["state"] = "connected"
                srv["error"] = None
                self.manager.log(self.name, f"server '{name}' connected ({len(srv['tools'])} tools)")
                srv["ready"].set()

                # stay connected until shutdown is requested
                await srv["stop"].wait()

        except Exception as e:
            if srv["state"] != "timeout":
                srv["state"] = "error"
                srv["error"] = _flatten_error(e)
            self.manager.log(self.name, f"server '{name}' stopped: {core.detail_error(e)}")

        finally:
            # always release the startup wait, even on early failure
            srv["ready"].set()
            srv["session"] = None
            if srv["state"] not in ("error", "timeout"):
                srv["state"] = "stopped"
                srv["tools"] = []

    @staticmethod
    def _open_transport(cfg):
        """Return the SDK's async context manager for this entry's transport."""
        if cfg["type"] == "stdio":
            params = mcp.client.stdio.StdioServerParameters(command=cfg["command"], args=cfg["args"])
            return mcp.client.stdio.stdio_client(params)
        if cfg["type"] == "sse":
            return mcp.client.sse.sse_client(cfg["url"])
        return mcp.client.streamable_http.streamable_http_client(cfg["url"])

    def _make_message_handler(self, name):
        """Servers may announce that their tool list changed: re-sync when they do."""
        async def handler(message):
            if type(message).__name__ == "ToolListChangedNotification":
                self.manager.log(self.name, f"server '{name}' announced a tool list change")
                asyncio.create_task(self._resync_tools(name))
        return handler

    # -------------------------
    #   TOOL INJECTION
    # -------------------------

    def _loaders(self):
        """Every channel's ToolLoader: injected tools must exist in all of them."""
        return [ch.tool_loader for ch in self.manager.channels.values()]

    def _tool_name(self, server, tool):
        """Build a unique, legal tool name for a server's tool."""
        name = f"mcp_{self._sanitize(server)}_{self._sanitize(tool)}"[:64].rstrip("_-")

        base, counter = name, 2
        while name in self._used_names:
            name = f"{base[:61]}_{counter}"
            counter += 1
        self._used_names.add(name)
        return name

    def _purge_server(self, name):
        """Remove every injected tool belonging to a server again."""
        srv = self._servers.get(name)
        names = set(srv["tools"]) if srv else set()
        if srv:
            srv["tools"] = []
        self._used_names -= names

        for tool_name in names:
            if tool_name in self.__dict__:
                delattr(self, tool_name)

        for loader in self._loaders():
            loader.catalog = {n: entry for n, entry in loader.catalog.items() if n not in names}
            loader.active_tools = [t for t in loader.active_tools if t["function"]["name"] not in names]
            loader.active_names = [n for n in loader.active_names if n not in names]

    async def _resync_tools(self, name):
        """Fetch a server's current tool list and (re)inject all of it."""
        srv = self._servers.get(name)
        if srv is None or srv["session"] is None:
            return

        try:
            listing = await srv["session"].list_tools()
        except Exception as e:
            self.manager.log(self.name, f"could not list tools for '{name}': {_flatten_error(e)}")
            return

        # remember which tool names chats currently have loaded, to restore that
        was_active = set()
        for loader in self._loaders():
            was_active.update(loader.active_names)

        self._purge_server(name)

        for tool in listing.tools:
            self._inject_tool(name, tool, was_active, srv)
        srv["tools"] = sorted(srv["tools"])

        # keep the tools_load meta tool's module description in sync
        for loader in self._loaders():
            loader.refresh_meta_tool_descriptions()

    def _inject_tool(self, server, tool, was_active, srv):
        """
        Register one MCP tool: build an OpenAI-format definition from the
        server's own JSON Schema, attach a dispatcher closure to this module
        instance, and add a catalog entry to every channel.
        """
        tool_name = self._tool_name(server, tool.name)
        description = tool.description or f"MCP tool '{tool.name}' from server '{server}'."
        definition = {
            "type": "function",
            "function": {
                "name": tool_name,
                "description": description,
                # the server provides a ready-made JSON Schema for its input
                "parameters": tool.input_schema or {"type": "object", "properties": {}}
            }
        }

        # the core executor calls getattr(module, entry["method"]), so this
        # closure is what runs when the AI invokes the tool
        setattr(self, tool_name, self._make_call(server, tool.name))

        for loader in self._loaders():
            loader.catalog[tool_name] = {
                "tool": definition,
                "module": self.name,
                "method": tool_name,
                "description": description
            }
            # if a chat had this tool loaded before the resync, load it again
            if tool_name in was_active and tool_name not in loader.active_names:
                loader.active_tools.append(definition)
                loader.active_names.append(tool_name)

        srv["tools"].append(tool_name)

    def _make_call(self, server, tool_name):
        """Build the dispatcher closure that executes one MCP tool call."""
        async def call(**kwargs):
            srv = self._servers.get(server)
            session = srv["session"] if srv else None
            if session is None:
                return self.result(f"MCP server '{server}' is not connected. Check mcp_status.", success=False)
            try:
                result = await session.call_tool(tool_name, kwargs)
            except Exception as e:
                return self.result(f"MCP call '{tool_name}' failed: {_flatten_error(e)}", success=False)
            return self.result(self._render_result(result), success=not getattr(result, "is_error", False))
        return call

    def _render_result(self, result):
        """Turn an MCP CallToolResult into plain text for the AI.
        (Attribute names are snake_case per the mcp SDK v2 protocol types.)"""
        parts = []
        for block in getattr(result, "content", None) or []:
            if block.type == "text":
                parts.append(block.text)
            elif block.type in ("image", "audio"):
                parts.append(f"[{block.type} content omitted: {block.mime_type}]")
            elif block.type == "resource":
                text = getattr(block.resource, "text", None)
                parts.append(text or f"[binary resource: {getattr(block.resource, 'uri', 'unknown')}]")
            elif block.type == "resource_link":
                parts.append(f"[resource link: {block.uri}]")
            else:
                parts.append(f"[unsupported content: {block.type}]")

        # no text at all: fall back to structured output, if any
        if not any(str(part).strip() for part in parts):
            structured = getattr(result, "structured_content", None)
            return json.dumps(structured) if structured is not None else "(empty result)"
        return "\n".join(str(part) for part in parts)

    # -------------------------
    #   USER-FACING COMMANDS
    # -------------------------

    @core.module.command("mcp", help={
        "": "Shows the status of all configured MCP servers",
        "reload": "Reconnects all MCP servers and refreshes their tools (use after changing the config)"
    })
    async def mcp_command(self, args: list):
        if args and args[0].lower() == "reload":
            await self._stop_servers()
            await self._start_servers()
            lines = ["reloaded MCP servers:"]
        else:
            lines = ["MCP servers:"]

        if not self._servers:
            lines.append("  (none configured)")

        for name, srv in self._servers.items():
            line = f"  {name}: {srv['state']}"
            if srv["state"] == "connected":
                line += f" ({len(srv['tools'])} tools)"
            if srv["error"]:
                line += f" - {srv['error']}"
            lines.append(line)

        if self._parse_error:
            lines.append(f"  config error: {self._parse_error}")
        return "\n".join(lines)
