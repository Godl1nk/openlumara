import asyncio
import hashlib
import json
import json_repair
import re

import partial_json_parser

# -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01)
# parse streamed tool-call arguments with partial_json_parser (same
# approach as core/channel.py): the backend parses what it can at every
# yield point and stamps `args_parsed` onto each tool call, so channels
# only ever render a plain object. a `_raw` fallback mirrors the old
# frontend behaviour for non-JSON argument blobs.

def parse_lenient_json(raw):
    """parse a (possibly incomplete) JSON object string into a plain dict.
    never raises: falls back to {'_raw': text} for non-JSON input."""
    if not isinstance(raw, str) or not raw.strip():
        return {}
    try:
        parsed = partial_json_parser.loads(raw, allow_partial=partial_json_parser.Allow.ALL)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    return {"_raw": raw}


def turn_hash(turn):
    """stable content hash for a grouped turn. channels can reuse their
    existing turn object when the hash is unchanged instead of deep-diffing
    every message on every history reload."""
    parts = []
    for message in turn.get("messages", []):
        # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-13)
        # display annotations live under the tool call's _metadata key
        calls = ",".join(
            f"{tc.get('id')}:{(tc.get('_metadata') or {}).get('response')}"
            for tc in (message.get("tool_calls") or [])
        )
        parts.append("|".join([
            str(message.get("index")),
            str(message.get("role")),
            str(message.get("content")),
            str(message.get("reasoning_content")),
            str((message.get("_metadata") or {}).get("is_cmd")),
            calls,
        ]))
    payload = "\n".join(parts).encode("utf-8")
    return hashlib.md5(payload).hexdigest()


class TurnCollector:
    """
    this takes a raw openAI messages array and turns it into a grouped list of dicts,
    where a "turn" is a group of any assistant/tool messages inbetween a user's request

    so basically, a user makes their request, then the response gets grouped into one single object
    that contains multiple messages, grouped by type (reasoning, content, toolcall, etc)

    this works for chat history (group_history) and even for streams (group_stream)

    this is a port from the old webui's frontend-only turn collection logic
    now available in the core for any channel to use :)
    """

    async def group_history(self, history):
        """
        Groups all finalized messages from history into turns.
        Returns a list of turn objects.
        """
        turns = []
        current_assistant_turn = None

        for index, msg in enumerate(history):
            # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-13)
            # copy the message before stamping anything onto it: turns hold
            # references to the stored chat messages, and in-place annotations
            # (index, and the tool call annotations further down) rewrote chat
            # storage, which changed already-sent context and invalidated the
            # provider-side prompt cache on the next build.
            msg = dict(msg)

            role = msg.get('role')

            # add the index to the message so that it can be directly targeted no matter which turn it is in
            msg["index"] = index
            
            if role == 'user':
                if current_assistant_turn:
                    # if a user message arrives and it's currently still
                    # the assistant's turn, that means we finalize it, and move onto a new turn!
                    turns.append(current_assistant_turn)
                    current_assistant_turn = None
                
                # append the user message as a single turn. a user message is never multiple turns
                turns.append({
                    "role": "user",
                    "messages": [msg.copy()],
                    "first_message_index": index
                })
            else:
                # create the assistant turn if it doesn't already exist
                if not current_assistant_turn:
                    current_assistant_turn = {
                        "role": "assistant",
                        "first_message_index": index,
                        "messages": []
                    }

                # update the last message index.. since this is a for loop,
                # by the time we reach the last message, this will be set to the last message index
                current_assistant_turn["last_message_index"] = index
                    
                current_assistant_turn["messages"].append(msg)

        if current_assistant_turn:
            turns.append(current_assistant_turn)

        # merge tool responses into their tool calls
        for turn in turns:
            if turn["role"] != 'assistant':
                continue
            
            response_map = {}
            for msg in turn["messages"]:
                if msg.get("role") == 'tool':
                    response_map[msg["tool_call_id"]] = msg.get("content")

            for msg in turn["messages"]:
                if msg.get("tool_calls"):
                    # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-13)
                    # rebuild the tool_calls list with copies of each call: the
                    # original dicts are shared with chat storage (shallow copies
                    # all the way down), so annotating in place rewrote stored
                    # history and invalidated the provider-side prompt cache.
                    annotated_tools = []
                    for tool in msg["tool_calls"]:
                        tool = dict(tool)
                        # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-13)
                        # all display annotations go under _metadata (mirroring
                        # the message-level convention). context.get() strips
                        # _metadata off tool calls before the API call, so even
                        # a leaked copy can never bloat requests or invalidate
                        # the provider-side prompt cache.
                        meta = {}
                        tool["_metadata"] = meta
                        if tool.get("id") in response_map:
                            meta["response"] = response_map[tool["id"]]
                        # precompute the failed flag so channels don't
                        # re-parse every response just to tint a card
                        meta["failed"] = self._tool_call_failed(tool)
                        # ... and the parsed arguments (plus the one-line arg
                        # summary for headers). tools_call proxies are unwrapped
                        # so the card shows the proxied call, not the wrapper.
                        raw_args = (tool.get("function") or {}).get("arguments")
                        parsed_args = parse_lenient_json(raw_args)
                        bridge_name, bridge_args = self._bridge_from_args(
                            (tool.get("function") or {}).get("name"), parsed_args, raw_args
                        )
                        if bridge_name is not None or bridge_args is not None:
                            meta["bridge"] = True
                            if bridge_name:
                                meta["display_name"] = bridge_name
                            meta["args_parsed"] = bridge_args if bridge_args is not None else {}
                            meta["summary"] = self._summary_from_args(meta["args_parsed"])
                        else:
                            meta["args_parsed"] = parsed_args
                            meta["summary"] = self._tool_call_summary(tool)
                        annotated_tools.append(tool)
                    msg["tool_calls"] = annotated_tools

        # -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01)
        # stamp a content hash per turn so channels can keep their existing
        # turn objects (and their render caches) on reloads by comparing
        # one string instead of deep-diffing every message.
        for turn in turns:
            turn["hash"] = turn_hash(turn)

        # -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01)
        # fold each assistant turn's chain into display steps so channels
        # don't re-derive the agentic-step grouping themselves.
        for turn in turns:
            if turn["role"] != "assistant":
                continue
            steps, final_messages = self.build_steps(turn["messages"])
            turn["steps"] = steps
            turn["final_messages"] = final_messages

        return turns

    # -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01)
    # -- step model: ports of the webui frontend's chainDisplay()/
    # -- historyTurnSplit() grouping. a step = one reasoning/content run
    # -- plus the tool calls it leads to (or a tool-less thinking-only step).
    # -- steps carry precomputed "modules" display data so templates only
    # -- need to render, never to group.

    @staticmethod
    def _tool_call_failed(tool):
        # a tool call failed when its parsed response is {status: "error"}
        # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-13)
        # response lives under the call's _metadata key
        response = (tool.get("_metadata") or {}).get("response")
        if response is None:
            return False
        try:
            parsed = json.loads(response) if isinstance(response, str) else response
        except (json.JSONDecodeError, TypeError):
            return False
        return isinstance(parsed, dict) and parsed.get("status") == "error"

    # -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01)
    # one-line arg summary for completed tool call headers, ported from
    # the webui frontend's toolCallArgsSummary(): the single most
    # informative argument value, paths keep their tail.
    TOOL_ARG_PRIORITY = [
        "path", "file_path", "filepath", "file", "filename", "url",
        "query", "pattern", "regex_pattern", "sub_path", "subfolder",
        "folder", "id", "name", "content", "text",
    ]

    @staticmethod
    def _truncate_arg(s):
        if len(s) <= 70:
            return s
        if "/" in s or "\\" in s:
            return ".." + s[-68:]
        return s[:69].rstrip() + ".."

    @staticmethod
    def _arg_to_string(value):
        if isinstance(value, str):
            return value
        if isinstance(value, (dict, list)):
            try:
                return json.dumps(value)
            except (TypeError, ValueError):
                return str(value)
        if value is None:
            return "null"
        if value is True:
            return "true"
        if value is False:
            return "false"
        return str(value)

    # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-21) harness:openlumara
    # tools_call (and friends) proxy the real call as {name, params}.
    # display-wise we unwrap that: the card shows the proxied call's name
    # and arguments, never the wrapper. unwrap results live under the call's
    # _metadata (display_name + swapped args_parsed), so requests and stored
    # history are untouched.
    BRIDGE_TOOLS = ("tools_call",)

    @classmethod
    def _bridge_from_args(cls, tool_name, wrapper_args, raw=""):
        """Extract whatever is confidently known from a bridge tool's (possibly
        partial) wrapper args: (display_name_or_None, inner_args_or_None).

        Both None means "not a recognisable bridge call yet" -> render raw.
        Order-agnostic: models may stream {"arguments": {...}, "name": ...},
        and the inner args must already display while the name is still
        pending, or long arguments never appear to stream at all.
        """
        if tool_name not in cls.BRIDGE_TOOLS or not isinstance(wrapper_args, dict):
            return None, None

        # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-21) harness:openlumara
        # trust the name only once it is terminated in the raw stream: the
        # JSON is complete (history / final delta) or the value is closed by
        # its own quote ("name": "foo"). the old "a sibling key parsed beside
        # it" heuristic was order-dependent: with arguments-before-name the
        # completed arguments sibling let the still-growing name value
        # ("c" -> "co" -> ...) through, flickering the header and registry
        # match during the last ~1% of the stream.
        name = wrapper_args.get("name")
        name = name.strip() if isinstance(name, str) and name.strip() else None

        # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-22) harness:openlumara
        # partial_json_parser can choke on wrapper payloads dominated by one
        # huge escaped string (the string-typed params transport): the lenient
        # parse degrades to {_raw: ...} and the name - even though it completed
        # long ago - never surfaces, so _bridge_from_args returns (None, None)
        # and the card stays the raw tools_call wrapper for the whole live turn
        # (custom views match the UNWRAPPED name only; it fixes itself on the
        # next history reload, which is why this looked intermittent).
        # json_repair reads those payloads fine, so retry with it whenever the
        # lenient wrapper parse yielded no usable name. The termination check
        # below still gates still-growing values, so headers never flicker.
        if name is None and raw:
            try:
                repaired_wrapper = json_repair.loads(raw)
            except Exception:
                repaired_wrapper = None
            if isinstance(repaired_wrapper, dict) and repaired_wrapper:
                wrapper_args = repaired_wrapper
                name = wrapper_args.get("name")
                name = name.strip() if isinstance(name, str) and name.strip() else None

        if name is not None:
            complete = False
            if raw:
                if len(raw) < 512:
                    try:
                        json.loads(raw)
                        complete = True
                    except (ValueError, TypeError):
                        pass
                if not complete:
                    complete = re.search(
                        r'"name"\s*:\s*"' + re.escape(name) + r'\s*"', raw
                    ) is not None
            else:
                # no raw to check (shouldn't happen via turns): fall back to
                # the old sibling heuristic so history still unwraps.
                complete = (
                    "params" in wrapper_args or "arguments" in wrapper_args
                    or len(wrapper_args) >= 2
                )
            if not complete:
                name = None

        # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-22) harness:openlumara
        # the bridge args key is 'params' now (sorts after 'name' so models emit
        # the name first); 'arguments' stays supported for old chat history.
        inner = wrapper_args.get("params")
        if inner is None:
            inner = wrapper_args.get("arguments")
        if isinstance(inner, str):
            # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-21) harness:openlumara
            # transport format: arguments rides as a JSON-encoded string so the
            # provider streams it token by token (object-typed nested values
            # arrive as one atomic chunk - bridge debug log 2026-10-21). the
            # lenient parser surfaces the partial string value; json_repair
            # then decodes whatever of the inner json exists so far into a
            # growing dict (it never raises).
            inner_parsed = parse_lenient_json(inner)
            if "_raw" in inner_parsed:
                try:
                    inner_parsed = json_repair.loads(inner)
                except Exception:
                    inner_parsed = None
            inner = inner_parsed if isinstance(inner_parsed, dict) else None
        elif inner is not None and not isinstance(inner, dict):
            inner = None
        if inner is None and raw:
            # partial-JSON parsers can DROP an in-progress nested value
            # entirely: while the wrapper's "arguments" object is unclosed
            # it may never surface in the lenient wrapper parse, leaving the
            # unwrap blind until the JSON completes - which is precisely why
            # long bridged args showed nothing while streaming. slice the
            # inner value out of the raw text and parse it ON ITS OWN: a
            # top-level partial object hits the same lenient path that makes
            # native (unbridged) tool args stream.
            started = re.search(r'"(?:arguments|params)"\s*:\s*[{"\[]', raw)
            if started:
                chunk = raw[started.end() - 1:]
                sliced = parse_lenient_json(chunk)
                if isinstance(sliced, dict) and "_raw" not in sliced:
                    inner = sliced
                else:
                    # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-22) harness:openlumara
                    # string-typed params transport: the slice starts at a QUOTE,
                    # so it parses to a plain str (or {_raw}) and used to be
                    # dropped here - raw wrapper card again. two-step it instead:
                    # decode the (partial) string literal, then json_repair the
                    # embedded json it holds into a growing dict.
                    try:
                        cand = json_repair.loads(chunk)
                        if isinstance(cand, str):
                            cand = json_repair.loads(cand)
                        if isinstance(cand, dict) and cand:
                            inner = cand
                    except Exception:
                        pass
        if name is None and inner is None:
            return None, None
        return name, inner

    @staticmethod
    def _display_name(tool):
        """The name a tool call should display as (unwrapped bridge name if any)."""
        return ((tool.get("_metadata") or {}).get("display_name")
                or (tool.get("function") or {}).get("name"))

    @classmethod
    def _summary_from_args(cls, args):
        if not isinstance(args, dict) or not args or "_raw" in args:
            return ""
        entries = list(args.items())
        chosen = None
        for priority_key in cls.TOOL_ARG_PRIORITY:
            hit = next(((k, v) for k, v in entries if k == priority_key), None)
            if hit:
                chosen = hit
                break
        if chosen is None:
            chosen = next(((k, v) for k, v in entries if isinstance(v, str)), entries[0])
        return "(" + cls._truncate_arg(cls._arg_to_string(chosen[1])) + ")"

    @classmethod
    def _tool_call_summary(cls, tool):
        # -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01)
        # lenient parse instead of strict json.loads: headers can now show
        # the arg summary LIVE while arguments stream in, not only once
        # the full JSON is complete.
        raw = (tool.get("function") or {}).get("arguments")
        if not isinstance(raw, str):
            return ""
        return cls._summary_from_args(parse_lenient_json(raw))

    @staticmethod
    def _modules_for(tool_calls):
        # deduped per-function counts grouped by module (first token):
        # [{"module": "Coder", "actions": [{"name": "file edit", "count": 2}]}]
        counts = {}
        order = []
        for tool in tool_calls or []:
            # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-21) harness:openlumara
            # prefer the unwrapped bridge name so proxied calls group under
            # their real module ("Calendar: add event", not "Tools: call")
            fn = TurnCollector._display_name(tool)
            if not fn:
                continue
            if fn not in counts:
                counts[fn] = 0
                order.append(fn)
            counts[fn] += 1
        groups = {}
        group_order = []
        for fn in order:
            parts = fn.split("_")
            module = parts[0][:1].upper() + parts[0][1:]
            action = "_".join(parts[1:])
            if module not in groups:
                groups[module] = []
                group_order.append(module)
            existing = next((a for a in groups[module] if a["name"] == action), None)
            if existing:
                existing["count"] += counts[fn]
            else:
                groups[module].append({"name": action, "count": counts[fn]})
        return [{"module": m, "actions": groups[m]} for m in group_order]

    @staticmethod
    def _step_status(tool_calls):
        # running: some call still lacks a response. failed: every call
        # failed. thoughts: tool-less step.
        if not tool_calls:
            return "thoughts"
        if any((t.get("_metadata") or {}).get("response") is None for t in tool_calls):
            return "running"
        if all(TurnCollector._tool_call_failed(t) for t in tool_calls):
            return "failed"
        return "done"

    @staticmethod
    def _is_final_content(msg):
        return (
            msg.get("role") == "assistant"
            and not msg.get("tool_calls")
            and isinstance(msg.get("content"), str)
            and msg.get("content", "").strip() != ""
        )

    @staticmethod
    def _segment_label(segment):
        # short human label for the collapsed Process header: the last
        # tool call as "Module: action", or what the model is busy doing
        tool_calls = segment.get("tool_calls")
        if tool_calls:
            # unwrapped bridge name when available (staticmethod: no self!)
            fn = TurnCollector._display_name(tool_calls[-1])
            if fn:
                parts = fn.split("_")
                return parts[0][:1].upper() + parts[0][1:] + ": " + " ".join(parts[1:])
        if isinstance(segment.get("reasoning_content"), str) and segment["reasoning_content"].strip():
            return "Thinking.."
        if isinstance(segment.get("content"), str) and segment["content"].strip():
            return "writing"
        return ""

    @staticmethod
    def _has_visible_chain_content(msg):
        if msg.get("tool_calls"):
            return len(msg["tool_calls"]) > 0
        if isinstance(msg.get("reasoning_content"), str) and msg["reasoning_content"].strip():
            return True
        if msg.get("role") == "assistant" and isinstance(msg.get("content"), str) and msg["content"].strip():
            return True
        return False

    def build_steps(self, messages):
        # split a finalized assistant turn's messages into (steps, final).
        # the last content-without-toolcalls message is the final answer;
        # everything else is the chain. reasoning riding on the final
        # answer becomes its own trailing Thoughts step (copies, the
        # stored messages are never mutated).
        final_index = -1
        for i in range(len(messages) - 1, -1, -1):
            if self._is_final_content(messages[i]):
                final_index = i
                break

        chain = []
        final = []
        for i, message in enumerate(messages):
            if i == final_index:
                if isinstance(message.get("reasoning_content"), str) and message["reasoning_content"].strip():
                    chain_copy = dict(message)
                    chain_copy["content"] = ""
                    chain.append(chain_copy)
                    final_copy = dict(message)
                    final_copy.pop("reasoning_content", None)
                    final.append(final_copy)
                else:
                    final.append(message)
            elif self._has_visible_chain_content(message):
                chain.append(message)

        steps = []
        step_num = 0
        i = 0
        while i < len(chain):
            m = chain[i]
            has_tools = bool(m.get("tool_calls"))

            if has_tools:
                step_num += 1
                steps.append({
                    "step": step_num,
                    "status": self._step_status(m["tool_calls"]),
                    "reasoning_content": m.get("reasoning_content") or "",
                    "content": m.get("content") or "",
                    "tool_calls": m["tool_calls"],
                    "modules": self._modules_for(m["tool_calls"]),
                })
                i += 1
                continue

            # thought run: consecutive reasoning/content segments
            def is_thought(msg):
                return (
                    not msg.get("tool_calls")
                    and ((isinstance(msg.get("reasoning_content"), str) and msg["reasoning_content"].strip())
                         or (isinstance(msg.get("content"), str) and msg["content"].strip()))
                )
            j = i
            while j < len(chain) and is_thought(chain[j]):
                j += 1
            tool_seg = chain[j] if (j > i and j < len(chain) and chain[j].get("tool_calls")) else None

            reasoning = ""
            content = ""
            for k in range(i, j):
                if chain[k].get("reasoning_content"):
                    reasoning = (reasoning + "\n\n" if reasoning else "") + chain[k]["reasoning_content"]
                if chain[k].get("content"):
                    content = (content + "\n\n" if content else "") + chain[k]["content"]

            if tool_seg:
                # the run led to a tool call: fold it into that step
                step_num += 1
                steps.append({
                    "step": step_num,
                    "status": self._step_status(tool_seg["tool_calls"]),
                    "reasoning_content": reasoning,
                    "content": content,
                    "tool_calls": tool_seg["tool_calls"],
                    "modules": self._modules_for(tool_seg["tool_calls"]),
                })
                i = j + 1
            elif j == len(chain):
                # trailing thought run with no tool call: a thoughts step
                step_num += 1
                steps.append({
                    "step": step_num,
                    "status": "thoughts",
                    "reasoning_content": reasoning,
                    "content": content,
                    "tool_calls": [],
                    "modules": [],
                })
                i = j
            else:
                # thought run followed by something odd (e.g. tool-result
                # only message): keep the message as its own thoughts step
                step_num += 1
                steps.append({
                    "step": step_num,
                    "status": "thoughts",
                    "reasoning_content": m.get("reasoning_content") or "",
                    "content": m.get("content") or "",
                    "tool_calls": [],
                    "modules": [],
                })
                i += 1

        return steps, final

    async def group_stream(self, stream_generator):
        """
        this takes the raw stream generator and yields 'streaming turn' objects
        as tokens come in.

        this way, we can display each segment throughout the UI, seperately,
        using whatever layout and components we want!

        it's basically a state machine that groups tokens into segments.
        a segment is just a group of tokens of the same type.

        unlike normal streaming deltas, these tokens accumulate,
        and are meant to be used in UI's where you can fully replace the content of a UI component
        with the new content with the newly streamed tokens added

        since an assistant response can contain multiple kinds of content in sequence,
        like reasoning -> content -> tool_calls -> tool responses -> more reasoning -> final answer (reasoning+content)
        we need to track when the type changes so we can create a new segment.

        it creates a clear separation between types of content,
        where all you ever need to do is create a new UI element when the segment type changes,
        without worrying about merging the different types of tokens manually

        this used to be exclusive to the webUI, handled in the frontend.
        but since this is now in the core, it can be used in *ANY* channel.

        usage: (from within your channel's run()):
          async for partial_turn in self.get_streaming_turns(
              self.send_stream("user's message") 
          ):
              do_whatever_with(partial_turn)

        the state machine works like this:
        - if the token type changes, we create a new segment and start filling it
        - if the token type stays the same, we keep appending to the current segment
        - for tool responses, we don't yield them as segments,
          instead we merge their responses back into the corresponding tool_calls segment
        """

        current_segment = None
        last_segment_type = None
        stream_response_map = {}
        last_tool_call_id = None
        last_tool_calls_segment = None

        # -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-1)
        # -- step tracking: reasoning/content runs and the tool calls they
        # -- lead to share one step number; the step increments when a new
        # -- segment starts after the current one already attached tools
        # -- (that step is then complete). consumers accumulate steps from
        # -- the active-step-only yields by grouping on the step field.
        step_num = 0
        step_has_tools = False

        # -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01)
        # monotonic args_parsed cache keyed by tool call id: a mid-stream
        # parse can never yield fewer keys than what was already sent.
        args_cache = {}
        # same idea for unwrapped bridge calls: the inner arguments object
        # resolved from the raw wrapper stream (see _bridge_from_args).
        inner_cache = {}
        # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-22) harness:openlumara
        # once a bridge call's real name resolved mid-stream, keep it: a later
        # token whose parse hiccups (or drops the name) must never regress the
        # card from the unwrapped view back to the raw tools_call wrapper.
        name_cache = {}

        def _stamp_args(tool):
            tool_id = tool.get("id")
            raw = (tool.get("function") or {}).get("arguments")
            parsed = parse_lenient_json(raw)
            prev = args_cache.get(tool_id)
            if prev is not None and len(prev) > len(parsed):
                parsed = prev
            else:
                args_cache[tool_id] = parsed
            # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-13)
            # annotations live under the call's _metadata key
            meta = tool.setdefault("_metadata", {})
            # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-21) harness:openlumara
            # unwrap tools_call proxies order-agnostically so bridged calls
            # render as the real call while streaming too (mirrors history)
            bridge_name, bridge_args = self._bridge_from_args(
                (tool.get("function") or {}).get("name"), parsed, raw
            )
            if bridge_name is None and bridge_args is None:
                if tool_id in name_cache:
                    # name resolved on an earlier token: keep the card fully
                    # unwrapped (inner args from the cache when we have them)
                    meta["bridge"] = True
                    meta["display_name"] = name_cache[tool_id]
                    cached_inner = inner_cache.get(tool_id)
                    meta["args_parsed"] = cached_inner if cached_inner is not None else parsed
                else:
                    meta["args_parsed"] = parsed
            else:
                meta["bridge"] = True
                if bridge_args is None:
                    bridge_args = inner_cache.get(tool_id)
                elif inner_cache.get(tool_id) is not None and len(inner_cache[tool_id]) > len(bridge_args):
                    bridge_args = inner_cache[tool_id]
                if bridge_args is not None:
                    inner_cache[tool_id] = bridge_args
                if bridge_name:
                    name_cache[tool_id] = bridge_name
                    meta["display_name"] = bridge_name
                elif tool_id in name_cache:
                    meta["display_name"] = name_cache[tool_id]
                meta["args_parsed"] = bridge_args if bridge_args is not None else {}

        async for raw_token in stream_generator:
            # copy the token so we don't mutate it
            token = dict(raw_token)

            # -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01)
            # enrich prompt progress with precomputed percent + ETA so
            # channels render the indicator without doing the math
            if token.get("type") == "prompt_progress" and isinstance(token.get("content"), dict):
                progress = dict(token["content"])
                cache = progress.get("cache") or 0
                processed = (progress.get("processed") or 0) - cache
                total = (progress.get("total") or 0) - cache
                elapsed_ms = progress.get("time_ms") or 0

                percent = round((processed / total) * 100) if total > 0 else 0
                eta = (elapsed_ms / 1000 / processed) * (total - processed) if (processed > 0 and total > processed) else 0

                progress["percent"] = percent
                progress["eta_seconds"] = round(eta, 1)
                token["content"] = progress

            # yield the raw token in case it needs to be processed 
            # (for things like user messages, API errors, etc)
            yield {"type": "token", "content": token}

            # skip grouping for non-display tokens
            # -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01)
            # model_load_progress: llama.cpp router load progress, passthrough
            if token.get("type") in ['prompt_progress', 'token_usage', 'timings', 'user_message', 'model_load_progress']:
                continue

            # remove timing data from the token
            if token.get("timings"):
                token.pop("timings")

            segment_type = token.get("type")
            
            # merge tool call deltas and toolcalls into one type
            if segment_type in ['tool_call_delta', 'tool_calls']:
                segment_type = 'tool_calls'

            # determine whether this is a new tool response (different tool_call_id)
            # since tool responses can arrive for multiple different tools in sequence,
            # each needs its own response tracking
            is_new_tool_response = (
                segment_type == 'tool' and 
                last_tool_call_id != token.get("tool_call_id")
            )

            # the grouping works like this:
            # if the token type is different from the previous one,
            # or if we're switching to a new tool response (different tool_call_id),
            # we create a new segment.
            #
            # otherwise, we append to the existing segment that's currently
            # being filled
            if segment_type != last_segment_type or is_new_tool_response:
                # create a new segment (message within the turn)
                current_segment = token.copy()
                current_segment["role"] = "assistant" if segment_type != 'tool' else "tool"
                current_segment["type"] = segment_type

                # -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01)
                # step bookkeeping: a new assistant segment starts a new
                # step only if the current one already attached tools (or
                # no step exists yet); tool calls themselves join the
                # reasoning run that preceded them
                if segment_type != 'tool':
                    if step_num == 0 or step_has_tools:
                        step_num += 1
                        step_has_tools = False
                    if segment_type == 'tool_calls':
                        step_has_tools = True
                    current_segment["step"] = step_num
                
                if segment_type == 'reasoning':
                    if "content" in current_segment.keys():
                        # remove non-reasoning content from the reasoning segment
                        current_segment.pop("content")

                    current_segment.setdefault("reasoning_content", token.get("content", ''))
                elif segment_type == 'content':
                    current_segment.setdefault("content", token.get("content", ''))
                elif segment_type == 'tool_calls':
                    # copy the list since we mutate it in place during merges
                    # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-13)
                    # also copy each call dict: these token dicts are shared with
                    # the message the toolcall manager stores into chat history,
                    # and the annotations below would rewrite stored history
                    current_segment.setdefault("tool_calls", [dict(tc) for tc in token.get("tool_calls", [])])
                    last_tool_calls_segment = current_segment  # remember this for later merging
                elif segment_type == 'tool':
                    current_segment["type"] = "tool_response"
                    current_segment.setdefault("content", token.get("content", ''))
                
                last_segment_type = segment_type
                last_tool_call_id = token.get("tool_call_id") if segment_type == 'tool' else None
            
            else:
                # if it's the same token type as the last one,
                # that means we're still working with the same segment,
                # so here's where we do the streaming magic
                # that merges new tokens into the existing segment
                if segment_type == 'tool_calls':
                    if token.get("tool_calls"):
                        existing_calls = current_segment.setdefault("tool_calls", [])
                        # merge the tool calls using their id
                        # so that batched tool calls properly show up
                        for incoming_call in token["tool_calls"]:
                            # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-13)
                            # copy on insert: shared with the stored message's tool calls
                            incoming_call = dict(incoming_call)
                            call_id = incoming_call.get("id")
                            if call_id:
                                for idx, existing_call in enumerate(existing_calls):
                                    if existing_call.get("id") == call_id:
                                        existing_calls[idx] = incoming_call
                                        break
                                else:
                                    existing_calls.append(incoming_call)
                            elif existing_calls and not existing_calls[-1].get("id"):
                                # no id to match on: assume it continues the last
                                # id-less call (providers that stream ids late/never)
                                existing_calls[-1] = incoming_call
                            else:
                                existing_calls.append(incoming_call)
                elif segment_type == 'tool':
                    current_segment["content"] = (current_segment.get("content") or '') + (token.get("content") or '')
                else:
                    content_key = "reasoning_content" if segment_type == 'reasoning' else 'content'
                    current_segment[content_key] = (current_segment.get(content_key) or '') + (token.get("content") or '')

            # tool responses need to be merged back into their corresponding tool calls
            # so we maintain a response map that accumulates tool response content by tool_call_id
            if token.get("type") == 'tool':
                stream_response_map[token["tool_call_id"]] = token.get("content", '')

            # ----
            # yield logic:
            # - for normal segments (reasoning, content, tool_calls), yield the current segment
            #   with any available tool responses merged into the tool calls
            # - for tool_response segments, we don't yield them directly. instead,
            #   we update the last_tool_calls_segment with the new response and re-yield it.
            # ----
            if current_segment.get("type") != 'tool_response':
                # merge tool responses into tool calls for display
                if current_segment.get("tool_calls"):
                    for tool in current_segment["tool_calls"]:
                        # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-13)
                        # annotations live under the call's _metadata key
                        meta = tool.setdefault("_metadata", {})
                        if tool.get("id") in stream_response_map:
                            meta["response"] = stream_response_map[tool["id"]]
                            # precomputed failed flag (mirrors group_history)
                            meta["failed"] = self._tool_call_failed(tool)
                        # parsed args (mirrors group_history; unwraps tools_call)
                        _stamp_args(tool)
                        # arg summary on the (possibly unwrapped) args
                        if meta.get("bridge"):
                            meta["summary"] = self._summary_from_args(meta.get("args_parsed"))
                        else:
                            meta["summary"] = self._tool_call_summary(tool)
                    # -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01)
                    # live step status + precomputed module display data
                    current_segment["step_status"] = self._step_status(current_segment["tool_calls"])
                    current_segment["modules"] = self._modules_for(current_segment["tool_calls"])
                else:
                    current_segment["step_status"] = "thinking"
                # -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01)
                # stamp the collapsed-header label, and skip yielding
                # segments with nothing visible: they'd be ghost stations
                current_segment["label"] = self._segment_label(current_segment)
                if self._has_visible_chain_content(current_segment):
                    yield {"type": "turn", "content": current_segment}
            elif last_tool_calls_segment:
                # tool response segment: update and re-yield the tool_calls segment instead
                for tool in last_tool_calls_segment["tool_calls"]:
                    # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-13)
                    # annotations live under the call's _metadata key
                    meta = tool.setdefault("_metadata", {})
                    if tool.get("id") in stream_response_map:
                        meta["response"] = stream_response_map[tool["id"]]
                        meta["failed"] = self._tool_call_failed(tool)
                    _stamp_args(tool)
                    if meta.get("bridge"):
                        meta["summary"] = self._summary_from_args(meta.get("args_parsed"))
                    else:
                        meta["summary"] = self._tool_call_summary(tool)
                # -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01)
                # responses landed: refresh the re-yielded step's status
                last_tool_calls_segment["step_status"] = self._step_status(last_tool_calls_segment["tool_calls"])
                last_tool_calls_segment["label"] = self._segment_label(last_tool_calls_segment)
                yield {"type": "turn", "content": last_tool_calls_segment}

