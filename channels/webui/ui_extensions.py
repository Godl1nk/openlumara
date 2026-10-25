"""
WebUI Extension System

lets modules ship their own webui pieces: templates, static assets (/ext-assets/),
and API routes (served by the /api/ext dispatcher in server.py, marked with @webui.route from api.py)
"""

import os
import importlib

import jinja2
import markupsafe

import core

class UiExtensionsMixin:
    def _ui_extension_enabled(self, module):
        """lets the user enable/disable the webui extension via a special setting on the module"""
        enabled = module.config.get("enable_webui_extension")
        
        if enabled is None:
            return True
        
        return bool(enabled)

    def _ext_module_config(self, module):
        """settings of a module for use inside its shipped templates"""
        values = {}
        for name in module.settings:
            values[name] = module.config.get(name)
        return values

    def _ext_template_vars(self, template_name):
        """jinja vars for a prefixed extension template ('<module>/..'):
        the owning module's settings, exposed as `module_config`.
        an empty dict for templates."""
        module = self.manager.modules.get(template_name.split("/", 1)[0])
        return {"module_config": self._ext_module_config(module) if module else {}}

    def _ui_extension_dirs(self):
        """collect webui template folders from all enabled modules, as {module_name: path}"""
        dirs = {}
        for package_name in ("modules", "user_modules"):
            try:
                package = importlib.import_module(package_name)
            except ImportError:
                continue

            for module_name in core.config.get(package_name, "enabled", []):
                module = self.manager.modules.get(module_name)
                if module is None or not self._ui_extension_enabled(module):
                    continue

                for sub_path in package.__path__:
                    candidate = os.path.join(sub_path, module_name, "webui", "templates")
                    if os.path.isdir(candidate):
                        dirs[module_name] = candidate
        return dirs

    # modules can ship static assets (css/js/...)
    # in <module>/webui/assets/, served under /ext-assets/.
    def _ui_asset_dirs(self):
        """collect webui asset folders from all enabled modules, as {module_name: path}"""
        dirs = {}
        for package_name in ("modules", "user_modules"):
            try:
                package = importlib.import_module(package_name)
            except ImportError:
                continue

            for module_name in core.config.get(package_name, "enabled", []):
                module = self.manager.modules.get(module_name)
                if module is None or not self._ui_extension_enabled(module):
                    continue

                for sub_path in package.__path__:
                    candidate = os.path.join(sub_path, module_name, "webui", "assets")
                    if os.path.isdir(candidate):
                        dirs[module_name] = candidate
        return dirs

    def _ui_asset_urls(self, ext):
        """urls for css/js files shipped by enabled modules, as
        /ext-assets/<module>/<relpath> entries meant to be appended to
        the css_files/js_files template variables."""
        urls = []
        for module_name, assets_dir in sorted(self._ui_asset_dirs().items()):
            ext_dir = os.path.join(assets_dir, ext)
            if not os.path.isdir(ext_dir):
                continue
                
            for root, _sub, files in os.walk(ext_dir):
                for filename in sorted(files):
                    if not filename.endswith(f".{ext}"):
                        continue
                    rel = os.path.relpath(os.path.join(root, filename), assets_dir).replace(os.sep, "/")
                    urls.append(f"/ext-assets/{module_name}/{rel}")
                    
        return urls

    def setup_ui_extensions(self):
        """(re)build the jinja loader so module-provided templates become available.
        called at startup and after settings saves (module reloads)."""
        dirs = self._ui_extension_dirs()

        loaders = [jinja2.FileSystemLoader(self.template_path)]
        if dirs:
            loaders.append(jinja2.PrefixLoader(
                {name: jinja2.FileSystemLoader(path) for name, path in dirs.items()},
                delimiter="/"
            ))

        env = self.templates.env
        env.loader = jinja2.ChoiceLoader(loaders)

        def _extension_templates(relative_path):
            """all module templates that mirror the given template path, sorted by module name.
            each is compiled once here, so a broken extension is skipped and logged
            instead of breaking the page."""
            found = []
            for module_name in sorted(dirs):
                template_name = f"{module_name}/{relative_path}"
                if not os.path.isfile(os.path.join(dirs[module_name], relative_path)):
                    continue
                    
                try:
                    env.get_template(template_name)
                except Exception as e:
                    self.log("webui", f"skipping UI extension '{template_name}': {core.detail_error(e)}")
                    continue
                    
                found.append(template_name)
            return found

        def extension_modals():
            """auto-discovers modal templates: every .html file directly in
            <module>/webui/templates/modals/ is included by the core modal area."""
            found = []
            for module_name in sorted(dirs):
                modal_root = os.path.join(dirs[module_name], "modals")
                if not os.path.isdir(modal_root):
                    continue
                    
                module = self.manager.modules.get(module_name)
                module_config = self._ext_module_config(module) if module else {}
                for filename in sorted(os.listdir(modal_root)):
                    filepath = os.path.join(modal_root, filename)
                    
                    if not os.path.isfile(filepath):
                        continue
                    if not filename.endswith(".html") or filename == "index.html":
                        continue
                        
                    rel = os.path.relpath(filepath, dirs[module_name]).replace(os.sep, "/")
                    template_name = f"{module_name}/{rel}"
                    try:
                        env.get_template(template_name)
                    except Exception as e:
                        self.log("webui", f"skipping UI modal '{template_name}': {core.detail_error(e)}")
                        continue
                        
                    found.append({"template": template_name, "config": module_config})
            return found

        def extension_sidebars():
            """
            auto-discovers sidebar tab panels: every .html file directly in
            <module>/webui/templates/sidebars/ renders as its own tab in the
            core sidebar, and a same-named .svg next to it becomes the tab icon
            the tab label is derived from the filename

			templates can access module config using var `module_config`
            """
            found = []
            for module_name in sorted(dirs):
                sidebar_root = os.path.join(dirs[module_name], "sidebars")
                if not os.path.isdir(sidebar_root):
                    continue
                    
                module = self.manager.modules.get(module_name)
                module_config = self._ext_module_config(module) if module else {}
                for filename in sorted(os.listdir(sidebar_root)):
                    filepath = os.path.join(sidebar_root, filename)
                    
                    if not os.path.isfile(filepath):
                        continue
                    if not filename.endswith(".html"):
                        continue
                        
                    name = filename[:-5]
                    template_name = f"{module_name}/sidebars/{filename}"
                    try:
                        env.get_template(template_name)
                    except Exception as e:
                        self.log("webui", f"skipping UI sidebar '{template_name}': {core.detail_error(e)}")
                        continue
                        
                    icon = markupsafe.Markup("")
                    icon_path = os.path.join(sidebar_root, f"{name}.svg")
                    if os.path.isfile(icon_path):
                        try:
                            with open(icon_path, encoding="utf-8") as f:
                                icon = markupsafe.Markup(f.read())
                        except Exception as e:
                            self.log("webui", f"skipping sidebar icon '{icon_path}': {core.detail_error(e)}")
                            
                    label = name.replace("_", " ").replace("-", " ").title()
                    found.append({
                        "module": module_name,
                        "name": name,
                        "label": label,
                        "template": template_name,
                        "icon": icon,
                        "config": module_config,
                    })
            return found

        @jinja2.pass_context
        def extension_slot(ctx, slot_name, relative_path=None):
            """renders the macro `slot_name` from every module template mirroring the
            calling template's path (or the explicit one). lets a single module file
            fill multiple named regions of a core component:
            {% macro left() %}...{% endmacro %} -> {{ extension_slot("left") }}.
            the caller's context is passed to a macro as the `ctx` kwarg only if the
            macro declares it, so slots needing scoped data (turn/message in chat
            templates) declare `{% macro below_message(ctx) %}` and read
            `ctx['message']`. zero-arg macros are called plain, untouched.
            modules that don't define the slot are silently skipped.

            the owning module's settings are injected as `module_config`, so a
            slot template can gate its own markup with plain jinja:
            `{% if module_config.get("show_welcome_card", true) %}`.
            """
            relative_path = relative_path or ctx.name
            if not relative_path:
                return markupsafe.Markup("")
            
            parts = []
            for template_name in _extension_templates(relative_path):
                try:
                    template_vars = self._ext_template_vars(template_name)
                    macro = getattr(env.get_template(template_name).make_module(vars=template_vars), slot_name, None)
                    if macro is not None:
                        if "ctx" in getattr(macro, "arguments", ()):
                            parts.append(str(macro(ctx=ctx.get_all())))
                        else:
                            parts.append(str(macro()))
                except Exception as e:
                    self.log("webui", f"skipping extension slot '{slot_name}' in '{template_name}': {core.detail_error(e)}")
                    continue
            return markupsafe.Markup("\n".join(parts))

        env.globals["extension_modals"] = extension_modals
        env.globals["extension_sidebars"] = extension_sidebars
        env.globals["extension_slot"] = extension_slot
        env.cache.clear()
