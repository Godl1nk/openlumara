/* alpine.js directive that adds autoscrolling to any element
 * by adding x-auto-scroll to your element
 */
// -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-25) harness:openlumara
// THE NATIVE PUMP (same mechanism as the chat follow in stores/ui.js):
// native smooth scroll exposes no speed/duration parameter - the curve
// belongs to the browser - so instead of one hop at the true bottom, the
// pump re-aims a browser-eased hop at a FRACTION of the remaining gap
// every animation frame. per-frame retargeting keeps Chrome's velocity-
// blended smooth-scroll animation continuously in cruise (slower re-aim
// rates let each short hop finish its ease-out between aims, which reads
// as micro stop-and-go), and re-reading the bottom per hop folds streamed
// growth into one glide. the browser owns 100% of the easing; the pump
// only picks the targets.
//
// knobs, read fresh per hop so they can be tweaked live from the devtools
// console (shared with stores/ui.js; first file to load initialises):
//   window.NATIVE_AUTOSCROLL_DAMP  fraction of the gap closed per hop AT A
//                                  60HZ REFERENCE - the pump converts it by
//                                  actual frame time (see dampFor), so the
//                                  glide runs at the same speed on 60/90/
//                                  120/144Hz screens and through refresh
//                                  hiccups. 1 = plain hop, 0.15 = relaxed
//                                  glide, 0.07 = very languid
//   window.NATIVE_PUMP_MS          throttle: 0 = every frame; raise it
//                                  only to deliberately cut retarget
//                                  frequency (DAMP then needs raising to
//                                  keep the overall speed)
window.NATIVE_AUTOSCROLL_DAMP ??= 0.15;
window.NATIVE_PUMP_MS ??= 0;

function autoScroll(el) {
  let isAtBottom = true;
  let pumpRaf = null;
  let pumpLast = 0;

  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

  const checkBottom = () => {
    const threshold = 50; // px tolerance
    isAtBottom = (el.scrollHeight - el.scrollTop - el.clientHeight) < threshold;
  };

  const stopPump = () => {
    if (pumpRaf !== null) {
      cancelAnimationFrame(pumpRaf);
      pumpRaf = null;
    }
  };

  // DAMP is a per-hop fraction at a 60Hz reference, but rAF fires at the
  // display's real refresh rate - so convert by elapsed frame time:
  // 1 - (1-DAMP)^(dt/16.67ms). mathematically identical at 60Hz, and on a
  // 120Hz panel each hop automatically shrinks so the glide runs at the
  // same on-screen speed instead of compounding double-fast. dt is capped
  // so a backgrounded tab or long stall converges with one big eased hop
  // instead of an instant teleport.
  const dampFor = (dt) => {
    const base = window.NATIVE_AUTOSCROLL_DAMP;
    if (base >= 1) return 1;
    return 1 - Math.pow(1 - base, Math.min(dt, 100) / (1000 / 60));
  };

  // one hop: a browser-smooth scrollTo aimed at dampFor(dt) of the
  // remaining gap. returns false once the bottom is reached (1px +
  // instant snap), which stops the loop and re-evaluates the resting
  // position.
  const pumpHop = (dt) => {
    const bottom = el.scrollHeight - el.clientHeight;
    const remaining = bottom - el.scrollTop;
    if (remaining <= 1) {
      el.scrollTo({ top: bottom, behavior: 'instant' });
      stopPump();
      checkBottom();
      return false;
    }
    el.scrollTo({ top: el.scrollTop + remaining * dampFor(dt),
                  behavior: 'smooth' });
    return true;
  };

  // rAF driver: hop every animation frame (throttled by NATIVE_PUMP_MS).
  // dt comes from the rAF timestamps, so hop size adapts to whatever
  // refresh rate - or hiccup - the display throws at it.
  const pumpStep = (now) => {
    const dt = now - pumpLast;
    if (dt >= window.NATIVE_PUMP_MS) {
      pumpLast = now;
      if (!pumpHop(dt)) {
        pumpRaf = null;
        return;
      }
    }
    pumpRaf = requestAnimationFrame(pumpStep);
  };

  // user input wins: give up the pump; onScroll resumes bottom-tracking
  const giveUp = () => {
    stopPump();
    el.removeEventListener('wheel', giveUp);
    el.removeEventListener('touchstart', giveUp);
  };

  const onScroll = () => {
    // ignore the intermediate positions of our own pump; the resting
    // position is checked when the pump stops
    if (pumpRaf !== null) return;
    checkBottom();
  };

  el.addEventListener('scroll', onScroll);

  const observer = new MutationObserver(() => {
    if (!isAtBottom) return;

    if (reducedMotion.matches) {
      el.scrollTo({ top: el.scrollHeight, behavior: 'instant' });
      return;
    }

    if (pumpRaf === null) {
      el.addEventListener('wheel', giveUp, { passive: true });
      el.addEventListener('touchstart', giveUp, { passive: true });
      // seed with the current time so the very first hop sees a real
      // frame-sized dt instead of "time since page load"
      pumpLast = performance.now();
      pumpRaf = requestAnimationFrame(pumpStep);
    }
  });

  observer.observe(el, { childList: true, subtree: true });

  return () => {
    stopPump();
    el.removeEventListener('wheel', giveUp);
    el.removeEventListener('touchstart', giveUp);
    el.removeEventListener('scroll', onScroll);
    observer.disconnect();
  };
}
