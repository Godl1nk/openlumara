# -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-24) harness:openlumara status:reviewed
"""
text/event-stream (SSE) parsing.

implements the field-parsing part of the SSE spec:
  - lines may end in LF, CRLF or a lone CR
  - a field is written as "field: value"; exactly one leading space after
    the colon belongs to the separator, not the value
  - multiple data lines are joined with newlines
  - an empty line completes the current event
  - lines starting with ":" are comments (keep-alive pings)
  - a data line containing just [DONE] ends the stream

usage:
    async for event in core.http_sse.iter_events(response):
        ...
"""

import codecs
import json

class StreamEnd:
    """sentinel: the server signaled the end of the stream with a [DONE] data line"""

class SSEParser:
    """
    incremental parser for a text/event-stream body.

    feed() raw bytes as they arrive from the connection; it returns a list
    of completed events (dicts). call finish() once the connection closed,
    to flush whatever is still pending.

    decoding is strict and incremental, so multi-byte characters that are
    split across chunk boundaries are handled, and invalid utf-8 raises an
    error instead of being silently replaced.
    """

    def __init__(self):
        self.decoder = codecs.getincrementaldecoder("utf-8")()
        self.buffer = ""          # text that has not been parsed yet
        self.event_type = ""      # value of the current event's event: field
        self.event_id = ""        # value of the current event's id: field
        self.data_lines = []      # values of the current event's data: lines
        self.done = False         # set once the server sent [DONE]

    def feed(self, raw_bytes):
        """decode a chunk from the stream and return any completed events"""
        self.buffer += self.decoder.decode(raw_bytes)
        return self._extract_events(at_end_of_stream=False)

    def finish(self):
        """flush the decoder and any pending event after the stream closed"""
        self.buffer += self.decoder.decode(b"", final=True)
        return self._extract_events(at_end_of_stream=True)

    def _extract_events(self, at_end_of_stream):
        events = []

        for line in self._extract_complete_lines(at_end_of_stream):
            result = self._handle_line(line)
            if result is StreamEnd:
                self.done = True
                return events
            if result is not None:
                events.append(result)

        # some servers end the stream right after the last data line,
        # without closing it with a blank line
        if at_end_of_stream:
            final_event = self._build_event()
            if final_event is not None and final_event is not StreamEnd:
                events.append(final_event)

        return events

    def _extract_complete_lines(self, at_end_of_stream):
        """
        splits all complete lines off the buffer, and keeps whatever remains
        (an unfinished line) in it for next time.

        a CR at the very end of the buffer is NOT treated as a line end yet:
        the next chunk might start with an LF, which would make it a CRLF
        pair. only at the end of the stream do we know for sure that the CR
        terminated its line.
        """
        complete_lines = []
        line_start = 0

        while line_start < len(self.buffer):
            lf_at = self.buffer.find("\n", line_start)
            cr_at = self.buffer.find("\r", line_start)

            if lf_at == -1 and cr_at == -1:
                break  # no line terminator left in the buffer

            use_lf = cr_at == -1 or (lf_at != -1 and lf_at < cr_at)

            if use_lf:
                line_end = lf_at
                next_line_start = lf_at + 1
            elif cr_at == len(self.buffer) - 1 and not at_end_of_stream:
                # buffer ends on a CR: wait for the next chunk to learn
                # whether an LF follows it
                break
            else:
                line_end = cr_at
                # a CRLF pair counts as a single line terminator
                is_crlf = self.buffer[cr_at + 1 : cr_at + 2] == "\n"
                next_line_start = cr_at + (2 if is_crlf else 1)

            complete_lines.append(self.buffer[line_start:line_end])
            line_start = next_line_start

        self.buffer = self.buffer[line_start:]
        return complete_lines

    def _handle_line(self, line):
        """
        feeds one SSE line into the pending event state.
        returns an event (see _build_event) when the line completed one,
        or None while the event is still incomplete.
        """
        if line.startswith(":"):
            return None  # comment / keep-alive ping

        if line:
            field, _, value = line.partition(":")
            # per the spec, exactly one leading space after the colon
            # belongs to the separator, not the value
            if value.startswith(" "):
                value = value[1:]

            if field == "data":
                self.data_lines.append(value)
            elif field == "event":
                self.event_type = value
            elif field == "id":
                self.event_id = value
            # any other field (e.g. retry) is ignored
            return None

        # an empty line means the current event is complete
        return self._build_event()

    def _build_event(self):
        """
        turns the accumulated event fields into a final event:
          StreamEnd -> the server signaled the end of the stream
          dict      -> a completed event, ready to be used
          None      -> nothing was accumulated, so there is no event
        """
        # take the pending fields and reset them,
        # so the next event starts with a clean slate
        pending_data, pending_type, pending_id = self.data_lines, self.event_type, self.event_id
        self.data_lines, self.event_type, self.event_id = [], "", ""

        if not pending_data:
            return None

        joined_data = "\n".join(pending_data)
        if joined_data == "[DONE]":
            return StreamEnd

        try:
            payload = json.loads(joined_data)
        except json.JSONDecodeError:
            return None  # not JSON, nothing we can do with it

        if not isinstance(payload, dict):
            payload = {"content": payload}

        # merge the SSE metadata into the payload,
        # unless the JSON already carries its own values
        if pending_type and "event" not in payload:
            payload["event"] = pending_type
        if pending_id and "id" not in payload:
            payload["id"] = pending_id

        return payload


async def iter_events(response):
    """
    async generator that yields every event of an aiohttp SSE response body
    as a dict. ends when the server sends a [DONE] data line or the
    connection closes.
    """
    parser = SSEParser()

    async for raw_bytes in response.content.iter_any():
        for event in parser.feed(raw_bytes):
            yield event
        if parser.done:
            return

    for event in parser.finish():
        yield event
