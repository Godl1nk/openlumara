let isWsConnected = false;
let wsReconnecting = false;
let responseSoundPlayed = false;

// -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-12)
// remembers that the server went away while this page was open, so the
// reconnect can reload the page and pick up fresh assets after a restart.
// wsClosedAt also lets us tell a real restart (multi-second outage) apart
// from a momentary proxy/network blip.
let serverShutdownSeen = false;
let wsClosedAt = null;

// -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-23) harness:openlumara
// app-level heartbeat: sends {type:"ping"} every 25s while connected and
// tracks when the last message of ANY kind arrived. defeats idle-socket
// reapers (reverse proxies / tunnels dropping quiet connections) and the
// last-seen timestamp tells us whether a 1006 hit during total silence
// (network path died) or right after traffic (server side issue).
let wsHeartbeatTimer = null;
window.wsLastRx = Date.now();

// intended to be used to queue up messages for sending to the backend in case the
// websocket isn't connected. it's a stub for now
let sendQueue = [];

// -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-13)
// true while the stream_complete handoff handler is running. ws handlers run
// per-message and interleave at every await, so a push event landing during
// the handoff (the backend opens its push gate before stream_complete is even
// broadcast, and stream_state idle can arrive mid-fold) must NOT reloadChat
// concurrently: the live turn has no hash, so the index-merge drops it, and
// stream_complete's fallback then re-pushes it as a duplicate Process turn.
let streamFinalizing = false;

async function connectWebSocket() {
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const token = window.apiToken || '';
    const tokenParam = token ? `?token=${encodeURIComponent(token)}` : '';

    const pathname = `${window.location.pathname || '/'}`;
    const pathBase = pathname.endsWith('/') ? pathname.slice(0, -1) : pathname;
    const wsPath = `${pathBase === '' ? '' : pathBase}/ws`;
    const wsUrl = `${wsProtocol}//${window.location.host}${wsPath}${tokenParam}`;

    try {
        wsSocket = new WebSocket(wsUrl);

        // store a global reference of it
        window.socket = wsSocket;
    } catch (e) {
        await scheduleWsReconnect();
        return;
    }

    wsSocket.onopen = async () => {
        console.log('WebSocket connected');
        Alpine.store('ui').notice = null;
        isWsConnected = true;
        wsReconnecting = false;

        // -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-12)
        // the server came back after having gone away: reload the page so
        // fresh templates/css/js and any module changes take effect. only
        // counts as a real restart when the shutdown broadcast arrived, the
        // restart button was used, or the outage outlasted a blip.
        const downFor = wsClosedAt ? Date.now() - wsClosedAt : 0;
        wsClosedAt = null;
        if (serverShutdownSeen || Alpine.store('system').restarting || downFor > 2500) {
            window.location.reload();
            return;
        }

        // -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-23) harness:openlumara
        // start the app-level heartbeat (server answers {type:"pong"}; the
        // message switch ignores unknown types, so nothing else changes)
        clearInterval(wsHeartbeatTimer);
        wsHeartbeatTimer = setInterval(() => {
            if (wsSocket && wsSocket.readyState === WebSocket.OPEN) {
                try { wsSocket.send(JSON.stringify({ type: "ping" })); } catch (e) {}
            }
        }, 25000);

        await Alpine.store("chat").reloadChat();
    };

    wsSocket.onmessage = async (event) => {
        let data = null;
        window.wsLastRx = Date.now();
        try {
            data = JSON.parse(event.data);
            await handleWebSocketMessage(data);
        } catch (e) {
            console.error('Error parsing WebSocket message:', e);
        } finally {
            // -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-13)
            // safety net so a throwing stream_complete handler can't leave the
            // finalizing flag stuck (pushes would stop reloading). only cleared
            // for stream_complete itself, so a push handler resolving mid-
            // handoff can never clear it early.
            if (data && data.type === 'stream_complete') {
                streamFinalizing = false;
            }
        }
    };

    wsSocket.onclose = async (event) => {
        if (!wsReconnecting) {
            clearInterval(wsHeartbeatTimer);
            const silence = Math.round((Date.now() - window.wsLastRx) / 1000);
            console.log('WebSocket disconnected:', event.code, event.reason, `(silent for ${silence}s before the drop)`);
            wsSocket = null;
            window.socket = null;
            isWsConnected = false;
            wsClosedAt = Date.now();

            // -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-23) harness:openlumara
            // make the disconnect actually diagnosable: the close code tells
            // auth failures apart from server restarts, and the generic
            // "is it running?" notice made all of them look identical.
            let notice = "Not connected to the backend server! Is OpenLumara running?";
            if (event.code === 4001) {
                notice = "Login session no longer accepted (expired, or the session secret changed). Log out and back in.";
            } else if (event.code === 4003) {
                notice = "WebSocket blocked: origin mismatch. The address in the URL bar does not match the webui's host/port settings.";
            } else if (event.code === 1012 || event.code === 1011 || event.code === 1006) {
                notice = "Connection to the backend dropped (code " + event.code + "). Reconnecting..";
            }
            notice += " [" + event.code + (event.reason ? ' - ' + event.reason : '') + "]";
            Alpine.store('ui').notice = notice;
            stream = Alpine.store("stream")
            stream.state = 'idle';

            await scheduleWsReconnect();
        }
    };

    wsSocket.onerror = async (error) => {
        if (!wsReconnecting) {
            console.error('WebSocket error:', error);
        }
    };
}

async function scheduleWsReconnect() {
    console.log(`attempting to reconnect to websocket..`);
    setTimeout(function () {
        connectWebSocket();
    }, 1000);
}

async function handleWebSocketMessage(data) {
    // we store all the stream-related data in an Alpine store
    const stream = Alpine.store("stream");
    const chat = Alpine.store("chat");
    const ui = Alpine.store('ui');

    data_type = data.type;
    data_content = data.content;

    // if (data_type != 'token' && data_type != "turn_stream") {
    //     console.log(data);
    // }

    // process based on broadcast type
    switch (data_type) {
        // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-12)
        // the backend now owns the stream state machine and announces every
        // transition here; the frontend is a pure mirror. this also arrives
        // on websocket connect, so reconnects and page reloads mid-stream
        // resync automatically instead of guessing.
        case "stream_state":
            stream.state = data.state;
            break;

        case "sync_state":
            /*
             * use the token buffer from the backend
             * to load into the frontend
             *
             * fun lil comment about this... this used to take me ages to get right in the old webUI
             * i had to basically simulate a replay of the entire token stream
             * here it's just a simple assignment!
             * thanks alpine.js
             */
        
            // actually nope its not even needed anymore because we just stream an entire turn from the backend LOL
            // this is now just here for a memory, this data type doesn't actually get broadcast anymore
            break;

        case "user_message_added":
            // keep a reference to the user message so stream_complete can push
            // it to the turn history without it being null
            stream.userMsg = data.message;

            // reload chat from backend so that the new user message shows up
            await chat.reloadChat();

            // force scroll to bottom
            await ui.forceScrollToBottom();

            // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-12)
            // state transitions removed: the backend announces them via
            // stream_state. this handler only keeps the UI side effects.
            break;

        case "user_message_confirmed":
            break;

        case "turn_stream":
            const segment = data.turn;

            if (stream.turn.length <= 0) {
                // -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-22) harness:openlumara
                // mid-stream reload: the fetched history can already contain
                // a persisted assistant turn after the last user turn (tool
                // rounds get saved to chat storage before the answer is
                // final). The live turn - rebuilt in full from the backend's
                // segment replay - is that snapshot's superset, so drop the
                // trailing assistant turns instead of rendering them twice.
                while (chat.turnHistory.length > 0 &&
                       chat.turnHistory[chat.turnHistory.length - 1].role === 'assistant' &&
                       chat.turnHistory[chat.turnHistory.length - 1].live !== true) {
                    chat.turnHistory.pop();
                }

                // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-12)
                // the live turn joins turnHistory the moment its first
                // segment arrives, flagged live. the streaming templates
                // render it as a branch inside the turn x-for (reading the
                // same object), and stream_complete promotes it in place
                // (live -> false) instead of removing a streaming node and
                // appending a history node - so the alpine-animation FLIP
                // watching #messages never sees a remove+add when a stream
                // finishes.
                stream.turn = {role: "assistant", live: true, messages: []};
                chat.turnHistory.push(stream.turn);
                Alpine.store('ui').syncMountWindows();
            }

            // check if this updates the last segment or starts a new one
            const last_idx = stream.turn.messages.length - 1;
            const last_segment = stream.turn.messages[last_idx];

            // same type and same tool_call_id = update existing segment
            const is_update = last_segment &&
                              last_segment.type === segment.type &&
                              last_segment.tool_call_id === segment.tool_call_id;

            if (is_update) {
                // backend sends FULL accumulated content.
                // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-16)
                // this used to swap in the fresh parsed segment object every
                // token: pure garbage for the collector, and it churned the
                // object identity that the markdown cache + lazy-height
                // WeakMaps key on. mutate the existing message in place
                // instead; alpine's proxy set-trap fires the same way.
                Object.assign(last_segment, segment);
            } else {
                // new segment type (or new tool response), push it
                stream.turn.messages.push(segment);
            }

            // scroll
            await ui.scrollToBottom();

            // handle state based on the current segment
            const current_segment = stream.turn.messages[stream.turn.messages.length - 1];
            const segment_type = current_segment.type;

            switch (segment_type) {
                case "reasoning":
                    stream.processing = {};
                    stream.modelLoad = null;
                    AudioManager.stopProcessingSound();
                    AudioManager.play("token");
                    if (!responseSoundPlayed) {
                        AudioManager.play("response_start");
                        responseSoundPlayed = true;
                    }
                    break;
                case "content":
                    stream.processing = {};
                    stream.modelLoad = null;
                    AudioManager.stopProcessingSound();
                    AudioManager.play("token");
                    if (!responseSoundPlayed) {
                        AudioManager.play("response_start");
                        responseSoundPlayed = true;
                    }
                    break;
            }

            if (current_segment.is_cmd) {
                await chat.reloadChats();
                await chat.reloadCategories();
            }

            break;

        case "push":
            // it's a push messsage (like a scheduler reminder)
            // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-16)
            // removed the manual turnHistory.push(): reloadChat() fetches the
            // authoritative history anyway, and pushing first shifted every
            // index by one, making mergeTurnHistory see the entire chat as
            // "changed" and re-parse the markdown of every turn.

            // -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-13)
            // never reloadChat while a stream is active. the backend opens its
            // push gate in the send_stream finally, which runs a hair BEFORE
            // stream_complete is broadcast; reloading in that window merges the
            // finalized history while the turnHistory tail is still the live
            // turn, which duplicates the Process turn. stream_complete does its
            // own reloadChat a frame later anyway, and that one picks the
            // pushed message up from history. sound + notification still fire.
            // this also covers defer=False chain-internal pushes, which used to
            // be able to reload mid-stream for the same reason.
            if (stream.state !== 'idle' || streamFinalizing) {
                await AudioManager.play('response_start');
                await Alpine.store('notifications').send(data.content.content);
                break;
            }

            await chat.reloadChat();

            await AudioManager.play('response_start');
            await Alpine.store('notifications').send(data.content.content);

            await ui.forceScrollToBottom();
            break;

        case "log":
            // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-15)
            // cap the log buffer so a chatty backend can't grow it forever
            const logs = Alpine.store('system').logs;
            logs.push(data);
            if (logs.length > 1000) logs.splice(0, 500);
            break;

        case "ready":
            sys = Alpine.store("system")
            sys.running = true;
            sys.restarting = false;

            // reload the system data from the backend
            await sys.loadData();
            break;

        case "shutdown":
            sys = Alpine.store("system")
            serverShutdownSeen = true;
            if (!sys.restarting) {
                sys.message = "Server is down! Trying to reconnect..";
                sys.running = false;
            }
            break;

        case "token":
            token = data_content;
            token_type = token.type;
            token_content = token.content;

            // process tokens based on their type
            switch (token_type) {
                case "error":
                    stream.modelLoad = null;
                    // restore the user's last input
                    if (!chat.user_input && chat.last_user_input) {
                        chat.user_input = chat.last_user_input;
                    }
                    await chat.reloadChat();
                    break;
                // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-12)
                // all state assignments removed from the token handler: the
                // backend derives the state from these same tokens and
                // announces it via stream_state. kept: audio cues and the
                // processing/modelLoad payload bookkeeping.
                case "tool":
                    AudioManager.playProcessingSound();
                    break;
                case "prompt_progress":
                    // prompt eval started, so any model-load progress is done
                    stream.modelLoad = null;

                    stream.processing = token_content;

                    AudioManager.playProcessingSound();
                    break;
                case "model_load_progress":
                    // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01)
                    // the llama.cpp router is swapping a model in: hijack the
                    // processing indicator with load progress until the real
                    // stream starts (cleared on prompt_progress/content below)
                    stream.modelLoad = token_content;

                    AudioManager.playProcessingSound();
                    break;
                case "token_usage":
                    chat.currentTokenUsage = token_content;
                    break;
                case "tool_call_delta":
                    stream.processing = {};
                    stream.modelLoad = null;
                    break;
                case "tool_calls":
                    break;
            }

            // always scroll to the bottom upon a token coming in
            await ui.scrollToBottom();

            break;

        case "sync":
            // make sure we sync chat
            chat.turnHistory = [];
            await stream.clear();
            await chat.reloadChat();

            if (ui.scrollToTurnIndex) {
                await ui.scrollToTurn(ui.scrollToTurnIndex);
            } else {
                // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-11)
                // turnHistory was wiped and rebuilt; reloadChat's
                // syncMountWindows remounted the tail, but estimated
                // placeholder heights above still settle the scrollHeight -
                // the iterative jump converges on the true bottom fast.
                await ui.forceScrollToBottom();
            }

            break;

        case "chat_switched":
            // make sure we sync chat switches across instances
            await chat.loadChat(data.id);
            break;

        case "stream_complete":
            /*
             * this prevents UI flicker that comes from re-rendering the entire turn history
             */

            // -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-13)
            // block push-triggered reloads for the duration of the handoff
            // (cleared in onmessage's finally, also when this handler throws)
            streamFinalizing = true;

            // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-11)
            // smooth fold: the history chain is collapsed by design, so the
            // streaming chain folds away (animated height, matching the
            // history x-collapse's 250ms) BEFORE the handoff instead of
            // snap-collapsing in the swap frame. the scroll is pinned to the
            // bottom every frame while it folds, so the final answer stays
            // exactly where it is and the chain shrinks behind it. a
            // wheel/touch or a scroll-away cancels the pin; reduced-motion
            // users keep the instant fold.
            const foldEl = document.querySelector('.agent-chain.is-streaming .agent-chain-body');
            if (foldEl && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
                const foldMsgs = document.getElementById('messages');
                foldEl.style.overflow = 'hidden';
                const fold = foldEl.animate(
                    [{ height: foldEl.offsetHeight + 'px' }, { height: '0px' }],
                    { duration: 250, easing: 'ease-in-out', fill: 'forwards' }
                );
                let foldCancelled = false;
                const cancelFoldPin = () => { foldCancelled = true; };
                foldMsgs.addEventListener('wheel', cancelFoldPin, { passive: true });
                foldMsgs.addEventListener('touchstart', cancelFoldPin, { passive: true });
                const pinBottom = () => {
                    if (foldCancelled || !ui.shouldScroll) return;
                    foldMsgs.scrollTo({ top: foldMsgs.scrollHeight - foldMsgs.clientHeight, behavior: 'instant' });
                    if (fold.playState === 'running') requestAnimationFrame(pinBottom);
                };
                requestAnimationFrame(pinBottom);
                try { await fold.finished; } catch (err) { /* cancelled or gone: fine */ }
                foldMsgs.removeEventListener('wheel', cancelFoldPin);
                foldMsgs.removeEventListener('touchstart', cancelFoldPin);
            }

            // push the user message + the fully collected assistant turn to the history.
            // user_message_added already reloads the chat, so the user turn is usually
            // already displayed - only push it if it's missing, otherwise we render a
            // duplicate bubble that shifts the scroll height right when we scroll to bottom
            // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-12)
            // the live assistant turn is now the tail of turnHistory, so
            // the user turn to check against sits one slot earlier - and if
            // it's somehow missing it must be spliced in BEFORE the live
            // turn, never after it.
            const hist = chat.turnHistory;
            const hasLiveTail = hist.length > 0 && hist[hist.length - 1] && hist[hist.length - 1].live === true;
            const lastTurn = hist[hist.length - 1 - (hasLiveTail ? 1 : 0)];
            const userAlreadyShown = lastTurn && lastTurn.role === 'user' &&
                stream.userMsg && lastTurn.messages?.[0]?.index === stream.userMsg.index;

            // -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-22) harness:openlumara
            // stream.userMsg is null after a mid-stream reload (the
            // user_message_added broadcast went to the old page instance) -
            // pushing it then rendered a phantom turn of [null]. the user
            // message is in the backend history either way, so only push
            // when we actually have it.
            if (!userAlreadyShown && stream.userMsg) {
                const userTurn = {"role": "user", "messages": [stream.userMsg]};
                if (hasLiveTail) hist.splice(hist.length - 1, 0, userTurn);
                else hist.push(userTurn);
            }

            // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-11)
            // shape the streamed turn into the history format BEFORE pushing:
            // a raw stream turn carries neither steps nor final_messages, so
            // the pushed copy rendered as an empty bubble for the whole
            // reloadChat round-trip below - the reply visibly collapsed and
            // popped back in. streamSteps()/streamTurnSplit() are the exact
            // folds the streaming templates use, so the history DOM mounts
            // with identical content and the handoff frame is invisible.
            const handoffSplit = streamTurnSplit(stream.turn);
            stream.turn.steps = streamSteps(handoffSplit.chain);
            stream.turn.final_messages = handoffSplit.final;

            // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-12)
            // promote the live turn in place: same object, same x-for
            // index, same DOM element - the streaming branch and the
            // history branch swap INSIDE the turn element, so no node is
            // ever removed from or added to #messages and the animation
            // FLIP stays silent. the push below only runs as a fallback
            // when the live turn never made it into history (e.g. the chat
            // was reloaded or switched mid-stream, or the response was
            // empty so no token ever arrived).
            if (hist.length > 0 && hist[hist.length - 1] && hist[hist.length - 1].live === true) {
                stream.turn.live = false;
            } else {
                chat.turnHistory.push(stream.turn);
            }

            // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-11)
            // mount the pushed turns synchronously: they land exactly where
            // the viewport is about to be, so they must never render as
            // placeholders first
            Alpine.store('ui').syncMountWindows();

            // then clear the user message placeholder and the current turn
            await stream.clear();

            // finalize the stream
            responseSoundPlayed = false;
            AudioManager.play("completion");
            // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-11)
            // the handoff now mounts the history turn with the same content
            // the streaming DOM had, so the remaining distance is only the
            // action-row/finish-flag delta: glide it with the lerp chase
            // instead of snapping. the chase re-reads the target every frame
            // and survives content swaps via its MutationObserver, so the
            // finalized-turn reload landing mid-chase just extends the glide.
            await ui.scrollToBottom('messages');

            // and finally, sync back up with the backend
            await chat.reloadChat();
            await chat.reloadChats();

            // the reload can swap in finalized turn objects after the chase
            // settled, which changes content heights - chase once more so we
            // end up at the true bottom (no-op if the user scrolled up)
            await ui.scrollToBottom('messages');

            // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-12)
            // no state write here: the backend broadcasts stream_state idle
            // right after stream_complete, including on cancelled streams.

            break;
    }
}
