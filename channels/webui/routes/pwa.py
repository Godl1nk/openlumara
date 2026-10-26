"""
PWA routes: the generated service worker, manifest, icons and favicon.
"""

import os
import json

import fastapi

import core

def pwa_dir(channel):
    return os.path.join(channel.path, "pwa")

def generate_cache_version():
    # generate an sw.js cache version based on this file's last modified time
    # because bumping sw.js's version manually each time i update the webui
    # is a total pain and i don't want to deal with it

    webui_folder = core.get_path("channels/webui")

    # Get the latest modification time among all files in the folder
    latest_mtime = os.path.getmtime(__file__)  # fallback to this file

    for root, dirs, files in os.walk(webui_folder):
        for file in files:
            file_path = os.path.join(root, file)
            try:
                file_mtime = os.path.getmtime(file_path)
                if file_mtime > latest_mtime:
                    latest_mtime = file_mtime
            except (OSError, FileNotFoundError):
                # Skip files that can't be accessed
                pass

    return f"v{int(latest_mtime)}"

def register(app, channel):
    @app.get('/sw.js')
    async def service_worker():
        base_path = core.get_path("channels/webui")
        assets_base = os.path.join(base_path, 'assets')

        files_to_cache = []
        for subdir in ['js', 'css']:
            dir_path = os.path.join(assets_base, subdir)
            if os.path.isdir(dir_path):
                for root, _, files in os.walk(dir_path):
                    for filename in files:
                        full_path = os.path.join(root, filename)
                        rel_path = os.path.relpath(full_path, assets_base)
                        files_to_cache.append('/assets/' + rel_path.replace(os.sep, "/"))
        files_to_cache.sort()

        sw_template_path = os.path.join(pwa_dir(channel), 'sw.js')
        with open(sw_template_path) as f:
            sw_code = f.read()

        version = generate_cache_version()

        sw_code = sw_code.replace('{{VERSION}}', version)
        sw_code = sw_code.replace('{{FILE_LIST}}', json.dumps(files_to_cache).replace("'", "\\'"))

        return fastapi.Response(
            content=sw_code,
            media_type='application/javascript',
            headers={
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'Expires': '0',
            }
        )

    @app.get('/manifest.json')
    async def manifest():
        """Serve the PWA manifest."""
        with open(os.path.join(pwa_dir(channel), "manifest.json")) as f:
            manifest_data = json.loads(f.read())
        return manifest_data

    @app.get('/icon-192.png')
    async def icon_192():
        """Serve the 192x192 icon for PWA."""
        return fastapi.responses.FileResponse(os.path.join(pwa_dir(channel), "icon-192.png"))

    @app.get('/icon-512.png')
    async def icon_512():
        """Serve the 512x512 icon for PWA."""
        return fastapi.responses.FileResponse(os.path.join(pwa_dir(channel), "icon-512.png"))

    @app.get('/favicon.ico')
    async def favicon():
        """Serve the favicon for the web interface."""
        return fastapi.responses.FileResponse(os.path.join(pwa_dir(channel), "favicon.ico"))

    @app.get('/favicon.svg')
    async def favicon_svg():
        """Serve the scalable Aegis favicon."""
        return fastapi.responses.FileResponse(
            os.path.join(channel.path, "favicon.svg"),
            media_type="image/svg+xml"
        )

    @app.get('/icon-maskable-512.png')
    async def icon_maskable_512():
        """Serve the maskable icon used by installed PWAs."""
        return fastapi.responses.FileResponse(os.path.join(channel.path, "icon-maskable-512.png"))
