# EV — Roadmap

Source of truth for build order: `CLAUDE.md` §12. This file expands each phase into deliverables and
a "done when" gate. A phase starts only after the previous gate passes. Gates reference the budgets
in `CLAUDE.md` §4 and `docs/PERFORMANCE.md`.

Status legend: `planned` · `in progress` · `blocked (reason)` · `done (date)`.

| Phase | Name | Status |
|---|---|---|
| 0 | Foundation & spikes | in progress (Linux foundation done 2026-10-17; waiting on CI run + Windows spikes) |
| 1 | Brain | in progress (provisional, branch `feat/phase-1-brain`; started before the Phase 0 gate, see decisions.md) |
| 2 | Island | planned |
| 3 | Tools | planned |
| 4 | Voice | planned |
| 5 | Vision & media | planned |
| 6 | Memory & search | planned |
| 7 | Companion features | planned |
| 8 | First-run & system | planned |
| 9 | Polish & beta (`0.1.0-beta.1`) | planned |
| 10 | Public release (`1.0.0`) | planned |

---

## Phase 0 — Foundation & spikes

Goal: a repository where every later module has a home, a stable wire protocol, versioned config,
structured logging, CI, and evidence that the three risky platform assumptions hold on Windows 11.

### Deliverables

Foundation (developed and verified on Linux):
1. Repository layout per `CLAUDE.md` §9: `protocol/`, `app/`, `core/`, `bench/`, `scripts/`,
   `.github/workflows/`, `THIRD_PARTY_NOTICES.md`.
2. Protocol v1 (`protocol/`): JSON Schema for the message envelope and the Phase 0 message set
   (`hello`, `hello.ack`, `ping`, `pong`, `error`, `shutdown`). Python and Rust types generated
   from the schemas; CI fails when generated code is stale. Contract tests on both sides.
3. Core skeleton (`core/ev_core`): package layout, WebSocket server (127.0.0.1, random port,
   per-session token), event bus, module registry with per-module status, versioned config
   (`config.toml`, migrations, unknown keys preserved, invalid values fall back with a warning,
   hot reload), structured rotating logs, data directory resolution.
4. App skeleton (`app/`): Tauri 2 + Svelte 5 + TypeScript strict, core supervisor with restart
   backoff (1 s, 2 s, 5 s, then stop and report), Rust ↔ core handshake, typed Tauri commands via
   tauri-specta, structured rotating logs.
5. Tooling: version single-source check, protocol codegen check, llama.cpp binary fetch script with
   pinned SHA-256, ESLint/Prettier/svelte-check, ruff/mypy/pytest, rustfmt/clippy.
6. CI (`.github/workflows/`): lint + typecheck + tests on `ubuntu-latest` and `windows-latest`;
   a Windows build workflow that produces the spike installer as an artifact.

Spikes (built by CI, verified by the user on the Windows 11 laptop):
- **S1 Island window:** transparent, undecorated, no shadow, always on top, not in taskbar, never
  takes focus on show; click-through outside the pill via Rust cursor hit-testing and
  `set_ignore_cursor_events`; fullscreen detection; 60 fps morph with a frame-time readout.
- **S2 Sidecar packaging:** `ev-core` built with PyInstaller onedir, launched and supervised by the
  Tauri app from the installed location; cold start time recorded.
- **S3 llama-server:** pinned `b11696` CPU and Vulkan builds; `-lm none` RSS and iGPU throughput
  measured on Windows with Qwen3.5-4B Q4_K_M.

Docs: `ARCHITECTURE.md`, `DESIGN.md`, `PERFORMANCE.md`, `FEATURES.md`, `ROADMAP.md` (this file).

### Done when
- [ ] All CI jobs green on Linux and Windows. *(Workflows written and actionlint-clean; they
      first run when the branch is pushed, which waits for the user.)*
- [x] Protocol contract tests pass on both sides; codegen check passes. *(local, 2026-10-17)*
- [x] Core: config, logging, bus, registry, server have unit tests; `mypy --strict` clean.
      *(75 Python tests; 30 Rust tests; 15 frontend tests)*
- [x] App runs end-to-end on Linux: island window appears, core starts, handshake succeeds,
      killing core triggers restart with backoff, three failures show the error state.
      *(Run manually on the dev machine: handshake, SIGKILL → restart in 1.1 s, app SIGKILL →
      core exits. The three-failure path is covered by Rust tests with a scripted fake core;
      the island's error text was not checked visually.)*
- [ ] S1 verified on Windows 11 at 100% and 150% DPI: click-through works outside the pill,
      no shadow, no focus steal, fullscreen app hides the island, morph holds 60 fps with 0 dropped
      frames on the reference machine.
- [ ] S2 verified on Windows 11: installed app starts the onedir core; cold start → island visible
      ≤ 1.5 s.
- [ ] S3 measured on Windows 11 and recorded in `PERFORMANCE.md` and `decisions.md`.
- [ ] Every spike outcome recorded in `docs/decisions.md` (including "approach changed because…").

---

## Phase 1 — Brain
Status (2026-10-17): built and verified on Linux with Qwen3.5-4B (see PERFORMANCE.md §4.5).
- [x] Golden tests pass against fakes (`tests/test_agent_loop.py`, CI) and against the real 4B
      model (`tests/test_golden.py`, run manually: 6/6 on 2026-10-17).
- [x] Instant ≤ 300 ms (router: 1 ms).
- [x] Normal first token measured and recorded (0.42 s cached prefix, 3.5 s cold; linux-dev).
- [ ] RAM within budget on the Windows test laptop (linux-dev: 3.2–3.4 GB llama-server + 51 MB
      core; app and WebView not yet summed).
- [ ] Chat used interactively in the island on Windows (spike kit, optional section).

llama-server supervisor (random port, auth token, `-lm none`, restart policy), `LlmBackend`
interface, agent loop (§5.4) with grammar-constrained tool calls, rule router (Instant), effort
levels (§5.5), rolling history, typed chat in a minimal panel.
Done when: golden tests pass against fakes in CI and against the real 4B model manually; Instant
≤ 300 ms; Normal first token measured and recorded; RAM within budget with 4B loaded.

## Phase 2 — Island
All island states and motion, design tokens and Minimal theme (light/dark, Windows accent),
settings window skeleton with every §6.5 section, hotkey (`Ctrl+Space`, IME conflict detection),
tray, auto-hide, multi-monitor and DPI handling. Font specimen shown to the user and locked.
Done when: hover → panel ≤ 120 ms first frame / ≤ 350 ms complete; 60 fps, 0 dropped frames;
hotkey → focused ≤ 150 ms; review gate screenshots at 100/150% DPI, light and dark.

## Phase 3 — Tools
`Tool` interface, PC control set (§7 "PC"), risk levels and inline confirmations, action log with
undo, post-step verification, Windows CI tool tests against Notepad/Calculator/Explorer.

## Phase 4 — Voice
STT streaming (Moonshine), TTS streaming (Kokoro; KittenTTS listening test), barge-in, earcons,
then wake word (openWakeWord custom phrases).
Done when: wake → chime ≤ 250 ms; barge-in ≤ 100 ms; Normal first spoken word ≤ 2 s; idle CPU ≤ 3%.

## Phase 5 — Vision & media
Screen explain (region drag), RapidOCR, document/PDF Q&A, video pipeline (§5.8).

## Phase 6 — Memory & search
History with retention policy, explicit memory, sensitive-data filter, semantic file index,
web search (`WebSearchProvider`, caching, backoff, "search unavailable" state) with sources.
Done when: Normal + web first word ≤ 6 s, complete ≤ 10 s.

## Phase 7 — Companion features
Personality presets, daily brief, routines, notification digest, live captions, meeting notes.

## Phase 8 — First-run & system
Setup flow, compute benchmark (§5.6), model downloader (SHA-256, resume), updater, crash log and
"Report issue", privacy mode, performance HUD.

## Phase 9 — Polish & beta
Performance tuning against every §4 budget, accessibility pass (§6.6), 8 h soak (< 50 MB/h),
installer ≤ 150 MB, docs, `0.1.0-beta.1` pre-release on GitHub.
Ship full license texts for every bundled component (generated, e.g. cargo-about),
not only the component list.

## Phase 10 — Public release
Feedback fixes, SignPath code signing, README, `1.0.0`.
