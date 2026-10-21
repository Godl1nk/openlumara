# -- AI GENERATED CODE (qwen3.8-flash-next) :: (2026-10-21) harness:openlumara
"""the webui's css theming, ported to Qt.

the webui paints itself entirely from css custom properties: base.json holds
the shared defaults, a theme family json (pro-monochrome, cute-sakura,
catppuccin-mocha...) overrides them per dark/light mode. the widgets then
only ever reference var(--bg-primary) and friends.

this module reads those very same files and turns the variables into:
- build_qss(): a Qt stylesheet mirroring the webui's look: layered dark
  backgrounds, 1px subtle borders, 6px rounded corners, gradient buttons,
  ghost icon buttons, hairline pill scrollbars, tinted selection
- message_colors(): the flat color set the rich-text chat view paints
  labels, user bubbles, tool cards and code with

css color syntax is translated on the way: linear-gradient(135deg,..) becomes
qlineargradient, rgba() stays rgba(), color-mix(accent, transparent) becomes
a plain rgba with the accent's own channels.
"""
import json
import os
import regex as re

# channels/gui -> channels -> the webui's theme files live next door
THEMES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "webui", "themes"
)

# used when a theme file can't be read at all: base.json's defaults inline
FALLBACK_VARS = {
    "--bg-primary": "#09090b",
    "--bg-secondary": "#0c0c0f",
    "--bg-tertiary": "#111115",
    "--bg-message-user": "linear-gradient(135deg, #1c1c20 0%, #18181b 100%)",
    "--bg-input": "#0f0f12",
    "--bg-code": "#0c0c0f",
    "--bg-sidebar": "#08080a",
    "--border-color": "#1e1e24",
    "--border-user": "#2a2a35",
    "--text-primary": "#fafafa",
    "--text-secondary": "#a1a1aa",
    "--text-muted": "#52525b",
    "--accent": "#d4d4d8",
    "--error": "#fca5a5",
    "--button-bg": "linear-gradient(135deg, #27272a 0%, #1e1e24 100%)",
    "--button-hover": "linear-gradient(135deg, #3f3f46 0%, #27272a 100%)",
    "--scrollbar": "#1e1e24",
    "--scrollbar-hover": "#2a2a35",
    "--radius-sm": "6px",
    "--radius-md": "10px",
}


# -------------------
# theme loading
# -------------------

def _read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle) or {}
    except Exception:
        return {}


def load_theme(family, mode="dark"):
    """resolve base.json + the family's dark/light var set into a flat
    {css var -> value} dict with every var(--x) reference already expanded"""
    merged = dict(FALLBACK_VARS)
    merged.update(_read_json(os.path.join(THEMES_DIR, "base.json")))
    family_data = _read_json(os.path.join(THEMES_DIR, str(family) + ".json"))

    values = family_data.get(mode)
    if values is None:
        values = family_data.get("dark")
    if values is None:
        values = family_data.get("light")
    if isinstance(values, dict):
        merged.update(values)

    return _resolve_vars(merged)


_VAR_RE = re.compile(
    r"var\(\s*(--[a-zA-Z0-9-]+)\s*(?:,\s*((?:[^()]|\([^()]*\))*)\)\s*)?\)"
)


def _resolve_vars(variables):
    """substitute var(--x, fallback) until stable (circular refs give up)"""
    result = {}
    for key, value in variables.items():
        result[key] = str(value)

    for _ in range(8):
        changed = False
        for key in result:
            def _replace(match):
                referenced = match.group(1)
                fallback = match.group(2)
                if referenced in result:
                    return result[referenced]
                if fallback is not None:
                    return fallback.strip()
                return match.group(0)

            new_value = _VAR_RE.sub(_replace, result[key])
            if new_value != result[key]:
                result[key] = new_value
                changed = True
        if not changed:
            break

    return result


# -------------------
# css value -> qt value
# -------------------

_HEX_RE = re.compile(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
_RGB_RE = re.compile(r"^rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([\d.]+)\s*)?\)$")
_STOP_RE = re.compile(r"#[0-9a-fA-F]{3,8}|rgba?\([^)]*\)")


def css_to_qt(value, fallback="transparent"):
    """normalize a css color (hex3/hex6/rgb/rgba) into a string qt accepts"""
    value = str(value or "").strip()
    if not value or value == "none" or value == "transparent":
        return fallback

    match = _HEX_RE.match(value)
    if match:
        digits = match.group(1)
        if len(digits) == 3:
            digits = "".join(ch * 2 for ch in digits)
        return "#" + digits.lower()

    match = _RGB_RE.match(value)
    if match:
        alpha = match.group(4)
        if alpha is None:
            return "rgb({}, {}, {})".format(match.group(1), match.group(2), match.group(3))
        return "rgba({}, {}, {}, {})".format(
            match.group(1), match.group(2), match.group(3), alpha
        )

    return value


def gradient_stops(value):
    """extract the color stops of a linear-gradient(...) css value"""
    return _STOP_RE.findall(str(value or ""))


def background_qss(value, fallback="transparent"):
    """translate a css background (flat color OR 135deg gradient) into qss"""
    value = str(value or "").strip()
    if not value or value == "none":
        return fallback

    if value.startswith("linear-gradient"):
        stops = gradient_stops(value)
        if not stops:
            return fallback
        if len(stops) == 1:
            return css_to_qt(stops[0], fallback)
        first = css_to_qt(stops[0], fallback)
        last = css_to_qt(stops[-1], first)
        # css 135deg runs top-left -> bottom-right; that's exactly qt's 0,0->1,1
        return "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {}, stop:1 {})".format(
            first, last
        )

    return css_to_qt(value, fallback)


def parse_css_color(value, fallback=(250, 250, 250, 255)):
    """css color -> (r, g, b, a) with no qt involved, so theming works even
    before/without a QApplication"""
    value = css_to_qt(value, "")
    if not value:
        return fallback

    match = _RGB_RE.match(value)
    if match:
        alpha = float(match.group(4)) if match.group(4) else 1.0
        return (
            int(match.group(1)), int(match.group(2)), int(match.group(3)),
            max(0, min(255, int(round(alpha * 255)))),
        )

    match = _HEX_RE.match(value)
    if match:
        digits = match.group(1)
        if len(digits) == 3:
            digits = "".join(ch * 2 for ch in digits)
        return (
            int(digits[0:2], 16), int(digits[2:4], 16), int(digits[4:6], 16), 255
        )

    return fallback


def rgba_with_alpha(value, alpha):
    """color-mix(in srgb, X <alpha*100>%, transparent) as plain rgba()"""
    r, g, b, _old = parse_css_color(value)
    return "rgba({}, {}, {}, {})".format(r, g, b, alpha)


def _channel_linear(value):
    value = value / 255.0
    if value <= 0.03928:
        return value / 12.92
    return pow((value + 0.055) / 1.055, 2.4)


def _contrast_ratio(a, b):
    """wcag contrast ratio (1..21) between two css colors"""
    luminances = []
    for color in (a, b):
        r, g, b_, _alpha = parse_css_color(color, (128, 128, 128, 255))
        luminances.append(
            0.2126 * _channel_linear(r)
            + 0.7152 * _channel_linear(g)
            + 0.0722 * _channel_linear(b_)
        )
    high = max(luminances)
    low = min(luminances)
    return (high + 0.05) / (low + 0.05)


def mix_css_colors(a, b, factor):
    """blend two css colors: factor 0 keeps a, 1 keeps b"""
    ar, ag, ab, _aa = parse_css_color(a)
    br, bg, bb, _ba = parse_css_color(b)
    return "rgba({}, {}, {}, 255)".format(
        int(ar + (br - ar) * factor),
        int(ag + (bg - ag) * factor),
        int(ab + (bb - ab) * factor),
    )


def disabled_text_color(variables):
    """a readable text color for disabled rows (settings tree, module list):
    the theme's muted/secondary text, but only if it actually contrasts the
    tree's own background (bg_secondary); otherwise blend the main text color
    toward that background until it does. never palette-based, so a stale
    platform palette can't hand light text to a light theme again"""
    v = variables or {}

    def g(name, fallback):
        value = str(v.get(name, "") or "").strip()
        return css_to_qt(value, fallback) if value else fallback

    bg = g("--bg-secondary", "#0c0c0f")
    text = g("--text-primary", "#fafafa")

    for name in ("--text-muted", "--text-secondary"):
        candidate = g(name, "")
        # 2.0 was too generous: a pastel muted like sakura-dark's #f48fb1
        # squeaked past it at 2.16 and vanished on a light background
        if candidate and _contrast_ratio(candidate, bg) >= 3.0:
            return candidate

    # nothing dim in the theme reads on this bg: fade the main text toward
    # it ourselves, shallow blend first (still clearly "text", just muted)
    color = mix_css_colors(text, bg, 0.45)
    if _contrast_ratio(color, bg) < 3.0:
        color = mix_css_colors(text, bg, 0.25)
    return color


def _radius(variables, name, default):
    match = re.search(r"(\d+)", str(variables.get(name, "") or ""))
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            pass
    return default


# -------------------
# the stylesheet
# -------------------

def build_qss(variables):
    """a qt stylesheet painted from the webui theme variables: same layers,
    borders, radii and gradients the browser would show"""
    v = variables or {}

    def g(name, fallback=""):
        value = str(v.get(name, "") or "").strip()
        return value if value else fallback

    bg_primary = css_to_qt(g("--bg-primary", "#09090b"))
    bg_secondary = css_to_qt(g("--bg-secondary", "#0c0c0f"))
    bg_tertiary = css_to_qt(g("--bg-tertiary", "#111115"))
    bg_input = css_to_qt(g("--bg-input", "#0f0f12"))
    bg_sidebar = css_to_qt(g("--bg-sidebar", g("--bg-primary", "#09090b")))
    border = css_to_qt(g("--border-color", "#1e1e24"))
    border_user = css_to_qt(g("--border-user", "#2a2a35"))
    text = css_to_qt(g("--text-primary", "#fafafa"))
    # themes with loud button gradients (cute-sakura's hot pink) ship a dark
    # --button-text with them; ignoring it paints white-on-pink mush. if even
    # that turns out low-contrast against the gradient (some light themes
    # inherit base.json's white button-text), fall back to the text color
    button_text = css_to_qt(g("--button-text", ""), "") or text
    stops = gradient_stops(g("--button-bg", ""))
    button_face = stops[0] if stops else g("--button-bg", bg_tertiary)
    # only second-guess the theme when its own choice is unreadable AND the
    # plain text color would genuinely read better on the button face
    if _contrast_ratio(button_text, button_face) < 3.0 and _contrast_ratio(
        text, button_face
    ) > _contrast_ratio(button_text, button_face):
        button_text = text
    # webui disabled buttons are the same look at 50% opacity; a stylesheet
    # can't fade, so blend the button's own text into its face instead.
    # (painting --text-muted here was the bug: sakura's pale pink disabled
    # label sitting on the pale pink gradient = invisible)
    button_disabled_text = mix_css_colors(button_text, button_face, 0.45)
    text_secondary = css_to_qt(g("--text-secondary", "#a1a1aa"))
    text_muted = css_to_qt(g("--text-muted", "#52525b"))
    accent = css_to_qt(g("--accent", "#d4d4d8"))
    error = css_to_qt(g("--error", "#fca5a5"))
    # --error-bg is a gradient in the themes themselves: translate properly
    error_bg = background_qss(g("--error-bg"), bg_tertiary)
    scrollbar = css_to_qt(g("--scrollbar", border))
    scrollbar_hover = css_to_qt(g("--scrollbar-hover", border_user))

    button_bg = background_qss(g("--button-bg"), bg_tertiary)
    button_hover = background_qss(g("--button-hover"), bg_tertiary)

    selection = rgba_with_alpha(accent, 0.3)
    radius = _radius(v, "--radius-sm", 6)
    radius_md = _radius(v, "--radius-md", 10)
    pill = 9999

    return (
        """
        QMainWindow, QDialog {{ background-color: {bg_primary}; }}
        QWidget {{ background-color: {bg_primary}; color: {text}; }}

        QToolTip {{
            background-color: {bg_secondary}; color: {text};
            border: 1px solid {border}; border-radius: {radius}px;
        }}
        QMenu {{
            background-color: {bg_primary}; border: 1px solid {border};
            border-radius: 0px; padding: 4px;
        }}
        QMenu::item {{ padding: 6px 10px; border-radius: {radius}px; color: {text}; }}
        QMenu::item:selected {{ background-color: {bg_tertiary}; color: {text}; }}
        QMenu::separator {{ height: 1px; background: {border}; margin: 4px 0; }}

        #sidebar {{ background-color: {bg_sidebar}; }}

        QTextEdit#chatView {{
            background-color: {bg_primary}; color: {text};
            border: none; border-radius: 0px;
            padding: 12px 20px;
            selection-background-color: {selection}; selection-color: {text};
        }}

        QLineEdit {{
            background-color: {bg_input}; color: {text};
            border: 1px solid {border}; border-radius: {radius}px; padding: 4px 14px;
            selection-background-color: {selection}; selection-color: {text};
        }}
        QLineEdit:focus {{ border-color: {accent}; }}

        QPushButton {{
            background: {button_bg}; color: {button_text};
            border: 1px solid {border}; border-radius: {radius}px;
            padding: 0 16px; font-weight: 600;
        }}
        QPushButton:hover {{ background: {button_hover}; border-color: {accent}; }}
        QPushButton:pressed {{ background: {bg_tertiary}; }}
        QPushButton:disabled {{
            color: {button_disabled_text}; border-color: {border};
        }}

        QPushButton#chip {{
            background: transparent; border: 1px solid transparent;
            color: {text_secondary}; padding: 3px 12px; font-weight: 400;
        }}
        QPushButton#chip:hover {{
            background-color: {bg_tertiary}; color: {accent};
            border: 1px solid transparent;
        }}

        /* the header's icon buttons are real buttons, not ghost chips:
           raised on the tertiary layer with a hairline border, so they
           read as clickable even before a hover */
        QPushButton#iconbtn {{
            background-color: {bg_tertiary}; color: {text_secondary};
            border: 1px solid {border}; border-radius: {radius}px;
            padding: 0px; font-weight: 400;
        }}
        QPushButton#iconbtn:hover {{
            background-color: {bg_tertiary}; color: {accent};
            border-color: {accent};
        }}
        QPushButton#iconbtn:pressed {{
            background-color: {selection};
        }}

        /* the webui's send is a ghost because it sits inside the bordered
           input wrapper; here it's a standalone button, so it gets the same
           button-bg treatment as everything else */
        QPushButton#send {{
            background: {button_bg}; border: 1px solid {border};
            color: {button_text}; padding: 0 24px; font-weight: 600;
        }}
        QPushButton#send:hover {{ background: {button_hover}; border-color: {accent}; }}

        QPushButton#stop {{
            background: {error_bg}; border: 1px solid transparent;
            color: {error}; padding: 0 24px; font-weight: 600;
        }}
        QPushButton#stop:hover {{ color: {error}; }}

        QComboBox {{
            background-color: {bg_input}; color: {text};
            border: 1px solid {border}; border-radius: 0px;
            padding: 4px 12px;
        }}
        QComboBox:hover {{ border-color: {accent}; }}
        /* no ::drop-down / ::down-arrow rules at all: overriding them hands
           the arrow's paint job to the stylesheet engine (which then draws
           "creative" things). untouched, the widget style draws its own
           native arrow inside our border */
        /* official qt way (stylesheet-examples): the combo's pop-up is a
           QAbstractItemView styled via this descendant selector. anything
           further - the container frame/shadow - is unstyleable by design,
           so we leave it native and do zero showPopup surgery */
        QComboBox QAbstractItemView {{
            background-color: {bg_primary}; color: {text};
            border: 1px solid {border};
            border-radius: 0px;
            selection-background-color: {bg_tertiary}; selection-color: {text};
            outline: none;
        }}
        QComboBox QAbstractItemView::item {{
            padding: 4px 8px;
            min-height: 20px;
        }}

        QListWidget {{
            background-color: transparent; color: {text};
            border: none; border-radius: 0px; padding: 7px; outline: none;
        }}
        QListWidget::item {{
            border: 1px solid transparent; border-radius: {radius}px;
            padding: 5px 14px;
        }}
        QListWidget::item:hover {{ background-color: {bg_secondary}; }}
        QListWidget::item:selected {{
            background-color: {bg_secondary}; border: 1px solid {border};
            color: {text};
        }}

        QProgressBar {{
            background-color: {bg_secondary}; color: {text};
            border: 1px solid {border}; border-radius: {pill}px;
            text-align: center; font-size: 8pt;
        }}
        QProgressBar::chunk {{
            border-radius: {pill}px; background-color: {accent};
        }}

        QScrollBar:vertical {{ background: transparent; width: 8px; margin: 0; }}
        QScrollBar:horizontal {{ background: transparent; height: 8px; margin: 0; }}
        QScrollBar::handle {{
            background: {scrollbar}; border-radius: {pill}px;
            min-height: 24px; min-width: 24px;
        }}
        QScrollBar::handle:hover, QScrollBar::handle:pressed {{ background: {scrollbar_hover}; }}
        QScrollBar::up-arrow, QScrollBar::down-arrow,
        QScrollBar::left-arrow, QScrollBar::right-arrow,
        QScrollBar::add-line, QScrollBar::sub-line {{
            width: 0px; height: 0px; border: none; background: none;
        }}
        QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

        QCheckBox {{ color: {text}; background: transparent; spacing: 8px; }}

        QGroupBox {{
            color: {accent}; background-color: {bg_secondary};
            border: 1px solid {border}; border-radius: {radius}px;
            margin-top: 10px; padding-top: 8px;
        }}
        QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 4px; }}

        QSpinBox, QDoubleSpinBox, QPlainTextEdit {{
            background-color: {bg_input}; color: {text};
            border: 1px solid {border}; border-radius: {radius}px; padding: 3px 8px;
            selection-background-color: {selection}; selection-color: {text};
        }}

        QTreeWidget, QTreeView, QTableWidget, QTableView {{
            background-color: {bg_secondary}; color: {text};
            border: 1px solid {border}; border-radius: {radius}px;
            outline: none; alternate-background-color: {bg_tertiary};
        }}
        /* deliberately NO ::item / ::item:selected rules here: styling the
           item subcontrol hands item (and tree branch) painting to the
           stylesheet engine, which then double-draws selection boxes around
           the native branch chevron. untouched, the widget style paints the
           whole row selection itself - clean, corners and all */
        QHeaderView::section {{
            background: transparent; color: {text_secondary};
            border: none; padding: 6px 8px;
        }}

        QSplitter::handle {{ background: {border}; width: 1px; }}
        QSplitter::handle:hover {{ background: {accent}; }}
        """.format(
            bg_primary=bg_primary, bg_secondary=bg_secondary, bg_tertiary=bg_tertiary,
            bg_input=bg_input, bg_sidebar=bg_sidebar, border=border,
            border_user=border_user, text=text, button_text=button_text,
            button_disabled_text=button_disabled_text,
            text_secondary=text_secondary,
            text_muted=text_muted, accent=accent, error=error, error_bg=error_bg,
            scrollbar=scrollbar, scrollbar_hover=scrollbar_hover,
            button_bg=button_bg, button_hover=button_hover, selection=selection,
            radius=radius, radius_md=radius_md, pill=pill,
        )
    )


# -------------------
# colors for the rich-text chat view
# -------------------

def _first_stop(value, fallback):
    stops = gradient_stops(value)
    if stops:
        return css_to_qt(stops[0], fallback)
    return css_to_qt(value, fallback)


def message_colors(variables):
    """the flat hex/rgba set the chat view's QTextCharFormats and bubbles use,
    keyed by the channel's *_color setting names"""
    v = variables or {}

    def g(name, fallback=""):
        value = str(v.get(name, "") or "").strip()
        return value if value else fallback

    bg_primary = css_to_qt(g("--bg-primary", "#09090b"))
    accent = css_to_qt(g("--accent", "#d4d4d8"))
    text = css_to_qt(g("--text-primary", "#fafafa"))

    # the webui's user bubble is a tight rounded card, so even a saturated
    # theme gradient (sakura's #810a4d) reads fine there. here it's a block
    # stripe across the chat, so: average the gradient's stops, then blend
    # most of the way toward the background: still clearly "the user tint",
    # never a neon banner
    bubble_raw = _first_stop(
        g("--bg-message-user", "#1c1c20"), css_to_qt(g("--bg-tertiary", "#111115"))
    )
    stops = gradient_stops(g("--bg-message-user", ""))
    if len(stops) >= 2:
        bubble_mid = mix_css_colors(stops[0], stops[-1], 0.5)
    else:
        bubble_mid = bubble_raw
    user_bubble = mix_css_colors(bubble_mid, bg_primary, 0.55)

    return {
        "background_color": bg_primary,
        "text_color": text,
        "secondary_text_color": css_to_qt(g("--text-secondary", "#a1a1aa"), text),
        "accent_color": accent,
        "user_color": css_to_qt(g("--accent-secondary", ""), accent) or accent,
        "assistant_color": accent,
        "system_color": css_to_qt(g("--text-muted", "#52525b"), text),
        "error_color": css_to_qt(g("--error", "#fca5a5")),
        "important_color": css_to_qt(g("--important", "#fde68a"), text),
        "user_bubble_bg": user_bubble,
        "user_bubble_border": css_to_qt(g("--border-user", "#2a2a35")),
        "code_bg": css_to_qt(g("--bg-code", "#0c0c0f"), bg_primary),
        "code_border": css_to_qt(g("--border-color", "#1e1e24")),
        "tool_color": css_to_qt(g("--tool-completed-color", ""), accent) or accent,
    }
