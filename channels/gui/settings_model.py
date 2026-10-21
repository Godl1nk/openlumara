# -- AI GENERATED CODE (qwen3.8-flash-next) :: (2026-10-21) harness:openlumara
"""settings structure, ported from the webui backend: the raw config is merged
with the module/channel schemas into a render-ready category tree, and
flattened straight back into raw config on save"""
import core


SPECIAL_FIELD_TYPES = {
    "model.name": "model_select",
    "api.url": "api_url",
    "api.key": "api_key",
}

MODULE_CATEGORY_KEYS = ("modules", "user_modules", "channels", "user_channels")


def format_label(key):
    spaced = str(key).replace("_", " ")
    return " ".join([word[:1].upper() + word[1:] for word in spaced.split(" ")])


def is_toggle_list(data):
    return (
        isinstance(data, dict)
        and isinstance(data.get("enabled"), list)
        and isinstance(data.get("disabled"), list)
    )


def detect_field_type(value, key=""):
    if key in SPECIAL_FIELD_TYPES:
        return SPECIAL_FIELD_TYPES[key]
    if value is None:
        return "text"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)) and not key.lower().endswith("id"):
        return "number"
    if isinstance(value, list):
        return "array"
    if isinstance(value, str):
        if value.startswith("http://") or value.startswith("https://"):
            return "url"
        if "\n" in value:
            return "textarea"
    return "text"


def build_field_settings(obj, schema, prefix=""):
    # one setting = schema metadata + its current value
    if not obj or not isinstance(obj, dict):
        return {}

    if not isinstance(schema, dict):
        schema = {}

    settings = {}

    for key, value in obj.items():
        full_key = prefix + "." + key if prefix else key
        field_schema = schema.get(key)
        if not isinstance(field_schema, dict):
            field_schema = {}

        has_schema = False
        for marker in ("type", "default", "description"):
            if marker in field_schema:
                has_schema = True
                break

        if has_schema:
            if "default" in field_schema:
                schema_value = field_schema["default"]
            else:
                schema_value = value

            raw_type = field_schema.get("type")
            if raw_type == "long_text":
                field_type = "textarea"
            elif raw_type is not None:
                field_type = raw_type
            else:
                field_type = detect_field_type(schema_value, full_key)

            settings[key] = {
                "title": format_label(key),
                "type": field_type,
                "description": field_schema.get("description") or None,
                "unsafe": field_schema.get("unsafe", False),
                "value": value,
                "options": field_schema.get("options") or None,
                "min": field_schema.get("min"),
                "max": field_schema.get("max"),
                "step": field_schema.get("step"),
                "depends": field_schema.get("depends") or None,
            }
        elif isinstance(value, dict) and not is_toggle_list(value):
            settings[key] = {
                "type": "object",
                "title": format_label(key),
                "description": field_schema.get("description") or None,
                "depends": field_schema.get("depends") or None,
                "settings": build_field_settings(value, field_schema, full_key),
            }
        elif is_toggle_list(value):
            settings[key] = {
                "type": "toggle_list",
                "title": format_label(key),
                "value": value,
            }
        else:
            settings[key] = {
                "title": format_label(key),
                "type": detect_field_type(value, full_key),
                "description": field_schema.get("description") or None,
                "unsafe": field_schema.get("unsafe", False),
                "value": value,
                "options": None,
                "depends": field_schema.get("depends") or None,
            }

    return settings


def get_schemas():
    # (module schemas, core config section schemas) straight from core.config
    module_info = {}

    try:
        structure = core.config.get_module_structure()
    except Exception:
        structure = {}

    for name, data in (structure or {}).items():
        data = data or {}
        meta = data.get("metadata") or {}
        module_info[name] = {
            "description": meta.get("doc", "") or "",
            "unsafe": meta.get("unsafe", False),
            "settings_schema": data.get("settings") or {},
        }

    core_sections = {}

    try:
        core_structure = core.config.get_core_settings_structure()
    except Exception:
        core_structure = {}

    for name, data in (core_structure or {}).items():
        data = data or {}
        core_sections[name] = {
            "description": (data.get("metadata") or {}).get("doc", "") or "",
            "settings_schema": data.get("settings") or {},
        }

    return module_info, core_sections


def load_settings_tree():
    module_info, core_sections = get_schemas()

    try:
        raw = dict(core.config.config)
    except Exception:
        raw = {}

    categories = {}
    order = 0
    section_order = {"channels": 10, "modules": 11, "user_channels": 13, "user_modules": 14}
    section_titles = {
        "user_channels": "Installed Channels",
        "user_modules": "Installed Modules",
    }

    for top_key, top_value in raw.items():
        if top_key.lower() in ("theme", "theme_mode"):
            continue

        display = section_titles.get(top_key, format_label(top_key))
        category = {
            "title": display,
            "description": "Configure " + display.lower(),
            "order": section_order.get(top_key, order),
            "settings": {},
        }
        order += 1

        if not isinstance(top_value, dict) or not top_value:
            # nothing editable in here (a stray scalar or an empty section):
            # shown for information only, and never written back
            category["isReadOnly"] = True
            categories[top_key] = category
            continue

        if top_key in MODULE_CATEGORY_KEYS:
            value = top_value
            category["isModuleCategory"] = True
            category["enabled"] = list(value.get("enabled") or [])
            category["disabled"] = list(value.get("disabled") or [])

            settings = {}
            for name, item_settings in (value.get("settings") or {}).items():
                if not item_settings:
                    continue
                info = module_info.get(name) or {}
                settings[name] = {
                    "title": format_label(name),
                    "description": info.get("description") or "",
                    "unsafe": bool(info.get("unsafe")),
                    "value": build_field_settings(
                        item_settings, info.get("settings_schema") or {}, name
                    ),
                }
            category["settings"] = settings
        else:
            section_schema = (core_sections.get(top_key) or {}).get("settings_schema") or {}
            if isinstance(top_value, dict) and top_value:
                category["settings"] = build_field_settings(top_value, section_schema, top_key)

        categories[top_key] = category

    return categories


def flatten_field_settings(settings):
    # a (possibly edited) field tree back into plain key -> value config
    result = {}
    for key, setting in settings.items():
        if not isinstance(setting, dict):
            continue

        if setting.get("type") == "object":
            nested = setting.get("settings") or {}
            if nested:
                result[key] = flatten_field_settings(nested)
            else:
                # an empty or schema-less dict: keep whatever it was
                value = setting.get("value")
                result[key] = value if isinstance(value, dict) else {}
            continue

        # anything we render no widget for (toggle lists) keeps its raw value,
        # so a skipped field can never silently drop config keys
        result[key] = setting.get("value")
    return result


def flatten_categories(categories):
    result = {}

    for key, category in categories.items():
        if not isinstance(category, dict):
            continue

        if category.get("isReadOnly"):
            # information only: writing an empty section back would wipe config
            continue

        if category.get("isModuleCategory"):
            entry = {}
            if "enabled" in category:
                entry["enabled"] = list(category.get("enabled") or [])
            if "disabled" in category:
                entry["disabled"] = list(category.get("disabled") or [])
            module_settings = {}
            for name, module in (category.get("settings") or {}).items():
                if isinstance(module, dict) and module.get("value"):
                    module_settings[name] = flatten_field_settings(module["value"])
            if module_settings:
                entry["settings"] = module_settings
            if entry:
                result[key] = entry
        else:
            result[key] = flatten_field_settings(category.get("settings") or {})

    return result
