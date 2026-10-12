import os
import regex as re
import ast
import shutil
import asyncio
import core

# cloned library repos live here (inside the data folder)
LIBRARY_SUBFOLDER = "module_libraries"

# folder names we look for inside a library repo when scanning for installables
KNOWN_SUBFOLDERS = ("modules", "user_modules", "channels", "user_channels")

class ModuleManager:
    """
    manages external module libraries: git repos listed in the core setting
    `module_libraries`. repos are shallow-cloned into the data folder and can
    then be browsed (list_available) and installed into user_modules / user_channels.
    """

    def __init__(self, manager=None):
        self.manager = manager

    def log(self, msg):
        if self.manager:
            self.manager.log("modules", msg)
        else:
            core.log("modules", msg)

    def library_folder(self):
        path = core.get_data_path(LIBRARY_SUBFOLDER)
        if not os.path.exists(path):
            os.makedirs(path, exist_ok=True)

        return path

    def repo_name(self, url):
        """derive a safe local folder name from a git url"""
        name = url.rstrip("/").split("/")[-1]
        if name.endswith(".git"):
            name = name[:-4]

        name = re.sub(r"[^A-Za-z0-9._-]", "_", name)
        return name or "repo"

    def list_repos(self):
        repos = core.config.get("core", "module_libraries")
        return [r.strip() for r in repos if isinstance(r, str) and r.strip()]

    def _find_git(self):
        git = shutil.which("git")
        if not git:
            self.log("git executable not found - module libraries cannot be synced")

        return git

    async def _run_git(self, git, args):
        """run a git command without blocking the event loop. returns (returncode, stderr)"""
        proc = await asyncio.create_subprocess_exec(
            git, *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await proc.communicate()

        return proc.returncode, stderr.decode("utf-8", "replace").strip()

    async def sync_repo(self, url):
        """clone a library repo, or update it if already cloned. returns the local path, or None on failure."""
        git = self._find_git()
        if not git:
            return None

        url = url.strip()
        dest = os.path.join(self.library_folder(), self.repo_name(url))

        if os.path.isdir(os.path.join(dest, ".git")):
            code, err = await self._run_git(git, ["-C", dest, "fetch", "--depth", "1", "origin"])
            if code != 0:
                self.log(f"failed to fetch {url}: {err} - using existing copy")
                return dest

            code, err = await self._run_git(git, ["-C", dest, "reset", "--hard", "origin/HEAD"])
            if code != 0:
                # origin/HEAD can be missing on some clones; fall back to tracked branch
                code, err = await self._run_git(git, ["-C", dest, "reset", "--hard", "@{u}"])
                if code != 0:
                    self.log(f"failed to update {url}: {err} - using existing copy")

            return dest

        code, err = await self._run_git(git, ["clone", "--depth", "1", url, dest])
        if code != 0:
            self.log(f"failed to clone {url}: {err}")
            return None

        self.log(f"cloned module library {url}")
        return dest

    async def load(self):
        """sync all module libraries defined in core.module_libraries. returns True if at least one synced."""
        repos = self.list_repos()
        if not repos:
            return False

        synced = 0
        for repo in repos:
            if await self.sync_repo(repo):
                synced += 1

        return synced > 0

    def list_libraries(self):
        """list locally cloned libraries as {name: path}"""
        base = self.library_folder()
        libs = {}
        for entry in sorted(os.listdir(base)):
            path = os.path.join(base, entry)
            if os.path.isdir(path) and os.path.isdir(os.path.join(path, ".git")):
                libs[entry] = path

        return libs

    def _extract_module_docstring(self, module_file):
        """grab the first line of the module class docstring without importing anything"""
        try:
            with open(module_file, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read())
        except Exception:
            return ""

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                doc = ast.get_docstring(node)
                if doc:
                    return doc.strip().split("\n")[0]

        return ""

    def _scan_dir(self, scan_root, library_name, installed_names, available):
        for entry in sorted(os.listdir(scan_root)):
            mod_dir = os.path.join(scan_root, entry)

            if not os.path.isdir(mod_dir) or entry.startswith(("_", ".")):
                continue

            for entry_file, kind in (("module.py", "module"), ("channel.py", "channel")):
                entry_path = os.path.join(mod_dir, entry_file)
                if not os.path.isfile(entry_path):
                    continue

                available.append({
                    "library": library_name,
                    "name": entry,
                    "type": kind,
                    "doc": self._extract_module_docstring(entry_path),
                    "installed": entry in installed_names,
                })
                break

    def list_available(self):
        """
        scan cloned libraries for installable modules/channels.
        handles repos with entries at the root as well as repos that mirror
        openlumara's layout (modules/, user_modules/, channels/, user_channels/).
        returns list of dicts: {library, name, type, doc, installed}
        """
        installed_names = set()
        for pkg_name in KNOWN_SUBFOLDERS:
            try:
                installed_names.update(core.modules.discover_module_names(__import__(pkg_name)))
            except ImportError:
                pass

        available = []
        for lib_name, lib_path in self.list_libraries().items():
            self._scan_dir(lib_path, lib_name, installed_names, available)
            for sub in KNOWN_SUBFOLDERS:
                sub_path = os.path.join(lib_path, sub)
                if os.path.isdir(sub_path):
                    self._scan_dir(sub_path, lib_name, installed_names, available)

        return available

    def _find_source(self, lib_path, module_name):
        """locate a module/channel folder inside a cloned library. returns (source_dir, kind) or (None, None)"""
        search_roots = [lib_path] + [os.path.join(lib_path, sub) for sub in KNOWN_SUBFOLDERS]
        for root in search_roots:
            for entry_file, k in (("module.py", "module"), ("channel.py", "channel")):
                candidate = os.path.join(root, module_name, entry_file)
                if os.path.isfile(candidate):
                    return os.path.dirname(candidate), k

        return None, None

    def install(self, library, module_name):
        """
        copy a module/channel from a cloned library into the user folders.
        returns (success, message). dependency installation is left to the caller
        via core.modules.install_module_deps(user_modules, name, manager).
        """
        libs = self.list_libraries()
        lib_path = libs.get(library)
        if not lib_path:
            return False, f"library '{library}' not found - sync it first"

        source, kind = self._find_source(lib_path, module_name)
        if not source:
            return False, f"'{module_name}' not found in library '{library}'"

        target_root = core.get_path("user_modules" if kind == "module" else "user_channels", sandbox=False)
        target = os.path.join(target_root, module_name)
        if os.path.exists(target):
            return False, f"'{module_name}' is already installed at {target}"

        shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", ".git"))
        self.log(f"installed {kind} '{module_name}' from library '{library}'")
        return True, target

    async def update(self, library, module_name):
        """
        re-sync a library repo and overwrite an installed module/channel with the
        latest version from it. returns (success, message).
        """
        url = None
        for repo in self.list_repos():
            if self.repo_name(repo) == library:
                url = repo
                break
        if not url:
            return False, f"library '{library}' is not a configured repo - cannot update"

        dest = await self.sync_repo(url)
        if not dest:
            return False, f"failed to update library '{library}'"

        source, kind = self._find_source(dest, module_name)
        if not source:
            return False, f"'{module_name}' not found in library '{library}' anymore"

        target_root = core.get_path("user_modules" if kind == "module" else "user_channels", sandbox=False)
        target = os.path.join(target_root, module_name)
        if not os.path.isdir(target):
            return False, f"'{module_name}' is not installed - use install instead"

        shutil.copytree(source, target, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", ".git"))
        self.log(f"updated {kind} '{module_name}' from library '{library}'")
        return True, target

    def uninstall(self, module_name):
        """remove an installed user module/channel that came from a library. returns (success, message)."""
        for sub in ("user_modules", "user_channels"):
            target = os.path.join(core.get_path(sub, sandbox=False), module_name)
            if os.path.isdir(target):
                shutil.rmtree(target)
                self.log(f"removed {sub}/{module_name}")
                return True, target
        return False, f"'{module_name}' is not installed as a user module/channel"
