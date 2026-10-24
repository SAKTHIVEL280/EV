# EV — Features

Every beta feature (`CLAUDE.md` §7) gets a spec here **before** implementation starts. A spec is
written at the start of the phase that builds it, reviewed, then implemented. Phase 0 builds no
user-facing feature; it establishes this index and the template.

Spec status: `index` (listed, no spec yet) · `draft` · `approved` · `built` · `verified`.

## Spec template

```
### F-<id> <Name>
- Phase / status:
- Behavior: what the user does, what EV does, step by step.
- Effort level: Instant / Normal / Deep / Max, and why.
- Permissions & risk: tool risk (safe / confirm / dangerous), data touched, network use.
- Settings: config keys (section.key), defaults, Settings section.
- Island states used:
- Edge cases:
- Failure messages: exact user-facing copy (short, plain, no emoji, no "!").
- Performance: budgets from CLAUDE.md §4 that apply.
- Tests: unit, golden, Windows CI, manual checklist items.
```

## Index

### Core
| ID | Feature | Phase | Status |
|---|---|---|---|
| F-001 | Typed chat in panel | 1 | built (Linux-verified) |
| F-002 | Rule router (Instant commands) | 1 | built (Linux-verified) |
| F-003 | Effort levels (setting + voice) | 1 | built (Linux-verified) |
| F-004 | Hotkey `Ctrl+Space` with IME conflict detection | 2 | built (Windows check pending) |
| F-005 | Push-to-talk | 4 (beta 2 C) | spec written |
| F-006 | Barge-in | 4 (beta 2 C) | spec written |
| F-007 | Wake word (Hey / Yo / Bro / Hello EV) | 4 (beta 2 C) | spec written |
| F-008 | Voice mode: listen, then spoken replies | 4 (beta 2 C) | spec written |
| F-009 | Earcons (wake, done, error) | 4 (beta 2 C) | spec written |
| F-010 | Voice downloads (speech recognition, voice) | 4 (beta 2 C) | spec written |

### PC
| ID | Feature | Phase | Status |
|---|---|---|---|
| F-101 | Open / close / switch apps | 3 (beta 2 B) | built (Linux + Windows CI; Windows check pending) |
| F-102 | Window snap / arrange | 3 (beta 2 B) | built (Linux + Windows CI; Windows check pending) |
| F-103 | Volume, brightness, media | 3 (beta 2 B) | built (Linux + Windows CI; Windows check pending) |
| F-104 | Wi-Fi / Bluetooth toggles | 3 (beta 2 B) | built (Linux + Windows CI; Windows check pending) |
| F-105 | Screenshots | 3 (beta 2 B) | built (Linux + Windows CI; Windows check pending) |
| F-106 | Smart clipboard (history + actions, actions off by default) | 3 (beta 2 B) | built (Linux + Windows CI; Windows check pending) |
| F-107 | File search / open / move (delete = dangerous) | 3 (beta 2 B) | built (Linux + Windows CI; Windows check pending) |
| F-108 | Reminders, timers, alarms | 3 (beta 2 B) | built (Linux + Windows CI; Windows check pending) |
| F-109 | Focus mode | 3 (beta 2 B) | built (Linux + Windows CI; Windows check pending) |
| F-110 | Multi-step UI tasks with verification | 3 (beta 2 B) | built (Linux + Windows CI; Windows check pending) |
| F-111 | Action log with undo | 3 (beta 2 B) | built (Linux + Windows CI; Windows check pending) |
| F-112 | Routines ("Work mode") | 7 | index |
| F-113 | Notification digest | 7 | index |

### Understanding
| ID | Feature | Phase | Status |
|---|---|---|---|
| F-201 | "This" awareness (selection + active window) | 3 (beta 2 B) | built (Linux + Windows CI; Windows check pending) |
| F-202 | Selection quick actions (Explain, Fix, Shorten, Reply, Translate) | 3 (beta 2 B) | built (Linux + Windows CI; Windows check pending) |
| F-203 | Screen explain (drag a region) | 5 | index |
| F-204 | Documents / PDF Q&A | 5 | index |
| F-205 | Video Q&A | 5 | index |
| F-206 | Research with sources (web) | 6 | index |
| F-207 | Semantic file search (index at idle / charging) | 6 | index |
| F-208 | Live captions | 7 | index |
| F-209 | Meeting notes | 7 | index |

### Companion
| ID | Feature | Phase | Status |
|---|---|---|---|
| F-301 | Personality presets (Friendly, Professional, Witty, Concise, Calm, Hype, Mentor, Custom) | 7 | index |
| F-302 | Daily brief | 7 | index |
| F-303 | Searchable history | 6 | index |
| F-304 | Explicit memory ("remember…", "update your memory") | 6 | index |

### System
| ID | Feature | Phase | Status |
|---|---|---|---|
| F-401 | First-run setup (models, mic test, voice, wake word, personality, benchmark) | 8 | index |
| F-402 | Compute benchmark and backend selection | 8 | index |
| F-403 | Model downloader (SHA-256, resume, offline folder) | 2 (pulled forward) | built (Linux-verified) |
| F-404 | Performance HUD (optional) | 8 | index |
| F-405 | Privacy mode (mic + screen off, visible indicator) | 8 | index |
| F-406 | Battery saver | 8 | index |
| F-407 | Plugin tools folder (declared permissions) | 8 | index |
| F-408 | Update check (GitHub Releases, user approves) | 8 | index |
| F-409 | Local crash log + "Report issue" | 8 | index |
| F-410 | Settings window (all §6.5 sections, §6.5.1 customization) | 2 | built (skeleton; Linux-verified) |
| F-411 | Auto-hide in fullscreen / screen share | 2 | index |
| F-412 | Tray icon and menu | 2 | built (Windows check pending) |
| F-413 | Arc island and its size settings | beta 2 A | built (Linux-verified; Windows check pending) |
| F-414 | Chat that stays, and New chat | beta 2 A | built (Linux-verified; Windows check pending) |
| F-415 | Settings controls: model picker, folder picker, shortcut recorder, sliders | beta 2 A | built (Linux-verified; Windows check pending) |
| F-416 | Honesty benchmark (`bench/honesty`) | beta 2 A | built (Linux-verified) |
| F-417 | Date math | 3 (beta 2 B) | built (Linux + Windows CI; Windows check pending) |
| F-418 | Confirmations and permissions | 3 (beta 2 B) | built (Linux + Windows CI; Windows check pending) |

## Specs

### F-001 Typed chat in panel
- Phase / status: 1 / built, verified on Linux with Qwen3.5-4B; Windows pending (spec written 2026-10-17, before the Phase 0 gate; see decisions.md).
- Behavior: the user opens the panel (click or, from Phase 2, the hotkey), types a message and
  presses Enter. The island shows `thinking` until the first token, then streams the reply into
  the panel. A new message while a reply is streaming cancels that reply and starts the new one.
  Esc closes the panel; an unfinished reply keeps streaming and is there when the panel reopens.
- Effort level: the request's effort (F-003); default Normal.
- Local time: the current user message (not history, not the cached system prompt) starts with
  one line, `[Local time: Saturday, October 17, 2026, 3:41 PM, India Standard Time]`, so every
  effort level knows the date, including Instant, which has no tools. Added after the 2026-10-17
  beta test, where the model gave a wrong date.
- Permissions & risk: no tools beyond those registered (Phase 1: `current_time`, safe). Tools with
  risk `confirm` or `dangerous` are refused until the confirmation UI exists (Phase 3), and the
  model is told so.
- Settings: `agent.default_effort`, `llm.*` (models, threads, context, idle unload).
- Island states used: panel (input, reply), thinking, error text in the reply area.
- Edge cases: empty or whitespace-only input is ignored by the panel; if it reaches core anyway it is answered with `chat.failed` (`empty_input`, "Type a message first."). Input over 8,000 characters is refused
  with a message. The model is still loading: the reply waits and the panel shows "Waking up".
  No model installed: a failure message. Core restarts mid-reply: the reply ends with an error line.
- Failure messages: "No model installed. Add one in Settings." · "The model stopped responding.
  Try again." · "That message is too long." · "Couldn't load the model. Details are in the log."
- Performance: Normal first token measured and recorded (spoken-word budget is Phase 4);
  prompt static prefix ≤ 1,000 tokens.
- Tests: fake-LLM agent tests (streaming, cancel, tool step, max steps, history window);
  protocol contract fixtures; manual run against Qwen3.5-4B.

### F-002 Rule router (Instant commands)
- Phase / status: 1 / built (Linux-verified).
- Behavior: before any model call, a rule table (regular expressions, no LLM) matches the
  request. A match runs its tool directly and answers from a template. Phase 1 rules:
  current time and date ("what time is it", "what's the date", "what day is it", "what's the date
  and time"). Phase 3 adds
  volume, open app, timers, media and brightness to the same table.
- Effort level: Instant. A router match always wins, whatever effort was requested.
- Permissions & risk: router rules may only call `safe` tools.
- Settings: none in Phase 1.
- Edge cases: a match that is part of a longer request ("what time is it in Tokyo") does not
  match (rules are anchored); it goes to the model.
- Failure messages: tool failure → "Couldn't do that." plus the tool's own message.
- Performance: input → reply ≤ 300 ms (budget §4).
- Tests: table-driven positive and negative phrases; latency test with the real tool.

### F-003 Effort levels
- Phase / status: 1 / built (Linux-verified).
- Behavior: four levels (CLAUDE.md §5.5). Set by `agent.default_effort` or per request by a
  spoken or typed prefix: "instant/quick", "normal", "deep", "max effort" followed by a comma or
  colon ("max effort, plan my week"). The prefix is removed before the model sees the text.
  | Level | Model | Thinking | Max steps |
  |---|---|---|---|
  | Instant | router; else default (small only when it is the only model) | off | 1 |
  | Normal | default | off | 5 |
  | Deep | largest installed | on | 15 |
  | Max | largest installed | on | 40, cancellable |
  Web search (auto for Normal, 2–3 searches for Deep, iterative for Max) is added in Phase 6.
- Model mapping: `llm.model_small`, `llm.model_default`, `llm.model_large` are filenames in
  `llm.models_dir`. Empty means not installed. Each level falls back to the nearest installed
  model (small → default → large; large → default → small). Switching models reloads llama-server
  (status `loading`).
- Settings: `agent.default_effort` (default `normal`).
- Edge cases: prefix with nothing after it → ignored as empty input. Unknown level word → not a
  prefix (text passes through unchanged).
- Tests: prefix parsing table; model fallback table; step limit enforced per level.

### F-410 Settings window
- Phase / status: 2 / skeleton built (written 2026-10-17, before the Phase 0 gate; see decisions.md).
  Verified on Linux: settings round trip through the real core; the window itself still needs the
  Windows review gate (screenshots at 100/150% DPI, light and dark), and Mica.
  Phase 2 delivers the window, every section and the settings that exist so far. Later phases add
  their settings to the same mechanism (§6.5.1 list is complete only at beta).
- Behavior: opened from the island panel (Settings) and, from the tray (Phase 2, Windows). A
  normal, focusable window: left navigation with the 13 sections of CLAUDE.md §6.5, right content.
  Each setting shows a label, a one-line description and its default; a change applies at once
  (no Save button); a Reset control returns it to the default and is hidden while the value is
  the default. Editing `config.toml` by hand updates the open window within a second.
- Effort level: n/a.
- Permissions & risk: settings change only `config.toml` through core. Core validates every
  value with the same rules as loading; an invalid value is refused and the file is unchanged.
- Settings: the settings themselves. Each config key declares its section in the schema
  (`nav`), its label (`title`) and its description.
- Sections without settings yet (Voice, Personality, Hotkeys, Permissions, Memory & History,
  Routines, Web & Privacy) show one plain line saying which feature brings them.
- Advanced: "Open config file" and the file path. Diagnostics: module states with their
  messages, config warnings, versions, "Open logs folder". About: versions, license, third-party
  notices.
- Edge cases: core not running → the window shows "EV's core isn't running." and controls are
  disabled; `config.toml` has a syntax error → values show defaults, the warning is shown and
  changes are refused with "config.toml has a syntax error. Fix it or reset it first."
- Failure messages: "That value isn't allowed." (with the rule, e.g. "Use 2048 to 131072.") ·
  "Couldn't save the setting. Details are in the log."
- Performance: change → applied and confirmed ≤ 300 ms (local file write + reload).
- Tests: core store set/reset (preserves comments and unknown keys, refuses invalid values,
  refuses on syntax error), descriptors from the schema, protocol fixtures, UI state functions.

### F-004 Global hotkey
- Phase / status: 2 / draft (written 2026-10-17, before the Phase 0 gate; see decisions.md).
- Behavior: the configured shortcut (default `Ctrl+Space`) opens the island panel with the cursor
  in the message box from anywhere; pressing it again while the panel is open closes it and
  returns focus to the previous app. It is registered at app start (before core is ready), and
  re-registered when the setting changes.
- Effort level: n/a.
- Permissions & risk: system-wide shortcut only; no key logging (only this combination reaches EV).
- Settings: `hotkeys.open_panel` (Hotkeys section), default `Ctrl+Space`. Format: one to three
  of Ctrl, Alt, Shift, Super, then a key (A–Z, 0–9, F1–F12, Space), joined by `+`. Empty turns
  the shortcut off. Never suggest `Win+Shift+T` (PowerToys Text Extractor).
- Status shown under the setting: active · off · "Another app uses this shortcut. Choose a
  different one." · IME conflict (Windows): when the shortcut is Ctrl+Space and a Chinese,
  Japanese or Korean keyboard layout is installed: "Ctrl+Space may also switch your input
  method. If typing is affected, choose Ctrl+Shift+Space."
- Edge cases: the shortcut is taken by another app → status as above, the island still opens by
  click; invalid text → refused by core's validation.
- Performance: hotkey → panel focused ≤ 150 ms (budget §4), measured on Windows.
- Tests: config validation table; Rust parsing and IME language detection; manual Windows check.

### F-413 Arc island and its size settings
- Phase / status: beta 2 stage A / built, Linux-verified (2026-10-17); Windows check pending. User request after the second Windows test:
  the idle drop looked wrong; it should be "a simple arc from the top", and its size should be
  the user's choice.
- Behavior: at rest the island is a shallow arc, a circle segment hanging from the top edge of
  the screen: `island.arc_width` wide and `island.arc_depth` deep, pure black with the faint rim.
  Hover and panel shapes are unchanged. One outline morphs between all three: the shape is a
  blend of the circle segment and the rounded body, both drawn with the same number of points,
  and the blend follows the height spring, so the arc swells into the capsule without a jump.
  The reveal area is the arc's bounding box plus `island.reveal_distance`.
- Settings (Appearance): `island.arc_width` (24–160 px, default 56) and `island.arc_depth`
  (3–24 px, default 7), both sliders with a live preview drawn as the arc on a strip of screen
  edge, and three presets (Small 36 × 5, Default 56 × 7, Large 88 × 10). The depth is capped at
  half the width (a half circle) when drawn. Changes apply to the island at once.
- Island states used: idle (arc), hover, panel.
- Edge cases: values outside the range are refused by core; a hand-edited depth over half the
  width draws a half circle; reduced motion swaps shapes with a cross-fade.
- Failure messages: the standard "That value isn't allowed. Use 24 to 160."
- Performance: same morph budgets (first frame ≤ 120 ms, complete ≤ 350 ms, 60 fps).
- Tests: arc geometry (endpoints on the edge, depth at the center, depth cap, point count equal
  to the body outline, blend endpoints), settings descriptors, pointer bounds; specimen rendered
  for the user before the default is locked.

### F-414 Chat that stays, and New chat
- Phase / status: beta 2 stage A / built, Linux-verified (2026-10-17); Windows check pending. User report: closing the panel (Esc) lost
  the conversation.
- Behavior: the panel shows the whole session as a scrollable list, oldest at the top, newest at
  the bottom, and scrolls to the newest message when it opens or a reply streams (unless the user
  has scrolled up to read). Closing the panel by any route (Esc, click outside, hotkey) keeps the
  session and any reply still streaming. A New chat button (icon, next to Settings) clears the
  list and starts a new session: the running reply is cancelled and core's history is cleared
  (`chat.reset`, additive protocol message). Quitting EV ends the session; the next launch starts
  empty. Saved, searchable history is F-303 (stage E).
- Effort level: n/a.
- Permissions & risk: the session lives in memory only (UI and core); nothing is written to disk.
- Settings: none.
- Island states used: panel.
- Edge cases: New chat while a reply streams → the reply stops ("Stopped" is not shown, the list
  is cleared); core restarts → the list stays, core's history is empty, so a note "EV restarted.
  Earlier messages aren't remembered." is added once; a long session is capped at the last 50
  exchanges in the panel (core's history window is unchanged).
- Failure messages: "Couldn't start a new chat. Try again."
- Tests: chat state (append, stream into the right turn, reset, cap, restart note), core
  `chat.reset` clears history and cancels the turn, protocol fixtures.

### F-415 Settings controls: model picker, folder picker, shortcut recorder, sliders
- Phase / status: beta 2 stage A / built, Linux-verified (2026-10-17); Windows check pending. User report: model and shortcut fields
  needed typing exact text the user cannot know.
- Behavior: each setting declares a control in the schema (`widget`), so no setting needs typing
  unless it is free text:
  - `model`: a menu of installed models for that role, each with its name, size and summary
    from the catalog, plus files found in the models folder that are not in the catalog (shown
    by file name), and "None". When nothing is installed: "No model installed" and a Download
    button that goes to the model list.
  - `folder`: the path, a Choose folder button (native dialog) and Reset.
  - `shortcut`: a Record button; while recording, the next key combination is captured
    (Ctrl / Alt / Shift / Win plus one key) and saved. Esc cancels; a key without a modifier is
    refused with "Add Ctrl, Alt, Shift or Win." Clear turns the shortcut off. The status line
    (active, taken, IME note) stays.
  - `slider`: integers with bounds get a slider plus the number and unit; the value applies when
    the slider is released or a key changes it.
- Design pass over the whole window (DESIGN.md §6): a page header with a one-line summary per
  section, settings grouped under subheadings, values aligned on one column, quieter defaults,
  every state (core not running, loading, error, disabled) designed.
- Settings: `widget` hints on `llm.model_*` (model), `llm.models_dir` (folder),
  `hotkeys.open_panel` (shortcut), bounded integers (slider unless `widget` says otherwise).
- Edge cases: the configured model file is missing → the menu shows "Missing: <file>" selected
  and the description says "This file isn't in the models folder."; recording while another app
  holds the shortcut → saved, then the status line says it is taken.
- Failure messages: "Add Ctrl, Alt, Shift or Win." · "That key can't be used in a shortcut." ·
  "Couldn't open the folder picker."
- Tests: descriptors carry `widget`; shortcut capture → config string table (letters, digits,
  F-keys, Space, modifiers, refusals); model menu entries from models state; slider commit.

### F-416 Honesty benchmark
- Phase / status: beta 2 stage A / built, Linux-verified (2026-10-17); Windows check pending.
- Behavior: `bench/honesty/` runs fixed questions (made-up entities, niche real facts, common
  facts, help requests) against a real model through the app's own prompt and sampling, scores
  each answer (invented / not sure / right / wrong / refused) and writes a dated result file.
  Used before any prompt or model change; results history is kept in the folder.
- Pass mark for beta 2: Qwen3.5-4B invents nothing on made-up questions and refuses no help
  request. Target, reported separately: every common fact answered right without hedging (first
  runs: 8 and 9 of 10; the Titanic director is the miss).
- Tests: the scorer has unit tests; the run itself is manual (needs a model).

### F-412 Tray icon and menu
- Phase / status: 2 / draft.
- Behavior: EV shows a tray icon with the tooltip "EV". Left click opens the island panel. The
  menu (right click) has: Open EV, Settings, Quit EV.
- Edge cases: tray unavailable (some Linux desktops) → logged once; the island and hotkey still
  work.
- Tests: manual on Windows (light and dark taskbar: the icon must be visible on both; tracked for
  the Phase 2 design pass).

### F-403 Model downloader
- Phase / status: pulled forward from Phase 8 to the Phase 2 fix round (user request after the
  first Windows test, 2026-10-17: nothing can be tried without a model).
- Behavior: when no model is installed, the island panel shows the model choices instead of the
  chat. Settings → Models & Performance shows the same list at any time. Choosing Download starts
  it; the row shows percent, speed and time left, and a Stop control. A dropped connection is
  retried automatically (3 times, resuming where it stopped). A stopped or interrupted download
  keeps its partial file and resumes from there, also after EV restarts. The finished file is
  checked against its SHA-256, then renamed into place. If the model's slot (`llm.model_small`,
  `model_default` or `model_large`) is empty, it is filled, and the default model warms at once.
- Catalog (`core/ev_core/models/manifest.json`, CLAUDE.md §10.6): Qwen3.5 2B / 4B / 9B Q4_K_M from
  `unsloth/Qwen3.5-*-GGUF` at pinned revisions, with size and SHA-256. 4B is recommended.
- Effort level: n/a.
- Permissions & risk: network to huggingface.co (and its CDN redirect) only, for files in the
  catalog. Writes only inside the models folder. Never deletes a finished model.
- Settings: `llm.models_dir` (empty: `<data>/models`), `llm.model_*` slots.
- Island states used: panel (choices, progress), hover status ("Downloading 42%").
- Edge cases: not enough disk space; offline; server ignores the resume request (restart from
  zero); file damaged (checksum); file already present (checked by size, shown as installed);
  models folder not writable; two download requests for the same model (second ignored).
- Failure messages: "Not enough free space. EV needs {n} GB more." · "Couldn't reach Hugging Face.
  Check the connection and try again." · "The download was damaged. Try again." · "Couldn't save
  the model. Check the models folder in Settings."
- Performance: hashing and file writes run off the event loop; progress is sent at most 4 times a
  second.
- Tests: downloader against a local HTTP server (full, resume with Range, server ignores Range,
  checksum mismatch, cancel, retry after a dropped connection, disk space); catalog validation;
  module state and config filling; protocol fixtures; Rust conversion; UI formatting.


## Phase 3 specs (beta 2 stage B, written 2026-10-17)

Shared by every PC tool:
- Tools live in core (`ev_core/tools/`) and act on the PC only through the `PcControl` interface
  (`ev_core/interfaces/pc.py`). Windows: the real implementation (UI Automation via pywinauto,
  Win32 and WinRT calls). Linux (development): a fake that keeps state in memory and records
  every call, so the agent, confirmations and the action log run end to end; Windows behavior
  is proven by tool tests on the `windows-latest` CI runner and the user's checklist.
- Risk (CLAUDE.md §5.4): `safe` runs at once; `confirm` asks in the island (yes / no) unless the
  user set the tool to Allow; `dangerous` asks every time, whatever the setting. Settings →
  Permissions lists every tool with Allow / Ask / Block (F-418).
- Every action that changes something is recorded in the action log (F-111) with an undo when
  one exists. After each step the tool reads the state back (verification, CLAUDE.md §5.4.6);
  on a mismatch it retries once, then reports the mismatch so EV asks the user.
- Tool descriptions are at most 25 words (cached prompt prefix ≤ 1,000 tokens with all tools).
- Failure copy is short and plain; the model receives `error: ...` with the reason.

### F-101 Open / close / switch apps
- Phase / status: 3 (beta 2 B) / built (2026-10-17); Linux end to end with the fake PC, Windows by CI tool tests; the user's Windows check pending.
- Behavior: `open_app(name)` finds the app by name among Start menu shortcuts and installed
  apps (fuzzy, best match) and starts it; `switch_to_app(name)` brings its window to the front;
  `close_app(name)` asks the app to close normally (it may ask to save); `list_apps()` returns
  the open windows. "Open Notepad" and "switch to Chrome" also go through the router (Instant).
- Risk: open, switch, list `safe`; close `confirm` (unsaved work).
- Verification: after open, a new window of that app exists within 10 s; after switch, it is the
  foreground window; after close, its windows are gone (or a save prompt is up: reported).
- Undo: open → close it; close → open it again.
- Failure copy: "Couldn't find an app called {name}." · "{name} didn't open." · "{name} is
  asking to save first."
- Tests: name matching table; fake backend in CI (Linux); Windows CI opens, switches to and
  closes Notepad.

### F-102 Window snap / arrange
- Phase / status: 3 (beta 2 B) / built (2026-10-17); Linux end to end with the fake PC, Windows by CI tool tests; the user's Windows check pending.
- Behavior: `arrange_window(app, position)` with position left, right, top, bottom, top-left,
  top-right, bottom-left, bottom-right, maximize, minimize, restore, center. Uses the work area
  of the window's monitor. App omitted: the window the user was in before opening EV.
- Risk: `safe`. Undo: the previous position and state. Verification: the window rectangle.
- Failure copy: "Couldn't find that window."
- Tests: rectangle math per position and DPI; Windows CI snaps Notepad left and restores it.

### F-103 Volume, brightness, media
- Phase / status: 3 (beta 2 B) / built (2026-10-17); Linux end to end with the fake PC, Windows by CI tool tests; the user's Windows check pending.
- Behavior: `set_volume(level? 0–100, change? ±, mute? bool)`, `set_brightness(level?, change?)`,
  `media(action: play_pause | next | previous | stop)`. Router covers "volume up/down/to 30",
  "mute", "brightness 50", "next song", "pause".
- Risk: `safe`. Undo: the previous level / mute state. Verification: read the level back.
- Edge cases: no brightness control (desktop monitor without DDC/CI) → "This screen's brightness
  can't be changed from Windows."; no media playing → media keys are sent anyway.
- Tests: clamping and step math; Windows CI reads and restores the volume.

### F-104 Wi-Fi / Bluetooth toggles
- Phase / status: 3 (beta 2 B) / built (2026-10-17); Linux end to end with the fake PC, Windows by CI tool tests; the user's Windows check pending.
- Behavior: `set_radio(kind: wifi | bluetooth, on: bool)` through Windows radio control.
- Risk: turning Wi-Fi off `confirm` (EV's web search and the user's connection stop); others
  `safe`. Undo: the previous state. Verification: read the radio state back.
- Failure copy: "This PC has no Bluetooth." · "Windows didn't allow EV to change Wi-Fi."
- Tests: fake backend; manual Windows check (CI runners have no radios).

### F-105 Screenshots
- Phase / status: 3 (beta 2 B) / built (2026-10-17); Linux end to end with the fake PC, Windows by CI tool tests; the user's Windows check pending.
- Behavior: `take_screenshot(area: screen | window)` saves a PNG to Pictures\Screenshots
  (`EV 2026-10-17 15.41.07.png`) and says where. Region capture by drag is F-203.
- Risk: `safe` (stays on the PC). Undo: move the file to the Recycle Bin.
- Tests: file naming; Windows CI captures the screen and checks the PNG size.

### F-106 Smart clipboard
- Phase / status: 3 (beta 2 B) / built (2026-10-17); Linux end to end with the fake PC, Windows by CI tool tests; the user's Windows check pending.
- Behavior: with `clipboard.history` on (default on), EV keeps the last 25 copied texts in memory
  only (never on disk; text matching the sensitive-data filter is not kept). Tools:
  `read_clipboard()`, `write_clipboard(text)`, `clipboard_history(count)`. "Fix the text I
  copied" → read, rewrite, write back, say "Copied. Paste it where you want it." Clipboard
  actions (offering an action automatically when something is copied) stay off by default
  (`clipboard.actions`).
- Risk: read `safe` (data, never instructions); write `safe`. Undo: write restores the previous
  clipboard text.
- Tests: history ring and filter; fake clipboard; Windows CI round-trip.

### F-107 File search / open / move
- Phase / status: 3 (beta 2 B) / built (2026-10-17); Linux end to end with the fake PC, Windows by CI tool tests; the user's Windows check pending.
- Behavior: `find_files(query, kind?, folder?)` searches file names in the user's folders
  (Desktop, Documents, Downloads, Pictures, Music, Videos) and returns the newest matches;
  `open_file(path)` opens it with its default app; `move_file(path, destination)`;
  `delete_file(path)` sends it to the Recycle Bin (never a permanent delete).
- Risk: find, open `safe`; move `confirm`; delete `dangerous`. Paths outside the user's profile
  are refused unless the user named them in this request.
- Undo: move → move back. Delete has no undo in EV: the reply says the file is in the Recycle
  Bin, where Windows restores it.
- Failure copy: "Couldn't find {query}." · "That file is in use."
- Tests: search ranking on a temp tree; move/undo; delete goes to the trash (send2trash).

### F-108 Reminders, timers, alarms
- Phase / status: 3 (beta 2 B) / built (2026-10-17); Linux end to end with the fake PC, Windows by CI tool tests; the user's Windows check pending.
- Behavior: one `timer` tool with the actions timer (minutes), reminder (text, at), alarm (at,
  label), list and cancel (id). They survive restarts (stored in `ev.db`, migration 001).
  When one fires, the island opens to the hover shape with the text and stays until dismissed
  or 60 s pass; missed ones (PC off) are shown once at the next start, marked missed.
- Risk: `safe`. Undo: cancel.
- Router: "set a timer for 10 minutes", "remind me at 5 to call mom".
- Tests: parsing durations and times ("in 10 minutes", "at 5 pm", "tomorrow at 9"), scheduler
  with a fake clock, persistence across restart.

### F-109 Focus mode
- Phase / status: 3 (beta 2 B) / built (2026-10-17); Linux end to end with the fake PC, Windows by CI tool tests; the user's Windows check pending.
- Behavior: `focus_mode(on, minutes?)` makes EV quiet: no proactive messages, timers show without
  opening the island (alarms still do), and the arc shows a small focus mark. Windows has no
  supported API to switch its own Do Not Disturb, so EV says so and offers to open the Windows
  setting (`ms-settings:quiethours`). Ends after `minutes` or when turned off.
- Risk: `safe`. Settings: none.
- Tests: state machine with a fake clock.

### F-110 Multi-step UI tasks with verification
- Phase / status: 3 (beta 2 B) / built (2026-10-17); Linux end to end with the fake PC, Windows by CI tool tests; the user's Windows check pending.
- Behavior: `ui_snapshot(app?)` returns the interactive elements of a window (id, role, name,
  value, enabled) from UI Automation, at most 60, in reading order; `ui_click(id)`,
  `ui_type(id, text)`, `ui_keys(keys)`. Each action re-reads the window and returns what
  changed. Ids are valid only for the snapshot they came from.
- Risk: snapshot `safe`; click, type, keys `confirm`, asked once per request: one yes covers the
  remaining steps of that request. An element whose name means sending, buying, paying,
  deleting, installing or posting makes that step `dangerous` (asked separately).
- Tests: element filtering and ordering on a recorded tree; Windows CI types into Notepad and
  reads it back; the golden test plans "open Notepad and type hello" as tool calls.

### F-111 Action log with undo
- Phase / status: 3 (beta 2 B) / built (2026-10-17); Linux end to end with the fake PC, Windows by CI tool tests; the user's Windows check pending.
- Behavior: every action that changes something is written to `ev.db` (time, tool, one-line
  summary, undo data). The island shows "Undo" under each reply that made a change; saying or
  typing "undo" or "undo that" undoes the most recent undoable action (router, instant). Kept 30
  days. A searchable list of past actions comes with searchable history (F-303, stage E).
- Tests: log and undo per tool with the fake backend; retention.

### F-201 "This" awareness
- Phase / status: 3 (beta 2 B) / built (2026-10-17); Linux end to end with the fake PC, Windows by CI tool tests; the user's Windows check pending.
- Behavior: when the panel opens (hotkey or click), EV reads the text selected in the app the
  user was in (UI Automation text selection of its front-most window; no clipboard tricks) and
  that app's name and window title. The panel
  shows a removable chip ("Selected text from Notepad"); the next request receives it as
  context (≤ 300 tokens, trimmed in the middle), marked as data.
- Tools: a request with a selection is about that text, so it gets the PC tools only when its own
  words ask for a PC action (an earlier tool turn doesn't count). Risky steps after it always ask,
  because the selection is outside text (CLAUDE.md §8).
- Privacy: captured only on the hotkey, never in the background; not stored.
- Tests: trimming; fake selection; Windows CI selects text in Notepad and reads it.

### F-202 Selection quick actions
- Phase / status: 3 (beta 2 B) / built (2026-10-17); Linux end to end with the fake PC, Windows by CI tool tests; the user's Windows check pending.
- Behavior: with a selection chip present, the panel offers Explain, Fix, Shorten, Reply,
  Translate (to English; other languages are out of scope). The conversation shows the action's
  name; the request the model gets says exactly what to return. The result has Copy and Replace
  (Replace types the result into the selection's app through UI Automation, so it needs that
  app's text control to accept it; otherwise it copies and says "Copied. Paste it to replace.").
- Risk: Replace is the user's own click, so it runs without a second question.
- Tests: action prompts; fake replace; Windows CI replaces text in Notepad.

### F-417 Date math
- Phase / status: 3 (beta 2 B) / built (2026-10-17); Linux end to end with the fake PC, Windows by CI tool tests; the user's Windows check pending. Found in the beta test: "days until Christmas" was answered wrong.
- Behavior: `date_math(operation: days_between | add | weekday, ...)` computes in the local time
  zone. The model calls it for any date arithmetic.
- Risk: `safe`. Tests: table of cases, leap years, past dates.

### F-418 Confirmations and permissions
- Phase / status: 3 (beta 2 B) / built (2026-10-17); Linux end to end with the fake PC, Windows by CI tool tests; the user's Windows check pending.
- Behavior: a `confirm` or `dangerous` step pauses the turn and the island shows the `confirm`
  state: one line saying exactly what will happen ("Close Notepad?", "Move report.pdf to
  Documents?", shell commands shown verbatim) with Yes and No (Enter / Esc). No answer in 60 s
  counts as No. Steps proposed right after reading untrusted content (web, files, screen,
  clipboard) always ask. Settings → Permissions: every tool with Allow / Ask / Block
  (`permissions.<tool>`); `dangerous` tools offer only Ask / Block.
- Protocol: `tool.confirm` (core → app) and `tool.answer` (app → core), additive.
- Tests: policy table (risk × setting × untrusted); timeout; protocol fixtures; island state.

### F-008 Voice mode: listen, then spoken replies
- Phase / status: 4 (beta 2 C) / spec written 2026-10-24, before the code. User decisions of
  2026-10-17 (decisions.md "Voice mode").
- Behavior: the hotkey (F-004) opens the panel already listening: the earcon plays, the island
  shows a live level and the words as they are recognized. When the user stops talking (end of
  speech detected by Moonshine's built-in voice activity detection), the words are sent as a chat
  message, exactly as if typed, marked as spoken. Typing a character in the message box switches
  to text: the mic turns off and nothing is spoken for that request.
  A spoken request gets a spoken reply: the reply is spoken sentence by sentence as it streams
  (first sentence as soon as it is complete). If the turn starts a tool before saying anything,
  EV first says "Okay, on it." so the user knows it heard. Typed requests get text only.
  After a spoken reply EV listens for a follow-up for 5 s (`voice.follow_up`); no speech → the
  mic closes. No speech within 8 s of opening → the mic closes and the panel says "Didn't hear
  anything."
- Panel: a mic button next to the message box shows and toggles listening; while listening the
  box shows the live words. The island shows `listening` (level) and `speaking` shapes when the
  panel is closed (follow-up, wake word), with the mic indicator always visible while the mic is
  open (CLAUDE.md §8).
- Effort level: the request's (F-003).
- Permissions & risk: the mic opens only on the hotkey, the mic button, a follow-up window, or
  the wake word (F-007). Audio is never stored or sent anywhere; only the recognized text is kept
  as chat history.
- Engines: speech recognition Moonshine v2 streaming, small (default) or tiny
  (`voice.recognizer`); speech Kokoro through moonshine-voice (decisions.md 2026-10-24).
  Both load on first use and unload with the language model's idle timer.
- Settings ([voice], Voice section): `enabled` (on), `speak_replies` (when I speak · always ·
  never), `voice` (Kokoro voices; default Heart), `speed` (70–150 %, 100), `volume` (0–100, 80),
  `recognizer` (small · tiny), `follow_up` (on).
- Edge cases: voice not downloaded → the panel says "Voice isn't installed. Download it in
  Settings → Voice." with a button that opens it; no microphone → "No microphone found.";
  mic in use or blocked by Windows privacy settings → "EV can't use the microphone. Check
  Windows Settings → Privacy → Microphone."; a new request while speaking stops the speech;
  closing the panel stops listening but not speaking; the hotkey while speaking stops speaking
  and listens (barge-in by key).
- Failure messages: as above, plus "Couldn't start voice. Details are in the log."
- Performance: Normal first spoken word ≤ 2 s (input received → first audio played); recognition
  final ≤ 300 ms after end of speech is detected.
- Tests: voice module with fake mic, recognizer, synthesizer and speaker (listen → chat request
  marked spoken, sentence splitting, acknowledgement, follow-up and silence timeouts, typing
  stops the mic, unload); real-engine test (synthesize a sentence, recognize it back) when the
  voice files are present; manual Windows check with a real mic.

### F-005 Push-to-talk
- Phase / status: 4 (beta 2 C) / spec written 2026-10-24.
- Behavior: holding the hotkey longer than 400 ms is push-to-talk: EV listens while it is held
  and sends what was said on release (no end-of-speech wait). A short press is the normal
  toggle (F-008).
- Settings: the hotkey itself. Edge cases: released before any speech → nothing is sent.
- Tests: Rust press/release timing rule; voice module "end now" path.

### F-006 Barge-in
- Phase / status: 4 (beta 2 C) / spec written 2026-10-24.
- Behavior: while EV speaks, the mic stays open (spoken turns only). When the user starts
  talking, speech stops within 100 ms and EV listens; what they say becomes the next request
  (which cancels the old reply). The hotkey does the same.
- Echo guard: without echo cancellation, EV's own voice reaches the mic through laptop
  speakers. Speech only counts as barge-in when the mic level is clearly above the echo level
  measured during the current reply (ratio `voice.barge_in` sensitivity, internal default 2.5x).
  With headphones the echo level is near zero, so any speech counts.
- Performance: voice activity detected → audio output stopped ≤ 100 ms.
- Tests: fake speaker and mic: speech during playback stops it, echo-level audio does not.

### F-009 Earcons
- Phase / status: 4 (beta 2 C) / spec written 2026-10-24.
- Behavior: three short sounds, generated in code (no audio files): wake/listening (two soft
  rising tones, 120 ms), done (one soft falling tone, 140 ms; plays when the mic closes after a
  request was taken), error (two low soft pulses, 200 ms). No jingles.
- Settings: `voice.earcons_volume` (0–100, 50; 0 = off). Silent when Windows Do Not Disturb /
  Focus is on.
- Performance: wake detection or hotkey → earcon start ≤ 250 ms.
- Tests: generated length, peak level and fade-in/out (no clicks); DND rule.

### F-010 Voice downloads
- Phase / status: 4 (beta 2 C) / spec written 2026-10-24.
- Behavior: voice files are not in the installer. Settings → Voice lists two packs: "Speech
  recognition" (Moonshine small streaming, 143 MB; tiny 45 MB) and "Voice" (Kokoro, about
  110 MB with the G2P files, plus 0.5 MB per voice). Download / Cancel / progress like models
  (F-403): pinned URLs on download.moonshine.ai, SHA-256 per file, resume. Files land in
  `models/voice/` inside the models folder. First-run setup (F-401) downloads them later.
- Edge cases: offline → "Couldn't reach the download server. Try again later."; a changed file
  on the server fails its SHA-256 → "The download was damaged. Try again." (nothing installed).
- Tests: catalog validation (hosts, hashes), multi-file download with a fake server, partial
  pack not reported installed.

### F-007 Wake word
- Phase / status: 4 (beta 2 C) / spec written 2026-10-24.
- Behavior: with `voice.wake_word` on, EV listens for its wake phrase ("Hey EV" default; Yo EV,
  Bro EV, Hello EV) with a small always-on detector (openWakeWord-style: shared mel-spectrogram
  and speech-embedding models plus one small classifier per phrase, trained for EV from
  synthetic speech). Detection → earcon → listening as with the hotkey, with the island showing
  the listening shape (no focus taken; the panel stays closed unless the user opens it).
- Settings: `voice.wake_word` (on), `voice.wake_phrase`, `voice.wake_sensitivity` (low · normal ·
  high). Pauses on battery when `battery` setting says so (F-406), in privacy mode (F-405), and
  while a fullscreen app runs.
- Performance: idle CPU (wake word only) ≤ 3 % total; detection → chime ≤ 250 ms.
- Tests: detector on generated positive and negative clips (recall and false accepts per hour
  recorded in PERFORMANCE.md); module tests with a fake detector.

