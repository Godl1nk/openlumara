"""
Generic helpers shared across the webui's modules.
"""

import os

def serialize_for_json(obj):
    """Recursively converts non-serializable objects into plain dicts/lists."""
    if isinstance(obj, dict):
        return {k: serialize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [serialize_for_json(x) for x in obj]
    elif hasattr(obj, 'to_dict'):
        return serialize_for_json(obj.to_dict())
    elif hasattr(obj, '__dict__'):
        return serialize_for_json(obj.__dict__)
    elif isinstance(obj, (str, int, float, bool, type(None))):
        return obj
    else:
        return str(obj)

_ASSET_VERSION_CACHE = {}


def asset_version(assets_path):
    """Newest mtime under the assets tree, cached once per process."""
    if assets_path not in _ASSET_VERSION_CACHE:
        latest = 0.0
        for root, _dirs, files in os.walk(assets_path):
            for name in files:
                try:
                    latest = max(latest, os.path.getmtime(os.path.join(root, name)))
                except OSError:
                    pass
        _ASSET_VERSION_CACHE[assets_path] = str(int(latest))
    return _ASSET_VERSION_CACHE[assets_path]


def get_recursive_assets(assets_path, ext, skip: list = []):
    """Recursively list asset files with paths relative to server root."""
    files = []
    
    for root, dirs, filenames in os.walk(assets_path):
        # Skip files and directories marked for skipping
        filenames[:] = [f for f in filenames if os.path.basename(f) not in skip]
        dirs[:] = [d for d in dirs if d not in skip]
        
        for filename in filenames:
            if filename.endswith(f".{ext}"):
                full_path = os.path.join(root, filename)
                rel_path = os.path.relpath(full_path, assets_path)
                files.append(rel_path)
    
    return sorted(files)

def inject_indexes_into_messages(lst: list):
    """speaks for itself lol"""
    return [{**dickt, 'index': index} for index, dickt in enumerate(lst)]

def inject_indexes_into_chat(chat):
    """injects indexes into a chat's messages"""
    # copy it so we dont mutate it when injecting indexes
    chat_copy = dict(chat)

    # insert indexes into the messages array
    # so that the UI can track them for things like
    # editing messages, regenerating, deleting, etc
    chat_copy["messages"] = inject_indexes_into_messages(chat["messages"])

    return chat_copy

def api_result(obj = None, success: bool = True):
    if obj is None:
        result = {}
    else:
        result = obj

    return {"data": result, "success": success}

def trusted_client_ip(conn):
    """get the user's real IP, even if running openlumara behind a reverse proxy"""
    peer = conn.client.host if conn.client else "unknown"
    if peer in ("127.0.0.1", "::1"):
        forwarded = conn.headers.get("x-forwarded-for")
        if forwarded:
            first = forwarded.split(",")[0].strip()
            if first:
                return first
    return peer
