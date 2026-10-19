# 4-Mode System (Work / Play / Study / Normal) — Build Spec

Status: DESIGNED, NOT BUILT. This file is the source of truth for this feature.
When building, read this whole file first — do not re-derive the architecture from
scratch, and do not assume anything this file leaves open; ask Aditya instead.

## Why this file exists
"Core Modes: Work / Play / Study / Normal" was a single bare line in
TRON_PHASES_AND_MODES.md with zero design behind it. This file is the result of
actually reading the codebase (scholar.py, focus.py, revenue.py, server.py's persona
funnel) and a back-and-forth with Aditya to pin down what each mode does, before any
code gets written. Phase II's last item.

## What already exists that this feature reuses (read these first)

1. **The persona funnel — `server.py`'s `wear_persona()` → `brain_preamble()` →
   `persona_prompt(cfg) + capabilities_manifest(cfg)`.** This is the ONE place system
   -prompt text is injected into every call site (notes, small talk, web, compose,
   vision, webcam, nudge, greeting — eight sites, one funnel, by explicit design — see
   `wear_persona`'s own docstring). Mode-specific tone text plugs in HERE, inside
   `persona_prompt()` (or a new function it calls), reading the active mode. Do not
   duplicate the injection at each of the eight call sites.

2. **`scholar.py` — THE SCHOLAR.** Already a continuously-running background daemon
   (its own thread, own lock, never touches the conversational path's locks) that
   rotates topics from `scholar_syllabus.json`, researches each (web + one YouTube
   talk, transcribed via Groq), and writes 3 screened insight bullets to
   `notes/study/auto/<date>-<topic>.md`. **This already runs regardless of any mode.**
   Study Mode does not start or stop it — it changes what Galaxy DOES with it
   conversationally (see below).

3. **`focus.py` — the focus-lock accountability timer**, and the "work mode" ambient
   lighting it drives in `viewer/index.html` (checked by `preflight.py`'s
   `check_room_hour`). This is a DIFFERENT "work mode" — a visual/UI theme tied to a
   locked focus session, not a behavior mode. Do not conflate the two. (Whether the new
   Work Mode should also auto-trigger a focus.py lock is an open question below.)

4. **`revenue.py`'s pattern for a spoken on/off switch + report** —
   `parse_request()` (regex-matched sentences → `{"action": ...}`), a small JSON state
   file written atomically (`.tmp` + `os.replace`, under `hunter.file_lock`), and a
   `report()` function that reads real files and composes one spoken line. This is the
   template to copy for Mode's own switch + "what mode am I in" / "study update"
   commands — NOT revenue.py's card/confirmation mechanism (see decision below, no
   card needed here).

## Decisions made (Aditya, 2026-10-19 — do not re-litigate these)

- **Trigger: voice/chat command only** (not automatic, not a UI button, at least for
  v1). e.g. "work mode mein jao" / "study mode shuru karo" / "play mode" / "normal
  mode mein wapas aao" — exact phrasing patterns are still open, see below.
- **No confirmation card.** Unlike Revenue Mode, switching modes is low-stakes and
  reversible (it only changes tone/behavior, not real-world actions), so it switches
  **instantly** on the spoken command — no "yes" needed.
- **Work Mode = tone only, v1.** Nothing is hidden or gated. Galaxy becomes serious,
  concise, to-the-point, task-first — no small talk, minimal pleasantries. All tools
  remain available exactly as in Normal.
- **Play Mode = fun, casual tone.** Relaxed, can joke, less formal register.
- **Study Mode = tone (patient, teacher-like) PLUS two concrete behaviors:**
  1. **Recap on demand** ("study update" / "padhai update" — mirror revenue.py's
     `report()` exactly): read recent files from `notes/study/auto/`, summarize what
     the Scholar has studied, speak it back in one composed line/paragraph.
  2. **On-demand deep-dive**: when Aditya names a topic while in Study Mode, Galaxy
     researches THAT topic immediately (not waiting for the Scholar's own rotation)
     and reports back. This needs `scholar.py` to expose its gather-and-summarize
     logic as a callable for one ad-hoc topic, separate from its rotating background
     loop — currently it's only reachable through the loop. Needs a small refactor;
     see open questions.
- **Normal Mode = exactly today's behavior, unchanged.** This is the baseline/default
  — nothing about it changes. It exists as the explicit "reset" target from any other
  mode.

## Architecture sketch (for whoever builds this — confirm against the real code
before writing anything, this is a sketch, not gospel)

- `mode.py` (new, small — model it on revenue.py's state-file plumbing, not its full
  size): holds `read_state()` / `switch(mode, by)` writing a tiny
  `mode-state.json` (`{"mode": "normal", "since": ..., "by": ...}`), atomic write,
  `hunter.file_lock`. No daemon thread needed — this is not a background loop like
  Revenue Mode, it is just a state flag other code reads.
- `server.py`: a `mode_asked(question)` / `answer_mode(...)` pair following the exact
  shape of `revenue_asked` / `answer_revenue` (see server.py around §where Revenue
  Mode is wired into `answer_question()`), wired in BEFORE the persona is applied to
  that turn's reply, so the switch itself can also confirm in the new mode's voice.
- `persona_prompt(cfg)` (or wherever it lives) reads `mode.read_state()["mode"]` and
  appends a short mode-specific instruction block. Keep each mode's addition SHORT —
  a few sentences, not a rewrite of the whole persona. The underlying identity (who
  Galaxy is, who Aditya is) never changes; only register/focus does.
- Study Mode's two behaviors are NOT inside `persona_prompt` — they are two small
  routes next to `answer_mode`, reusing `scholar.py`'s file-reading and (for the
  deep-dive) a new small public function in `scholar.py` that does one research pass
  on a named topic, guarded exactly like the rest of scholar.py already is (no hand
  access, writes only under STUDY_DIR, safety-screened before it's spoken).

## Open questions — answer these before or during build, do not silently assume

1. **Exact trigger phrases.** What should Aditya actually be able to say for each
   mode (Hindi/Hinglish included)? Needs the same hand-written regex care revenue.py's
   `_START`/`_STOP`/`_REPORT` got — ask Aditya for the phrases he'd actually use.
2. **Study Mode's deep-dive: live research or notes-only?** A full `scholar.py`-style
   web+YouTube research pass is slow (seconds to minutes) and burns a Groq call budget
   per topic. A notes-only search over the existing `notes/study/auto/` corpus is
   instant but can only answer what's already been studied. Decide before building —
   may want both, picked by whether the corpus already covers the topic.
3. **Does mode revert automatically** (e.g. back to Normal after N hours idle), or
   does it stay until explicitly changed? Revenue Mode stays on until "stop" — probably
   the same default here, but confirm.
4. **UI surfacing.** TRON_PHASES_AND_MODES.md's own UI notes call for a status bar —
   should the current mode show there? That's a `viewer/index.html` change, coordinate
   with the "preserve every existing feature, UI-only when visual" rule already in
   that file.
5. **Does switching mode interrupt or announce mid-task?** Almost certainly no — it
   should just change the tone/behavior of what comes next, silently, the way
   Revenue Mode's switch does.

## What NOT to do

- Don't gate tools/features by mode in v1 — Aditya explicitly said tone-only for Work
  Mode "to start." If that changes, it's a deliberate later decision, not something to
  build preemptively.
- Don't touch `focus.py`'s existing lock-timer or `viewer/index.html`'s existing "work
  mode" lighting as part of this — they're a different, already-shipped feature. If
  Work Mode should someday trigger a focus.py lock automatically, that's a named,
  separate decision — not assumed here.
- Don't rebuild `scholar.py`'s architecture to do this — add one small callable
  function to it for the on-demand topic, keep its existing async/lock/safety laws
  intact (see its own docstring, "THE ASYNC LAW", "THE GATE HOLDS").
