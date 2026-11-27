"""Websocket Manager"""

import asyncio

import fastapi
import starlette.websockets

import core

import channels.webui.utils as utils

class WebSocketManager:
    # prevent the stream from stalling forever
    SEND_TIMEOUT = 10

    def __init__(self, channel):
        self.channel = channel
        self.active_connections = []
        self.active_stream_task = None
        self.webui_ready = False
        self.stream_state = "idle"
        # one buffer per live on_stream invocation (the root answer turn plus
        # any nested compaction/subagent streams), keyed by stream id. sharing
        # one buffer let a nested stream clobber the main chain's steps/final
        # because both number their steps from 1.
        self.streams = {}
        self._next_stream_id = 0
        self.stack = []          # currently-open stream ids, root at index 0

    # -- AI GENERATED CODE (GPT-6.2-Sol) :: 2026-11-27 08:40 +08:00 harness:Codex
    def begin_stream(self):
        """Open a stream buffer and return its routing metadata."""
        self._next_stream_id += 1
        stream_id = self._next_stream_id
        lane = {"stream_id": stream_id}
        if self.stack:
            parent = self.stack[-1]
            parent_steps = self.streams[parent]["steps"]
            lane.update(parent_id=parent, root_stream_id=self.stack[0], attach_step=max(parent_steps, default=0))
        self.streams[stream_id] = {"steps": {}, "final": [], "lane": lane}
        self.stack.append(stream_id)
        return lane

    def end_stream(self, stream_id):
        if stream_id in self.stack:
            self.stack.remove(stream_id)

    def reset_streams(self):
        self.streams = {}
        self.stack = []

    def _buffer(self, stream_id):
        return self.streams[stream_id]

    def record_step_snapshot(self, stream_id, step: dict):
        """track the newest snapshot of one streaming step (upsert by number)"""
        self._buffer(stream_id)["steps"][step.get("step")] = step

    def record_final_snapshot(self, stream_id, messages: list):
        """track the newest final-bubble snapshot"""
        self._buffer(stream_id)["final"] = messages

    def apply_step_delta(self, stream_id, delta: dict):
        """fold a streaming append into the stored step snapshot, so a
        mid-stream reconnect replay stays current between checkpoints"""
        step = self._buffer(stream_id)["steps"].get(delta.get("step"))
        if step is None:
            return

        for append in delta.get("append", []):
            if append.get("field") == "reasoning_content":
                step["reasoning_content"] = (step.get("reasoning_content") or "") + append["text"]
            elif append.get("field") == "tool_response":
                for tool in step.get("tool_calls", []):
                    if tool.get("id") == append.get("id"):
                        meta = tool.setdefault("_metadata", {})
                        meta["response"] = (meta.get("response") or "") + append["text"]
                        break

    def apply_final_delta(self, stream_id, delta: dict):
        final = self._buffer(stream_id)["final"]
        if not final:
            return
        last = final[-1]
        last["content"] = (last.get("content") or "") + delta["text"]

    async def push_context_update(self, connection=None):
        """push the token usage and the full context breakdown
        over the websocket. called on every context-changing event"""
        try:
            size = utils.serialize_for_json(await self.channel.context.get_size())
            messages = [
                {"type": "token_usage", "content": size["total_tokens"], "source": "estimation"},
                {"type": "context_size", "content": size},
            ]
            
            for message in messages:
                if connection is not None:
                    await connection.send_json(message)
                else:
                    await self.broadcast(message)
        except Exception as e:
            self.channel.log(self.channel.name, f"error pushing context update: {core.detail_error(e)}")

    async def set_stream_state(self, state: str):
        """update the stream state and notify all clients"""
        if state == self.stream_state:
            return
        self.stream_state = state

        if state == "idle" or (state == "message_sending" and not self.stack):
            self.reset_streams()

        await self.broadcast({"type": "stream_state", "state": state})

    async def connect(self, websocket: fastapi.WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

        current_chat_id = self.channel.context.chat.get("id")

        if current_chat_id:
            await websocket.send_json({
                "type": "ready"
            })

        # push the current stream state to the client
        await websocket.send_json({
            "type": "stream_state",
            "state": self.stream_state
        })

        # when reconnecting mid-stream, replay every lane so far, in creation
        # order, tagged with its stream id / parent / attach_step so nested
        # chains rebuild inline under the step that spawned them
        if self.stream_state != "idle":
            for stream_id in list(self.streams):
                buf = self.streams.get(stream_id)
                if not buf:
                    continue
                lane = buf["lane"]
                for step_num in sorted(buf["steps"]):
                    await websocket.send_json({
                        "type": "turn_step",
                        "step": buf["steps"][step_num],
                        **lane,
                    })
                await websocket.send_json({
                    "type": "turn_final",
                    "messages": buf["final"],
                    **lane,
                })
                if "parent_id" in lane and stream_id not in self.stack:
                    await websocket.send_json({"type": "turn_lane_end", "stream_id": stream_id})

        await self.push_context_update(connection=websocket)

        asyncio.create_task(self.queue_ready_signal())

    def disconnect(self, websocket: fastapi.WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def queue_ready_signal(self):
        while not self.webui_ready:
            await asyncio.sleep(0.1)
        await self.broadcast({"type": "ready"})

    def send_ready_signal(self):
        self.webui_ready = True

    async def broadcast(self, message: dict):
        """broadcast a websocket event to all connected clients.

        -- AI GENERATED CODE (Qwen3.8-Flash-Next-Gufo) :: (2026-11-24) harness:openlumara
        sends run concurrently: one stalled client (backgrounded tab, full
        socket buffer) used to hold up delivery to every other client for up
        to SEND_TIMEOUT seconds per broadcast event."""
        async def _send(connection):
            try:
                if connection.client_state == starlette.websockets.WebSocketState.CONNECTED:
                    await asyncio.wait_for(
                        connection.send_json(message), timeout=self.SEND_TIMEOUT
                    )
            except Exception:
                return connection
            return None

        results = await asyncio.gather(
            *(_send(connection) for connection in list(self.active_connections))
        )

        for conn in results:
            if conn is None:
                continue
            self.disconnect(conn)
            try:
                await asyncio.wait_for(conn.close(), timeout=2)
            except Exception:
                pass

    # -- AI GENERATED CODE (GPT-6.2-Sol) :: 2026-11-27 08:49 +08:00 harness:Codex
    async def _stream_task(self, message: str, files: list = None):
        try:
            await self.set_stream_state("message_sending")
            self.channel._ws_stream_index = len(await self.channel.context.chat.messages.get())
            await self.channel.push_stream(
                self.channel.send_stream(
                    message=message,
                    files=files,
                    commands_authorized=self.channel.config.get("enable_admin_settings", False)
                )
            )
        finally:
            # always finalize the stream, no matter what
            await self.broadcast({
                "type": "stream_complete",
                "revision": getattr(self.channel.context.chat.messages, "revision", None),
            })
            await self.set_stream_state("idle")

    async def start_stream(self, channel, chat_id: str, message: str, files: list = None):
        # route chat input into a pending ask_user question instead of
        # cancelling the paused turn
        ask_mod = (getattr(channel.manager, "modules", None) or {}).get("ask_user")
        if not files and message and ask_mod and hasattr(ask_mod, "_try_intercept_chat_answer"):
            try:
                answer_text = ask_mod._try_intercept_chat_answer(message, chat_id)
                if answer_text:
                    await channel.push({"role": "user", "content": answer_text})
                    return
            except Exception as e:
                channel.log(channel.name, f"ask_user intercept failed: {core.detail_error(e)}")

        if self.active_stream_task and not self.active_stream_task.done():
            # don't cancel the running turn: steer it at the next safe point
            descriptor = await channel.queue_steering_message(
                message,
                files=files,
                commands_authorized=channel.config.get("enable_admin_settings", False)
            )
            if descriptor:
                await self.broadcast({
                    "type": "queue_queued",
                    "messages": [descriptor]
                })
            return

        try:
            self.active_stream_task = asyncio.create_task(self._stream_task(message, files=files))
        except asyncio.CancelledError:
            pass
        except Exception as e:
            channel.log(channel.name, f"Background stream error: {core.detail_error(e)}")
