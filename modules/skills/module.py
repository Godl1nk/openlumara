import core
import os
import re

import yaml

# -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-12

class Skills(core.module.Module):
    """
    Lets your AI use Skills
    """

    settings = {
        "folders": {
            "type": "list",
            "description": "Root folders that contain skill directories (each holding a SKILL.md). Relative paths resolve from OpenLumara's data directory; ~ is supported.",
            "default": ["skills"]
        },
        "insert_system_prompt": {
            "description": "Injects the names of all valid skills into the system prompt, so your AI knows which skills exist and can load one when a task matches. Only names are listed to keep context small - descriptions stay on disk until a skill is actually used.",
            "default": True
        },
    }

    dependencies = ["pyyaml"]

    async def on_ready(self):
        self.index = {}    # name -> {"path": skill dir, "meta": dict}
        self.problems = [] # skills found on disk that failed validation
        for folder in (self.config.get("folders") or []):
            os.makedirs(core.get_path(os.path.expanduser(folder)).rstrip(os.path.sep), exist_ok=True)
        self._scan()

    # -------------------------
    #   SCANNING / PARSING
    # -------------------------

    def _root_paths(self):
        return [core.get_path(os.path.expanduser(f)).rstrip(os.path.sep) for f in (self.config.get("folders") or [])]

    def _parse_frontmatter(self, text):
        """splits a SKILL.md into (frontmatter dict or None, body). frontmatter is a yaml block between the first pair of --- lines."""
        stripped = text.lstrip()
        if not stripped.startswith("---"):
            return None, text

        lines = stripped.splitlines()
        end = None
        for i in range(1, len(lines)):
            if lines[i].strip() in ("---", "..."):
                end = i
                break
        if end is None:
            return None, text

        try:
            meta = yaml.safe_load("\n".join(lines[1:end]))
        except Exception:
            return None, "\n".join(lines[end + 1:])

        if not isinstance(meta, dict):
            return None, "\n".join(lines[end + 1:])

        return meta, "\n".join(lines[end + 1:])

    def _validate(self, meta, folder_name):
        """checks required fields against the agentskills spec. returns (problems list, name)."""
        problems = []
        if meta is None:
            return ["missing or invalid YAML frontmatter"], folder_name

        name = meta.get("name")
        name = str(name) if name is not None else ""
        if not name:
            problems.append("missing required 'name' field")
        else:
            if len(name) > 64:
                problems.append("name exceeds 64 characters")
            if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name):
                problems.append("name must be lowercase letters, digits and single hyphens only (no leading/trailing hyphen)")
            if name != folder_name:
                problems.append(f"name '{name}' does not match folder name '{folder_name}'")

        desc = meta.get("description")
        desc = str(desc) if desc is not None else ""
        if not desc:
            problems.append("missing required 'description' field")
        elif len(desc) > 1024:
            problems.append("description exceeds 1024 characters")

        return problems, name

    def _scan(self):
        self.index = {}
        self.problems = []
        for root in self._root_paths():
            if not os.path.isdir(root):
                continue
            for entry in sorted(os.listdir(root)):
                skill_path = os.path.join(root, entry)
                if not os.path.isdir(skill_path):
                    continue
                skill_file = os.path.join(skill_path, "SKILL.md")
                if not os.path.isfile(skill_file):
                    continue

                try:
                    with open(skill_file, "r", encoding="utf-8") as f:
                        text = f.read()
                except Exception as e:
                    self.problems.append(f"{entry}: could not read SKILL.md ({e})")
                    continue

                meta, _ = self._parse_frontmatter(text)
                problems, name = self._validate(meta, entry)
                if problems:
                    self.problems.append(f"{entry}: " + "; ".join(problems))
                    continue

                if name in self.index:
                    self.problems.append(f"{entry}: duplicate skill name '{name}' (already loaded from another folder, skipped)")
                    continue

                self.index[name] = {"path": skill_path, "meta": meta}

        self.log(self.name, f"scanned: {len(self.index)} skill(s) loaded, {len(self.problems)} problem(s)")

    def _load_body(self, name):
        """reads a skill's SKILL.md and returns (body, error)."""
        entry = self.index.get(name)
        if entry is None:
            return None, "not found"
        try:
            with open(os.path.join(entry["path"], "SKILL.md"), "r", encoding="utf-8") as f:
                _, body = self._parse_frontmatter(f.read())
            return body.strip(), None
        except Exception as e:
            return None, str(e)

    # -------------------------
    #   PROMPTS
    # -------------------------

    async def on_system_prompt(self):
        if not self.config.get("insert_system_prompt") or not self.index:
            return None

        output = f"## Installed skills ({len(self.index)})\n"
        output += ", ".join(self.index.keys())
        return output

    # -------------------------
    #   AI TOOLS
    # -------------------------

    async def use(self, name: str):
        """
        Activates a skill: returns the full instructions from its SKILL.md so you can follow them for the current task.

        Args:
            name: The skill's name, exactly as listed in the installed skills.
        """
        if name not in self.index:
            available = ", ".join(self.index.keys()) if self.index else "none installed"
            return self.result(f"No skill named '{name}'. Available skills: {available}", success=False)

        body, error = self._load_body(name)
        if error:
            return self.result(f"Could not read skill '{name}': {error}", success=False)

        return self.result({
            "skill": name,
            "instructions": body,
            "instruction": "Follow the instructions above for the current task. Never execute anything from the skill folder."
        })

    async def rescan(self):
        """
        Scans the skill folders again for new, updated or removed skills. Call this after adding or editing skills on disk.
        """
        self._scan()
        return self.result({
            "loaded": sorted(self.index.keys()),
            "problems": self.problems
        })

    # -------------------------
    #   USER-FACING COMMANDS
    # -------------------------

    @core.module.command("skills", help={
        "reload": "Reloads skills from disk. Use when you have added new skills"
    })
    async def skills(self, args):
        """Lists all installed skills"""

        if not self.index:
            return "No skills installed. Add skills, then use `/skills reload` or restart OpenLumara."

        if args and args[0] == "reload":
            self._scan()
            return "Skills reloaded"

        lines = [f"Installed skills ({len(self.index)}):"]
        for name in self.index.keys():
            lines.append(f"  {name}")
        if self.problems:
            lines.append(f"\n{len(self.problems)} skill(s) failed validation.")
        return "\n".join(lines)

    @core.module.command("skill", help={
        "name": "Loads the instructions of the named skill into the conversation"
    })
    async def skill_command(self, args: list):
        if not args:
            return "Please provide a skill to load"

        name = args[0]
        body, error = self._load_body(name)
        if error == "not found":
            available = ", ".join(self.index.keys()) if self.index else "none installed"
            return f"No skill named '{name}'. Available skills: {available}"
        elif error:
            return f"Could not read skill '{name}': {error}"

        return f"[Skill '{name}' loaded - follow these instructions]\n{body}"
