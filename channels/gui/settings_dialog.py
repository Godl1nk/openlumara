# -- AI GENERATED CODE (qwen3.8-flash-next) :: (2026-10-21) harness:openlumara
"""the qt6 settings dialog: category tree sidebar, typed fields built from
each setting's schema, module toggles and a dirty-tracking Revert/Save footer"""
import copy
import json

import PySide6.QtCore as QtCore
import PySide6.QtGui as QtGui
import PySide6.QtWidgets as QtWidgets

import core
import channels.gui.settings_model as settings_model
import channels.gui.widgets as widgets
import channels.gui.webui_style as webui_style


def _resize_mode(name):
    # pyside6 builds disagree about where these live (scoped SectionResizeMode,
    # legacy ResizeMode, or plain shortcut attributes): take whichever exists
    hv = QtWidgets.QHeaderView
    for source in (
        getattr(hv, "SectionResizeMode", None),
        getattr(hv, "ResizeMode", None),
        hv,
    ):
        if source is not None and hasattr(source, name):
            return getattr(source, name)
    return None


class QtSettingsDialog(QtWidgets.QDialog):
    # the webui settings modal, in Qt: a category sidebar, typed fields built
    # from each setting's schema, module enable toggles, and a manual
    # Revert/Save footer that warns about unsaved changes on close
    def __init__(self, channel, parent=None):
        super().__init__(parent)
        self.channel = channel
        self.categories = {}
        self.original = {}
        self.active_category = None
        self.active_module = ""
        self.show_unsafe = False
        self.saving = False
        self.models = []
        self.model_fields = []

        self.setWindowTitle("Settings")
        self.resize(940, 640)
        # window-modal, but shown instead of exec()'d: a nested Qt event loop
        # would stall the asyncio loop this channel pumps its chat through
        self.setWindowModality(QtCore.Qt.WindowModal)

        self._build()
        self.reload()

    # -------------------
    # layout
    # -------------------

    def _build(self):
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        body = QtWidgets.QHBoxLayout()
        body.setSpacing(10)

        nav_column = QtWidgets.QVBoxLayout()
        nav_column.setSpacing(6)

        self.nav = QtWidgets.QTreeWidget()
        self.nav.setFixedWidth(230)
        self.nav.setHeaderHidden(True)
        self.nav.setColumnCount(1)
        self.nav.setUniformRowHeights(True)
        self.nav.currentItemChanged.connect(self._on_nav_item)
        nav_column.addWidget(self.nav, 1)





        body.addLayout(nav_column)

        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.form_host = QtWidgets.QWidget()
        self.form = QtWidgets.QVBoxLayout(self.form_host)
        self.form.setSpacing(10)
        # the style default margin here floated a phantom gap above every page
        self.form.setContentsMargins(2, 2, 2, 2)
        self.form.addStretch(1)
        self.scroll.setWidget(self.form_host)
        body.addWidget(self.scroll, 1)

        root.addLayout(body, 1)

        footer = QtWidgets.QHBoxLayout()
        footer.setSpacing(8)

        self.status = QtWidgets.QLabel("")
        self.status.setWordWrap(True)

        self.dirty = QtWidgets.QLabel("Unsaved changes")
        self.dirty.setVisible(False)

        self.restart_button = QtWidgets.QPushButton("Restart Server")
        self.restart_button.setToolTip("Restart OpenLumara, needed for module and channel changes")
        self.restart_button.setFixedHeight(34)
        # enter belongs to Save, never to whatever button got built first
        # (autoDefault would crown this one and hit restart on a keystroke)
        self.restart_button.setAutoDefault(False)
        self.restart_button.setDefault(False)
        self.restart_button.clicked.connect(self._restart)

        self.revert_button = QtWidgets.QPushButton("Revert")
        self.revert_button.setToolTip("Go back to the values from the last save")
        self.revert_button.setFixedHeight(34)
        self.revert_button.setAutoDefault(False)
        self.revert_button.setDefault(False)
        self.revert_button.clicked.connect(self._revert)

        self.save_button = QtWidgets.QPushButton("Save")
        self.save_button.setFixedHeight(34)
        self.save_button.setDefault(True)
        self.save_button.clicked.connect(self._save)

        footer.addWidget(self.restart_button)
        footer.addWidget(self.status, 1)
        footer.addWidget(self.dirty)
        footer.addWidget(self.revert_button)
        footer.addWidget(self.save_button)
        root.addLayout(footer)

        self._update_footer()

    def _clear_form(self):
        self.model_fields = []
        while self.form.count():
            item = self.form.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def _muted(self, text):
        label = QtWidgets.QLabel(str(text))
        label.setWordWrap(True)
        label.setEnabled(False)
        return label

    # -------------------
    # data
    # -------------------

    def reload(self):
        try:
            tree = settings_model.load_settings_tree()
        except Exception as e:
            self.status.setText("Could not read the settings tree: " + core.detail_error(e))
            return

        if not tree:
            self.status.setText("The settings tree came back empty.")
            return

        self.categories = tree
        self.original = copy.deepcopy(tree)
        self.active_module = ""
        self._rebuild_nav()
        self._render()
        self._update_footer()

    def refresh_from_disk(self):
        # re-opened: pull the latest values, but never clobber live edits
        if not self._is_dirty():
            self.reload()

    def _default_category(self, keys):
        for section in ("user_channels", "channels"):
            if section in keys:
                enabled = self.categories[section].get("enabled") or []
                if self.channel.name in enabled:
                    return section
        for section in ("api", "model", "core"):
            if section in keys:
                return section
        return keys[0] if keys else None

    def _module_names(self, category):
        names = set(category.get("enabled") or [])
        names.update(category.get("disabled") or [])
        names.update((category.get("settings") or {}).keys())
        return sorted(names)

    def _disabled_brush(self):
        # disabled rows must dim toward the theme, not toward the platform
        # palette: under KDE that palette belongs to the system colorscheme,
        # so light-mode trees were getting the dark scheme's near-white text.
        # NOTE: chat_window._native==True IS the custom webui-theme mode
        # (it's set to `not system_style_active()`), which is exactly when
        # the palette belongs to the wrong scheme and _theme_vars holds right
        window = getattr(self.channel, "_window", None)
        variables = getattr(window, "_theme_vars", None) if window is not None else None
        if variables and getattr(window, "_native", False):
            color = QtGui.QColor(webui_style.disabled_text_color(variables))
            if color.isValid():
                return QtGui.QBrush(color)
        base = self.palette().color(QtGui.QPalette.Text)
        dim = QtGui.QColor(base)
        dim.setAlpha(105)
        return QtGui.QBrush(dim)

    def _rebuild_nav(self):
        keys = sorted(
            self.categories,
            key=lambda k: (self.categories[k].get("order", 0), k),
        )

        if self.active_category not in keys:
            self.active_category = self._default_category(keys)

        self.nav.blockSignals(True)
        self.nav.clear()

        target_item = None
        for key in keys:
            category = self.categories[key]
            top = QtWidgets.QTreeWidgetItem([str(category.get("title") or key)])
            top.setData(0, QtCore.Qt.UserRole, key)
            top.setData(0, QtCore.Qt.UserRole + 1, "")
            description = category.get("description")
            if description:
                top.setToolTip(0, str(description))
            self.nav.addTopLevelItem(top)

            if key == self.active_category and not self.active_module:
                target_item = top

            if category.get("isModuleCategory"):
                enabled = category.get("enabled") or []
                for name in self._module_names(category):
                    module = (category.get("settings") or {}).get(name) or {}
                    child = QtWidgets.QTreeWidgetItem([settings_model.format_label(name)])
                    child.setData(0, QtCore.Qt.UserRole, key)
                    child.setData(0, QtCore.Qt.UserRole + 1, name)
                    if name not in enabled:
                        child.setForeground(0, self._disabled_brush())
                    module_desc = module.get("description")
                    if module_desc:
                        child.setToolTip(0, str(module_desc))
                    top.addChild(child)
                    if key == self.active_category and name == self.active_module:
                        target_item = child

                top.setExpanded(key == self.active_category)

        if target_item is None and self.nav.topLevelItemCount() > 0:
            target_item = self.nav.topLevelItem(0)
            self.active_category = target_item.data(0, QtCore.Qt.UserRole)
            self.active_module = ""
            target_item.setExpanded(True)

        self.nav.setCurrentItem(target_item)
        self.nav.blockSignals(False)

    def _on_nav_item(self, current, previous):
        if current is None:
            return
        self.active_category = current.data(0, QtCore.Qt.UserRole)
        self.active_module = current.data(0, QtCore.Qt.UserRole + 1) or ""
        self._render()

    def _refresh_tree_item(self, name, on):
        for index in range(self.nav.topLevelItemCount()):
            top = self.nav.topLevelItem(index)
            if top.data(0, QtCore.Qt.UserRole) != self.active_category:
                continue
            for row in range(top.childCount()):
                child = top.child(row)
                if child.data(0, QtCore.Qt.UserRole + 1) == name:
                    if on:
                        child.setForeground(0, QtGui.QBrush())
                    else:
                        child.setForeground(0, self._disabled_brush())
                    return



    # -------------------
    # rendering
    # -------------------

    def _render(self):
        # the channel's show_unsafe_settings is re-read on every render:
        # changing it in the qt6 settings page takes effect right away
        self.show_unsafe = bool(self.channel._val("show_unsafe_settings", False))
        self._clear_form()

        category = self.categories.get(self.active_category)
        if category is None:
            self.form.addStretch(1)
            return

        show_module = bool(category.get("isModuleCategory")) and bool(self.active_module)

        # no in-page title block anywhere: the sidebar already says where you are
        if category.get("isReadOnly"):
            self.form.addWidget(self._muted("Nothing configurable here."))
        elif show_module:
            self._render_module_settings(category)
        elif category.get("isModuleCategory"):
            self._render_module_section(category)
        else:
            settings = category.get("settings") or {}
            if not any(isinstance(node, dict) for node in settings.values()):
                self.form.addWidget(self._muted("Nothing configurable here."))
            else:
                self._render_settings(self.form, settings)

        self.form.addStretch(1)

    def _render_module_section(self, category):
        # the module category itself is just a switchboard: a table listing every
        # module with its description and an on/off toggle. a module's settings
        # are reached from its node in the sidebar tree, not from here.
        enabled = category.get("enabled") or []
        settings = category.get("settings") or {}
        names = self._module_names(category)

        table = QtWidgets.QTableWidget(len(names), 3)
        table.setHorizontalHeaderLabels(
            [str(category.get("title") or "Module"), "Description", "Enabled"]
        )
        table.verticalHeader().setVisible(False)
        table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setFocusPolicy(QtCore.Qt.NoFocus)
        table.setShowGrid(False)
        table.setAlternatingRowColors(True)

        header = table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setHighlightSections(False)
        header.setSectionResizeMode(0, _resize_mode("ResizeToContents"))
        header.setSectionResizeMode(1, _resize_mode("Stretch"))
        header.setSectionResizeMode(2, _resize_mode("Fixed"))
        table.setColumnWidth(2, 84)
        table.setMinimumHeight(max(1, min(len(names), 14)) * 32 + 40)

        metrics = table.fontMetrics()
        for row, name in enumerate(names):
            module = settings.get(name) or {}
            label = settings_model.format_label(name)

            name_item = QtWidgets.QTableWidgetItem(label)
            name_item.setToolTip(str(module.get("description") or label))
            table.setItem(row, 0, name_item)

            description = str(module.get("description") or "")
            if description:
                desc_item = QtWidgets.QTableWidgetItem(
                    metrics.elidedText(description, QtCore.Qt.ElideRight, 380)
                )
                desc_item.setToolTip(description)
            else:
                desc_item = QtWidgets.QTableWidgetItem("")
            table.setItem(row, 1, desc_item)

            check = widgets.ToggleSwitch()
            check.setToolTip("Enable or disable " + label)
            check.setChecked(name in enabled)
            check.toggled.connect(lambda on, target=name: self._toggle_module(target, on))
            holder = QtWidgets.QWidget()
            # without this the global QWidget background rule paints the holder
            # as an opaque plate, boxing the switch in against striped rows
            holder.setStyleSheet("background: transparent;")
            holder_layout = QtWidgets.QHBoxLayout(holder)
            holder_layout.setContentsMargins(0, 0, 0, 0)
            holder_layout.setAlignment(QtCore.Qt.AlignCenter)
            holder_layout.addWidget(check)
            table.setCellWidget(row, 2, holder)

        self.form.addWidget(table, 1000)

    def _render_module_settings(self, category):
        # a single module's settings, opened from its node in the sidebar tree
        name = self.active_module
        module = (category.get("settings") or {}).get(name) or {}
        label = settings_model.format_label(name)

        bar = QtWidgets.QWidget()
        bar_layout = QtWidgets.QHBoxLayout(bar)
        bar_layout.setContentsMargins(0, 0, 0, 0)
        bar_layout.setSpacing(10)

        titles = QtWidgets.QWidget()
        titles_layout = QtWidgets.QVBoxLayout(titles)
        titles_layout.setContentsMargins(0, 0, 0, 0)
        titles_layout.setSpacing(2)
        title = QtWidgets.QLabel(label)
        title_font = title.font()
        title_font.setBold(True)
        title.setFont(title_font)
        titles_layout.addWidget(title)
        description = module.get("description")
        if description:
            titles_layout.addWidget(self._muted(str(description)))
        bar_layout.addWidget(titles, 1)

        check = widgets.ToggleSwitch("Enabled")
        check.setToolTip("Enable or disable " + label)
        check.setChecked(name in (category.get("enabled") or []))
        check.toggled.connect(lambda on, target=name: self._toggle_module(target, on))
        bar_layout.addWidget(check)
        self.form.addWidget(bar)

        fields = module.get("value") or {}
        if fields:
            self._render_settings(self.form, fields)
        else:
            self.form.addWidget(self._muted("This module has no configurable settings."))

    def _toggle_module(self, name, on):
        category = self.categories.get(self.active_category) or {}
        enabled = category.get("enabled")
        disabled = category.get("disabled")
        if not isinstance(enabled, list) or not isinstance(disabled, list):
            return

        if on:
            if name in disabled:
                disabled.remove(name)
            if name not in enabled:
                enabled.append(name)
        else:
            if name in enabled:
                enabled.remove(name)
            if name not in disabled:
                disabled.append(name)

        enabled.sort()
        disabled.sort()
        self._refresh_tree_item(name, on)
        self._mark_changed()

    def _render_settings(self, layout, settings):
        for key, setting in settings.items():
            if not isinstance(setting, dict):
                continue
            if setting.get("unsafe") and not self.show_unsafe:
                continue
            if not self._depends_ok(setting.get("depends"), settings):
                continue

            if setting.get("type") == "object" and setting.get("settings"):
                box = QtWidgets.QGroupBox(str(setting.get("title") or settings_model.format_label(key)))
                inner = QtWidgets.QVBoxLayout(box)
                self._render_settings(inner, setting["settings"])
                layout.addWidget(box)
                continue

            widget = self._make_field(setting)
            if widget is not None:
                layout.addWidget(widget)

    def _depends_ok(self, depends, settings):
        # mirrors the webui's checkDependency: a key path must be truthy, or
        # every key in the mapping must match its expected value
        if not depends:
            return True

        def resolve(path):
            current = settings
            for part in str(path).split("."):
                if not isinstance(current, dict) or part not in current:
                    return None, False
                node = current[part]
                if isinstance(node, dict):
                    current = node.get("value") if "value" in node else node.get("settings")
                else:
                    current = node
            return current, True

        if isinstance(depends, dict):
            for path, expected in depends.items():
                actual, found = resolve(path)
                if not found or actual != expected:
                    return False
            return True

        actual, found = resolve(depends)
        if not found:
            return False
        return bool(actual)

    def _row(self, label_text, control):
        row = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(QtWidgets.QLabel(str(label_text)), 1)
        layout.addWidget(control)
        return row

    def _make_field(self, setting):
        field_type = str(setting.get("type") or "text")
        if field_type == "toggle_list":
            return None

        value = setting.get("value")
        options = setting.get("options") or {}

        block = QtWidgets.QWidget()
        outer = QtWidgets.QVBoxLayout(block)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(3)

        title = str(setting.get("title") or "")
        if setting.get("unsafe"):
            title = title + "  (unsafe)"

        hint = self._muted("")

        def refresh_hint(shown=None):
            parts = []
            if setting.get("description"):
                parts.append(str(setting["description"]))
            if shown is not None:
                option_text = options.get(shown)
                if isinstance(option_text, str) and option_text:
                    parts.append(option_text)
            hint.setText(" ".join(parts))

        def commit(new, shown=None):
            setting["value"] = new
            refresh_hint(shown)
            self._mark_changed()

        if field_type == "boolean":
            control = widgets.ToggleSwitch()
            control.setChecked(bool(value))
            outer.addWidget(self._row(title, control))
            control.toggled.connect(lambda on: commit(bool(on)))

        elif field_type == "number":
            number = value if isinstance(value, (int, float)) and not isinstance(value, bool) else 0
            step = setting.get("step")

            if isinstance(number, float) or isinstance(step, float):
                control = QtWidgets.QDoubleSpinBox()
                control.setDecimals(4)
                control.setRange(-1000000.0, 1000000.0)
                control.setSingleStep(float(step) if isinstance(step, (int, float)) else 0.1)
            else:
                control = QtWidgets.QSpinBox()
                control.setRange(-1000000000, 1000000000)
                if isinstance(step, int):
                    control.setSingleStep(max(1, step))

            minimum = setting.get("min")
            if isinstance(minimum, (int, float)):
                try:
                    control.setMinimum(minimum)
                except Exception:
                    pass
            maximum = setting.get("max")
            if isinstance(maximum, (int, float)):
                try:
                    control.setMaximum(maximum)
                except Exception:
                    pass

            try:
                control.setValue(number)
            except Exception:
                pass

            outer.addWidget(self._row(title, control))
            control.valueChanged.connect(lambda new: commit(new))

        elif field_type == "select":
            control = QtWidgets.QComboBox()
            keys = [str(option) for option in options.keys()]
            current = str(value) if value is not None else ""
            if current and current not in keys:
                keys.append(current)
            control.addItems(keys)
            if current in keys:
                control.setCurrentIndex(keys.index(current))
            outer.addWidget(self._row(title, control))
            control.currentTextChanged.connect(lambda text: commit(text, text))
            refresh_hint(current)

        elif field_type == "model_select":
            holder = QtWidgets.QWidget()
            line = QtWidgets.QHBoxLayout(holder)
            line.setContentsMargins(0, 0, 0, 0)
            line.setSpacing(6)

            control = QtWidgets.QComboBox()
            control.setEditable(True)
            control.setMinimumWidth(260)

            refresh = QtWidgets.QPushButton("reload")
            refresh.setObjectName("chip")
            refresh.setToolTip("Load the model list from the API")
            refresh.clicked.connect(lambda: self.channel.submit_async(self._load_models))

            line.addWidget(control, 1)
            line.addWidget(refresh)

            row = QtWidgets.QWidget()
            row_layout = QtWidgets.QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(8)
            row_layout.addWidget(QtWidgets.QLabel(title), 1)
            row_layout.addWidget(holder)
            outer.addWidget(row)

            self.model_fields.append((control, setting))
            control.currentTextChanged.connect(lambda text: commit(text.strip()))
            self._fill_one_model_field(control, setting)

        elif field_type in ("textarea", "long_text"):
            outer.addWidget(QtWidgets.QLabel(title))
            control = QtWidgets.QPlainTextEdit()
            control.setFixedHeight(96)
            control.setPlainText(str(value) if value is not None else "")
            outer.addWidget(control)
            control.textChanged.connect(lambda: commit(control.toPlainText()))

        elif field_type == "array":
            outer.addWidget(QtWidgets.QLabel(title))
            outer.addWidget(self._array_editor(setting, commit))

        else:
            # text, url, api_url, api_key and anything unknown
            outer.addWidget(QtWidgets.QLabel(title))
            control = QtWidgets.QLineEdit()
            if field_type == "api_key":
                control.setEchoMode(QtWidgets.QLineEdit.Password)
            control.setMinimumWidth(280)
            control.setText(str(value) if value is not None else "")
            outer.addWidget(control)
            control.textChanged.connect(lambda text: commit(text))

        if field_type != "select":
            refresh_hint()

        if hint.text():
            outer.addWidget(hint)

        return block

    def _array_editor(self, setting, commit):
        host = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(host)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        values = setting.get("value")
        if not isinstance(values, list):
            values = []

        for entry in values:
            layout.addWidget(self._array_row(host, commit, str(entry)))

        add_row = QtWidgets.QWidget()
        add_line = QtWidgets.QHBoxLayout(add_row)
        add_line.setContentsMargins(0, 0, 0, 0)
        add_line.setSpacing(6)

        add_box = QtWidgets.QLineEdit()
        add_box.setPlaceholderText("Add item...")

        add_button = QtWidgets.QPushButton("+")
        add_button.setObjectName("chip")
        add_button.setFixedWidth(34)

        def add(_=False):
            text = add_box.text().strip()
            if not text:
                return
            add_box.clear()
            layout.insertWidget(layout.count() - 1, self._array_row(host, commit, text))

            empty = host.findChild(QtWidgets.QLabel, "arrayEmpty")
            if empty is not None:
                empty.setParent(None)
                empty.deleteLater()

            commit(self._array_values(host))

        add_row.setProperty("arrayAdd", True)

        add_button.clicked.connect(add)
        add_box.returnPressed.connect(add)

        add_line.addWidget(add_box, 1)
        add_line.addWidget(add_button)
        layout.addWidget(add_row)

        if not values:
            empty = self._muted("No items. Add items below.")
            empty.setObjectName("arrayEmpty")
            layout.insertWidget(0, empty)

        return host

    def _array_row(self, host, commit, text):
        row = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        editor = QtWidgets.QLineEdit(text)
        editor.editingFinished.connect(lambda: commit(self._array_values(host)))

        remove = QtWidgets.QPushButton("remove")
        remove.setObjectName("chip")

        def drop(_=False):
            row.setParent(None)
            row.deleteLater()
            commit(self._array_values(host))

        remove.clicked.connect(drop)

        layout.addWidget(editor, 1)
        layout.addWidget(remove)
        return row

    def _array_values(self, host):
        values = []
        layout = host.layout()
        for index in range(layout.count()):
            item = layout.itemAt(index)
            widget = item.widget()
            if widget is None or widget.property("arrayAdd"):
                continue
            editors = widget.findChildren(QtWidgets.QLineEdit)
            if not editors:
                continue
            text = editors[0].text().strip()
            if text:
                values.append(text)
        return values

    # -------------------
    # models (for model_select fields)
    # -------------------

    def _fill_one_model_field(self, control, setting):
        current = setting.get("value")
        current = str(current) if current else ""

        names = list(self.models)
        if current and current not in names:
            names.insert(0, current)

        control.blockSignals(True)
        control.clear()
        control.addItems(names)
        if current:
            control.setCurrentText(current)
        control.blockSignals(False)

    def _fill_model_fields(self):
        for control, setting in list(self.model_fields):
            self._fill_one_model_field(control, setting)

    async def _load_models(self):
        self.status.setText("Loading models...")
        try:
            models = await self.channel.manager.API.list_models()
        except Exception as e:
            self.status.setText("Could not load models: " + core.detail_error(e))
            return

        if isinstance(models, core.api.APIError):
            self.status.setText("Could not load models: " + str(models))
            return

        self.models = [str(name) for name in (models or [])]
        self._fill_model_fields()
        self.status.setText("")

    # -------------------
    # dirty tracking, save, revert, close guard
    # -------------------

    def _snapshot(self, data):
        try:
            return json.dumps(data, sort_keys=True, default=str)
        except Exception:
            return repr(data)

    def _is_dirty(self):
        return self._snapshot(self.categories) != self._snapshot(self.original)

    def _mark_changed(self):
        self.status.setText("")
        self._update_footer()

    def _update_footer(self):
        dirty = self._is_dirty()
        self.dirty.setVisible(dirty)
        self.save_button.setEnabled(dirty and not self.saving)
        self.revert_button.setEnabled(dirty and not self.saving)

    def _revert(self):
        self.categories = copy.deepcopy(self.original)
        self._render()
        self.status.setText("Reverted to the last saved values.")
        self._update_footer()

    def _save(self):
        if self.saving or not self._is_dirty():
            return
        self.saving = True
        self.status.setText("Saving...")
        self._update_footer()
        self.channel.submit_async(self.channel._do_save_settings, copy.deepcopy(self.categories))

    def on_saved(self, result):
        self.saving = False
        result = result if isinstance(result, dict) else {}

        if not result.get("ok"):
            self.status.setText("Could not save: " + str(result.get("error") or "unknown error"))
            self._update_footer()
            return

        self.original = copy.deepcopy(self.categories)

        notes = ["Saved."]
        if result.get("requires_reconnect"):
            notes.append("API reconnected.")
        if result.get("requires_restart"):
            notes.append("Restart needed to apply the module/channel changes.")
        self.status.setText(" ".join(notes))
        self._update_footer()

    def _restart(self):
        answer = QtWidgets.QMessageBox.question(
            self,
            "Restart Server",
            "Restart OpenLumara now?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if answer == QtWidgets.QMessageBox.Yes:
            self.channel.submit_async(self.channel.manager.restart)

    def closeEvent(self, event):
        if self.saving:
            event.ignore()
            return

        if self._is_dirty():
            answer = QtWidgets.QMessageBox.question(
                self,
                "Unsaved Changes",
                "You have unsaved changes. Save before closing?",
                QtWidgets.QMessageBox.Save | QtWidgets.QMessageBox.Discard
                | QtWidgets.QMessageBox.Cancel,
                QtWidgets.QMessageBox.Save,
            )
            if answer == QtWidgets.QMessageBox.Cancel:
                event.ignore()
                return
            if answer == QtWidgets.QMessageBox.Save:
                self._save()
                event.ignore()
                return

        super().closeEvent(event)
