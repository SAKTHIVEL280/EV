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
| F-004 | Hotkey `Ctrl+Space` with IME conflict detection | 2 | index |
| F-005 | Push-to-talk | 4 | index |
| F-006 | Barge-in | 4 | index |
| F-007 | Wake word (Hey / Yo / Bro / Hello EV) | 4 | index |

### PC
| ID | Feature | Phase | Status |
|---|---|---|---|
| F-101 | Open / close / switch apps | 3 | index |
| F-102 | Window snap / arrange | 3 | index |
| F-103 | Volume, brightness, media | 3 | index |
| F-104 | Wi-Fi / Bluetooth toggles | 3 | index |
| F-105 | Screenshots | 3 | index |
| F-106 | Smart clipboard (history + actions, actions off by default) | 3 | index |
| F-107 | File search / open / move (delete = dangerous) | 3 | index |
| F-108 | Reminders, timers, alarms | 3 | index |
| F-109 | Focus mode | 3 | index |
| F-110 | Multi-step UI tasks with verification | 3 | index |
| F-111 | Action log with undo | 3 | index |
| F-112 | Routines ("Work mode") | 7 | index |
| F-113 | Notification digest | 7 | index |

### Understanding
| ID | Feature | Phase | Status |
|---|---|---|---|
| F-201 | "This" awareness (selection + active window) | 3 | index |
| F-202 | Selection quick actions (Explain, Fix, Shorten, Reply, Translate) | 3 | index |
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
| F-403 | Model downloader (SHA-256, resume, offline folder) | 8 | index |
| F-404 | Performance HUD (optional) | 8 | index |
| F-405 | Privacy mode (mic + screen off, visible indicator) | 8 | index |
| F-406 | Battery saver | 8 | index |
| F-407 | Plugin tools folder (declared permissions) | 8 | index |
| F-408 | Update check (GitHub Releases, user approves) | 8 | index |
| F-409 | Local crash log + "Report issue" | 8 | index |
| F-410 | Settings window (all §6.5 sections, §6.5.1 customization) | 2 | index |
| F-411 | Auto-hide in fullscreen / screen share | 2 | index |

## Specs

### F-001 Typed chat in panel
- Phase / status: 1 / built, verified on Linux with Qwen3.5-4B; Windows pending (spec written 2026-10-17, before the Phase 0 gate; see decisions.md).
- Behavior: the user opens the panel (click or, from Phase 2, the hotkey), types a message and
  presses Enter. The island shows `thinking` until the first token, then streams the reply into
  the panel. A new message while a reply is streaming cancels that reply and starts the new one.
  Esc closes the panel; an unfinished reply keeps streaming and is there when the panel reopens.
- Effort level: the request's effort (F-003); default Normal.
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
  current time and date ("what time is it", "what's the date", "what day is it"). Phase 3 adds
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
  | Instant | router; else smallest installed | off | 1 |
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
