# -- AI GENERATED CODE (qwen3.8-flash-next) :: (2026-10-21) harness:openlumara
"""Qt6 desktop channel entry point: the channel object, its settings and all
the async glue. UI lives in chat_window.py, the settings modal in
settings_dialog.py, the settings data model in settings_model.py and the
small widgets in widgets.py."""
import core
import asyncio
import copy
import os
import sys

import PySide6.QtCore as QtCore
import PySide6.QtWidgets as QtWidgets

import channels.gui.chat_window as chat_window
import channels.gui.widgets as widgets
import channels.gui.settings_model as settings_model
import channels.gui.native_style as native_style
import channels.gui.webui_style as webui_style

QtChatWindow = chat_window.QtChatWindow


def _theme_family_options():
    """one select option per theme family file in channels/webui/themes
    (base.json is the shared var base, not a family). built once at import:
    a newly dropped-in theme json shows up here after a restart"""
    options = {}
    try:
        names = sorted(os.listdir(webui_style.THEMES_DIR))
    except Exception:
        names = []
    for filename in names:
        filename = str(filename)
        if not filename.endswith(".json"):
            continue
        stem = filename[: -len(".json")]
        if stem == "base":
            continue
        options[stem] = ""
    options.setdefault("pro-monochrome", "")
    return options


class Qt6Channel(core.channel.Channel):
    """
    A Qt6 desktop proof-of-concept channel using PySide6.
    This opens a native Qt window and lets you chat with OpenLumara through it.
    """

    settings = {
        "window_title": {
            "default": "AI",
            "description": "Title of the window, also the display name above the AI's messages",
        },
        "allow_admin_commands": {
            "type": "boolean",
            "default": True,
            "description": "Allow running admin commands in this channel (such as /restart)",
        },
        "shutdown_on_close": {
            "type": "boolean",
            "default": True,
            "description": "Shut down the OpenLumara server when the window is closed",
        },
        "follow_system_style": {
            "type": "boolean",
            "default": False,
            "description": "Off: use our included styling that looks similar to the WebUI but is 100% native GUI. On: use your system's own native GUI style.",
        },
        "show_chat_sidebar": {
            "type": "boolean",
            "default": True,
            "description": "Show the chat list sidebar, for switching, renaming and deleting chats.",
        },
        "auto_refresh_models": {
            "type": "boolean",
            "default": True,
            "description": "Automatically fetch the model list from the API on startup.",
        },
        "font_family": {
            "default": "Sans Serif"
        },
        "theme": {
            "type": "select",
            "options": _theme_family_options(),
            "default": "pro-material",
            "description": "Which theme to use (uses the webui's themes)",
        },
        "theme_mode": {
            "type": "select",
            "options": {
                "dark": "The theme's dark color mode",
                "light": "The theme's light color mode",
            },
            "default": "dark"
        },
        "show_reasoning": {
            "type": "boolean",
            "default": False,
            "description": "Whether to show thinking",
        },
        "stream_tool_calls": {
            "type": "boolean",
            "default": True,
            "description": "Whether to stream tool call arguments. Very useful for coding!",
        },
        "show_logs": {
            "type": "boolean",
            "default": False,
            "description": "Whether to show system logs. Errors are always shown.",
        },
        "show_unsafe_settings": {
            "type": "boolean",
            "default": False,
            "description": "Reveal settings that are marked as unsafe",
        },
    }

    dependencies = ["PySide6"]

    async def on_ready(self):
        self._loop = asyncio.get_running_loop()
        self._qapp = None
        self._window = None
        self._send_task = None
        self._stop_requested = False
        # set once the Qt app exists: whether the OS's native styling took hold
        self._system_theme = False

    def system_style_active(self):
        """the toggle is a force switch: on means we always defer to the
        platform's own qt look, even when the desktop's style plugins could
        not be loaded and qt sits on its built-in default; off means the
        webui theme is painted, always"""
        return self.wants_system_style()

    def wants_system_style(self):
        """the follow_system_style toggle. old string values from the
        auto/true/false era: only 'true' (and friends) count as on, so a
        stale 'auto' keeps the webui theme instead of silently flipping the
        window to qt's default style"""
        value = self._val("follow_system_style", False)
        if isinstance(value, str):
            return value.strip().lower() in ("true", "yes", "on")
        return bool(value)

    def _style_report(self):
        # tell in chat which theming branch actually won, so "what am I
        # looking at right now?" always has an answer
        style_name = ""
        try:
            if self._qapp is not None:
                style_name = str(self._qapp.style().objectName()) or str(
                    self._qapp.style().metaObject().className()
                )
        except Exception:
            style_name = ""

        if self._system_theme:
            return "System style in use: " + (style_name or "unknown")
        if self.wants_system_style():
            return (
                "System style forced (the desktop's qt plugins could not be "
                "loaded, so qt's own default style is all you get; the webui "
                "theme is never painted while the toggle is on)"
            )
        return "Custom theme in use (follow_system_style is off)"

    def _val(self, key, fallback):
        value = self.config.get(key)
        if value is None:
            return fallback
        return value

    async def run(self):
        try:
            self._init_gui()
        except Exception as e:
            self.log_error("Qt6 channel failed to start", e)
            return

        app = self._qapp
        if app is None:
            return

        poll = 0.03
        try:
            poll = float(poll)
        except Exception:
            poll = 0.03
        if poll <= 0:
            poll = 0.03

        try:
            while not self._shutting_down:
                try:
                    app.processEvents()
                except RuntimeError:
                    break

                if self._stop_requested:
                    break

                window = self._window
                if window is not None and getattr(window, "closed", False):
                    break

                await asyncio.sleep(poll)
        finally:
            self._cancel_send_task()

        if not self._shutting_down and self._val("shutdown_on_close", True):
            await self.manager.shutdown()

    def _init_gui(self):
        if self._window is not None:
            return

        # ask for the desktop's own qt platform theme before the app exists:
        # inside a plasma session with distro-packaged Qt this alone gets us
        # the chosen style, colors and icons, exactly like any native kde app
        native_style.prepare_environment()

        app = QtWidgets.QApplication.instance()
        if app is None:
            app = QtWidgets.QApplication(sys.argv[:1] or ["openlumara"])

        self._qapp = app

        # qt >= 6.9 has a global kill switch for the ugly opaque shadow
        # margins it bolts onto menus and combo popups; no stylesheet
        # property can remove those. probed both enum spellings because
        # class-scope enums come and go with pyside6 builds
        for flag_name in ("AA_DisableMenuShadows", "AA_DisableTooltipShadows"):
            flag = getattr(QtCore.Qt, flag_name, None) or getattr(
                QtCore.Qt.ApplicationAttribute, flag_name, None
            )
            if flag is not None:
                try:
                    app.setAttribute(flag, True)
                except Exception:
                    pass

        # bundled pip Qt won't see the desktop theme: try to borrow the style
        # from the system Qt installation and read the kde config ourselves.
        # when the toggle is on we defer to the system style either way
        if self.wants_system_style():
            self._system_theme = native_style.apply(app)
        else:
            self._system_theme = False

        window = QtChatWindow(self)
        self._window = window
        window.show()

        self._emit_ui("set_status", "ready")
        self._emit_ui("append_system", "Qt6 desktop channel started.")
        self._emit_ui("append_system", self._style_report())
        self.submit_async(self._startup_refresh)

    # -------------------
    # webui-style operations
    # (chats, models, tokens)
    # -------------------

    def submit_async(self, coro_func, *args):
        """fire an async operation from Qt button slots, on the same event loop"""
        if self._shutting_down:
            return None

        try:
            task = asyncio.ensure_future(coro_func(*args))
        except Exception as e:
            self._emit_ui("append_error", core.detail_error(e))
            return None

        def _done(finished_task):
            if finished_task.cancelled():
                return
            exc = finished_task.exception()
            if exc is not None:
                self._emit_ui("append_error", core.detail_error(exc))

        task.add_done_callback(_done)
        return task

    async def _startup_refresh(self):
        # render the resumed chat's history, like the webui does on load
        await self._redraw_history()
        await self._refresh_after_switch()
        if self._val("auto_refresh_models", True):
            await self._do_refresh_models()

    def _chat_op_allowed(self):
        if self._send_task is not None and not self._send_task.done():
            # said out loud in the chat: there is no status bar, so an
            # invisible "wait" reads exactly like "clicking chats does nothing"
            self._emit_ui(
                "append_system", "Wait for the current response to finish first."
            )
            return False
        return True

    def _current_chat_title(self):
        try:
            title = self.context.chat.get("title", default="Untitled")
        except Exception:
            return ("No chat loaded", None)

        try:
            chat_id = self.context.chat.get("id")
        except Exception:
            chat_id = None

        return (title, chat_id)

    def _token_text(self, count):
        if count is None:
            try:
                count = self.context.chat.get("token_usage", default=None)
            except Exception:
                count = None

        if count is None:
            return ""

        max_context = None
        try:
            max_context = core.config.get("api", "max_context")
        except Exception:
            max_context = None

        try:
            if max_context:
                pct = round((int(count) / int(max_context)) * 100)
                return f"{count}/{max_context} tok ({pct}%)"
        except Exception:
            pass

        return f"{count} tok"

    def _current_token_count(self):
        try:
            return self.context.chat.get("token_usage", default=None)
        except Exception:
            return None

    def _token_percent(self, count):
        max_context = None
        try:
            max_context = core.config.get("api", "max_context")
        except Exception:
            max_context = None

        if not max_context or count is None:
            return None
        try:
            return max(0, min(100, round((int(count) / int(max_context)) * 100)))
        except Exception:
            return None

    def _emit_token_status(self, count=None):
        if count is None:
            count = self._current_token_count()
        self._emit_ui("set_token_text", self._token_text(count), self._token_percent(count))

    async def _redraw_history(self):
        try:
            turns = await self.group_history()
        except Exception:
            turns = []
        self._emit_ui("render_history", turns)

    async def _refresh_after_switch(self):
        title, chat_id = self._current_chat_title()
        self._emit_ui("set_chat_title", title, chat_id)
        self._emit_token_status()

        chats, categories = self._chat_list_data()
        self._emit_ui("set_chat_list", chats, chat_id, categories)

    async def _do_refresh_chats(self):
        chats, categories = self._chat_list_data()

        try:
            current_id = self.context.chat.get("id")
        except Exception:
            current_id = None

        self._emit_ui("set_chat_list", chats, current_id, categories)

    def _chat_list_data(self):
        # chat list + category list for the sidebar filter, never raises
        try:
            chats = self.context.chat.get_all()
        except Exception:
            chats = []

        try:
            categories = self.context.chat.get_categories()
        except Exception:
            categories = None

        return chats, categories

    async def _do_new_chat(self):
        if not self._chat_op_allowed():
            return

        await self.context.chat.new()
        self._emit_ui("render_history", [])
        self._emit_ui("set_status", "new chat created")
        await self._refresh_after_switch()

    async def _do_clear_chat(self):
        if not self._chat_op_allowed():
            return

        await self.context.chat.clear()
        self._emit_ui("render_history", [])
        self._emit_ui("set_status", "chat cleared")
        self._emit_token_status()

    async def _do_load_chat(self, chat_id):
        if not self._chat_op_allowed():
            return

        switched = await self.context.chat.load(chat_id)
        if switched is False:
            self._emit_ui("set_status", "this chat is already open")
            return

        await self._redraw_history()
        self._emit_ui("set_status", "chat loaded")
        await self._refresh_after_switch()

    async def _do_rename_chat(self, chat_id, new_title):
        chat = self.context.chat
        index = chat._find_index(chat_id)
        if index is None:
            return

        await chat.set("title", new_title, index=index)
        await chat.save()

        if getattr(chat, "current", None) == index:
            self._emit_ui("set_chat_title", new_title, chat_id)

        await self._do_refresh_chats()
        self._emit_ui("set_status", "chat renamed")

    async def _do_delete_chat(self, chat_id):
        if not self._chat_op_allowed():
            return

        await self.context.chat.delete(chat_id)
        await self._redraw_history()
        self._emit_ui("set_status", "chat deleted")
        await self._refresh_after_switch()

    async def _do_refresh_models(self):
        self._emit_ui("set_status", "loading models...")

        try:
            models = await self.manager.API.list_models()
        except Exception as e:
            self._emit_ui("set_status", "model list failed")
            self._emit_ui("append_error", core.detail_error(e))
            return

        # list_models returns an APIError object (truthy, non-iterable) when
        # the connection itself fails, instead of raising
        if isinstance(models, core.api.APIError):
            self._emit_ui("set_status", "model list failed")
            self._emit_ui("append_error", str(models))
            return

        try:
            current = self.manager.API.get_model()
        except Exception:
            current = None

        self._emit_ui("set_models", models, current)
        self._emit_ui("set_status", self._status_text(None))

    async def _do_set_model(self, model_name):
        self.manager.API.set_model(model_name)
        self._emit_ui("set_status", f"model set to {model_name}")

    async def _do_save_settings(self, categories):
        # same contract as the webui's /api/settings/save: flatten the edited
        # tree back into raw config, write it, then figure out from a config
        # diff whether a restart or an API reconnect is needed
        try:
            old_config = copy.deepcopy(dict(core.config.config))
        except Exception:
            old_config = {}

        flattened = settings_model.flatten_categories(categories)

        # merge instead of replacing: keys outside the settings tree (theme and
        # friends) must survive the write
        merged = copy.deepcopy(old_config)
        merged.update(flattened)

        try:
            ok = core.config.config.load(data=merged)
            core.config.config.save()
        except Exception as e:
            self._emit_ui("settings_saved", {"ok": False, "error": core.detail_error(e)})
            return

        if not ok:
            self._emit_ui(
                "settings_saved",
                {"ok": False, "error": "the config refused the new values"},
            )
            return

        requires_restart = any(
            {k: (old_config.get(section) or {}).get(k) for k in ("enabled", "disabled")} !=
            {k: (merged.get(section) or {}).get(k) for k in ("enabled", "disabled")}
            for section in settings_model.MODULE_CATEGORY_KEYS
        )
        requires_reconnect = (not requires_restart) and (
            old_config.get("api") != merged.get("api")
        )

        # reload the modules whose own settings actually changed
        for section in ("modules", "user_modules"):
            old_settings = (old_config.get(section) or {}).get("settings") or {}
            new_settings = (merged.get(section) or {}).get("settings") or {}

            for name, values in new_settings.items():
                if old_settings.get(name) == values:
                    continue
                if name not in self.manager.modules:
                    continue
                try:
                    await self.manager.reload_module(name)
                except Exception as e:
                    self.log_error("Reloading " + str(name) + " after a settings save failed", e)

        if requires_reconnect:
            try:
                await self.manager.API.reconnect()
            except Exception as e:
                self.log_error("Reconnecting the API after a settings save failed", e)

        self.log(self.name, "Settings saved")
        self._emit_ui(
            "settings_saved",
            {
                "ok": True,
                "requires_restart": requires_restart,
                "requires_reconnect": requires_reconnect,
            },
        )

    def _emit_ui(self, method_name, *args):
        window = self._window
        if not window or getattr(window, "closed", False):
            return

        method = getattr(window, method_name, None)
        if method is None:
            return

        try:
            method(*args)
        except RuntimeError:
            self._window = None
        except Exception as e:
            self.log(self.name, f"Qt6 UI callback failed in {method_name}(): {core.detail_error(e)}")

    def request_stop(self):
        self._stop_requested = True

    def submit_user_message(self, text):
        if self._shutting_down:
            return None

        if self._send_task is not None and not self._send_task.done():
            return None

        self._emit_ui("append_user", text)
        self._emit_ui("set_busy", True)

        try:
            task = asyncio.ensure_future(self._stream_user_message(text))
        except Exception as e:
            self._emit_ui("append_error", str(e))
            self._emit_ui("set_busy", False)
            return None

        self._send_task = task
        task.add_done_callback(self._forget_send_task)
        return task

    async def _stream_user_message(self, text):
        self._send_task = asyncio.current_task()
        try:
            if self._shutting_down:
                return

            self._emit_ui("set_status", "thinking...")

            authorized = bool(self._val("allow_admin_commands", True))
            stream = self.send_stream(text, commands_authorized=authorized)
            await self._display_stream(stream)
        except asyncio.CancelledError:
            self._emit_ui("append_system", "Request cancelled")
        except Exception as e:
            self._emit_ui("append_error", core.detail_error(e))
            self.log_error("Qt6 user message stream failed", e)
        finally:
            self._emit_ui("set_busy", False)

    async def on_stream(self, stream):
        try:
            if hasattr(stream, "__aiter__"):
                await self._display_stream(stream, show_user=True)
            else:
                # pushed channels may hand us a finalized message instead of a
                # stream generator: render it as a plain assistant bubble
                if isinstance(stream, dict):
                    content = widgets.extract_text(stream.get("content"))
                else:
                    content = str(stream)
                if content and content.strip():
                    self._emit_ui("append_assistant_message", self._display_text(content))
        except asyncio.CancelledError:
            self._emit_ui("append_system", "Stream cancelled")
        except Exception as e:
            self._emit_ui("append_error", core.detail_error(e))
            self.log_error("Qt6 pushed stream failed", e)

    async def _display_stream(self, stream, show_user=False):
        self._emit_ui("begin_stream")
        last_progress = None

        try:
            async for event in self.group_stream(stream):
                if self._shutting_down:
                    break

                event_type = event.get("type")

                if event_type == "token":
                    token = event.get("content")
                    if not isinstance(token, dict):
                        continue

                    token_type = token.get("type")
                    token_content = token.get("content")

                    if token_type == "user_message":
                        # pushed streams display the user turn from this token
                        # (it can be modified by module hooks); the submit
                        # path already appended it locally for instant feedback
                        if show_user and token_content is not None:
                            text = widgets.extract_text(token_content)
                            if isinstance(text, str) and text.strip():
                                self._emit_ui("append_user", self._display_text(text))
                    elif token_type == "prompt_progress":
                        percent = 0
                        if isinstance(token_content, dict):
                            last_progress = token_content
                            percent = token_content.get("percent") or 0
                        self._emit_ui("set_progress", percent, f"Processing your request.. {percent}%")
                    elif token_type == "model_load_progress":
                        percent = 0
                        if isinstance(token_content, dict):
                            percent = token_content.get("percent") or 0
                        self._emit_ui("set_progress", percent, f"Warming up... {percent}%")
                    elif token_type == "token_usage" and isinstance(token_content, int):
                        self._emit_token_status(token_content)
                    elif token_type == "error" and token_content is not None:
                        self._emit_ui("stream_error", self._display_text(token_content))
                elif event_type == "step":
                    # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-25) harness:openlumara
                    # step upserts (reasoning + content + tool calls all
                    # folded backend-side, shaped like history steps)
                    step = event.get("content")
                    if not isinstance(step, dict):
                        continue

                    # the prompt is processed once real words arrive: the
                    # progress bar simply disappears, no done-line noise
                    if last_progress is not None:
                        self._emit_ui("clear_progress")
                        last_progress = None

                    self._emit_ui("apply_step", step)
                elif event_type == "final":
                    # authoritative final-bubble snapshot (empty = retract)
                    if last_progress is not None:
                        self._emit_ui("clear_progress")
                        last_progress = None

                    self._emit_ui("apply_final", event.get("content") or [])
        finally:
            self._emit_ui("end_stream")
            self._emit_ui("set_status", self._status_text(None))

            # the current chat's timestamp changed: keep the sidebar fresh, like the webui does
            self.submit_async(self._do_refresh_chats)

    def _display_text(self, value):
        text = str(value)
        return text.replace("**", "").replace("__", "")

    def _status_text(self, token_count):
        parts = []

        try:
            model = self.manager.API.get_model()
            if model:
                parts.append(str(model))
        except Exception:
            pass

        if token_count is not None:
            max_context = None
            try:
                max_context = core.config.get("api", "max_context")
            except Exception:
                max_context = None

            if max_context:
                parts.append(f"{token_count}/{max_context} tokens")
            else:
                parts.append(f"{token_count} tokens")

        if parts:
            return " | ".join(parts)
        return "ready"

    def _forget_send_task(self, task):
        if self._send_task is task:
            self._send_task = None

    def _cancel_send_task(self):
        task = self._send_task
        if task is not None and not task.done():
            try:
                task.cancel()
            except Exception:
                pass

    async def on_push(self, message):
        content = message.get("content")
        if not content:
            return

        self._emit_ui("append_assistant_message", self._display_text(content))

    def on_log(self, category, message):
        if not self._window or getattr(self._window, "closed", False):
            return

        is_error = category in ("error", "exception")
        should_show = bool(self._val("show_logs", False)) or category in ("error", "exception", self.name)
        if not should_show:
            return

        text = f"{category}: {message}"
        if is_error:
            self._emit_ui("append_error", text)
        else:
            self._emit_ui("append_system", text)

    async def on_shutdown(self):
        self._stop_requested = True
        self._cancel_send_task()

        window = self._window
        if window is not None and not getattr(window, "closed", False):
            try:
                window.close()
            except Exception:
                pass

        app = self._qapp
        if app is not None:
            try:
                app.processEvents()
            except Exception:
                pass
