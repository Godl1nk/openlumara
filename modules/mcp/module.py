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
    """the mcp SDK buries real causes twice: anyio ExceptionGroups around the
    transport, and MCPError hiding the server's JSON-RPC error on .error.
    Dig it all out (plus the exception cause chain) so status says what
    actually went wrong."""
    subs = getattr(exc, "exceptions", None)
    if subs and depth < 5:
        seen = []
        for sub in subs:
            msg = _flatten_error(sub, depth + 1)
            if msg not in seen:
                seen.append(msg)
        return "; ".join(seen)

    err = getattr(exc, "error", None)
    if err is not None and getattr(err, "code", None) is not None:
        text = f"{type(exc).__name__} [{err.code}] {getattr(err, 'message', '')}".strip()
        data = getattr(err, "data", None)
        if data:
            text += f" | data: {data}"
    else:
        text = f"{type(exc).__name__}: {exc}"

    cause = exc.__cause__ if exc.__cause__ is not None else exc.__context__
    if cause is not None and cause is not exc and depth < 5:
        inner = _flatten_error(cause, depth + 1)
        if inner and inner not in text:
            text += f" <- {inner}"
    return text


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
        self._tasks = {}
        self._sessions = {}
        self._stop_events = {}
        self._status = {}
        self._injected = {}
        self._server_cfg = {}
        self._parse_error = None
        self._used_names = {"mcp_status"}

        await self._startup()

    async def on_shutdown(self):
        await self._teardown()

    # -------------------------
    #   CONNECTION MANAGEMENT
    # -------------------------

    _GENERIC_HOST_LABELS = ("mcp", "api", "www", "app", "server", "gateway")

    @staticmethod
    def _derive_url_name(url, index):
        """Server name for a remote server = first meaningful label of the
        hostname, skipping generic ones (mcp.exa.ai -> exa, not mcp)."""
        host = urllib.parse.urlparse(url).hostname or ""
        labels = [l for l in host.split(".") if l]

        for label in labels:
            if label.lower() not in Mcp._GENERIC_HOST_LABELS:
                return Mcp._sanitize(label)
        name = labels[0] if labels else f"server{index + 1}"

        return Mcp._sanitize(name)

    @staticmethod
    def _derive_stdio_name(argv, index):
        """Server name for a stdio server: for common package runners (uvx, npx,
        python -m, ...) the package name is far more telling than the runner."""
        runners = ("uvx", "npx", "pnpx", "bunx", "deno", "node", "python", "python3", "py")
        base = argv[0].replace("\\", "/").rsplit("/", 1)[-1]

        if base in runners:
            args = argv[1:]

            if args and args[0] in ("-m", "--module") and len(args) > 1:
                return Mcp._sanitize(args[1].rsplit(".", 1)[-1])

            for a in args:
                if not a.startswith("-"):
                    return Mcp._sanitize(a)

        return Mcp._sanitize(base) or f"server{index + 1}"

    async def _startup(self):
        self._parse_error = None
        self._server_cfg = {}
        timeout = float(self.config.get("connect_timeout", default=30))

        index = 0
        for setting, stype in (("servers_http", "http"), ("servers_sse", "sse"), ("servers_stdio", "stdio")):
            raw = self.config.get(setting, default=[])

            if isinstance(raw, str):
                raw = [raw] if raw.strip() else []
            if not isinstance(raw, list):
                self._parse_error = f"'{setting}' must be a list"
                self.manager.log(self.name, self._parse_error)
                continue

            for item in raw:
                if not isinstance(item, str) or not item.strip():
                    continue
                item = item.strip()

                if stype == "stdio":
                    try:
                        argv = shlex.split(item)
                    except ValueError as e:
                        self._parse_error = f"invalid command in '{setting}': '{item}' ({e})"
                        self.manager.log(self.name, self._parse_error)
                        continue
                    if not argv:
                        continue
                    cfg = {"type": "stdio", "command": argv[0], "args": argv[1:]}
                    name = self._derive_stdio_name(argv, index)
                else:
                    cfg = {"type": stype, "url": item}
                    name = self._derive_url_name(item, index)

                base = name
                k = 2
                while name in self._server_cfg:
                    name = f"{base}_{k}"
                    k += 1
                self._server_cfg[name] = cfg
                index += 1

        ready_events = {}
        for name, cfg in self._server_cfg.items():
            self._status[name] = {"state": "connecting", "tools": [], "error": None}
            ready_events[name] = asyncio.Event()
            self._stop_events[name] = asyncio.Event()
            self._tasks[name] = asyncio.create_task(self._server_loop(name, cfg, ready_events[name]))

        for name, ev in ready_events.items():
            try:
                await asyncio.wait_for(ev.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                self._status[name]["state"] = "timeout"
                self._status[name]["error"] = f"did not connect within {timeout}s"
                self.manager.log(self.name, f"server '{name}' timed out while connecting")

    async def _teardown(self):
        for name, ev in getattr(self, "_stop_events", {}).items():
            ev.set()

        for name, task in getattr(self, "_tasks", {}).items():
            try:
                await asyncio.wait_for(task, timeout=10)
            except Exception:
                task.cancel()

        for name in list(getattr(self, "_injected", {})):
            self._purge_server(name)

        self._tasks = {}
        self._sessions = {}
        self._stop_events = {}
        self._status = {}

    async def _server_loop(self, name, cfg, ready):
        """Owns one MCP connection for its entire life, so the transport's
        anyio scopes are entered and exited inside this same task."""
        try:
            async with contextlib.AsyncExitStack() as stack:
                stype = cfg.get("type", "http" if cfg.get("url") else "stdio")

                if stype == "stdio":
                    params = mcp.client.stdio.StdioServerParameters(
                        command=cfg["command"],
                        args=cfg.get("args") or [],
                        env=cfg.get("env") or None
                    )
                    read, write = await stack.enter_async_context(
                        mcp.client.stdio.stdio_client(params)
                    )
                elif stype == "sse":
                    read, write = await stack.enter_async_context(
                        mcp.client.sse.sse_client(
                            cfg["url"], headers=cfg.get("headers") or None
                        )
                    )
                else:
                    http_fn = getattr(mcp.client.streamable_http, "streamable_http_client", None)
                    if http_fn is None:
                        raise RuntimeError("this mcp SDK is too old - run: pip install -U 'mcp>=2'")
                    read, write = await stack.enter_async_context(http_fn(cfg["url"]))

                session = await stack.enter_async_context(
                    mcp.ClientSession(read, write, message_handler=self._make_handler(name))
                )
                await session.initialize()

                self._sessions[name] = session
                await self._resync_tools(name)
                self._status[name]["state"] = "connected"
                self._status[name]["error"] = None
                self.manager.log(self.name, f"server '{name}' connected ({len(self._injected.get(name, []))} tools)")

                ready.set()

                await self._stop_events[name].wait()
        except Exception as e:
            if self._status.get(name, {}).get("state") != "timeout":
                self._status[name] = {
                    "state": "error",
                    "tools": self._status.get(name, {}).get("tools", []),
                    "error": _flatten_error(e)
                }

            self.manager.log(self.name, f"server '{name}' stopped: {core.detail_error(e)}")
        finally:
            ready.set()

            self._sessions.pop(name, None)
            if self._status.get(name, {}).get("state") not in ("error", "timeout"):
                self._status[name] = {"state": "stopped", "tools": [], "error": None}

    def _make_handler(self, server):
        """Handles inbound server notifications; re-syncs tools when a server says its tool list changed."""
        async def handler(message):
            if type(message).__name__ == "ToolListChangedNotification":
                self.manager.log(self.name, f"server '{server}' announced a tool list change")
                asyncio.create_task(self._resync_tools(server))

        return handler

    # -------------------------
    #   TOOL INJECTION
    # -------------------------

    def _loaders(self):
        return [ch.tool_loader for ch in self.manager.channels.values()]

    @staticmethod
    def _sanitize(text):
        text = re.sub(r"[^a-zA-Z0-9_-]", "_", str(text))
        return text.strip("_-") or "x"

    def _tool_name(self, server, tool):
        name = f"mcp_{self._sanitize(server)}_{self._sanitize(tool)}"[:64].rstrip("_-")
        base = name
        i = 2

        while name in self._used_names:
            suffix = f"_{i}"
            name = base[:64 - len(suffix)] + suffix
            i += 1

        self._used_names.add(name)
        return name

    def _purge_server(self, server):
        names = self._injected.pop(server, set())

        for n in names:
            if n in self.__dict__:
                delattr(self, n)
            self._used_names.discard(n)

        for tl in self._loaders():
            for n in names:
                tl.catalog.pop(n, None)
            tl.active_tools = [t for t in tl.active_tools if t["function"]["name"] not in names]
            tl.active_names = [n for n in tl.active_names if n not in names]

    async def _resync_tools(self, server):
        session = self._sessions.get(server)

        if session is None:
            return
        try:
            listing = await session.list_tools()
        except Exception as e:
            self.manager.log(self.name, f"could not list tools for '{server}': {_flatten_error(e)}")
            return

        # remember which of this server's tools were active so we can restore them
        was_active = set()
        for tl in self._loaders():
            was_active.update(tl.active_names)

        self._purge_server(server)

        cfg = self._server_cfg.get(server, {})
        disabled = set(cfg.get("disabled_tools") or [])
        injected = set()

        for tool in listing.tools:
            if tool.name in disabled:
                continue
            fn = self._tool_name(server, tool.name)
            description = getattr(tool, "description", "") or f"MCP tool '{tool.name}' from server '{server}'."
            schema = (getattr(tool, "input_schema", None) or getattr(tool, "inputSchema", None)
                      or {"type": "object", "properties": {}})
            tool_dict = {
                "type": "function",
                "function": {
                    "name": fn,
                    "description": description,
                    "parameters": schema
                }
            }

            setattr(self, fn, self._make_call(server, tool.name))
            for tl in self._loaders():
                tl.catalog[fn] = {
                    "tool": tool_dict,
                    "module": self.name,
                    "method": fn,
                    "description": description
                }

            if fn in was_active:
                for tl in self._loaders():
                    if fn not in tl.active_names:
                        tl.active_tools.append(tool_dict)
                        tl.active_names.append(fn)

            injected.add(fn)

        self._injected[server] = injected
        self._status.setdefault(server, {"state": "connected", "error": None})["tools"] = sorted(injected)

        for tl in self._loaders():
            tl.refresh_meta_tool_descriptions()

    def _make_call(self, server, tool_name):
        async def call(**kwargs):
            session = self._sessions.get(server)

            if session is None:
                return self.result(f"MCP server '{server}' is not connected. Check mcp_status.", success=False)

            try:
                res = await session.call_tool(tool_name, kwargs or {})
            except Exception as e:
                return self.result(f"MCP call '{tool_name}' failed: {_flatten_error(e)}", success=False)

            is_error = getattr(res, "is_error", None)
            if is_error is None:
                is_error = getattr(res, "isError", False)

            return self.result(self._render_result(res), success=not is_error)

        return call

    def _render_result(self, res):
        parts = []
        for block in getattr(res, "content", None) or []:
            btype = getattr(block, "type", None)

            if btype == "text":
                parts.append(getattr(block, "text", ""))
            elif btype in ("image", "audio"):
                mime = getattr(block, "mime_type", None) or getattr(block, "mimeType", None) or "unknown type"
                parts.append(f"[{btype} content omitted: {mime}]")
            elif btype == "resource":
                r = getattr(block, "resource", None)
                rtext = getattr(r, "text", None)
                if rtext:
                    parts.append(rtext)
                else:
                    parts.append(f"[binary resource: {getattr(r, 'uri', 'unknown uri')}]")
            elif btype == "resource_link":
                parts.append(f"[resource link: {getattr(block, 'uri', '')}]")
            else:
                parts.append(f"[unsupported content: {btype}]")

        if not any(str(p).strip() for p in parts):
            structured = getattr(res, "structured_content", None)
            if structured is None:
                structured = getattr(res, "structuredContent", None)
            if structured is not None:
                return json.dumps(structured)
            return "(empty result)"

        return "\n".join(str(p) for p in parts)

    # -------------------------
    #   USER-FACING COMMANDS
    # -------------------------

    @core.module.command("mcp", help={
        "": "Shows the status of all configured MCP servers",
        "reload": "Reconnects all MCP servers and refreshes their tools (use after changing the config)"
    })
    async def mcp_command(self, args: list):
        if args and args[0].lower() == "reload":
            await self._teardown()
            await self._startup()
            out = ["reloaded MCP servers:"]
        else:
            out = ["MCP servers:"]

        if not self._status:
            out.append("  (none configured)")

        for name, info in self._status.items():
            line = f"  {name}: {info['state']}"
            if info["state"] == "connected":
                line += f" ({len(info['tools'])} tools)"
            if info.get("error"):
                line += f" - {info['error']}"
            out.append(line)

        if self._parse_error:
            out.append(f"  config error: {self._parse_error}")
        return "\n".join(out)
