import asyncio
import time
import ulid
import core
import channels.webui.api as webui

class AskUser(core.module.Module):
    """
    Enables human-in-the-loop interaction.
    Allows the AI to pause and ask the user questions, request approval,
    or seek clarifications during tool-calling operations.
    """

    category = "utilities"

    settings = {
        "default_timeout": {
            "type": "number",
            "default": 120,
            "description": "Default timeout in seconds to wait for a user response before failing the tool call."
        },
        "alert_channel": {
            "type": "boolean",
            "default": True,
            "description": "Whether to push an alert message into the current chat channel when a question is asked."
        },
        "intercept_chat_input": {
            "type": "boolean",
            "default": True,
            "description": "When a question is pending, allow the user to reply simply by sending a normal chat message without needing to type /answer."
        }
    }

    dependencies = []

    async def on_ready(self):
        """Initialize in-memory map of pending questions."""
        self._pending = {}

    async def on_shutdown(self):
        """Cancel any hanging futures on framework shutdown or reload."""
        for item in list(self._pending.values()):
            fut = item.get("future")
            if fut and not fut.done():
                fut.cancel()
        self._pending.clear()

    # -------------------------------------------------------------------------
    # AI Tools
    # -------------------------------------------------------------------------

    @core.module.tool
    async def ask(self, question: str, options: list = None, timeout: int = 0, default_choice: str = None, secret: bool = False):
        """
        Asks the user a question and pauses execution until the user responds or times out.
        Use this whenever you need clarification, a decision, additional input, or approval.

        Args:
            question: The question or prompt to present to the user.
            options: Optional list of acceptable string choices (e.g. ["yes", "no"] or ["retry", "skip", "abort"]).
            timeout: Maximum seconds to wait for a response (0 uses the module's default timeout setting).
            default_choice: Optional fallback value to automatically use if the user times out instead of failing.
            secret: If True, masks user input in the UI (useful for passwords, API keys, credentials).
        """
        if not question or not str(question).strip():
            return self.result("Question cannot be empty.", success=False)

        clean_options = [str(opt).strip() for opt in options] if isinstance(options, list) else []
        t_limit = timeout if timeout and timeout > 0 else int(self.config.get("default_timeout") or 120)

        # Clamp against system tool timeout if applicable to avoid framework hard-kills
        sys_timeout = core.config.get("core", "tool_timeout", default=30.0)
        clamped_by_system = False
        try:
            sys_timeout_f = float(sys_timeout)
            if sys_timeout_f > 5 and t_limit > sys_timeout_f:
                # Give a 2 second safety margin before core tool_timeout kicks in
                t_limit = max(5, int(sys_timeout_f - 2))
                clamped_by_system = True
        except (ValueError, TypeError):
            pass

        qid = f"q_{str(ulid.ULID()).lower()}"
        loop = asyncio.get_running_loop()
        future = loop.create_future()

        record = {
            "id": qid,
            "question": str(question).strip(),
            "options": clean_options,
            "future": future,
            "created_at": time.time(),
            "timeout": t_limit,
            "default_choice": str(default_choice).strip() if default_choice is not None else None,
            "secret": bool(secret),
            "chat_id": self._current_chat_id(),
        }
        self._pending[qid] = record

        # Alert the user across the active channel
        if (self.config.get("alert_channel") is not False) and self.channel:
            opts_hint = f"\n**Choices**: {', '.join(clean_options)}" if clean_options else ""
            try:
                await self.channel.push(
                    f"❓ **Question from AI**:\n{record['question']}{opts_hint}\n\n"
                    f"*Answer in the prompt popup or reply with `/answer <your reply>` in chat.*",
                    defer=False,
                    # display immediately, but don't inject an assistant message
                    # into the middle of the in-flight tool call chain
                    add_to_context=False
                )
            except Exception as e:
                self.log("ask_user", f"Could not push question alert to channel: {e}")

        # Await user answer
        try:
            answer = await asyncio.wait_for(future, timeout=float(t_limit))
            return self.result({
                "answered": True,
                "answer": answer,
                "question": record["question"]
            }, success=True)
        except asyncio.TimeoutError:
            if default_choice is not None:
                return self.result({
                    "answered": False,
                    "answer": str(default_choice).strip(),
                    "timed_out": True,
                    "used_default": True,
                    "note": f"User did not answer within {t_limit}s; auto-selected default choice: '{default_choice}'"
                }, success=True)
            hint = f" (clamped by core.tool_timeout={sys_timeout}s; increase tool_timeout in settings if you need more time)" if clamped_by_system else ""
            return self.result({
                "answered": False,
                "answer": None,
                "error": f"User did not answer within {t_limit} seconds{hint}. You may proceed with your best judgment or ask again.",
                "timed_out": True
            }, success=False)
        except asyncio.CancelledError:
            return self.result({
                "answered": False,
                "answer": None,
                "error": "The question was cancelled before an answer was received.",
                "cancelled": True
            }, success=False)
        finally:
            self._pending.pop(qid, None)

    @core.module.tool
    async def confirm(self, action: str, details: str = "", timeout: int = 60, default_choice: str = "no"):
        """
        Asks the user for a simple yes/no confirmation before executing a potentially destructive or irreversible action.

        Args:
            action: The action that requires confirmation (e.g. "Delete database backup", "Overwrite config.yaml").
            details: Optional additional details or context explaining why confirmation is needed.
            timeout: Maximum seconds to wait for confirmation (default 60).
            default_choice: Action fallback if timeout expires ('no' by default for safety).
        """
        prompt = f"Please confirm: {action}."
        if details:
            prompt += f" Details: {details}"

        res = await self.ask(question=prompt, options=["yes", "no"], timeout=timeout, default_choice=default_choice)
        content = res.get("content") or {}
        if res.get("status") != "success":
            return self.result({
                "confirmed": False,
                "answer": content.get("answer"),
                "action": action,
                "error": content.get("error") or "Confirmation failed or was cancelled."
            }, success=False)

        answer = str(content.get("answer") or "").strip().lower()
        confirmed = content.get("answered") is True and answer in ("yes", "y", "true", "confirm", "proceed", "ok", "sure")
        return self.result({
            "confirmed": confirmed,
            "answer": content.get("answer"),
            "timed_out": bool(content.get("timed_out")),
            "action": action
        }, success=True)

    # -------------------------------------------------------------------------
    # Internal Answer Resolution
    # -------------------------------------------------------------------------

    def _current_chat_id(self):
        try:
            if self.channel and getattr(self.channel, "context", None):
                return self.channel.context.chat.get("id")
        except Exception:
            pass
        return None

    def _try_intercept_chat_answer(self, message: str, chat_id: str = None):
        """Resolve the pending question from a normal chat message or /answer.

        Called by channels *before* they cancel/restart an active stream, so
        answering a question doesn't kill the paused agent turn.

        Returns the answer text that was delivered, or None.
        """
        if not self.config.get("intercept_chat_input", True):
            return None
        if not self._pending:
            return None

        text = str(message).strip()
        answer = text
        cmd_prefix = core.config.get("core", "cmd_prefix", default="/")
        if text.startswith(cmd_prefix):
            parts = text[len(cmd_prefix):].split(maxsplit=1)
            if len(parts) < 2 or parts[0].lower() != "answer":
                return None
            answer = parts[1].strip()

        if not answer:
            return None

        ok = self._resolve_answer("", answer, chat_id=chat_id or self._current_chat_id())
        return answer if ok else None

    def _resolve_answer(self, qid: str, answer: str, chat_id: str = None) -> bool:
        """Resolve a pending question by ID, or the oldest pending question (FIFO) if qid is empty."""
        target = None
        if qid and qid in self._pending:
            target = self._pending[qid]
        elif not qid and self._pending:
            # Pick the oldest pending question (FIFO order)
            candidates = [
                q for q in self._pending.values()
                if not chat_id or not q.get("chat_id") or q.get("chat_id") == chat_id
            ]
            target = candidates[0] if candidates else None

        if not target:
            return False

        # don't let a client in another chat answer this question
        if chat_id and target.get("chat_id") and target["chat_id"] != chat_id:
            return False

        fut = target.get("future")
        if fut and not fut.done():
            fut.set_result(str(answer).strip())
            return True
        return False

    async def on_user_message(self, content: str):
        """Allows the user to answer pending questions directly by typing into chat."""
        if not self.config.get("intercept_chat_input", True):
            return None
        if not self._pending:
            return None

        # Do not intercept commands
        cmd_prefix = core.config.get("core", "cmd_prefix", default="/")
        if str(content).strip().startswith(cmd_prefix):
            return None

        # Resolve pending question with message content
        ok = self._resolve_answer("", content, chat_id=self._current_chat_id())
        if ok:
            # Intercept: records user message in history and avoids spawning a second turn
            return False
        return None

    # -------------------------------------------------------------------------
    # WebUI API Routes (/api/ext/ask_user/...)
    # -------------------------------------------------------------------------

    @webui.route("pending")
    async def _route_pending(self, body=None, query=None):
        """Returns currently pending questions waiting for user answer."""
        now = time.time()
        chat_id = self._current_chat_id()
        results = []
        for q in self._pending.values():
            if chat_id and q.get("chat_id") and q["chat_id"] != chat_id:
                continue
            elapsed = now - q["created_at"]
            remaining = max(0, int(q["timeout"] - elapsed))
            results.append({
                "id": q["id"],
                "question": q["question"],
                "options": q["options"],
                "remaining_seconds": remaining,
                "timeout": q["timeout"],
                "default_choice": q.get("default_choice"),
                "secret": q.get("secret", False)
            })
        return {"pending": results}

    @webui.route("respond", method="POST")
    async def _route_respond(self, body=None, query=None):
        """Submit an answer to a pending question."""
        body = body or {}
        qid = str(body.get("id", "")).strip()
        answer = str(body.get("answer", "")).strip()

        if not answer:
            return self.result("Answer cannot be empty.", success=False)

        ok = self._resolve_answer(qid, answer, chat_id=self._current_chat_id())
        if ok:
            return self.result({"message": "Answer submitted successfully.", "answer": answer}, success=True)
        return self.result("No active question matching that ID.", success=False)

    @webui.route("cancel", method="POST")
    async def _route_cancel(self, body=None, query=None):
        """Cancel a pending question."""
        body = body or {}
        qid = str(body.get("id", "")).strip()
        chat_id = self._current_chat_id()
        record = self._pending.get(qid)
        if record and chat_id and record.get("chat_id") and record["chat_id"] != chat_id:
            return self.result("No active question matching that ID.", success=False)
        if record:
            fut = record.get("future")
            if fut and not fut.done():
                fut.cancel()
            self._pending.pop(qid, None)
            return self.result("Question cancelled.", success=True)
        return self.result("Question not found.", success=False)

    # -------------------------------------------------------------------------
    # User Command (/answer)
    # -------------------------------------------------------------------------

    @core.module.command("answer", help={
        "<reply>": "Submit an answer to the pending question asked by the AI"
    })
    async def answer_command(self, args: list):
        """Allows answering the pending question from any channel via `/answer <reply>`."""
        if not args:
            if not self._pending:
                return "There are no pending questions waiting for an answer."
            latest = list(self._pending.values())[-1]
            opts = f" (Options: {', '.join(latest['options'])})" if latest['options'] else ""
            return f"Pending question: {latest['question']}{opts}\nReply with `/answer <your reply>`."

        reply = " ".join(args).strip()
        if not self._pending:
            return "No pending question was found. The question may have already timed out or been answered."

        ok = self._resolve_answer("", reply)
        if ok:
            return f"Answer submitted: '{reply}'"
        return "Could not submit answer to the pending question."
