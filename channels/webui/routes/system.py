"""
System API routes: misc data, context size, logs, restart and updates.
"""

import asyncio
import os

import core

import channels.webui.utils as utils

def register(app, channel):
    # ----------------------------
    # System.. stuff
    # ----------------------------
    # -- GET
    @app.get("/api/system/data")
    async def get_data():
        """returns any relevant data for the webUI to use"""
        data = {
            "max_context": channel.manager.API.get_max_context()
        }

        return utils.api_result(data)

    @app.get("/api/system/context_size")
    async def get_context_size():
        """returns a detailed breakdown of the current context window usage"""
        try:
            size = dict(await channel.context.get_size())
        except Exception as e:
            return utils.api_result(core.detail_error(e), success=False)

        threshold = core.config.get("model", "context_compression_threshold") or 0
        size["compression_threshold"] = round(float(threshold) * 100, 1)
        size["auto_compress"] = bool(core.config.get("model", "automatically_compress_context"))

        return utils.api_result(size)

    @app.get("/api/system/logs")
    async def get_logs():
        return utils.api_result(channel.logs)

    @app.get("/api/command_prefix")
    async def get_command_prefix():
        return utils.api_result(core.config.get("core", "cmd_prefix"))

    @app.get("/api/commands")
    async def get_commands():
        return utils.api_result(core.commands.get_commands(channel.manager.modules))

    # ----------------------------
    # ----------------------------
    async def _run_git(*args, timeout=90):
        """runs git in the repo root; returns (returncode, stdout, stderr)"""
        proc = await asyncio.create_subprocess_exec(
            "git", *args,
            cwd=os.getcwd(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout)
        except asyncio.TimeoutError:
            proc.kill()
            return -1, "", "timed out"
        return proc.returncode, out.decode(errors="replace").strip(), err.decode(errors="replace").strip()

    @app.get("/api/system/update_check")
    async def update_check():
        """checks the git remote for updates: fetches, then compares HEAD to the upstream ref"""
        data = {
            "is_repo": False, "branch": None, "commit": None,
            "remote_commit": None, "behind": 0, "ahead": 0,
            "update_available": False, "note": None,
        }

        try:
            rc, _, _ = await _run_git("rev-parse", "--is-inside-work-tree")
        except FileNotFoundError:
            return utils.api_result("git is not installed on this system", success=False)

        if rc != 0:
            data["note"] = "This OpenLumara install is not a git repository, so it can't update itself."
            return utils.api_result(data)

        data["is_repo"] = True

        rc, _, _ = await _run_git("fetch")
        fetch_failed = rc != 0

        _, data["branch"], _ = await _run_git("rev-parse", "--abbrev-ref", "HEAD")
        _, data["commit"], _ = await _run_git("rev-parse", "--short", "HEAD")

        rc, _, _ = await _run_git("rev-parse", "--abbrev-ref", "@{u}")
        if rc != 0:
            data["note"] = "The current branch has no upstream configured."
            return utils.api_result(data)

        rc, remote, _ = await _run_git("rev-parse", "--short", "@{u}")
        if rc != 0:
            data["note"] = "Could not resolve the upstream ref."
            return utils.api_result(data)
        data["remote_commit"] = remote

        _, behind, _ = await _run_git("rev-list", "--count", "HEAD..@{u}")
        _, ahead, _ = await _run_git("rev-list", "--count", "@{u}..HEAD")
        data["behind"] = int(behind) if behind.isdigit() else 0
        data["ahead"] = int(ahead) if ahead.isdigit() else 0

        # -- AI GENERATED CODE (GPT-6.2-Sol) :: 2026-11-25 07:34 +08:00 harness:Codex
        if fetch_failed:
            data["note"] = "git fetch failed: the comparison below may be stale."
        elif data["ahead"] and data["behind"]:
            data["note"] = "The local and tracking branches have diverged. Reconcile them before updating."
        else:
            data["update_available"] = data["behind"] > 0

        return utils.api_result(data)

    async def _check_entry_git(git, folder):
        """fetch + compare one cloned repo against its upstream; returns a status dict"""
        st = {
            "commit": None, "remote_commit": None, "behind": 0,
            "update_available": False, "note": None,
        }

        rc, _, _ = await channel.manager.module_manager._run_git(git, ["-C", folder, "fetch"])
        fetch_failed = rc != 0

        rc, head, _ = await channel.manager.module_manager._run_git(git, ["-C", folder, "rev-parse", "--short", "HEAD"])
        if rc != 0:
            st["note"] = "Could not read this repo's HEAD."
            return st
        st["commit"] = head

        rc, remote, _ = await channel.manager.module_manager._run_git(git, ["-C", folder, "rev-parse", "--short", "@{u}"])
        if rc != 0:
            st["note"] = "No upstream branch configured."
            return st
        st["remote_commit"] = remote

        _, behind, _ = await channel.manager.module_manager._run_git(git, ["-C", folder, "rev-list", "--count", "HEAD..@{u}"])
        st["behind"] = int(behind) if behind.isdigit() else 0

        if fetch_failed:
            st["note"] = "git fetch failed; comparison may be stale."
        else:
            st["update_available"] = st["commit"] != st["remote_commit"]

        return st

    @app.get("/api/system/entry_updates")
    async def entry_updates():
        """git-update status for every installed user module/channel repo"""
        mm = channel.manager.module_manager
        git = mm._find_git()

        entries = []
        for item in mm.list_installed():
            if item["type"] not in ("module", "channel") or not item.get("git"):
                continue

            entry = {
                "name": item["name"],
                "type": item["type"],
                "library": item.get("library") or "",
            }

            if not git:
                entry.update({"update_available": False, "note": "git executable not found"})
                entries.append(entry)
                continue

            folder, _ = mm._git_dir_of(item["name"])
            if not folder:
                continue

            entry.update(await _check_entry_git(git, folder))
            entries.append(entry)

        return utils.api_result(entries)

    # -- AI GENERATED CODE (GPT-6.2-Sol) :: 2026-11-25 07:34 +08:00 harness:Codex
    update_lock = channel.manager.update_lock

    async def _run_update_script():
        returncode, output = await channel.manager.run_update_script()
        channel.log("webui", f"update finished (exit {returncode}):\n{output}")
        return returncode, output

    @app.post("/api/system/update")
    async def trigger_update():
        """runs the update script (same as the updater module's /update command), then hard-restarts"""
        if update_lock.locked():
            return utils.api_result("An update is already running.", success=False)

        async with update_lock:
            returncode, output = await _run_update_script()
            if returncode:
                return utils.api_result(output, success=False)
            await channel.manager.restart(hard=True)

        return utils.api_result(output)

    @app.post("/api/system/update_all")
    async def update_all():
        """Updates OpenLumara and installed module/channel repos, then restarts once."""
        if update_lock.locked():
            return utils.api_result("An update is already running.", success=False)

        async with update_lock:
            core_result = await update_check()
            core_available = core_result.get("success") and core_result["data"]["update_available"]
            if core_available:
                returncode, output = await _run_update_script()
                if returncode:
                    return utils.api_result(output, success=False)

            mm = channel.manager.module_manager
            updated, failed = [], []
            for item in mm.list_installed():
                if item["type"] not in ("module", "channel") or not item.get("git"):
                    continue

                name = item["name"]
                try:
                    success, message, _, changed = await mm.update_entry(name)
                except Exception as error:
                    failed.append(f"{name}: {core.detail_error(error)}")
                    continue
                if not success:
                    failed.append(f"{name}: {message}")
                elif changed:
                    updated.append(name)

            channel.log("webui", f"update all: updated {updated or 'nothing'}"
                                 f"{'; failed: ' + '; '.join(failed) if failed else ''}")
            restart_required = bool(core_available or updated)
            if restart_required:
                await channel.manager.restart(hard=True)

        return utils.api_result({"updated": updated, "failed": failed, "restart_required": restart_required})

    # -- POST
    @app.post("/api/system/restart")
    async def restart_server():
        await channel.manager.restart()
