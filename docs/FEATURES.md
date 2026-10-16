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
| F-001 | Typed chat in panel | 1 | index |
| F-002 | Rule router (Instant commands) | 1 | index |
| F-003 | Effort levels (setting + voice) | 1 | index |
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

(none yet — Phase 1 specs F-001 to F-003 are written at the start of Phase 1)
