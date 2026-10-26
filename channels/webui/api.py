# -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-03) status:reviewed
"""
Zero-dependency helper for modules that want to expose webui API endpoints.

Usage in any module:

    import channels.webui.api as webui

    class MyModule(core.module.Module):

        @webui.route("my_thing/list")
        async def _route_my_thing_list(self, body=None, query=None):
            return {"items": [...]}

        @webui.route("my_thing/do", method="POST")
        async def _route_my_thing_do(self, body=None, query=None):
            name = (body or {}).get("name")
            ...

Then call it from the frontend: GET /api/ext/my_module/my_thing/list
or POST /api/ext/my_module/my_thing/do with a JSON body.

CONTRACT:
- Handler methods MUST be private (underscore-prefixed): AI tools are
  registered only from methods explicitly marked with @core.module.tool,
  and route names come from the decorator path.
  Routes are addressed by the path given to the decorator, so the method
  name itself is irrelevant - use it for clarity anyway.
- Handlers are async with signature (self, body=None, query=None):
    body  -> parsed JSON body on POST (None on GET or empty body)
    query -> dict of query-string params
- Return raw JSON-serializable data: the webui wraps it in
  {"data": ..., "success": true}. Returning the standard self.result()
  dict works too - it is unwrapped into the same envelope, so a route can
  simply forward to an existing tool method and errors surface as
  success: false automatically.
- Raising is always safe: the exception is logged and returned as
  {"data": <error>, "success": false}.
- Routes are namespaced per module and discovered automatically at startup
  and after settings saves (module reloads). No registration call needed.
- Routes that do powerful things (run commands, write files, reconfigure)
  MUST be marked @webui.route(..., admin_only=True): while
  enable_admin_settings is off, those respond 403. Everything else stays
  reachable, since chat-UI widgets must keep working without admin settings.
"""

def route(path: str, method: str = "GET", admin_only: bool = False):
    """Marks a module method as a webui extension route at
    /api/ext/<module>/<path>. See module docstring for the contract.

    Pass admin_only=True for routes that do powerful things (run commands,
    write files, reconfigure): while enable_admin_settings is off those
    respond 403."""
    def decorator(func):
        func._ui_route = {
            "path": str(path).strip("/").lower(),
            "method": str(method).upper(),
            "admin_only": bool(admin_only),
        }
        return func
    return decorator
