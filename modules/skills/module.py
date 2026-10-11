import core
import os
import yaml

class Skills(core.module.Module):
    """
    Lets your AI use Skills
    """

    settings = {
        "folder": {
            "description": "The folder that contains skills.\n\n**NOTE**: *When using skills made for other harnesses with openlumara, keep in mind that many of them will want to use an unrestricted shell - which is highly unsafe.*\n\n*For many of the most common actions the AI might want to take, a tool already exists, but if anything is missing, please create a user module that gives the AI that functionality via a tool, rather than giving full shell access. Otherwise, you're compromising the security I worked so hard to achieve in OpenLumara.*\n\n~Rose22",
            "default": "skills"
        },
        "insert_system_prompt": {
            "description": "Injects the names of all valid skills into the system prompt, so your AI knows which skills exist and can load one when a task matches. Only the names are listed, to keep context small.",
            "default": True
        },
    }

    async def on_ready(self):
        # in-memory index of skills
        self.index = {}

        if self.config.get("folder"):
            os.makedirs(self._root_path(), exist_ok=True)

        self._scan()

    # -------------------------
    #   SCANNING / PARSING
    # -------------------------

    def _root_path(self):
        return core.get_path(os.path.expanduser(self.config.get("folder"))).rstrip(os.path.sep)

    def _parse_frontmatter(self, text):
        """splits a SKILL.md into (frontmatter dict or None, body). frontmatter is a yaml block between the first pair of --- lines."""
        stripped = text.lstrip()
        if not stripped.startswith("---"):
            return None, text

        # find last line of frontmatter
        lines = stripped.splitlines()
        end = None
        for i in range(1, len(lines)):
            if lines[i].strip() in ("---", "..."):
                end = i
                break
        if end is None:
            return None, text

        # and parse the full frontmatter block
        try:
            meta = yaml.safe_load("\n".join(lines[1:end]))
        except Exception:
            return None, "\n".join(lines[end + 1:])

        if not isinstance(meta, dict):
            return None, "\n".join(lines[end + 1:])

        return meta, "\n".join(lines[end + 1:])

    def _scan(self):
        self.index = {}
        root = self._root_path()
        if os.path.isdir(root):
            for entry in sorted(os.listdir(root)):
                skill_path = os.path.join(root, entry)
                if not os.path.isdir(skill_path):
                    continue

                skill_file = os.path.join(skill_path, "SKILL.md")
                if not os.path.isfile(skill_file):
                    continue

                # the skill is whatever folder holds a SKILL.md. the name comes from
                # the frontmatter if present, otherwise the folder name is used.
                name = entry
                try:
                    with open(skill_file, "r", encoding="utf-8") as f:
                        meta, _ = self._parse_frontmatter(f.read())
                    if meta and meta.get("name"):
                        name = str(meta["name"])
                except Exception:
                    pass

                if name not in self.index:
                    self.index[name] = skill_path

        self.log(self.name, f"scanned: {len(self.index)} skill(s) loaded")

    def _load_body(self, name):
        """reads a skill's SKILL.md and returns (body, error)."""
        skill_path = self.index.get(name)

        if skill_path is None:
            return None, "not found"
        try:
            with open(os.path.join(skill_path, "SKILL.md"), "r", encoding="utf-8") as f:
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

        return ", ".join(self.index.keys())

    # -------------------------
    #   AI TOOLS
    # -------------------------

    async def use(self, name: str):
        """uses skill listed in system prompt, returns instructions to follow"""
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
