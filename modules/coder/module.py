import core
import channels.webui.api as webui
import os
import importlib
import shutil
import regex
import glob
import fnmatch
import subprocess
import tree_sitter_language_pack as tslp

class Coder(core.module.Module):
    """Lets your AI write code within sandboxes, without using a shell. Validates code syntax before writing to disk to protect your code from breaking."""

    category = "development"

    # The coder module, now manually rewritten and free of any AI slop :)
    # ~ Rose22

    settings = {
        "read-only": {
            "default": False,
            "description": "Disables all operations that could modify your code or your filesystem. You can use `/coder readonly` to quickly toggle this during sessions."
        },
        "global_line_limit": {
            "default": 1000,
            "description": "Hard limit on the amount of lines the AI is allowed to read at once. Greatly helps reduce token usage!"
        },

        # paths
        "sandbox_paths": {
            "default": ["~/coder"],
            "description": "Paths to folders you want the coder to have access to. You can use the `~` character to refer to your home folder, such as `/home/you` on linux, /Users/You on mac, `C:\\Users\\You` on windows"
        },

        "template_paths": {
            "default": [],
            "description": "Templates are special files that the coder can read from anywhere at any time when requested, in order to show example code to the AI. You can define folders to load such templates from here!"
        },
        "enable_builtin_templates": {
            "default": True,
            "description": "Openlumara comes bundled with hand-written templates for creating your own modules and channels! Enable them here.\n\n**TIP**: To vibecode your own modules or channels, tell the AI to read the module or channel template in your prompt. Example: `read the openlumara channel template and make me a basic terminal user interface`"
        },

        "use_coding_prompt": {
            "default": False,
            "description": "If enabled, will allow you to specify a special prompt that instructs the AI on your preferred coding practices and guidelines."
        },
        "coding_prompt": {
            "type": "long_text",
            "default": "",
            "depends": "use_coding_prompt"
        },

        # flags
        "insert_sandbox_paths_into_system_prompt": {
            "default": True,
            "description": "Puts the list of sandboxes into the AI's system prompt so that it is always aware of which paths it can access. Recommended!"
        },
        "add_sandbox_contents_to_sandbox_list": {
            "default": False,
            "description": "Puts a list of top-level folders within each sandbox into the system prompt. This greatly speeds up sandbox exploration, and is not a recursive list - it only lists the folders that are directly at the root level of each sandbox.",
            "depends": "insert_sandbox_paths_into_system_prompt"
        },

        # webui editor extensions (umbrella toggle is auto-detected from the module's webui folder)
        "vim_mode": {
            "default": False,
            "description": "Vim keybindings (normal/insert/visual, motions, text objects) in the webui file editor.",
            "depends": "enable_webui_extension"
        },

        # blacklists
        "folder_blacklist": {
            "default": ["venv", "__pycache__"],
            "description": "Prevents recursive operations such as `glob` and `grep` from reaching into folders matching the names in this blacklist"
        }
    }

    # the coder likes sitting on a tree... of code
    # the tree is nice and green and it also tells the coder whether it made any oopsies
    dependencies = [
        "tree-sitter",
        "tree-sitter-language-pack",
    ]

    regex_timeout = 3
    builtin_templates_path = "modules/coder/templates"

    # -------------
    # events
    # -------------
    async def on_ready(self):
        self.disabled_tools = []

        # enable/disable tools based on selected modes
        if self.config.get("read-only"):
            self.disabled_tools.extend(["file_create", "file_move", "file_delete", "file_edit", "folder_delete"])

        if self.config.get("insert_sandbox_paths_into_system_prompt"):
            self.disabled_tools.append("list_sandboxes")

        # still figuring out how to best guide the AI in when to use file_inspect over file_read.
        # it's a very tough thing since most LLM's are trained to just read entire files
        # and are inclined to do so
        self.disabled_tools.append("file_outline")

    async def on_system_prompt(self):
        final_output = []

        templates = await self._get_templates()
        if templates:
            output_str = "## Templates you can read using read_template:\n"
            output_str += "\n".join([f"- {template}" for template in templates])
            final_output.append(output_str)

        if self.config.get("insert_sandbox_paths_into_system_prompt"):
            sandboxes = await self._get_sandbox_paths()
            if sandboxes:
                output_str = "## Sandboxes you have access to:\n"
                output_str += "\n".join([f"- {path}" for path in sandboxes])
                final_output.append(output_str)

            if self.config.get("add_sandbox_contents_to_sandbox_list"):
                for sandbox in sandboxes:
                    output_str = f"### Files within sandbox '{sandbox}':"
                    full_path = await self._get_full_sandbox_path(sandbox)
                    folder_list = os.listdir(full_path)

                    files = []
                    folders = []
                    for file in folder_list:
                        if os.path.isdir(os.path.join(full_path, file)):
                            folders.append(file)
                        else:
                            files.append(file)

                    folders.sort()
                    files.sort()

                    if folders:
                        output_str += "\n#### Folders:\n"
                        output_str += "\n".join([f"- {folder}" for folder in folders])
                    if files:
                        output_str += "\n#### Files:\n"
                        output_str += "\n".join([f"- {file}" for file in files])

                    final_output.append(output_str)

        if self.config.get("use_coding_prompt") and self.config.get("coding_prompt"):
            final_output.append(f"## Coding Guidelines\nYOU MUST ALWAYS follow these guidelines while using the coder:\n{self.config.get('coding_prompt')}")

        if self.config.get("read-only"):
            final_output.append("## IMPORTANT: Read-Only Mode\nYour coder module is in read-only mode and you cannot write to files. Provide output code to the user directly in your messages.")
        else:
            final_output.append("No need to check syntax. Coder has built-in syntax check.")

        if final_output:
            return "\n\n".join(final_output)
        return None

    # -------------------------------
    # helper functions: sandbox stuff
    # -------------------------------
    async def _get_sandbox_paths(self):
        """
        translates the sandbox path list into basenames
        so that it can actually be used by the AI without
        having to recite full paths all the time
        """
        paths = self.config.get("sandbox_paths")
        if not paths:
            return []

        # create them if they dont exist
        for path in paths:
            os.makedirs(os.path.expanduser(path).rstrip(os.path.sep), exist_ok=True)

        # strip the paths of separators at the end so that os.path.basename doesnt return a blank string (why, python?)
        paths = [path.rstrip(os.path.sep) for path in paths]

        # now return the basename of each sandbox
        return [os.path.basename(path) for path in paths]

    async def _get_full_sandbox_path(self, requested_path: str):
        """converts a basename'd sandbox path back into the full path"""
        paths = self.config.get("sandbox_paths")
        if not paths:
            return None

        for path in paths:
            if os.path.basename(path.rstrip(os.path.sep)) == requested_path.rstrip(os.path.sep):
                return os.path.expanduser(path).rstrip(os.path.sep)

        raise Exception("That sandbox does not exist")

    async def _get_sandbox_subpath(self, sandbox: str, requested_path: str):
        """
        resolves a basename'd sandbox path back to its full path,
        then checks whether the requested path is within the sandbox,
        and if so, returns it
        """
        # remove the sandbox path itself from the string in case the AI decided to add it
        if requested_path.startswith(sandbox):
            requested_path = requested_path[len(sandbox):]

        sandbox_path = await self._get_full_sandbox_path(sandbox)
        return core.sandbox_path(sandbox_path, requested_path)

    # -----------------------------
    # helper functions: treesitter
    # -----------------------------
    async def _check_syntax(self, code: str, file_path: str):
        """verifies code for syntax errors without writing it to disk"""
        errors = []

        lang = tslp.detect_language_from_path(file_path)
        if not lang or lang in ("vimdoc", "html", "htm"):
            # that means treesitter doesn't support the language,
            # or it's a plaintext file (labeled by treesitter as 'vimdoc'),
            # so to avoid blocking code editing for unsupported languages,
            # just pretend the syntax error check passed

            # also, html syntax is skipped because the checker is too aggressive and forbids & characters, causing tons of false positive rejections
            return []

        result = tslp.process(code, tslp.ProcessConfig(language=lang, diagnostics=True, structure=False))
        if not result:
            # was likely an empty file, or failed to parse
            errors.append("Failed to parse the file for syntax errors. For safety, the file was not written to disk.")
            return errors

        if result.diagnostics:
            for diag in result.diagnostics:
                errors.append(f"Line {diag.span.start_line + 1}, Col {diag.span.start_column + 1}: {diag.message}")

        # return errors if they were found, otherwise it's an empty list and callers will know there were no errors
        return errors

    async def _extract_code_structure(self, code: str, file_path: str):
        """
        uses treesitter-language-pack to extract useful information from source code
        this can then be used by the LLM to do very targeted reads of specific sections of code,
        reducing the need to read entire files into context and thus saving on token use massively

        (..but it's not done yet.)
        """
        lang = tslp.detect_language_from_path(file_path)
        if not lang:
            # return None so that the caller can handle it and tell the user
            return None

        extraction = tslp.process(code, tslp.ProcessConfig(
            language=lang,
            structure=True,
            imports=True,
            comments=False
        ))
        if not extraction:
            # was likely an empty file, or failed to parse
            return None

        data = {}
        data["symbols"] = []
        for item in extraction.structure:
            data["symbols"].append({
                "name": str(item.name),
                "kind": str(item.kind),
                "start_line": int(item.span.start_line),
                "end_line": int(item.span.end_line),
                "doc_comment": item.doc_comment,
                "signature": item.signature
            })

        if not data["symbols"]:
            # tell the AI that this is a file that must be read manually instead
            return None

        metrics = extraction.metrics
        data["metrics"] = {
            "total_lines": metrics.total_lines,
            "error_count": metrics.error_count
        }
        data["imports"] = [imprt.source for imprt in extraction.imports]

        return data

    # ---------------------------
    # helper functions: templates
    # ---------------------------
    async def _get_template_folders(self):
        template_folders = list(self.config.get("template_paths", default=[]))

        # add the internal templates path to the list of template folders
        if self.config.get("enable_builtin_templates"):
            template_folders.insert(0, self.builtin_templates_path)

        return template_folders or []

    async def _get_templates(self):
        all_templates = []
        template_folders = await self._get_template_folders()

        if not template_folders:
            return []

        for folder in template_folders:
            # resolve relative paths to the openlumara root,
            # absolute paths to their absolute locations
            folder_path = core.get_path(folder)

            try:
                templates = os.listdir(folder_path)
            except Exception as e:
                return self.result(str(e), success=False)

            all_templates.extend(templates)

        return all_templates

    # ----------------------
    # tools: file navigation
    # ----------------------
    async def list_sandboxes(self):
        return self.result(await self._get_sandbox_paths())

    async def glob(self, sandbox: str, pattern: str, sub_path=None, max_results: int = 200):
        """globs path for desired files. does not support regex. paths relative to sandbox root."""
        sandbox_path = await self._get_full_sandbox_path(sandbox)
        target_path = await self._get_sandbox_subpath(sandbox, sub_path or '.')

        folder_blacklist = self.config.get("folder_blacklist")

        try:
            # remove the sandbox path itself from the string in case the AI decided to add it
            if pattern.startswith(sandbox):
                pattern = pattern[len(sandbox):]

            matches = sorted(glob.glob(
                os.path.join(target_path, pattern),
                recursive=True
            ))

            results = []
            total = 0
            for match in matches:
                rel_path = os.path.relpath(match, target_path)

                # skip if any path component is in the blacklist
                path_parts = rel_path.split(os.sep)
                if any(part in folder_blacklist for part in path_parts):
                    continue

                total += 1
                if total > int(max_results):
                    break

                # ensure it's within the sandbox
                core.sandbox_path(sandbox_path, rel_path)
                results.append(rel_path)

            if total > int(max_results):
                return self.result({
                    "results": results,
                    "truncated": True,
                    "total": total,
                    "note": f"showing first {int(max_results)} of {total} matches - narrow your pattern to see more"
                })
            return self.result(results)
        except Exception as e:
            return self.result(str(e), success=False)

    async def folder_grep(self, sandbox: str, sub_path: str, regex_pattern: str, case_sensitive=False, context: int = 0, file_extensions: list = None, max_matches: int = 30):
        """searches for regex pattern in all files in folder"""
        folder_blacklist = self.config.get("folder_blacklist")

        if regex_pattern.strip() in [".", "*"]:
            return self.result("Forbidden pattern detected. Use a more specific search!", success=False)

        # compile regex with optional case-insensitive flag
        flags = 0 if case_sensitive else regex.IGNORECASE
        compiled_pattern = regex.compile(regex_pattern, flags)

        target_path = await self._get_sandbox_subpath(sandbox, sub_path)
        if os.path.isdir(target_path):
            # recursive search
            matches = []
            for (recursive_path, folders, files) in os.walk(target_path):
                # Filter out blacklisted and hidden directories using config
                folders[:] = [d for d in folders if not d.startswith('.') and d not in folder_blacklist]

                if len(matches) >= int(max_matches):
                    break

                for file in files:
                    try:
                        filepath = os.path.join(recursive_path, file)
                        
                        # filter by extensions if specified
                        if file_extensions:
                            _, ext = os.path.splitext(file)
                            if ext[1:] not in file_extensions:
                                continue

                        with open(filepath, 'r', encoding="utf-8") as f:
                            all_lines = f.readlines()
                            for line_num, line in enumerate(all_lines, 1):
                                if compiled_pattern.search(line, timeout=self.regex_timeout):
                                    # add context lines
                                    context_lines = []
                                    start = max(0, line_num - 1 - int(context))
                                    end = min(len(all_lines), line_num + int(context))
                                    for ctx_line_num in range(start, end):
                                        if ctx_line_num + 1 != line_num:
                                            context_lines.append(all_lines[ctx_line_num].rstrip())
                                    
                                    match_dict = {
                                        "file": os.path.relpath(filepath, target_path),
                                        "line_num": line_num,
                                        "line": line.rstrip(),
                                    }
                                    if context:
                                        match_dict.update({
                                            "context_before": context_lines[:context],
                                            "context_after": context_lines[-context:] if context > 0 else []
                                        })

                                    matches.append(match_dict)
                                    if len(matches) >= int(max_matches):
                                        return self.result({
                                            "matches": matches,
                                            "note": f"Showing up to {int(max_matches)} matches. More results may be available — narrow your search pattern to see them."
                                        })
                    except Exception as e:
                        pass

            if matches:
                return self.result(matches)
            else:
                return self.result("No matches found", success=False)
        else:
            return self.result("Target path is not a folder. Grep only works on folders.", success=False)


    # ----------------------
    # tools: file management
    # ----------------------
    async def file_create(self, sandbox: str, path: str, content: str):
        """creates new file, does not support overwriting existing files. auto-creates parent dirs in path."""
        target_path = await self._get_sandbox_subpath(sandbox, path)

        # first, check for syntax errors
        syntax_errors = await self._check_syntax(content, target_path)
        if syntax_errors:
            return self.result({"errors": syntax_errors, "message": "Syntax errors detected! File was not written to disk."}, success=False)

        # auto-create any parent folders that don't exist yet,
        # so the AI doesn't have to bother creating them manually
        parent_dir = os.path.dirname(target_path)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)

        # using try/except here instead of checking if the file exists, to defend against
        # TOCTOU (Time-Of-Check -> Time-Of-Use)
        # a race condition vulnerability that can escape sandboxes
        # am i the only one that thinks TOCTOU kinda sounds like TOC TUA aka HAWK TUAH? oh no
        try:
            with open(target_path, 'x') as f:
                f.write(content)
        except Exception as e:
            return self.result(str(e), success=False)

        return self.result(f"File {path} successfully created")

    async def file_move(self, sandbox: str, orig_path: str, target_path: str):
        orig_path_sandboxed = await self._get_sandbox_subpath(sandbox, orig_path)
        target_path_sandboxed = await self._get_sandbox_subpath(sandbox, target_path)

        try:
            shutil.move(orig_path_sandboxed, target_path_sandboxed)
        except Exception as e:
            # TAWK TUAH
            return self.result(str(e), success=False)

        return self.result(f"File successfully moved: {orig_path_sandboxed} -> {target_path_sandboxed}")

    async def file_delete(self, sandbox: str, path: str):
        """only use this if user explicitely requests it"""
        target_path = await self._get_sandbox_subpath(sandbox, path)

        try:
            os.remove(target_path)
        except Exception as e:
            # TAWCC THUA
            return self.result(str(e), success=False)

        return self.result(f"File {path} successfully deleted")

    async def folder_delete(self, sandbox: str, path: str):
        """only use this if user explicitely requests it. can only remove empty folders as safety precaution."""
        target_path = await self._get_sandbox_subpath(sandbox, path)
        
        try:
            os.rmdir(target_path)
        except Exception as e:
            # FAWK SHUA
            return self.result(str(e), success=False)

        return self.result(f"Folder {path} deleted")

    # ----------------------
    # tools: file reading
    # ----------------------
    async def file_outline(self, sandbox: str, path: str):
        """provides information about source code. only works on source code files."""
        target_path = await self._get_sandbox_subpath(sandbox, path)
        try:
            with open(target_path, 'r', encoding="utf-8") as f:
                file_content = f.read()
                structure = await self._extract_code_structure(file_content, target_path)
                if not structure:
                    return self.result("This file could not be read by the code inspector because it is not a source code file. Use file_read instead", success=False)

                return self.result(structure)
        except Exception as e:
            # FAWK KUAH
            return self.result(str(e), success=False)

    async def file_read(self, sandbox: str, path: str, line_start: int = None, line_end: int = None):
        """reads file, or part of file. use line_start and line_end to read in chunks."""
        target_path = await self._get_sandbox_subpath(sandbox, path)

        # protect against tocccc touh
        try:
            content = None
            with open(target_path, 'r', encoding="utf-8") as f:
                content = f.read()

            if not content:
                return self.result("File was empty", success=False)
        except Exception as e:
            return self.result(str(e), success=False)

        content_lines = content.split("\n")
        total_lines = len(content_lines)

        max_lines = self.config.get("global_line_limit")

        # filesize gate
        if line_start is None and line_end is None:
            if total_lines <= max_lines:
                # Allow plain reads for small files
                line_start = 1
                line_end = total_lines
            else:
                return self.result(f"File is too large to read in full! ({total_lines} lines). Read it in chunks.", success=False)

        # default ranges
        if line_start is None:
            line_start = 1
        if line_end is None:
            line_end = -1

        # make sure it's 0-indexed
        line_start = line_start-1

        # clamp line start to above 1
        if line_start < 0:
            line_start = 1

        # change a line end of -1 to the actual last line
        if line_end == -1 or line_end > total_lines:
            line_end = total_lines
        elif line_end < 1:
            line_end = 1

        # enforce hard limit on chunk size
        hit_line_limit = line_end - line_start > max_lines
        if hit_line_limit:
            line_end = line_start + max_lines

        # now get only the requested part
        content_partial = content_lines[line_start:line_end]

        # tell the AI what got truncated
        remaining = total_lines - line_end
        truncated = remaining > 0 or hit_line_limit
        truncation_note = f"Showing lines {line_start+1}-{line_end} of {total_lines}. {remaining} lines remaining." if truncated else None
        if hit_line_limit:
            truncation_note += f" WARNING: request clamped to global line limit of {max_lines} lines"

        result = {"content": "\n".join(content_partial), "truncated": truncated}
        if truncated:
            result["truncation_note"] = truncation_note
        result["success"] = True

        return result

    async def file_grep(self, sandbox: str, file_path: str, regex_pattern: str, case_sensitive: bool = True, context: int = 0, max_matches: int = 30):
        target_path = await self._get_sandbox_subpath(sandbox, file_path)
        
        # compile regex with optional case-insensitive flag
        flags = 0 if case_sensitive else regex.IGNORECASE
        compiled_pattern = regex.compile(regex_pattern, flags)

        try:
            matches = []
            with open(target_path, 'r', encoding="utf-8") as f:
                all_lines = f.readlines()
                for line_num, line in enumerate(all_lines, 1):
                    if compiled_pattern.search(line, timeout=self.regex_timeout):
                        # add context lines
                        context_lines = []
                        start = max(0, line_num - 1 - int(context))
                        end = min(len(all_lines), line_num + int(context))
                        for ctx_line_num in range(start, end):
                            if ctx_line_num + 1 != line_num:
                                context_lines.append(all_lines[ctx_line_num].rstrip(),)

                        match_dict = {
                            "line_num": line_num,
                            "line": line.rstrip()
                        }

                        if context:
                            match_dict.update({
                                "context_before": context_lines[:int(context)],
                                "context_after": context_lines[-int(context):] if int(context) > 0 else []
                            })

                        matches.append(match_dict)

                        if len(matches) >= int(max_matches):
                            return self.result({
                                "matches": matches,
                                "note": f"Showing up to {int(max_matches)} matches. More results may be available — narrow your search pattern to see them."
                            })

            if matches:
                return self.result(matches)
            else:
                return self.result("No matches found", success=False)
        except Exception as e:
            # FKAWK SUAH
            return self.result(str(e), success=False)

    async def read_template(self, template_name: str):
        template_folders = await self._get_template_folders()
        if not template_folders:
            raise Exception("no template folders were configured! this should never happen, since the builtin one is always included. notify the developer!")

        for folder in template_folders:
            # resolve relative paths to the openlumara root,
            # absolute paths to their absolute locations
            folder_path = core.get_path(folder)

            try:
                templates = os.listdir(folder_path)
            except Exception as e:
                # LAWK FUAH
                return self.result(str(e), success=False)

            if template_name in templates:
                try:
                    with open(os.path.join(folder_path, template_name), 'r', encoding="utf-8") as f:
                        return self.result(f.read())
                except Exception as e:
                    # FAWK MUAH
                    return self.result(str(e), success=False)

        return self.result("Template not found!", success=False) 

    # --------------------
    # tools: file writing
    # --------------------
    async def file_edit(self, sandbox: str, path: str, original_code: str, replacement_code: str):
       target_path = await self._get_sandbox_subpath(sandbox, path)

       file_content = None
       # protect against FAWK HUAH
       try:
           with open(target_path, 'r', encoding="utf-8") as f:
               file_content = f.read()
       except Exception as e:
           return self.result(str(e), success=False)

       if not file_content:
           return self.result("File is empty!", success=False)

       # now do the actual replacement
       new_file_content = file_content.replace(original_code, replacement_code)

       if new_file_content == file_content:
           # that means it failed to replace!
           return self.result("Failed to match your original code string against the file contents. Try again!", success=False)

       # check for syntax errors
       syntax_errors = await self._check_syntax(new_file_content, target_path)
       if syntax_errors:
           return self.result({"errors": syntax_errors, "message": "Syntax errors detected! File was not written to disk."}, success=False)

       # and write it to the file
       try:
           with open(target_path, 'w', encoding="utf-8") as f:
               f.write(new_file_content)
       except Exception as e:
           # TAWK TOUHA
           return self.result(str(e), success=False)

       return self.result(f"Successfully edited file {path}")

    # ---------------------
    # user-facing commands
    # ---------------------
    @core.module.command("coder", help={
       "readonly": "toggle read-only mode"
    })
    async def cmd_coder(self, args: list):
        if len(args) == 0:
            return "please specify a sub-command (see /help coder)"

        match args[0]:
            case "readonly":
                current_state = self.config.get("read-only")
                self.config.set("read-only", not current_state)
                await self.manager.reload_module(self.name)

                if current_state:
                    return "read-only mode disabled"
                else:
                    return "read-only mode enabled"

    # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
    # webui extension routes for the coder sidebar (sandbox dropdown +
    # lazy file tree + edit modal). private methods are ignored by the tool
    # loader; @webui.route exposes them under /api/ext/coder/<path>.
    # saves run through the same treesitter syntax gate as coder_file_edit.

    # files the webui editor refuses to open (binary / huge)
    ui_max_read_bytes = 1_000_000

    @webui.route("sandboxes")
    async def _route_sandboxes(self, body=None, query=None):
        """sandbox names for the dropdown + whether the module is read-only.
        also carries the effective vim-mode flag so the webui doesn't need
        its own settings endpoint (vim mode only counts when the umbrella
        extension toggle is on too)."""
        return {
            "sandboxes": await self._get_sandbox_paths(),
            "read_only": bool(self.config.get("read-only")),
            "vim_mode": bool(self.config.get("vim_mode")) and bool(self.config.get("enable_webui_extension")),
        }

    @webui.route("tree")
    async def _route_tree(self, body=None, query=None):
        """one directory level of a sandbox. path is relative to the sandbox
        root ('' = root). returns entries sorted folders-first."""
        sandbox = (query or {}).get("sandbox", "")
        rel_path = (query or {}).get("path", "") or ""

        if not sandbox:
            return self.result("no sandbox given", success=False)

        try:
            target = await self._get_sandbox_subpath(sandbox, rel_path)
        except Exception as e:
            return self.result(str(e), success=False)

        if not os.path.isdir(target):
            return self.result("not a folder", success=False)

        blacklist = self.config.get("folder_blacklist") or []
        entries = []
        try:
            for name in os.listdir(target):
                full = os.path.join(target, name)
                is_dir = os.path.isdir(full)
                child_rel = os.path.normpath(os.path.join(rel_path, name)).replace(os.sep, "/")
                entries.append({
                    "name": name,
                    "path": child_rel,
                    "is_dir": is_dir,
                    "hidden": name.startswith("."),
                    "blacklisted": is_dir and name in blacklist,
                })
        except Exception as e:
            return self.result(str(e), success=False)

        entries.sort(key=lambda e: (not e["is_dir"], e["name"].lower()))
        return {"path": rel_path, "entries": entries}

    # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
    @webui.route("files")
    async def _route_files(self, body=None, query=None):
        """full recursive file list of a sandbox (relative, slash-separated)
        for the ctrl+p quick-open modal. hidden + blacklisted folders are
        skipped. deliberately UNCAPPED: os.walk is depth-first, so an early
        cap silently starved every folder that sorts after the one that ate
        the budget. the frontend caps the scored matches instead."""
        sandbox = (query or {}).get("sandbox", "")
        if not sandbox:
            return self.result("no sandbox given", success=False)

        try:
            target = await self._get_full_sandbox_path(sandbox)
        except Exception as e:
            return self.result(str(e), success=False)

        if not target or not os.path.isdir(target):
            return self.result("sandbox not found", success=False)

        blacklist = self.config.get("folder_blacklist") or []

        files = []
        try:
            for recursive_path, folders, filenames in os.walk(target):
                # prune hidden + blacklisted branches in place so os.walk
                # never descends into them (same trick folder_grep uses)
                folders[:] = [d for d in folders if not d.startswith(".") and d not in blacklist]

                for name in filenames:
                    if name.startswith("."):
                        continue
                    full = os.path.join(recursive_path, name)
                    rel = os.path.relpath(full, target).replace(os.sep, "/")
                    files.append(rel)
        except Exception as e:
            return self.result(str(e), success=False)

        files.sort()
        return {"files": files}

    @webui.route("read")
    async def _route_read(self, body=None, query=None):
        """raw text of a file, for the edit modal"""
        sandbox = (query or {}).get("sandbox", "")
        rel_path = (query or {}).get("path", "")

        if not sandbox or not rel_path:
            return self.result("sandbox and path are both required", success=False)

        try:
            target = await self._get_sandbox_subpath(sandbox, rel_path)
        except Exception as e:
            return self.result(str(e), success=False)

        try:
            size = os.path.getsize(target)
            if size > self.ui_max_read_bytes:
                return self.result(f"file is too large to edit in the webui ({size} bytes)", success=False)

            with open(target, 'r', encoding="utf-8") as f:
                content = f.read()
        except UnicodeDecodeError:
            return self.result("this looks like a binary file and can't be edited here", success=False)
        except Exception as e:
            return self.result(str(e), success=False)

        return {"path": rel_path, "content": content, "read_only": bool(self.config.get("read-only"))}

    @webui.route("save", method="POST")
    async def _route_save(self, body=None, query=None):
        """writes the modal's content back to disk, gated by the same
        syntax check coder_file_edit uses. refuses in read-only mode."""
        if self.config.get("read-only"):
            return self.result("coder is in read-only mode", success=False)

        sandbox = (body or {}).get("sandbox", "")
        rel_path = (body or {}).get("path", "")
        content = (body or {}).get("content", "")

        if not sandbox or not rel_path:
            return self.result("sandbox and path are both required", success=False)

        try:
            target = await self._get_sandbox_subpath(sandbox, rel_path)
        except Exception as e:
            return self.result(str(e), success=False)

        syntax_errors = await self._check_syntax(content, target)
        if syntax_errors:
            return self.result({"errors": syntax_errors, "message": "Syntax errors detected! File was not written to disk."}, success=False)

        try:
            with open(target, 'w', encoding="utf-8") as f:
                f.write(content)
        except Exception as e:
            return self.result(str(e), success=False)

        return self.result(f"saved {rel_path}")

    @webui.route("lint", method="POST")
    async def _route_lint(self, body=None, query=None):
        """live syntax annotations for the webui editor: runs the same
        treesitter check that gates saves, but returns structured results
        and never touches the disk. languages treesitter can't check
        simply come back clean, same as the save gate treats them."""
        sandbox = (body or {}).get("sandbox", "")
        rel_path = (body or {}).get("path", "")
        content = (body or {}).get("content", "")

        if not sandbox or not rel_path:
            return self.result("sandbox and path are both required", success=False)

        try:
            target = await self._get_sandbox_subpath(sandbox, rel_path)
        except Exception as e:
            return self.result(str(e), success=False)

        lang = tslp.detect_language_from_path(target)
        if not lang or lang in ("vimdoc", "html", "htm"):
            return {"annotations": []}

        try:
            result = tslp.process(content, tslp.ProcessConfig(
                language=lang,
                diagnostics=True,
                structure=False,
            ))
        except Exception as e:
            return self.result(str(e), success=False)

        if not result:
            # empty file or failed to parse: stay quiet while typing,
            # the save gate is still the strict one
            return {"annotations": []}

        annotations = []
        for diag in (result.diagnostics or []):
            annotations.append({
                "line": int(diag.span.start_line) + 1,
                "col": int(diag.span.start_column) + 1,
                "end_line": int(diag.span.end_line) + 1,
                "end_col": int(diag.span.end_column) + 1,
                "message": str(diag.message),
            })

        return {"annotations": annotations}

    @webui.route("create", method="POST")
    async def _route_create(self, body=None, query=None):
        """creates an empty file or a folder (webui context menu). empty
        files always pass syntax, so no treesitter gate here."""
        if self.config.get("read-only"):
            return self.result("coder is in read-only mode", success=False)

        sandbox = (body or {}).get("sandbox", "")
        rel_path = (body or {}).get("path", "")
        is_dir = bool((body or {}).get("is_dir"))

        if not sandbox or not rel_path:
            return self.result("sandbox and path are both required", success=False)

        try:
            target = await self._get_sandbox_subpath(sandbox, rel_path)
        except Exception as e:
            return self.result(str(e), success=False)

        try:
            if is_dir:
                os.makedirs(target, exist_ok=False)
            else:
                # 'x' mode: fails if the file exists, no TOCTOU
                parent = os.path.dirname(target)
                if parent:
                    os.makedirs(parent, exist_ok=True)
                with open(target, 'x') as f:
                    f.write("")
        except Exception as e:
            return self.result(str(e), success=False)

        return self.result(f"created {rel_path}")

    @webui.route("move", method="POST")
    async def _route_move(self, body=None, query=None):
        """renames or moves an entry: src -> dst, both sandbox-relative.
        rename is just a move within the same parent."""
        if self.config.get("read-only"):
            return self.result("coder is in read-only mode", success=False)

        sandbox = (body or {}).get("sandbox", "")
        src = (body or {}).get("src", "")
        dst = (body or {}).get("dst", "")

        if not sandbox or not src or not dst:
            return self.result("sandbox, src and dst are all required", success=False)

        try:
            src_path = await self._get_sandbox_subpath(sandbox, src)
            dst_path = await self._get_sandbox_subpath(sandbox, dst)
        except Exception as e:
            return self.result(str(e), success=False)

        if os.path.exists(dst_path):
            return self.result(f"destination already exists: {dst}", success=False)

        try:
            parent = os.path.dirname(dst_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            shutil.move(src_path, dst_path)
        except Exception as e:
            return self.result(str(e), success=False)

        return self.result(f"moved {src} -> {dst}")

    @webui.route("delete", method="POST")
    async def _route_delete(self, body=None, query=None):
        """deletes a file, or a folder recursively. the webui confirms
        before calling this; the AI-facing tools stay stricter on purpose."""
        if self.config.get("read-only"):
            return self.result("coder is in read-only mode", success=False)

        sandbox = (body or {}).get("sandbox", "")
        rel_path = (body or {}).get("path", "")

        if not sandbox or not rel_path:
            return self.result("sandbox and path are both required", success=False)

        try:
            target = await self._get_sandbox_subpath(sandbox, rel_path)
        except Exception as e:
            return self.result(str(e), success=False)

        try:
            if os.path.isdir(target):
                shutil.rmtree(target)
            else:
                os.remove(target)
        except Exception as e:
            return self.result(str(e), success=False)

        return self.result(f"deleted {rel_path}")

    @webui.route("duplicate", method="POST")
    async def _route_duplicate(self, body=None, query=None):
        """copies a file or folder next to the original as 'name copy.ext'
        (numbered if taken)."""
        if self.config.get("read-only"):
            return self.result("coder is in read-only mode", success=False)

        sandbox = (body or {}).get("sandbox", "")
        rel_path = (body or {}).get("path", "")

        if not sandbox or not rel_path:
            return self.result("sandbox and path are both required", success=False)

        try:
            src = await self._get_sandbox_subpath(sandbox, rel_path)
        except Exception as e:
            return self.result(str(e), success=False)

        if not os.path.exists(src):
            return self.result(f"not found: {rel_path}", success=False)

        parent_rel = os.path.dirname(rel_path)
        base = os.path.basename(rel_path)

        if os.path.isdir(src):
            stem, ext = base, ""
        else:
            stem, ext = os.path.splitext(base)

        n = 1
        while True:
            suffix = " copy" if n == 1 else f" copy {n}"
            new_name = stem + suffix + ext
            candidate = os.path.join(os.path.dirname(src), new_name)
            if not os.path.exists(candidate):
                break
            n += 1

        try:
            if os.path.isdir(src):
                shutil.copytree(src, candidate)
            else:
                shutil.copy2(src, candidate)
        except Exception as e:
            return self.result(str(e), success=False)

        new_rel = (parent_rel + "/" if parent_rel else "") + new_name
        return self.result(f"duplicated to {new_rel}")

    # ----------------------------
    # webui routes: sandbox search
    # ----------------------------
    @webui.route("search", method="POST")
    async def _route_search(self, body=None, query=None):
        """recursive literal (or regex) text search across a sandbox.
        skips hidden/blacklisted folders and binary/huge files, like
        folder_grep does, but returns flat results for the sidebar UI."""
        sandbox = (body or {}).get("sandbox", "")
        needle = (body or {}).get("query", "")
        use_regex = bool((body or {}).get("regex"))
        max_matches = min(int((body or {}).get("max_matches") or 200), 500)

        if not sandbox or not needle:
            return self.result("sandbox and query are both required", success=False)

        try:
            root = await self._get_full_sandbox_path(sandbox)
        except Exception as e:
            return self.result(str(e), success=False)

        pattern = None
        if use_regex:
            try:
                pattern = regex.compile(needle, regex.IGNORECASE)
            except Exception as e:
                return self.result(f"invalid regex: {e}", success=False)

        blacklist = self.config.get("folder_blacklist") or []
        results = []
        truncated = False

        for (dirpath, dirnames, filenames) in os.walk(root):
            dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in blacklist]

            for fname in filenames:
                if fname.startswith("."):
                    continue

                fpath = os.path.join(dirpath, fname)
                try:
                    if os.path.getsize(fpath) > self.ui_max_read_bytes:
                        continue

                    with open(fpath, 'r', encoding="utf-8") as f:
                        for line_num, line in enumerate(f, 1):
                            if pattern:
                                try:
                                    hit = pattern.search(line, timeout=self.regex_timeout)
                                except TimeoutError:
                                    continue
                            else:
                                hit = needle.lower() in line.lower()

                            if hit:
                                results.append({
                                    "file": os.path.relpath(fpath, root).replace(os.sep, "/"),
                                    "line": line_num,
                                    "text": line.rstrip()[:300],
                                })
                                if len(results) >= max_matches:
                                    truncated = True
                                    break
                except (UnicodeDecodeError, IsADirectoryError, PermissionError, OSError):
                    continue

            if truncated:
                break

        return {"results": results, "truncated": truncated}

    # NOTE: the /files route lives up in the main webui-routes block
    # (_route_files, uncapped). there used to be a second, duplicate
    # _route_files here (3000-entry cap + truncated flag) left over from
    # scaffolding; python binds the LAST definition in a class body, so it
    # silently shadowed the real one. do not re-add one.

    # ---------------------
    # webui routes: git
    # ---------------------
    async def _run_git_bytes(self, sandbox_root: str, *args, timeout=15):
        """runs git, returns (returncode, raw stdout bytes). no text mode,
        no stripping - for output that must be parsed byte-exactly."""
        try:
            proc = subprocess.run(
                ["git", *args],
                cwd=sandbox_root,
                capture_output=True,
                timeout=timeout,
            )
        except FileNotFoundError:
            return 127, b"git executable not found"
        except subprocess.TimeoutExpired:
            return 124, b"git command timed out"
        except Exception as e:
            return 1, str(e).encode("utf-8", "replace")

        return proc.returncode, proc.stdout or b""

    def _parse_porcelain_z(self, raw: bytes):
        """parses `git status --porcelain=v1 -z` output from raw bytes.

        VERIFIED against real git output with od -c (2026-10-13): the
        separator is a BARE NUL, and every record is exactly
        'XY<sp>path' - including codes whose first char is a space (' M').
        (the space seen after each NUL in hexdumps IS that next record's
        status code; do not 'eat' it, and do not split on NUL+space.)

        renames/copies emit 'XY<sp>oldpath' followed by a separate field
        holding the new path.

        with -z, paths are never quoted and never mangled. returns a list
        of dicts: path / xy / staged / untracked."""

        def decode(data: bytes) -> str:
            return data.decode("utf-8", "replace").replace(os.sep, "/")

        fields = raw.split(b"\x00")

        entries = []
        idx = 0
        while idx < len(fields):
            field = fields[idx]
            idx += 1

            if not field:
                # empty piece after the trailing NUL
                continue

            if len(field) < 3 or field[2:3] != b" ":
                # not 'XY path' - malformed for us, skip rather than guess
                continue

            x = chr(field[0])
            y = chr(field[1])
            path = decode(field[3:])

            if x in ("R", "C") or y in ("R", "C"):
                # next field is the NEW path (kept); consume it either way
                if idx < len(fields):
                    newp = fields[idx]
                    idx += 1
                    if newp:
                        path = decode(newp)

            entries.append({
                "path": path,
                "xy": x + y,
                "staged": x not in (" ", "?"),
                "untracked": x == "?" and y == "?",
            })

        return entries

    async def _run_git(self, sandbox_root: str, *args, accept=(0,), timeout=15):
        """runs git in the sandbox root. returns (ok, output).
        accept lists return codes that count as success."""
        try:
            proc = subprocess.run(
                ["git", *args],
                cwd=sandbox_root,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except FileNotFoundError:
            return False, "git executable not found"
        except subprocess.TimeoutExpired:
            return False, "git command timed out"
        except Exception as e:
            return False, str(e)

        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()

        if proc.returncode not in accept:
            return False, (err or out or f"git {args[0] if args else ''} failed (code {proc.returncode})")

        return True, (out or err)

    async def _git_root(self, sandbox: str, subpath: str = ""):
        """resolves sandbox + optional subpath (sandbox-relative) into the
        folder git should run in. lets git work on repos nested inside a
        sandbox, e.g. 'openlumara_dev' within the 'dev' sandbox."""
        full = await self._get_full_sandbox_path(sandbox)
        if not subpath:
            return full
        return core.sandbox_path(full, subpath)

    def _check_git_paths(self, root: str, paths: list):
        """ensures repo-relative paths passed to git resolve inside the
        sandbox. without a subpath the repo root IS the sandbox root, so
        this only bites for repos nested inside a sandbox."""
        sandbox_root = os.path.dirname(root)
        for p in paths:
            full = os.path.normpath(os.path.join(root, p))
            if full != sandbox_root and not full.startswith(sandbox_root + os.sep):
                raise Exception(f"path escapes the sandbox: {p}")

    @webui.route("git_repos")
    async def _route_git_repos(self, body=None, query=None):
        """lists git repositories inside a sandbox: the sandbox root itself
        if it is one, plus nested repos up to 4 folder levels deep. once a
        repo is found its subtree is skipped, so the list stays shallow."""
        sandbox = (query or {}).get("sandbox", "")

        if not sandbox:
            return self.result("no sandbox given", success=False)

        try:
            root = await self._get_full_sandbox_path(sandbox)
        except Exception as e:
            return self.result(str(e), success=False)

        blacklist = self.config.get("folder_blacklist") or []
        max_depth = 6
        max_repos = 50

        repos = []

        def is_repo(path):
            return os.path.isdir(os.path.join(path, ".git")) or os.path.isfile(os.path.join(path, ".git"))

        if is_repo(root):
            repos.append("")

        for (dirpath, dirnames, filenames) in os.walk(root):
            rel = os.path.relpath(dirpath, root).replace(os.sep, "/")
            depth = 0 if rel == "." else len(rel.split("/"))

            # prune hidden + blacklisted folders, and anything too deep
            dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in blacklist and depth + 1 <= max_depth]

            if depth == 0 or depth > max_depth:
                continue

            if is_repo(dirpath):
                repos.append(rel)
                dirnames[:] = []  # skip the repo's own subtree
                if len(repos) >= max_repos:
                    break

        return {"repos": repos}

    @webui.route("git_status")
    async def _route_git_status(self, body=None, query=None):
        sandbox = (query or {}).get("sandbox", "")
        subpath = (query or {}).get("subpath", "")

        if not sandbox:
            return self.result("no sandbox given", success=False)

        try:
            root = await self._git_root(sandbox, subpath)
        except Exception as e:
            return self.result(str(e), success=False)

        ok, _ = await self._run_git(root, "rev-parse", "--is-inside-work-tree")
        if not ok:
            return {"is_repo": False, "read_only": bool(self.config.get("read-only"))}

        _, branch = await self._run_git(root, "rev-parse", "--abbrev-ref", "HEAD")

        ok_b, b_out = await self._run_git(root, "branch", "--format=%(refname:short)")
        branches = [b.strip() for b in b_out.split("\n") if b.strip()] if ok_b else []

        # nul-delimited porcelain, parsed from raw bytes (no text mode,
        # no stripping) by a dedicated parser with explicit separator
        # handling. see _parse_porcelain_z for the exact byte format.
        rc_s, raw_s = await self._run_git_bytes(root, "status", "--porcelain=v1", "-z")
        changes = self._parse_porcelain_z(raw_s) if rc_s == 0 else []

        return {
            "is_repo": True,
            "branch": branch,
            "branches": branches,
            "changes": changes,
            "read_only": bool(self.config.get("read-only")),
        }

    @webui.route("git_stage", method="POST")
    async def _route_git_stage(self, body=None, query=None):
        if self.config.get("read-only"):
            return self.result("coder is in read-only mode", success=False)

        sandbox = (body or {}).get("sandbox", "")
        subpath = (body or {}).get("subpath", "")
        paths = (body or {}).get("paths", [])

        if not sandbox or not paths:
            return self.result("sandbox and paths are both required", success=False)

        try:
            root = await self._git_root(sandbox, subpath)
            self._check_git_paths(root, paths)
            abs_paths = [os.path.normpath(os.path.join(root, p)) for p in paths]
        except Exception as e:
            return self.result(str(e), success=False)

        ok, out = await self._run_git(root, "add", "--", *abs_paths)
        if not ok:
            return self.result(out, success=False)

        return self.result("staged")

    @webui.route("git_unstage", method="POST")
    async def _route_git_unstage(self, body=None, query=None):
        if self.config.get("read-only"):
            return self.result("coder is in read-only mode", success=False)

        sandbox = (body or {}).get("sandbox", "")
        subpath = (body or {}).get("subpath", "")
        paths = (body or {}).get("paths", [])

        if not sandbox or not paths:
            return self.result("sandbox and paths are both required", success=False)

        try:
            root = await self._git_root(sandbox, subpath)
            self._check_git_paths(root, paths)
            abs_paths = [os.path.normpath(os.path.join(root, p)) for p in paths]
        except Exception as e:
            return self.result(str(e), success=False)

        ok, out = await self._run_git(root, "restore", "--staged", "--", *abs_paths)
        if not ok:
            return self.result(out, success=False)

        return self.result("unstaged")

    @webui.route("git_commit", method="POST")
    async def _route_git_commit(self, body=None, query=None):
        if self.config.get("read-only"):
            return self.result("coder is in read-only mode", success=False)

        sandbox = (body or {}).get("sandbox", "")
        subpath = (body or {}).get("subpath", "")
        message = (body or {}).get("message", "").strip()

        if not sandbox or not message:
            return self.result("sandbox and message are both required", success=False)

        try:
            root = await self._git_root(sandbox, subpath)
        except Exception as e:
            return self.result(str(e), success=False)

        ok, out = await self._run_git(root, "commit", "-m", message)
        if not ok:
            return self.result(out, success=False)

        return self.result(out)

    @webui.route("git_branch", method="POST")
    async def _route_git_branch(self, body=None, query=None):
        if self.config.get("read-only"):
            return self.result("coder is in read-only mode", success=False)

        sandbox = (body or {}).get("sandbox", "")
        subpath = (body or {}).get("subpath", "")
        name = (body or {}).get("name", "").strip()

        if not sandbox or not name:
            return self.result("sandbox and name are both required", success=False)

        try:
            root = await self._git_root(sandbox, subpath)
        except Exception as e:
            return self.result(str(e), success=False)

        ok, out = await self._run_git(root, "switch", name)
        if not ok:
            return self.result(out, success=False)

        return self.result(out or f"switched to {name}")

    @webui.route("git_ahead")
    async def _route_git_ahead(self, body=None, query=None):
        """what a push would send: the unpushed commits, the target ref and
        the warnings (behind/diverged, dirty tree). the push confirmation
        modal is built entirely from this payload."""
        sandbox = (query or {}).get("sandbox", "")
        subpath = (query or {}).get("subpath", "")

        if not sandbox:
            return self.result("no sandbox given", success=False)

        try:
            root = await self._git_root(sandbox, subpath)
        except Exception as e:
            return self.result(str(e), success=False)

        ok, branch = await self._run_git(root, "rev-parse", "--abbrev-ref", "HEAD")
        if not ok:
            return self.result(branch, success=False)
        if branch == "HEAD":
            return self.result("detached HEAD: switch to a branch before pushing", success=False)

        ok, out = await self._run_git(root, "remote")
        remotes = out.split() if ok else []
        if not remotes:
            return self.result("this repo has no remotes, nowhere to push to", success=False)
        remote = "origin" if "origin" in remotes else remotes[0]

        ok, upstream = await self._run_git(root, "rev-parse", "--abbrev-ref", "@{u}")
        upstream = upstream.strip() if ok else ""
        has_upstream = "/" in upstream

        if has_upstream:
            target = upstream
            # NOTE: _run_git_bytes returns (returncode, raw) NOT (ok, out) -
            # check rc != 0, never `if not ok` (0 means success!).
            rc, raw = await self._run_git_bytes(
                root, "log", "--pretty=%h%x09%s", f"{upstream}..HEAD", "-n100"
            )
        else:
            # brand new branch: commits that exist on no remote at all
            target = f"{remote}/{branch}"
            rc, raw = await self._run_git_bytes(
                root, "log", "--pretty=%h%x09%s", "HEAD", "--not", "--remotes", "-n100"
            )

        if rc != 0:
            return self.result(raw.decode("utf-8", "replace").strip() or "git log failed", success=False)

        ahead = []
        for line in raw.decode("utf-8", "replace").splitlines():
            if not line.strip():
                continue
            if "\t" in line:
                h, msg = line.split("\t", 1)
            else:
                h, msg = line, ""
            ahead.append({"hash": h.strip(), "msg": msg})

        behind = 0
        if has_upstream:
            ok, out = await self._run_git(root, "rev-list", "--count", f"HEAD..{upstream}")
            if ok and out.strip().isdigit():
                behind = int(out.strip())

        _, raw = await self._run_git_bytes(root, "status", "--porcelain=v1")
        dirty = bool(raw.strip())

        return {
            "branch": branch,
            "remote": remote,
            "upstream": upstream,
            "has_upstream": has_upstream,
            "target": target,
            "ahead": ahead,
            "behind": behind,
            "dirty": dirty,
        }

    @webui.route("git_push", method="POST")
    async def _route_git_push(self, body=None, query=None):
        if self.config.get("read-only"):
            return self.result("coder is in read-only mode", success=False)

        sandbox = (body or {}).get("sandbox", "")
        subpath = (body or {}).get("subpath", "")

        if not sandbox:
            return self.result("no sandbox given", success=False)

        try:
            root = await self._git_root(sandbox, subpath)
        except Exception as e:
            return self.result(str(e), success=False)

        # everything is re-checked server side: the modal's confirmation
        # button is human intent, not a security boundary.
        ok, branch = await self._run_git(root, "rev-parse", "--abbrev-ref", "HEAD")
        if not ok or branch == "HEAD":
            return self.result("detached HEAD: switch to a branch before pushing", success=False)

        ok, out = await self._run_git(root, "remote")
        remotes = out.split() if ok else []
        if not remotes:
            return self.result("this repo has no remotes, nowhere to push to", success=False)
        remote = "origin" if "origin" in remotes else remotes[0]

        ok, upstream = await self._run_git(root, "rev-parse", "--abbrev-ref", "@{u}")
        upstream = upstream.strip() if ok else ""

        # explicit refspec so a weird push.default config can never widen
        # the push to other branches. never --force: without it git itself
        # rejects anything that isn't a fast-forward.
        if "/" in upstream:
            up_remote, _, up_branch = upstream.partition("/")
            args = ["push", up_remote, f"{branch}:{up_branch}"]
        else:
            args = ["push", "-u", remote, branch]

        # pushes can be slow on big repos or bad connections
        rc, raw = await self._run_git_bytes(root, *args, timeout=180)
        out = raw.decode("utf-8", "replace").strip()
        if rc != 0:
            return self.result(out or "git push failed", success=False)

        return self.result(out or "pushed")

    @webui.route("git_log")
    async def _route_git_log(self, body=None, query=None):
        sandbox = (query or {}).get("sandbox", "")
        subpath = (query or {}).get("subpath", "")
        limit = min(int((query or {}).get("n", 20)), 100)

        if not sandbox:
            return self.result("no sandbox given", success=False)

        try:
            root = await self._git_root(sandbox, subpath)
        except Exception as e:
            return self.result(str(e), success=False)

        # %x09 = literal tab: hash and subject are split on the one
        # character a short hash can never contain. parsed from raw bytes.
        rc, raw = await self._run_git_bytes(
            root, "log", f"--pretty=%h%x09%s", f"-n{limit}"
        )
        if rc != 0:
            return self.result(raw.decode("utf-8", "replace").strip() or "git log failed", success=False)

        entries = []
        for line in raw.decode("utf-8", "replace").splitlines():
            if not line.strip():
                continue
            if "\t" in line:
                h, msg = line.split("\t", 1)
            else:
                h, msg = line, ""
            entries.append({"hash": h.strip(), "msg": msg})

        return {"log": entries}

    @webui.route("git_diff")
    async def _route_git_diff(self, body=None, query=None):
        sandbox = (query or {}).get("sandbox", "")
        subpath = (query or {}).get("subpath", "")
        rel_path = (query or {}).get("path", "")
        staged = (query or {}).get("staged", "") in ("1", "true")
        untracked = (query or {}).get("untracked", "") in ("1", "true")

        if not sandbox or not rel_path:
            return self.result("sandbox and path are both required", success=False)

        try:
            root = await self._git_root(sandbox, subpath)
            self._check_git_paths(root, [rel_path])
        except Exception as e:
            return self.result(str(e), success=False)

        # absolute pathspec: git resolves relative ones against the cwd,
        # which only matches the repo-root-relative porcelain paths when
        # the repo happens to BE the sandbox root. absolute works from any
        # cwd, so nested repos stage/unstage/diff the right file.
        abs_path = os.path.normpath(os.path.join(root, rel_path))

        if untracked:
            # no-index exits 1 when there IS a diff: accept both codes
            rc, raw = await self._run_git_bytes(
                root, "diff", "--no-index", "--", os.devnull, abs_path
            )
            ok = rc in (0, 1)
        elif staged:
            rc, raw = await self._run_git_bytes(root, "diff", "--staged", "--", abs_path)
            ok = rc == 0
        else:
            rc, raw = await self._run_git_bytes(root, "diff", "--", abs_path)
            ok = rc == 0

        if not ok:
            return self.result(raw.decode("utf-8", "replace").strip() or f"git diff failed (code {rc})", success=False)

        text = raw.decode("utf-8", "replace")
        return {"diff": text if text.strip() else "(no changes)"}
