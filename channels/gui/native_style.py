# -- AI GENERATED CODE (qwen3.8-flash-next) :: (2026-10-21) harness:openlumara
"""cross-platform native theming for the qt6 channel.

how an app looks like the rest of its OS is fully solved by the platform:
- windows & macos: qt ships the native styles; nothing to do at all
- linux/kde: plasma installs a small plugin (plasma-integration) into the
  system Qt6 plugins and exports QT_QPA_PLATFORMTHEME=kde in the session.
  every native kde app loads it at startup: it reads the widget style, color
  scheme and icon theme chosen in system settings and applies them.

the catch: a pip-installed PySide6 carries its OWN bundled Qt6 build in
site-packages, whose plugin dir has no KDE platform theme and no Breeze
style. the env var then hits a dead end and qt quietly falls back to Fusion
- the generic look that reads as "a decade old". this module handles both:
prepare_environment() turns the platform theme on (the whole fix when
PySide6 is the distro package), and apply() rescues the bundled case by
borrowing the style from the system Qt6 plugins, reading the very same
kdeglobals/color-scheme files the plasma plugin would read, and setting
palette + icon theme by hand.
"""
import configparser
import os
import sys

import PySide6.QtGui as QtGui
import PySide6.QtWidgets as QtWidgets


# where distro Qt6 keeps its plugins on the major layouts
SYSTEM_QT_PLUGIN_DIRS = (
    "/usr/lib/qt6/plugins",
    "/usr/lib64/qt6/plugins",
    "/usr/lib/x86_64-linux-gnu/qt6/plugins",
    "/usr/lib/aarch64-linux-gnu/qt6/plugins",
)


def prepare_environment():
    """call before QApplication exists: ask for the desktop's own Qt platform
    theme. no-op on windows/macos, on explicit user config, and on non-kde
    desktops (gnome etc. already set their own theme here)"""
    if not sys.platform.startswith("linux"):
        return
    if os.environ.get("QT_QPA_PLATFORMTHEME", "").strip():
        # the user/plasma already decided: kde, qt5ct, qt6ct, gtk3...
        return
    if "KDE" in os.environ.get("XDG_CURRENT_DESKTOP", "").upper():
        os.environ["QT_QPA_PLATFORMTHEME"] = "kde"


def kde_detected():
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").upper()
    if "KDE" in desktop:
        return True
    return os.environ.get("QT_QPA_PLATFORMTHEME", "").lower() in ("kde", "kde-plasma")


def apply(app):
    """returns True when the OS's own styling is actually in effect; False
    means the caller should fall back to its custom theme"""
    if not sys.platform.startswith("linux"):
        # windows/macos: qt uses the native styles out of the box
        return True

    if _platform_theme_active(app):
        return True

    if not kde_detected():
        return False

    # bundled-Qt rescue: mirror what the plasma plugin would have applied
    ok = _set_style(app, _kde_config_value("General", "widgetStyle", "Breeze"))
    _set_icon_theme(app)
    palette = _kde_palette()
    if palette is not None:
        app.setPalette(palette)
    return ok


# -------------------
# platform theme detection
# -------------------

def _platform_theme_active(app):
    # a live platform theme replaces the fallback style (breeze, adwaita-qt,
    # kvantum...). still seeing Fusion/Windows/macintosh means none took hold
    style = app.style()
    name = str(style.objectName()).lower() or str(style.metaObject().className()).lower()
    fallbacks = (
        "fusion",
        "qfusionstyle",
        "windows",
        "qwindowsstyle",
        "macintosh",
        "qmacstyle",
        "bb10",
    )
    return not any(marker in name for marker in fallbacks)


# -------------------
# kdeglobals / color scheme parsing
# -------------------

def _kde_parser():
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    try:
        parser.read([os.path.expanduser("~/.config/kdeglobals")], encoding="utf-8")
    except Exception:
        pass
    return parser


def _kde_config_value(section, key, fallback=""):
    parser = _kde_parser()
    try:
        if parser.has_option(section, key):
            value = str(parser.get(section, key)).strip()
            if value:
                return value
    except Exception:
        pass
    return fallback


def _set_icon_theme(app):
    theme = _kde_config_value("Icons", "theme", "breeze")
    try:
        QtGui.QIcon.setThemeName(str(theme))
    except Exception:
        pass


# -------------------
# style loading, with system-plugin rescue
# -------------------

def _style_factory():
    # qt6 moved this class to gui; pyside6 builds have shipped it in both
    factory = getattr(QtWidgets, "QStyleFactory", None) or getattr(QtGui, "QStyleFactory", None)
    if factory is None:
        raise RuntimeError("QStyleFactory unavailable in this Qt build")
    return factory


def _style_keys():
    return {str(key): str(key) for key in _style_factory().keys()}


def _pick_key(wanted, keys):
    lowered = str(wanted).lower()
    for key in keys:
        if key.lower() == lowered:
            return keys[key]
    return None


def _set_style(app, name):
    keys = _style_keys()
    chosen = _pick_key(name, keys) or _pick_key("Breeze", keys)

    if chosen is None:
        # the bundled Qt cannot see the distro's style plugin: offer the
        # system plugin dirs as an extra search location and look again
        try:
            known = list(app.libraryPaths())
        except Exception:
            known = []
        for path in SYSTEM_QT_PLUGIN_DIRS:
            if not os.path.isdir(os.path.join(path, "styles")) or path in known:
                continue
            try:
                app.addLibraryPath(path, True)
            except Exception:
                pass
        keys = _style_keys()
        chosen = _pick_key(name, keys) or _pick_key("Breeze", keys)

    if chosen is None:
        return False
    try:
        return bool(app.setStyle(chosen))
    except Exception:
        return False


# -------------------
# palette, built from the chosen KDE color scheme
# -------------------

def _colors_parser():
    # the scheme file named by kdeglobals holds the rgb values; some setups
    # carry the colors inline in kdeglobals instead
    scheme = _kde_config_value("General", "ColorScheme", "")
    parser = configparser.ConfigParser(interpolation=None, strict=False)

    if scheme:
        candidates = [
            os.path.join(
                os.path.expanduser("~"), ".local", "share", "color-schemes", scheme + ".colors"
            ),
            os.path.join("/usr/share/color-schemes", scheme + ".colors"),
        ]
        for path in candidates:
            if os.path.isfile(path):
                try:
                    parser.read([path], encoding="utf-8")
                    return parser
                except Exception:
                    pass

    # no scheme file found (or none named): take what kdeglobals itself has
    parser = _kde_parser()
    if any(section.startswith("Colors:") for section in parser.sections()):
        return parser
    return None


def _rgb(text):
    parts = str(text).split(",")
    if len(parts) != 3:
        return None
    try:
        return tuple(max(0, min(255, int(part.strip()))) for part in parts)
    except ValueError:
        return None


def _color(parser, section, key):
    if parser is None or not parser.has_section(section):
        return None
    rgb = _rgb(parser.get(section, key, fallback=""))
    if rgb is None:
        return None
    return QtGui.QColor(*rgb)


def _mix(a, b, factor):
    if a is None or b is None:
        return None
    return QtGui.QColor(
        int(a.red() + (b.red() - a.red()) * factor),
        int(a.green() + (b.green() - a.green()) * factor),
        int(a.blue() + (b.blue() - a.blue()) * factor),
    )


def _kde_palette():
    colors = _colors_parser()
    window_bg = _color(colors, "Colors:Window", "Background")
    if window_bg is None:
        return None

    window_fg = _color(colors, "Colors:Window", "Foreground")
    view_bg = _color(colors, "Colors:View", "BackgroundNormal") or window_bg
    view_fg = _color(colors, "Colors:View", "ForegroundNormal") or window_fg
    dim_fg = _color(colors, "Colors:Window", "ForegroundDimmed") or _mix(window_fg, window_bg, 0.5)

    sel_bg = _color(colors, "Colors:Selection", "BackgroundNormal")
    sel_fg = _color(colors, "Colors:Selection", "ForegroundNormal")
    btn_bg = _color(colors, "Colors:Button", "BackgroundNormal") or window_bg
    btn_fg = _color(colors, "Colors:Button", "ForegroundNormal") or window_fg
    tip_bg = _color(colors, "Colors:Tooltip", "BackgroundNormal") or window_bg
    tip_fg = _color(colors, "Colors:Tooltip", "ForegroundNormal") or window_fg
    link = _color(colors, "Colors:Window", "DecorationFocus") or sel_bg

    palette = QtGui.QPalette()

    def put(group, role, color):
        if color is not None:
            palette.setColor(group, role, color)

    normal = (
        (QtGui.QPalette.Window, window_bg),
        (QtGui.QPalette.WindowText, window_fg),
        (QtGui.QPalette.Base, view_bg),
        (QtGui.QPalette.AlternateBase, _mix(view_bg, view_fg, 0.04)),
        (QtGui.QPalette.Text, view_fg),
        (QtGui.QPalette.PlaceholderText, dim_fg),
        (QtGui.QPalette.Button, btn_bg),
        (QtGui.QPalette.ButtonText, btn_fg),
        (QtGui.QPalette.ToolTipBase, tip_bg),
        (QtGui.QPalette.ToolTipText, tip_fg),
        (QtGui.QPalette.Highlight, sel_bg),
        (QtGui.QPalette.HighlightedText, sel_fg),
        (QtGui.QPalette.Link, link),
        (QtGui.QPalette.LinkVisited, link),
    )
    # disabled text is the dimmed foreground, backgrounds stay put
    disabled = (
        (QtGui.QPalette.Window, window_bg),
        (QtGui.QPalette.WindowText, dim_fg),
        (QtGui.QPalette.Base, view_bg),
        (QtGui.QPalette.Text, dim_fg),
        (QtGui.QPalette.Button, btn_bg),
        (QtGui.QPalette.ButtonText, dim_fg),
        (QtGui.QPalette.ToolTipBase, tip_bg),
        (QtGui.QPalette.ToolTipText, dim_fg),
    )

    for role, color in normal:
        put(QtGui.QPalette.Active, role, color)
        put(QtGui.QPalette.Inactive, role, color)
    for role, color in disabled:
        put(QtGui.QPalette.Disabled, role, color)

    return palette
