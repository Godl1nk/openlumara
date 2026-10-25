# -- AI GENERATED CODE (qwen3.8-flash-next) :: (2026-10-21) harness:openlumara
"""the qt6 main window: chat sidebar, live streaming turn rendering (thoughts
collapsibles, tool cards, inline progress bar), theming and window widgets"""
import datetime
import json

import PySide6.QtCore as QtCore
import PySide6.QtGui as QtGui
import PySide6.QtWidgets as QtWidgets

import channels.gui.widgets as widgets
import channels.gui.settings_dialog as settings_dialog
import channels.gui.webui_style as webui_style


class QtChatWindow(QtWidgets.QMainWindow):
    def __init__(self, channel):
        super().__init__()
        self.channel = channel
        self.closed = False
        self.busy = False
        self._send_future = None
        self._suppress_list_signal = False
        self._live = None
        self._native = True
        self._collapsibles = []
        self._all_chats = []
        self._current_chat_id = None
        self.settings_dialog = None
        # the webui theme currently in effect (vars + derived message colors)
        self._theme_vars = {}
        self._theme_colors = {}

        # when the list's width changes (window/splitter), titles get re-elided
        self._list_reflow = QtCore.QTimer(self)
        self._list_reflow.setSingleShot(True)
        self._list_reflow.setInterval(50)
        self._list_reflow.timeout.connect(self._populate_chat_list)
        # last width the rows were elided for: guards against the rebuild's
        # own scrollbar flicker firing fresh resizes and looping forever
        self._list_width = -1
        self._scroll_to_current = False

        # live-region repaint throttle: every streamed token asks for a full
        # rebuild of the live turn; at token bursts (coder arg dumps!) doing
        # that mid-frame twice is wasted work and flicker. everything instead
        # coalesces to one repaint per screen frame, derived from the monitor
        # refresh rate below, so it's indistinguishable from per-token
        self._live_render_pending = False
        self._live_reflow = QtCore.QTimer(self)
        self._live_reflow.setSingleShot(True)
        frame_ms = 16.0
        try:
            screen = QtGui.QGuiApplication.primaryScreen()
            if screen is not None and screen.refreshRate() > 0:
                frame_ms = 1000.0 / float(screen.refreshRate())
        except Exception:
            pass
        self._live_reflow.setInterval(max(4, int(round(frame_ms))))
        self._live_reflow.timeout.connect(self._flush_live_render)

        title = str(channel._val("window_title", "Lumara Qt6"))
        self.setWindowTitle(title)
        self.resize(1080, 660)

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)

        root = QtWidgets.QHBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(0)

        self.splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        root.addWidget(self.splitter)

        self.sidebar = self._build_sidebar()
        self.chat_list.viewport().installEventFilter(self)
        self.splitter.addWidget(self.sidebar)

        self.splitter.addWidget(self._build_main_panel())

        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([260, 780])

        if not channel._val("show_chat_sidebar", True):
            self.sidebar.setVisible(False)

        # no status bar: everything the user needs lives in the header
        self.setStatusBar(None)

        self._apply_theme(title)

    # -------------------
    # layout construction
    # -------------------

    def _build_sidebar(self):
        panel = QtWidgets.QWidget()
        panel.setObjectName("sidebar")
        layout = QtWidgets.QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(6)

        # category filter: decides which chats the list below shows
        self.cat_filter = QtWidgets.QComboBox()
        # never demand width for its contents: the sidebar's width is decided
        # by the user dragging the splitter, not by the longest category name
        self.cat_filter.setSizeAdjustPolicy(
            QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon
        )
        self.cat_filter.setMinimumContentsLength(8)
        self.cat_filter.setToolTip("Only show chats from this category")
        self.cat_filter.currentTextChanged.connect(self._populate_chat_list)
        layout.addWidget(self.cat_filter)

        self.chat_list = QtWidgets.QListWidget()
        # fixed-width rows: no sideways panning, long titles get an ellipsis
        self.chat_list.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.chat_list.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.chat_list.customContextMenuRequested.connect(self._on_chat_context_menu)
        self.chat_list.itemClicked.connect(self._on_chat_clicked)
        # switch on press too: itemClicked needs the very same item under the
        # release, and the streaming sidebar refreshes love to replace items
        # between press and release, silently murdering the click
        self.chat_list.itemPressed.connect(self._on_chat_pressed)
        layout.addWidget(self.chat_list, 1)

        self.new_chat_button = QtWidgets.QPushButton("New Chat")
        # matches the input row's height, so the two bottom edges line up
        self.new_chat_button.setFixedHeight(32)
        self.new_chat_button.clicked.connect(
            lambda: self.channel.submit_async(self.channel._do_new_chat)
        )
        layout.addWidget(self.new_chat_button)

        return panel

    def _build_main_panel(self):
        panel = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(panel)
        # some air between the sidebar and the header/chat column: without the
        # left margin the chat title butts right up against the splitter seam
        layout.setContentsMargins(14, 0, 0, 0)
        layout.setSpacing(8)

        # header bar: chat title | model switcher | reload | settings
        header = QtWidgets.QHBoxLayout()
        header.setSpacing(8)

        self.chat_title = QtWidgets.QLabel("...")
        title_font = self.chat_title.font()
        title_font.setBold(True)
        self.chat_title.setFont(title_font)
        header.addWidget(self.chat_title)
        header.addStretch(1)

        # the model switcher sits left of all the header buttons
        # one shared 34px height for the whole control cluster: combo and
        # icon buttons form one clean line instead of a combo on stilts
        self.model_combo = QtWidgets.QComboBox()
        self.model_combo.setMinimumWidth(170)
        self.model_combo.setFixedHeight(34)
        self.model_combo.setToolTip("Active model")
        # this pyside6 build only exposes the int overload of activated
        self.model_combo.activated[int].connect(self._on_model_selected)
        header.addWidget(self.model_combo)

        self.refresh_models_button = QtWidgets.QPushButton("\u21bb")
        self.refresh_models_button.setObjectName("iconbtn")
        self.refresh_models_button.setFixedWidth(34)
        self.refresh_models_button.setFixedHeight(34)
        self.refresh_models_button.setToolTip("Reload model list")
        self.refresh_models_button.clicked.connect(
            lambda: self.channel.submit_async(self.channel._do_refresh_models)
        )
        header.addWidget(self.refresh_models_button)

        self.settings_button = QtWidgets.QPushButton("\u2699")
        self.settings_button.setObjectName("iconbtn")
        self.settings_button.setFixedWidth(34)
        self.settings_button.setFixedHeight(34)
        self.settings_button.setToolTip("Open settings")
        self.settings_button.clicked.connect(self._open_settings)
        header.addWidget(self.settings_button)

        # the ↻/⚙ labels are just glyphs, so their size is their font: bump
        # them a good notch above the ui text (explicitly per-widget, so
        # _apply_theme's window-level font swap never shrinks them back)
        for icon_button in (self.refresh_models_button, self.settings_button):
            icon_font = icon_button.font()
            base_size = icon_font.pointSize()
            if base_size < 0:
                base_size = 10
            icon_font.setPointSize(base_size + 5)
            icon_button.setFont(icon_font)

        layout.addLayout(header)

        self.chat = widgets.ChatTextEdit(self)
        self.chat.setObjectName("chatView")
        self.chat.document().setDocumentMargin(8)
        # markdown list indentation = list level x this unit (Qt6's
        # QTextDocument::indentWidth, historically 40px and misnamed plain
        # "indent" before that; hence the probe over its spellings). the
        # importer still hands top-level lists a nonzero level, so
        # _tighten_list_indent rebases the shallowest one to 0: lists start
        # flush with the prose, nested levels step by these pixels
        doc = self.chat.document()
        set_unit = getattr(doc, "setIndentWidth", None) or getattr(
            doc, "set_indent_width", None
        )
        if callable(set_unit):
            try:
                set_unit(18)
            except Exception:
                pass
        self.chat.setReadOnly(True)
        self.chat.setAcceptRichText(True)
        # default line wrap is fine, and pyside6's enum spelling is weird
        layout.addWidget(self.chat, 1)

        input_row = QtWidgets.QHBoxLayout()
        self.input = QtWidgets.QLineEdit()
        # the input row is a strict 32px strip: bar, context meter and send
        # button all share that one clean height
        self.input.setFixedHeight(32)
        self.input.setPlaceholderText(str(self.channel._val("placeholder", "Type your message...")))
        self.input.returnPressed.connect(self._on_return)

        # context usage: a mini progress bar with the percentage inside it,
        # parked left of Send and as tall as the input bar beside it
        self.token_bar = QtWidgets.QProgressBar()
        self.token_bar.setRange(0, 100)
        self.token_bar.setValue(0)
        self.token_bar.setFormat("0%")
        self.token_bar.setToolTip("Context window in use")
        self.token_bar.setFixedWidth(90)
        self.token_bar.setSizePolicy(
            QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Expanding
        )

        self.send_button = QtWidgets.QPushButton("Send")
        # webui styling: send is a ghost button that tints on hover, stop is
        # the red error-bg variant; the object name swaps with the label
        self.send_button.setObjectName("send")
        # grow to the input bar's full height instead of floating as a stub
        self.send_button.setSizePolicy(
            QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Expanding
        )
        self.send_button.clicked.connect(self._on_send_button)

        input_row.addWidget(self.input, 1)
        input_row.addWidget(self.token_bar)
        input_row.addWidget(self.send_button)
        layout.addLayout(input_row)

        return panel

    # -------------------
    # webui-style widgets
    # -------------------

    def set_chat_title(self, text, chat_id=None):
        if self.closed:
            return
        self.chat_title.setText(str(text))
        if chat_id:
            self.chat_title.setToolTip(f"chat id: {chat_id}")
        else:
            self.chat_title.setToolTip("")

    def set_token_text(self, text, percent=None):
        if self.closed:
            return
        try:
            value = int(percent) if percent is not None else 0
        except Exception:
            value = 0
        value = max(0, min(100, value))
        self.token_bar.setValue(value)
        self.token_bar.setFormat(f"{value}%")
        self.token_bar.setToolTip(str(text) if text else "Context window in use")

    def _fmt_time(self, iso_value):
        if not iso_value:
            return ""
        try:
            dt = datetime.datetime.fromisoformat(str(iso_value))
            return dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            return str(iso_value)

    def _fmt_when(self, iso_value):
        """short human-friendly 'modified' label for the chat rows"""
        if not iso_value:
            return ""
        try:
            dt = datetime.datetime.fromisoformat(str(iso_value))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.timezone.utc)
            dt = dt.astimezone()
            now = datetime.datetime.now()
            if dt.date() == now.date():
                return "today " + dt.strftime("%H:%M")
            if (now.date() - dt.date()).days == 1:
                return "yesterday " + dt.strftime("%H:%M")
            if dt.year == now.year:
                return dt.strftime("%b %d, %H:%M")
            return dt.strftime("%Y-%m-%d")
        except Exception:
            return self._fmt_time(iso_value)

    def set_chat_list(self, chats, current_id=None, categories=None):
        if self.closed:
            return

        self._all_chats = list(chats or [])
        # only a real chat switch is allowed to scroll the list to the current
        # item; a mere refresh of the same chats keeps your position
        self._scroll_to_current = current_id != self._current_chat_id
        self._current_chat_id = current_id

        if categories:
            names = sorted({str(c) for c in categories if c})
        else:
            names = sorted({str(c.get("category")) for c in self._all_chats if c.get("category")})

        previous = self.cat_filter.currentText()
        self.cat_filter.blockSignals(True)
        self.cat_filter.clear()
        self.cat_filter.addItems(names)
        # no "everything" pseudo-entry: default to general, otherwise keep
        # whatever category was chosen, otherwise just the first real one
        wanted = previous if previous in names else "general"
        keep = self.cat_filter.findText(wanted)
        self.cat_filter.setCurrentIndex(keep if keep >= 0 else 0)
        self.cat_filter.blockSignals(False)

        self._populate_chat_list()

    def _populate_chat_list(self, *args):
        """rebuild the visible list from _all_chats using the category filter"""
        if self.closed:
            return

        category = self.cat_filter.currentText()
        chats = [c for c in self._all_chats if c.get("category") == category]

        chats.sort(key=lambda c: str(c.get("updated") or ""), reverse=True)

        self._suppress_list_signal = True
        try:
            self._rebuild_chat_list(chats)
        finally:
            # a raise mid-rebuild must never leave this flag up: a stuck flag
            # silently swallows every chat click afterwards, which looks
            # exactly like "chat switching is dead"
            self._suppress_list_signal = False

    def _rebuild_chat_list(self, chats):
        # rebuilds the visible rows; chats arrives filtered and sorted
        fg = str(self._color("text_color", "#f6e7ff"))
        dim = str(self._color("system_color", "#9a88a6"))

        # the row labels get no font of their own at all: they simply inherit
        # the list's, so the text, its metrics and the row height can never
        # disagree about how tall the letters are

        # rows never push the list sideways: the viewport's own width, minus
        # the item's horizontal padding, decides how much title fits on it
        avail = max(24, self.chat_list.viewport().width() - 32)

        # a plain refresh (new message, renamed chat...) must leave the view
        # exactly where the user scrolled it; only a chat switch may move it
        list_bar = self.chat_list.verticalScrollBar()
        keep_scroll = list_bar.value()
        moved = False

        self.chat_list.clear()

        for entry in chats:
            chat_id = entry.get("id")
            title = entry.get("title") or "Untitled"
            is_current = chat_id is not None and chat_id == self._current_chat_id

            item = QtWidgets.QListWidgetItem("")
            item.setData(QtCore.Qt.UserRole, chat_id)
            item.setData(QtCore.Qt.UserRole + 1, title)
            item.setToolTip(
                f"{title}\n\n"
                f"id: {chat_id}\n"
                f"category: {entry.get('category') or 'none'}\n"
                f"updated: {self._fmt_time(entry.get('updated'))}\n"
                f"tokens: {entry.get('token_usage')}"
            )

            row = widgets.ChatListRow(self.chat_list)
            if is_current:
                # the current chat is bolded rather than recoloured: the
                # selection highlight underneath it already uses the accent
                # colour. weight goes on the font, never in the stylesheet:
                # a stylesheet font property makes qt re-resolve the family
                # (and size!) and it picks something odd
                bold = row.title.font()
                bold.setBold(True)
                row.title.setFont(bold)

            # measure with the label's own metrics: the exact font it will
            # paint with, so the elision and the row height always agree
            row.title.setText(row.title.fontMetrics().elidedText(
                title, QtCore.Qt.ElideRight, avail
            ))
            row.title.setStyleSheet("color: " + fg + "; background: transparent;")

            row.date.setText(self._fmt_when(entry.get("updated")))
            row.date.setStyleSheet("color: " + dim + "; background: transparent;")

            # let each row be exactly as tall as its own two lines of text
            self.chat_list.addItem(item)
            item.setSizeHint(row.sizeHint())
            self.chat_list.setItemWidget(item, row)

            if is_current:
                # flag it selected (that's what the stylesheet highlights)
                # instead of setCurrentItem, whose "keep still" hint kept
                # tripping; the view is only moved for a genuine chat switch
                item.setSelected(True)
                if self._scroll_to_current:
                    self.chat_list.setCurrentItem(item)
                    moved = True

        if not moved:
            list_bar.setValue(keep_scroll)
        self._scroll_to_current = False
        self._list_width = self.chat_list.viewport().width()

    def set_models(self, models, current_model=None):
        if self.closed:
            return

        models = list(models or [])
        if current_model and current_model not in models:
            models.insert(0, current_model)

        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        self.model_combo.addItems([str(m) for m in models])
        if current_model:
            index = self.model_combo.findText(str(current_model))
            if index >= 0:
                self.model_combo.setCurrentIndex(index)
        self.model_combo.blockSignals(False)

    def render_history(self, turns):
        if self.closed:
            return

        self.chat.clear()
        self._collapsibles = []
        show_reasoning = bool(self.channel._val("show_reasoning", False))

        for turn in turns or []:
            role = turn.get("role")

            if role == "user":
                texts = []
                for msg in turn.get("messages") or []:
                    text = widgets.extract_text(msg.get("content"))
                    if text.strip():
                        texts.append(text)
                if texts:
                    self.append_user("\n".join(texts))
                continue

            # assistant turn: same clean look as the live stream
            cursor = self.chat.textCursor()
            cursor.movePosition(QtGui.QTextCursor.End)
            if self.chat.toPlainText():
                cursor.insertText("\n")

            title = str(self.channel._val("window_title", "Lumara"))
            cursor.insertText(title + "\n", self._fmt(self._color("assistant_color", "#c084fc")))

            for step in turn.get("steps") or []:
                reasoning = step.get("reasoning_content") or ""
                if show_reasoning and reasoning.strip():
                    # collapsed by default in history, click the header to peek
                    self._append_collapsible(cursor, reasoning.strip(), False)

                step_content = step.get("content") or ""
                if step_content.strip():
                    self._insert_markdown(cursor, step_content.rstrip() + "\n")

                for tool in step.get("tool_calls") or []:
                    # history: start folded (click the header to peek at args)
                    self._tool_card(cursor, tool, expanded=False)

            finals = []
            for msg in turn.get("final_messages") or []:
                text = widgets.extract_text(msg.get("content"))
                if text.strip():
                    finals.append(text)
            if finals:
                self._insert_markdown(cursor, "\n".join(finals).rstrip() + "\n")

        self._scroll_bottom()

    # -------------------
    # widget event handlers
    # -------------------

    def eventFilter(self, obj, event):
        # the chat list changed width (window or splitter move): the elided
        # titles were measured for the old width, so rebuild them shortly after
        try:
            if (
                not self.closed
                and event.type() == QtCore.QEvent.Type.Resize
                and obj is self.chat_list.viewport()
                # only real width changes: the vertical scrollbar coming and
                # going also resizes the viewport, and reacting to that would
                # repopulate forever, hijacking every scroll you attempt
                and obj.width() != self._list_width
            ):
                self._list_reflow.start()
        except Exception:
            pass
        return super().eventFilter(obj, event)

    def _on_chat_clicked(self, item, column=0):
        if self._suppress_list_signal or item is None:
            return
        chat_id = item.data(QtCore.Qt.UserRole)
        if chat_id:
            self.channel.submit_async(self.channel._do_load_chat, chat_id)

    def _on_chat_pressed(self, item):
        # left-press switches immediately; right-press belongs to the menu
        try:
            if QtWidgets.QApplication.mouseButtons() & QtCore.Qt.RightButton:
                return
        except Exception:
            pass
        self._on_chat_clicked(item)

    def _on_chat_context_menu(self, position):
        item = self.chat_list.itemAt(position)
        if item is None:
            return

        chat_id = item.data(QtCore.Qt.UserRole)
        if not chat_id:
            return

        menu = QtWidgets.QMenu(self)
        rename_action = menu.addAction("Rename Chat")
        delete_action = menu.addAction("Delete Chat")

        chat_title = item.data(QtCore.Qt.UserRole + 1) or "Untitled"

        chosen = menu.exec(self.chat_list.mapToGlobal(position))
        if chosen is rename_action:
            new_title, ok = QtWidgets.QInputDialog.getText(
                self, "Rename Chat", "New title:", QtWidgets.QLineEdit.Normal, str(chat_title)
            )
            if ok and new_title.strip():
                self.channel.submit_async(self.channel._do_rename_chat, chat_id, new_title.strip())
        elif chosen is delete_action:
            answer = QtWidgets.QMessageBox.question(
                self,
                "Delete Chat",
                f"Really delete '{chat_title}'? This cannot be undone.",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No,
            )
            if answer == QtWidgets.QMessageBox.Yes:
                self.channel.submit_async(self.channel._do_delete_chat, chat_id)

    def _on_model_selected(self, index):
        # activated[int] fires after the selection moved, index is safe to read
        try:
            model_name = self.model_combo.itemText(int(index))
        except Exception:
            model_name = self.model_combo.currentText()
        if model_name:
            self.channel.submit_async(self.channel._do_set_model, str(model_name))

    def _open_settings(self):
        if self.closed:
            return

        dialog = self.settings_dialog
        if dialog is None:
            dialog = settings_dialog.QtSettingsDialog(self.channel, self)
            self.settings_dialog = dialog

        dialog.refresh_from_disk()
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def settings_saved(self, result):
        # the save ran on the channel side: hand the verdict back to the dialog
        # and re-apply the parts of the theme that can change live
        dialog = self.settings_dialog
        if dialog is not None:
            dialog.on_saved(result)

        self.refresh_theme()

    def refresh_theme(self):
        if self.closed:
            return

        title = str(self.channel._val("window_title", "Lumara Qt6"))
        self.setWindowTitle(title)
        self._apply_theme(title)
        self.sidebar.setVisible(bool(self.channel._val("show_chat_sidebar", True)))

        # the sidebar rows carry inline stylesheets painted with the colors of
        # the theme they were built under: rebuild them, or a dark->light flip
        # leaves dark-theme text sitting on the new light background
        try:
            self._populate_chat_list()
        except Exception:
            pass

        # same story for the chat itself: every label/bubble format baked the
        # old palette into the document, so have the channel redraw history
        try:
            self.channel.submit_async(self.channel._redraw_history)
        except Exception:
            pass

        dialog = self.settings_dialog
        if dialog is not None:
            try:
                dialog.setStyleSheet(self.styleSheet())
                dialog.setFont(self.font())
            except Exception:
                pass

    # -------------------
    # live streaming turns: in-chat progress bar + streamed tool calls
    # -------------------

    def _color(self, key, fallback):
        """resolve a message color: the replicated webui theme, or the system
        palette when following the KDE Plasma style"""
        if self._native:
            return str(self._theme_colors.get(key, fallback))

        if key == "user_color":
            return self.palette().color(QtGui.QPalette.Link).name()
        if key == "assistant_color":
            return self.palette().color(QtGui.QPalette.Highlight).name()
        if key == "system_color":
            return self.palette().color(QtGui.QPalette.PlaceholderText).name()
        if key == "accent_color":
            return self.palette().color(QtGui.QPalette.Highlight).name()
        if key == "text_color":
            return self.palette().color(QtGui.QPalette.Text).name()

        # errors: the configured red reads fine in every scheme
        return str(self.channel._val(key, fallback))

    def begin_stream(self):
        if self.closed:
            return

        self._live = {
            "start": None,
            "progress": None,
            "segs": {},
            "order": [],
            "errors": [],
            "final": [],
        }

        cursor = self.chat.textCursor()
        cursor.movePosition(QtGui.QTextCursor.End)
        if self.chat.toPlainText():
            cursor.insertText("\n")
        title = str(self.channel._val("window_title", "Lumara"))
        cursor.insertText(title + "\n", self._fmt(self._color("assistant_color", "#c084fc")))
        self._live["start"] = cursor.position()
        self._scroll_bottom()
        self.set_status("thinking...")

    def set_progress(self, percent, label):
        """inline themed progress bar: first line of the live turn"""
        if self.closed or not self._live:
            return
        try:
            percent = max(0, min(100, int(percent or 0)))
        except Exception:
            percent = 0

        self._live["progress"] = (percent, str(label))
        self._request_live_render()

    def finish_progress(self, final_label=None):
        """prompt processed: the progress bar quietly disappears from the turn"""
        self.clear_progress()

    def clear_progress(self):
        if self.closed or not self._live:
            return

        self._live["progress"] = None
        self._request_live_render()

    def apply_step(self, step):
        """step-based stream"""
        if self.closed or not self._live or not isinstance(step, dict):
            return

        step_no = step.get("step") or 1
        if step_no not in self._live["order"]:
            self._live["order"].append(step_no)
        self._live["segs"][f"{step_no}:step"] = step

        self._request_live_render()
        self.set_status("generating...")

    def apply_final(self, messages):
        """authoritative snapshot of the turn's final answer bubbles
        (an empty list retracts the provisional bubble back into its step)"""
        if self.closed or not self._live:
            return

        self._live["final"] = [m for m in (messages or []) if isinstance(m, dict)]
        self._request_live_render()
        self.set_status("generating...")

    def stream_error(self, text):
        if self.closed or not self._live:
            return
        self._live["errors"].append(str(text))
        self._request_live_render()

    def end_stream(self):
        live = self._live
        self._live = None

        if self.closed:
            return

        if live is not None:
            # the turn is over: a live bar may never survive it
            live["progress"] = None
            if live.get("start") is not None:
                self._render_region_into(live)

        text = self.chat.toPlainText()
        if text and not text.endswith("\n"):
            cursor = self.chat.textCursor()
            cursor.movePosition(QtGui.QTextCursor.End)
            cursor.insertText("\n")
        self._scroll_bottom()

    def _request_live_render(self):
        # one coalesced repaint per screen frame for all streaming: at
        # monitor rate nobody can tell this isn't per-token, and it spares
        # the document several rebuilds per frame when tokens burst in
        # (tool args especially). the interval is set from the refresh rate
        # in __init__, so this is literally vsync-paced rather than a lag
        if self._live_render_pending:
            return
        self._live_render_pending = True
        self._live_reflow.start()

    def _flush_live_render(self):
        self._live_render_pending = False
        self._render_region()

    def _render_region(self):
        live = self._live
        if not live or self.closed or live.get("start") is None:
            return
        self._render_region_into(live)

    @staticmethod
    def _piece_sig(kind, text):
        # cheap fingerprint of one render piece: anything that can visibly
        # change the live region has to leak into this tuple. tool cards
        # grow their args string, gain a response/summary, or flip to failed
        if kind == "tool_card" and isinstance(text, dict):
            fn = text.get("function") or {}
            meta = text.get("_metadata") or {}
            return (
                kind,
                str(fn.get("name")),
                len(str(fn.get("arguments") or "")),
                meta.get("response") is not None,
                bool(meta.get("failed")),
                str(meta.get("summary")),
                str(meta.get("args_parsed")),
            )
        return (kind, text)

    def _render_region_into(self, live):
        pieces = self._live_pieces(live)
        if not pieces:
            pieces = [("running", "Thinking...\n")]

        # identical fingerprint = the document already shows exactly this;
        # rebuilding anyway would be pure flicker (and would stomp a
        # collapsible the user just toggled open by hand)
        signature = tuple(self._piece_sig(kind, text) for kind, text in pieces)
        if signature == live.get("render_sig"):
            return
        live["render_sig"] = signature

        bar = self.chat.verticalScrollBar()
        was_at_bottom = bar.value() >= bar.maximum() - 80
        prev_scroll = bar.value()

        # any collapsible inside the region is about to be rebuilt from scratch
        self._collapsibles = [r for r in self._collapsibles if r["h_end"] <= live["start"]]

        # one atomic repaint: rip-and-reinsert would otherwise flash the
        # empty gap (and let the viewport wander mid-edit on huge regions)
        self.chat.setUpdatesEnabled(False)
        try:
            cursor = QtGui.QTextCursor(self.chat.document())
            cursor.setPosition(live["start"])
            cursor.movePosition(QtGui.QTextCursor.End, QtGui.QTextCursor.KeepAnchor)
            cursor.removeSelectedText()

            cursor.beginEditBlock()
            for kind, text in pieces:
                if kind == "reason_open":
                    self._append_collapsible(cursor, text, True)
                elif kind == "reason_collapsed":
                    self._append_collapsible(cursor, text, False)
                elif kind == "tool_card":
                    self._tool_card(cursor, text)
                elif kind == "plain":
                    self._insert_markdown(cursor, text)
                else:
                    cursor.insertText(text, self._live_fmt(kind))
            cursor.endEditBlock()
        finally:
            self.chat.setUpdatesEnabled(True)

        if was_at_bottom:
            self._scroll_bottom()
        else:
            # reading something earlier while it streams: the teardown moved
            # the text cursor, so pin the viewport back where it was
            bar.setValue(prev_scroll)

    def _live_pieces(self, live):
        # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-25) harness:openlumara
        # step-based stream: one folded step object per step number, plus
        # the live final bubbles (keyed by their step number).
        pieces = []

        show_reasoning = bool(self.channel._val("show_reasoning", False))

        final_by_step = {}
        for message in live.get("final", []):
            final_by_step[message.get("step") or 0] = message.get("content") or ""

        for step in live["order"]:
            seg = live["segs"].get(f"{step}:step") or {}
            reasoning_text = (seg.get("reasoning_content") or "").strip()
            tools = seg.get("tool_calls") or []

            # the step's own content plus its live final bubble: the two
            # never overlap (a retract moves the final text into the step
            # exactly when the final snapshot empties), but belt & braces
            # against an in-flight event pair
            parts = [
                p for p in (seg.get("content") or "", final_by_step.get(step, ""))
                if p.strip()
            ]
            content_text = "\n\n".join(parts)
            final_by_step.pop(step, None)

            if reasoning_text:
                if show_reasoning:
                    # still streaming? stays open. settled? tucks itself away
                    settled = (
                        bool(content_text.strip())
                        or bool(tools)
                        or not seg.get("reasoning_live")
                    )
                    pieces.append(("reason_collapsed" if settled else "reason_open", reasoning_text))
                elif not content_text.strip():
                    # reasoning hidden: show a placeholder until the answer comes
                    pieces.append(("running", "Thinking...\n"))

            if content_text.strip():
                pieces.append(("plain", content_text.rstrip() + "\n"))

            for tool in tools:
                pieces.append(("tool_card", tool))

        # final bubble of a step that never materialized: a pure content
        # answer streams with no step events at all
        for message in live.get("final", []):
            if (message.get("step") or 0) in set(live["order"]):
                continue
            text = message.get("content") or ""
            if text.strip():
                pieces.append(("plain", text.rstrip() + "\n"))

        for err in live["errors"]:
            pieces.append(("fail", "\u2717 " + err + "\n"))

        # prompt/model progress trails the newest content, never leads it
        if live["progress"] is not None:
            percent, label = live["progress"]
            filled = int(round(percent / 100.0 * 14))
            bar = "\u25b0" * filled + "\u25b1" * (14 - filled)
            pieces.append(("running", f"\n{label}  {bar}\n"))

        return pieces

    def _live_fmt(self, name):
        fmt = QtGui.QTextCharFormat()

        if name == "sys":
            fmt.setForeground(QtGui.QColor(self._color("system_color", "#9a88a6")))
        elif name == "fail":
            fmt.setForeground(QtGui.QColor(self._color("error_color", "#ff6b6b")))
        elif name == "reason":
            fmt.setForeground(QtGui.QColor(self._color("system_color", "#9a88a6")))
            fmt.setFontItalic(True)
        elif name == "reason_hdr":
            fmt.setForeground(QtGui.QColor(self._color("accent_color", "#c084fc")))
            fmt.setFontWeight(QtGui.QFont.Bold)
        elif name == "running":
            fmt.setForeground(QtGui.QColor(self._color("accent_color", "#c084fc")))
            fmt.setFontWeight(QtGui.QFont.Bold)
        elif name == "tool":
            # tool card body: the arg rows and response, de-emphasized
            fmt.setForeground(QtGui.QColor(self._color("system_color", "#9a88a6")))

        return fmt

    # -------------------
    # collapsible reasoning blocks
    # -------------------

    def _append_collapsible(self, cursor, text, expanded):
        """draw a Thoughts header (plus its body when open) at the cursor
        and remember where it landed, so a click on the header can toggle it"""
        body = str(text or "").strip()
        if not body:
            return
        body += "\n"

        h_start = cursor.position()
        glyph = "\u25be" if expanded else "\u25b8"
        cursor.insertText(glyph + " Thoughts\n", self._live_fmt("reason_hdr"))
        h_end = cursor.position()

        if expanded:
            cursor.insertText(body, self._live_fmt("reason"))

        self._collapsibles.append(
            {
                "h_start": h_start,
                "h_end": h_end,
                "start": h_end,
                "end": cursor.position(),
                "text": body,
                "expanded": expanded,
            }
        )

    def _card_value(self, value):
        # one argument / response value as tidy text, shown in FULL (never
        # truncated: code dumps must be readable end to end), continuation
        # lines kept indented under their key
        if isinstance(value, (dict, list)):
            try:
                text = json.dumps(value)
            except Exception:
                text = str(value)
        else:
            text = str(value)
        return "\n    ".join(text.splitlines()) if text else ""

    # -------------------
    # tool response rendering, ported from the webui's tool_results.js:
    # parsed json becomes key->value rows (arrays use index rows, never
    # inline previews), 'content' renders first and keyless, the rest of
    # the fields follow behind a separator; unparseable payloads print raw.
    # caps mirror the webui exactly: 12 entries top level, 8 when nested
    # -------------------

    _result_cap_top = 12
    _result_cap_nested = 8

    def _result_scalar(self, value):
        # js-ish scalar text: true/false/null lowercase, strings raw
        if value is None:
            return "null"
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, str):
            return value if value else "empty"
        return str(value)

    def _result_line(self, pad, prefix, text):
        # one scalar row; multi-line strings (stdout dumps, file reads) get
        # their continuation lines indented under the key
        parts = str(text).splitlines()
        if not parts:
            return [pad + prefix]
        rows = [pad + prefix + parts[0]]
        rows += [pad + "    " + part for part in parts[1:]]
        return rows

    def _result_rows(self, data, depth):
        pad = "  " * depth
        cap = self._result_cap_top if depth == 0 else self._result_cap_nested

        if isinstance(data, list):
            if not data:
                return [pad + "empty"]
            rows = []
            for index, item in enumerate(data[:cap]):
                if isinstance(item, (dict, list)):
                    rows.append(pad + str(index) + ":")
                    rows.extend(self._result_rows(item, depth + 1))
                else:
                    rows.extend(
                        self._result_line(pad, str(index) + ": ", self._result_scalar(item))
                    )
            if len(data) > cap:
                rows.append(pad + "+ " + str(len(data) - cap) + " more")
            return rows

        if isinstance(data, dict):
            if not data:
                return [pad + "empty"]
            rows = []
            for key, value in list(data.items())[:cap]:
                prefix = str(key) + ": "
                if isinstance(value, (dict, list)):
                    rows.append(pad + str(key) + ":")
                    rows.extend(self._result_rows(value, depth + 1))
                else:
                    rows.extend(self._result_line(pad, prefix, self._result_scalar(value)))
            if len(data) > cap:
                rows.append(pad + "+ " + str(len(data) - cap) + " more keys")
            return rows

        return self._result_line(pad, "", self._result_scalar(data))

    def _tool_response_lines(self, response):
        """webui response-row port: json object -> content rows first (keyless,
        full width), remaining fields below a separator line; anything else
        (plain strings, half-streamed json) shows raw, same fallback as the
        webui's .raw-response paragraph"""
        text = str(response)
        parsed = None
        try:
            candidate = json.loads(text)
            # webui parity: objects AND arrays get the row treatment,
            # scalars/half-streamed json fall back to raw text
            if isinstance(candidate, (dict, list)):
                parsed = candidate
        except Exception:
            parsed = None

        if parsed is None:
            return self._card_value(text)

        rows = []
        if isinstance(parsed, list):
            rows.extend(self._result_rows(parsed, 0))
        else:
            if "content" in parsed:
                content = parsed["content"]
                if isinstance(content, (dict, list)):
                    rows.extend(self._result_rows(content, 0))
                else:
                    rows.extend(self._result_line("", "", self._result_scalar(content)))

            rest = {k: v for k, v in parsed.items() if k != "content"}
            if rest:
                if rows:
                    rows.append("  ")  # the webui's hairline between content and rest
                rows.extend(self._result_rows(rest, 0))

        if not rows:
            return self._card_value(text)
        # every row is one line; the join indents them all under the → marker
        return "\n    ".join(rows)

    def _tool_card(self, cursor, tool, expanded=None):
        """a collapsible tool call card, the qt6 take on the webui's: a wrench
        + Module: action header (plus the backend's one-line arg summary),
        folding open to reveal the parsed arg rows and the response. args
        stream live because the backend re-stamps args_parsed every token"""
        if not isinstance(tool, dict):
            return

        meta = tool.get("_metadata") or {}
        fn = tool.get("function") or {}
        name = fn.get("name") or "tool"
        response = meta.get("response")
        failed = bool(meta.get("failed"))
        running = response is None
        # the arg summary/rows are the "streamed tool calls" part; hide them
        # entirely when that setting is off, just like the old compact line did
        show_args = bool(self.channel._val("stream_tool_calls", True))

        if expanded is None:
            # open while it runs (watch the args arrive), tucks itself away the
            # moment the response lands: the webui's auto-collapse. nothing to
            # watch when arg streaming is off, so it never opens on its own
            expanded = running and show_args

        if running:
            hdr = "running"
        elif failed:
            hdr = "fail"
        else:
            hdr = "sys"

        # "Coder: file read" style, mirroring the webui module/action split
        parts = str(name).split("_")
        label = parts[0][:1].upper() + parts[0][1:] if parts and parts[0] else name
        if len(parts) > 1:
            label += ": " + " ".join(parts[1:])

        glyph = "\u25be" if expanded else "\u25b8"
        header_runs = [(glyph + " \u2692 " + label, hdr)]

        lines = []
        args_parsed = meta.get("args_parsed")
        if show_args and isinstance(args_parsed, dict):
            for key, value in args_parsed.items():
                lines.append("  " + str(key) + ": " + self._card_value(value))
        if response is not None:
            lines.append("  \u2192 " + self._tool_response_lines(response))
        body = "\n".join(lines)
        if body:
            body += "\n"

        summary = meta.get("summary")
        if summary and show_args:
            header_runs.append((" " + str(summary), "tool"))
        if running:
            header_runs.append(("  ...", hdr))
        header_runs[-1] = (header_runs[-1][0] + "\n", header_runs[-1][1])

        self._append_block(cursor, header_runs, body, hdr, "tool", expanded)

    def _append_block(self, cursor, header_runs, body_text, hdr_fmt, body_fmt, expanded):
        """generic collapsible: a header made of (text, format) runs (its very
        first character is the toggle glyph) plus a body shown only when open.
        remembers where it landed so clicking the header folds/unfolds it."""
        h_start = cursor.position()
        for text, fmt in header_runs:
            cursor.insertText(text, self._live_fmt(fmt))
        h_end = cursor.position()

        body = str(body_text or "")
        opened = bool(expanded) and bool(body)
        if opened:
            cursor.insertText(body, self._live_fmt(body_fmt))

        self._collapsibles.append(
            {
                "h_start": h_start,
                "h_end": h_end,
                "start": h_end,
                "end": cursor.position(),
                "text": body,
                "hdr": hdr_fmt,
                "body": body_fmt,
                "expanded": opened,
            }
        )

    def collapsible_at(self, pos):
        # index of the collapsible whose header covers this document position
        try:
            pos = int(pos)
        except Exception:
            return None
        for index, rec in enumerate(self._collapsibles):
            if rec["h_start"] <= pos < rec["h_end"]:
                return index
        return None

    def handle_chat_click(self, pos):
        # returns True when the click hit a collapsible header
        index = self.collapsible_at(pos)
        if index is None:
            return False
        self._toggle_collapsible(index)
        return True

    def _set_glyph(self, rec, glyph):
        cursor = QtGui.QTextCursor(self.chat.document())
        cursor.setPosition(rec["h_start"])
        cursor.movePosition(QtGui.QTextCursor.NextCharacter, QtGui.QTextCursor.KeepAnchor, 1)
        cursor.insertText(glyph, self._live_fmt(rec.get("hdr", "reason_hdr")))

    def _shift_collapsibles(self, skip_index, from_pos, delta):
        """keep the other records' ranges honest after the text before them moved"""
        for index, rec in enumerate(self._collapsibles):
            if index == skip_index:
                continue
            if rec["h_start"] >= from_pos:
                rec["h_start"] += delta
                rec["h_end"] += delta
            if rec["start"] >= from_pos:
                rec["start"] += delta
            if rec["end"] >= from_pos:
                rec["end"] += delta

    def _toggle_collapsible(self, index):
        try:
            rec = self._collapsibles[int(index)]
        except Exception:
            return

        cursor = QtGui.QTextCursor(self.chat.document())

        if rec["expanded"]:
            length = rec["end"] - rec["start"]
            if length <= 0:
                return
            cursor.setPosition(rec["start"])
            cursor.movePosition(
                QtGui.QTextCursor.NextCharacter, QtGui.QTextCursor.KeepAnchor, length
            )
            cursor.removeSelectedText()
            rec["end"] = rec["start"]
            rec["expanded"] = False
            self._shift_collapsibles(index, rec["h_end"], -length)
            self._set_glyph(rec, "\u25b8")
        else:
            cursor.setPosition(rec["start"])
            cursor.insertText(rec["text"], self._live_fmt(rec.get("body", "reason")))
            added = len(rec["text"])
            rec["end"] = rec["start"] + added
            rec["expanded"] = True
            self._shift_collapsibles(index, rec["start"], added)
            self._set_glyph(rec, "\u25be")

    def _set_theme_variables(self):
        """load the chosen webui theme files and stash the outcome: both
        theming modes read their colors from these vars - custom mode paints
        the full qss from them, system mode only borrows them for the
        application palette while the platform style draws the widgets"""
        channel = self.channel
        family = str(channel._val("theme", "pro-monochrome"))
        mode = str(channel._val("theme_mode", "dark"))
        try:
            variables = webui_style.load_theme(family, mode)
        except Exception:
            variables = dict(webui_style.FALLBACK_VARS)

        self._theme_vars = variables
        self._theme_colors = webui_style.message_colors(variables)
        self._apply_palette(variables)
        return variables

    def _apply_theme(self, title):
        channel = self.channel
        # custom theme only when the OS didn't hand us a native style itself
        self._native = not channel.system_style_active()

        if not self._native:
            # system style mode: the platform's widget style draws everything
            # (no qss, no forced fonts), but the webui theme still supplies
            # the colors through the application palette. skipping that used
            # to leave the palette frozen at whatever the last custom-theme
            # session applied, so switching theme family/mode here did
            # nothing until follow_system_style got flipped off and on again.
            # any qss left over from a webui-theme session gets torn down
            self._set_theme_variables()
            self.setStyleSheet("")
            return

        # replicate the webui's look: read its very own theme files
        # (themes/base.json + themes/<family>.json, dark/light mode) and
        # derive the whole qt stylesheet + message colors from those vars
        variables = self._set_theme_variables()

        # family only, never a point size: the size stays whatever the app
        # defaults to, exactly like a native app leaves it
        font_family = str(channel._val("font_family", "Sans Serif"))
        font = QtGui.QFont(font_family)
        self.setFont(font)
        self.chat.setFont(font)
        self.input.setFont(font)
        self.send_button.setFont(font)
        self.model_combo.setFont(font)
        self.chat_list.setFont(font)
        self.cat_filter.setFont(font)
        title_font = QtGui.QFont(font_family)
        title_font.setBold(True)
        self.chat_title.setFont(title_font)

        self.setStyleSheet(webui_style.build_qss(variables))

    def _fmt(self, color):
        fmt = QtGui.QTextCharFormat()
        r, g, b, a = webui_style.parse_css_color(str(color))
        fmt.setForeground(QtGui.QColor(r, g, b, a))
        fmt.setFontWeight(QtGui.QFont.Bold)
        return fmt

    def _plain(self):
        return QtGui.QTextCharFormat()

    def _insert_markdown(self, cursor, text):
        """render assistant prose through qt's built-in commonmark importer
        (bold, italics, inline code, fenced code blocks, headings, lists,
        blockquotes, links). streamed turns re-render from scratch every tick,
        so partial markup simply shows as literal text until it gets closed"""
        text = str(text)
        try:
            fragment = QtGui.QTextDocumentFragment.fromMarkdown(text)
        except Exception:
            fragment = None
        if fragment is None or fragment.isEmpty():
            cursor.insertText(text, self._plain())
            return
        start = cursor.position()
        cursor.insertFragment(fragment)
        self._tighten_list_indent(start)
        # commonmark swallows trailing newlines as paragraph terminators, which
        # would glue the next element (tool card, system line) onto the last
        # sentence: if we end inside written text, force a fresh line
        try:
            if cursor.block().text():
                cursor.insertText("\n", self._plain())
        except Exception:
            cursor.insertText("\n", self._plain())

    def _apply_palette(self, variables):
        """the stylesheet paints the widgets it knows about, but plenty of
        surfaces fall back to the application palette: combo popup container
        margins, scrollbars, item views, native bits. inside a kde session
        the qt platform theme hands the app a dark breeze palette no matter
        what our qss says, so those fallback surfaces (e.g. the popup
        padding margins) rendered near-black. solution: derive a real
        QPalette from the very same theme variables"""
        app = QtWidgets.QApplication.instance()
        if app is None:
            return

        def color(name, fallback):
            raw = str(variables.get(name, "") or "").strip()
            return QtGui.QColor(*webui_style.parse_css_color(raw, fallback))

        window = color("--bg-primary", (9, 9, 11, 255))
        secondary = color("--bg-secondary", (12, 12, 15, 255))
        base = color("--bg-input", (15, 15, 18, 255))
        text = color("--text-primary", (250, 250, 250, 255))
        muted = color("--text-muted", (82, 82, 91, 255))
        accent = color("--accent", (212, 212, 216, 255))
        error = color("--error", (252, 165, 165, 255))

        palette = QtGui.QPalette()
        pairs = (
            (QtGui.QPalette.Window, window),
            (QtGui.QPalette.WindowText, text),
            (QtGui.QPalette.Base, base),
            (QtGui.QPalette.AlternateBase, secondary),
            (QtGui.QPalette.Text, text),
            (QtGui.QPalette.Button, window),
            (QtGui.QPalette.ButtonText, text),
            (QtGui.QPalette.ToolTipBase, secondary),
            (QtGui.QPalette.ToolTipText, text),
            (QtGui.QPalette.Highlight, accent),
            (QtGui.QPalette.HighlightedText, window),
            (QtGui.QPalette.Link, accent),
            (QtGui.QPalette.LinkVisited, accent),
            (QtGui.QPalette.BrightText, error),
        )
        placeholder = getattr(QtGui.QPalette, "PlaceholderText", None)
        if placeholder is not None:
            pairs = pairs + ((placeholder, muted),)

        dimmed = {
            QtGui.QPalette.WindowText: muted,
            QtGui.QPalette.Text: muted,
            QtGui.QPalette.ButtonText: muted,
        }

        for group in (QtGui.QPalette.Active, QtGui.QPalette.Inactive):
            for role, value in pairs:
                palette.setColor(group, role, value)
        for role, value in pairs:
            palette.setColor(QtGui.QPalette.Disabled, role, dimmed.get(role, value))

        app.setPalette(palette)

    def _tighten_list_indent(self, start):
        """rebase the lists of a freshly inserted markdown run: the shallowest
        level present drops to 0 so top-level bullets sit exactly where prose
        does (like the webui), while deeper levels keep their 18px step.
        edits the QTextList formats themselves, nothing is torn down; the
        streaming region is rebuilt fresh every tick so it stays consistent"""
        doc = self.chat.document()

        seen = {}
        block = doc.findBlock(start)
        while block.isValid():
            try:
                qlist = block.blockFormat().list()
            except Exception:
                qlist = None
            if qlist is not None:
                try:
                    seen.setdefault(id(qlist), (qlist, int(qlist.format().indent())))
                except Exception:
                    pass
            block = block.next()
        if not seen:
            return

        shallowest = min(entry[1] for entry in seen.values())
        for qlist, indent in seen.values():
            target = max(0, indent - shallowest)
            if target == indent:
                continue
            try:
                fmt = qlist.format()
                fmt.setIndent(target)
                qlist.setFormat(fmt)
            except Exception:
                pass

    def _scroll_bottom(self):
        bar = self.chat.verticalScrollBar()
        bar.setValue(bar.maximum())

    def append_message(self, label, color, text):
        if self.closed:
            return

        cursor = self.chat.textCursor()
        cursor.movePosition(QtGui.QTextCursor.End)
        if self.chat.toPlainText():
            cursor.insertText("\n")
        cursor.insertText(str(label) + "\n", self._fmt(color))
        cursor.insertText(str(text) + "\n", self._plain())
        self._scroll_bottom()

    def append_user(self, text):
        # the webui paints user turns as right-aligned bubbles; a full card
        # with rounded corners is beyond a QTextDocument, so this is its
        # block-level twin: the theme's --bg-message-user as padded block
        if self.closed:
            return

        cursor = self.chat.textCursor()
        cursor.movePosition(QtGui.QTextCursor.End)
        if self.chat.toPlainText():
            cursor.insertText("\n")
        label_start = cursor.position()
        cursor.insertText("You\n", self._fmt(self._color("user_color", "#d4d4d8")))
        # the label rides above its bubble, so it floats to the right edge too
        label_fmt = QtGui.QTextBlockFormat()
        label_fmt.setAlignment(QtCore.Qt.AlignRight)
        label_fmt.setRightMargin(16.0)
        label_cursor = QtGui.QTextCursor(self.chat.document())
        label_cursor.setPosition(label_start)
        label_cursor.mergeBlockFormat(label_fmt)
        self._insert_user_text(cursor, str(text) + "\n")
        self._scroll_bottom()

    def _insert_user_text(self, cursor, text):
        """the user's turn: right-aligned plain text. (a real content-sized,
        rounded bubble is impossible in a QTextDocument: block formats span
        the full line, so we skip the background entirely)"""
        body = QtGui.QTextCharFormat()
        r, g, b, a = webui_style.parse_css_color(self._color("text_color", "#fafafa"))
        body.setForeground(QtGui.QColor(r, g, b, a))
        start = cursor.position()
        cursor.insertText(text, body)
        end = cursor.position()

        block_fmt = QtGui.QTextBlockFormat()
        block_fmt.setLeftMargin(32.0)
        block_fmt.setRightMargin(16.0)
        block_fmt.setAlignment(QtCore.Qt.AlignRight)

        doc = self.chat.document()
        block_cursor = QtGui.QTextCursor(doc)
        block = doc.findBlock(start)
        while block.isValid() and block.position() < end:
            # with no selection, mergeBlockFormat applies to the block the
            # cursor sits in: no SelectionType enums involved (some pyside6
            # builds don't expose them at class scope)
            block_cursor.setPosition(block.position())
            block_cursor.mergeBlockFormat(block_fmt)
            block = block.next()

    def append_assistant_message(self, text):
        # pushed assistant messages get the same markdown treatment as the
        # streaming turns, instead of the plain label+text of user/system
        if self.closed:
            return
        title = str(self.channel._val("window_title", "Lumara"))
        cursor = self.chat.textCursor()
        cursor.movePosition(QtGui.QTextCursor.End)
        if self.chat.toPlainText():
            cursor.insertText("\n")
        cursor.insertText(title + "\n", self._fmt(self._color("assistant_color", "#c084fc")))
        self._insert_markdown(cursor, str(text).rstrip() + "\n")
        self._scroll_bottom()

    def append_system(self, text):
        self.append_message("System", self._color("system_color", "#9a88a6"), text)

    def append_error(self, text):
        self.append_message("Error", self._color("error_color", "#ff6b6b"), text)

    def begin_assistant(self):
        if self.closed:
            return

        cursor = self.chat.textCursor()
        if self.chat.toPlainText():
            cursor.insertText("\n\n")

        title = str(self.channel._val("window_title", "Lumara"))
        color = self._color("assistant_color", "#d4d4d8")
        cursor.insertText(title + "\n", self._fmt(color))
        self._scroll_bottom()

    def append_assistant_text(self, text):
        if self.closed or text == "" or text is None:
            return

        cursor = self.chat.textCursor()
        cursor.insertText(str(text), self._plain())
        self._scroll_bottom()

    def finish_assistant(self):
        if self.closed:
            return
        cursor = self.chat.textCursor()
        cursor.insertText("\n", self._plain())
        self._scroll_bottom()

    def set_status(self, text):
        # status bar removed on request: kept as a no-op sink for channel events
        return

    def set_busy(self, busy):
        if self.closed:
            return
        self.busy = bool(busy)
        self.send_button.setText("Stop" if self.busy else "Send")
        # the webui swaps the send button for the red stop button while a
        # stream runs: mirror that by switching the styled object name
        wanted = "stop" if self.busy else "send"
        if self.send_button.objectName() != wanted:
            self.send_button.setObjectName(wanted)
            style = self.send_button.style()
            style.unpolish(self.send_button)
            style.polish(self.send_button)

    def _send_now(self):
        if self.busy or self.closed:
            return

        text = self.input.text().strip()
        if not text:
            return

        self.input.clear()
        try:
            self._send_future = self.channel.submit_user_message(text)
        except Exception as e:
            self.append_error(str(e))
            self.set_busy(False)

    def _cancel_current(self):
        if self._send_future is not None and not self._send_future.done():
            try:
                self._send_future.cancel()
            except Exception:
                pass

    def _on_return(self):
        if not self.busy:
            self._send_now()

    def _on_send_button(self):
        if self.busy:
            self._cancel_current()
        else:
            self._send_now()

    def closeEvent(self, event):
        self.closed = True
        self.channel.request_stop()
        super().closeEvent(event)
