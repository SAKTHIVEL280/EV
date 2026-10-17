# CLAUDE.md — EV (Edge Voice)

This file is the contract for building EV. Read it fully before every task. If a rule here conflicts
with a request, stop and ask. If something is unknown, research or measure it first; never guess.

Companion files:
- `docs/decisions.md` — every product decision and the reason. Append, never silently rewrite.
- `docs/feasibility.md` — performance math and scenario analysis.
- Future docs (created in Phase 0): `docs/ARCHITECTURE.md`, `docs/DESIGN.md`, `docs/PERFORMANCE.md`,
  `docs/FEATURES.md`, `docs/ROADMAP.md`. Until they exist, this file is the source of truth.

---

## 1. What EV is

A free, open-source, fully local AI companion for **Windows 11**. It lives in a tiny "island" at the
top-center of the screen, listens for a wake word, talks back, can see the screen when asked, and
controls the PC through tools.

Non-negotiables:
1. **Runs smoothly on 16 GB RAM + a modern CPU with no discrete GPU.** Integrated GPU used by default
   when faster; discrete GPU used if present. All of it user-limitable.
2. **100% free and local.** No servers, no accounts, no API keys, no telemetry. The only network
   traffic: model downloads, update check (GitHub Releases), and web search/page fetches when the
   user allows web.
3. **Never disturbs the user.** Never steals focus, never covers content, never lags their apps.
4. **Premium and intentional.** Dynamic Island-level motion and feel. No generic "AI app" look.
5. **Plug and play architecture.** Every feature is a module behind a stable interface. Adding or
   changing one must not break another.

Language: **English only** (UI, STT, TTS, wake word) for beta and v1.

Out of scope for now: Windows 10, Linux, macOS, other languages, cloud models, mobile, accounts, telemetry.

---

## 2. Stack (decided, licenses verified 2026-10-17)

| Layer | Choice | License |
|---|---|---|
| Desktop shell | Tauri 2 (Rust) + Svelte 5 + TypeScript | Apache-2.0/MIT |
| Animation | CSS/WAAPI springs; Rive for character/state animations | MIT |
| Core | Python 3.12 sidecar ("core") launched and supervised by Tauri | — |
| LLM runtime | llama.cpp `llama-server` (bundled; CPU + Vulkan builds; CUDA optional download) | MIT |
| LLM models | Qwen3.5 2B / 4B (default) / 9B, GGUF Q4_K_M + mmproj for vision | Apache-2.0 |
| PC control | Windows-MCP (CursorTouch) + pywinauto UIA; vision fallback | MIT / BSD |
| Wake word | openWakeWord (custom EV phrases) | Apache-2.0 |
| STT live | Moonshine v2 streaming (`moonshine-voice`) | MIT |
| STT long audio | Parakeet TDT 0.6B v3 via sherpa-onnx | CC-BY-4.0 (attribute) |
| TTS | Kokoro int8 (default); KittenTTS micro (fast, if it passes listening test); Supertonic 3 optional download | Apache-2.0 / Apache-2.0 / OpenRAIL |
| Voice runtime | sherpa-onnx + onnxruntime | Apache-2.0 / MIT |
| OCR | RapidOCR (ONNX) | Apache-2.0 |
| Embeddings | EmbeddingGemma-300M | Gemma terms (free, attribute) |
| Storage | SQLite (WAL) + sqlite-vec | Public domain / Apache-2.0 |
| Web | `ddgs` (DuckDuckGo, headless) + trafilatura | MIT / Apache-2.0 |
| Video | yt-dlp (captions), ffmpeg (audio/frames) | Unlicense / LGPL build |

Rules:
- **Never add a dependency without:** license check (no GPL/AGPL/non-commercial in shipped code),
  last-commit check, size/RAM cost, and an entry in `docs/decisions.md`.
- Supertonic (OpenRAIL) and any other non-OSI asset is an **optional user download**, never bundled.
- Pin every version (lockfiles committed: `Cargo.lock`, `pnpm-lock.yaml`, `uv.lock`).
- **Rejected (do not reintroduce without new evidence):** Ollama (no Qwen3.5 vision GGUF, Windows
  Vulkan bugs), Electron (heavier), Piper (GPL), NPU backends (slower/unreliable, no tool calling),
  OpenVINO backend (preview, crashes), speculative decoding (no CPU gain measured), cloud APIs.
- `ddgs` is unofficial and may rate-limit or break: wrap behind the `WebSearchProvider` interface
  with caching, backoff, and a clear "search unavailable" state.

---

## 3. Measured baseline (do not contradict without new measurements)

Reference machine: i7-11800H, DDR4, CPU only, llama.cpp b11696, 8 threads.

| Item | Result |
|---|---|
| Qwen3.5-4B Q4_K_M | prompt 120 tok/s, generate 13.6 tok/s, **2.9 GB RSS with `-lm none`** (4.3 GB default) |
| Qwen3.5-2B Q4_K_M | prompt 329 tok/s, generate 29 tok/s, ~1.4 GB |
| 4B vision, 720p, 256 image tokens | ~7 s per image, exact text transcription; mmproj F16 +0.6 GB |
| Kokoro int8 | short sentence 0.9 s, 2.7x realtime, ~460 MB |
| Supertonic 3 | 0.6 s, 6x realtime, ~650 MB |
| KittenTTS micro 0.8 | 0.3 s, 15x realtime, ~360 MB (quality unverified) |

Implications that shape every design:
- On CPU, **reading the prompt is the bottleneck.** Keep prompts small; cache the static prefix.
- Always start llama-server with `-lm none` (avoids double copy of weights). Re-verify on Windows.
- Vision is the slow path (~7 s). Never loop it by default.

---

## 4. Performance budgets (hard limits; CI and benchmarks enforce them)

| Budget | Target |
|---|---|
| Total EV RAM, 4B loaded, steady | ≤ 5.0 GB (hard cap 5.5 GB) |
| EV RAM, model unloaded (idle) | ≤ 450 MB |
| Idle CPU (wake word only) | ≤ 3% total |
| RAM growth, 8 h soak test | < 50 MB/h |
| Island hover → panel visible | ≤ 120 ms to first frame, animation complete ≤ 350 ms |
| Animation | 60 fps sustained, 0 dropped frames on reference machine |
| Hotkey → panel focused | ≤ 150 ms |
| Instant effort (rule router) | ≤ 300 ms |
| Normal: first spoken word | ≤ 2 s |
| Normal + web: first spoken word | ≤ 6 s, complete ≤ 10 s |
| Wake word → listening chime | ≤ 250 ms |
| Barge-in → TTS stops | ≤ 100 ms |
| App cold start → island visible | ≤ 1.5 s (model warms in background) |
| Installer size (no models) | ≤ 150 MB |

Any PR that worsens a budget metric by more than 5% must explain why in the PR description.

---

## 5. Architecture

### 5.1 Processes
```
ev.exe (Tauri, Rust)            -- windows, island, tray, hotkeys, Win32 calls, supervisor
 ├── WebView2 (Svelte UI)       -- island + panel + settings; pure presentation
 ├── ev-core.exe (Python)       -- agent loop, tools, voice pipeline, memory, web
 └── llama-server.exe           -- LLM + vision, localhost only, random port, auth token
```
- Rust supervises both children: restart with backoff (1 s, 2 s, 5 s, then stop and show error).
- All children bind **127.0.0.1 only**, random port, per-session secret token. Never 0.0.0.0.
- Python is bundled with PyInstaller **onedir** (not onefile: onefile unpacks to temp every launch,
  slow and flagged by antivirus). Verify packaging in Phase 0 spike.

### 5.2 Communication
- UI ↔ Rust: Tauri commands + events (typed; generated TS types from Rust via `specta`/`tauri-specta`).
- Rust ↔ core: one local WebSocket, JSON messages, versioned schema (`protocol/` folder, JSON Schema;
  both sides generate types from it). Every message has `v`, `type`, `id`, `payload`.
- core ↔ llama-server: OpenAI-compatible HTTP API with streaming.
- Protocol changes are additive. Removing/renaming a field requires a protocol version bump and
  both sides updated in the same PR.

### 5.3 Module (plug-and-play) rules
Everything in core is a module implementing a small interface, registered in one registry:
- `Tool` (PC control, files, web, etc.): `name`, `description` (≤ 25 words), `json_schema`,
  `risk: safe|confirm|dangerous`, `run(args, ctx) -> ToolResult`, `undo(...)` optional.
- `SttEngine`, `TtsEngine`, `WakeWordEngine`, `OcrEngine`, `EmbeddingEngine`, `WebSearchProvider`,
  `LlmBackend`: each an abstract base class with one or more implementations.
- Modules **never import each other**. They talk only through interfaces and the event bus.
- A module failing to load disables only itself and shows a clear status in Settings → Diagnostics.
- Every module has: unit tests, a fake implementation for tests, and a config schema section.
- Feature flags in config for every feature; default values documented in the schema.

### 5.4 Agent loop
1. Input arrives (voice transcript, typed text, hotkey with selection, routine).
2. **Router** (no LLM): regex/intent rules for Instant commands (volume, open app, timer, media,
   brightness). If matched → run tool → done.
3. Build prompt: cached static prefix (system prompt + tool list, ≤ 1,000 tokens) + memory snippets
   (≤ 300 tokens) + context ("this": selection/active window, ≤ 300 tokens) + rolling history.
4. LLM call with **grammar-constrained tool-call JSON** (llama.cpp grammar / JSON schema).
5. Tool calls: `safe` run immediately; `confirm` shows inline confirm in the island; `dangerous`
   (delete, shell, send message, install, registry) needs explicit confirm every time, never auto.
6. After each tool step, verify result (re-read UIA state). On mismatch: retry once, then ask user.
7. Unclear request → ask one short written clarifying question. Unknown/recent fact → web search.
   Never present a guess as fact.
8. Stream reply to UI and TTS sentence by sentence.

### 5.5 Effort levels
| Level | Model | Thinking | Web | Max steps |
|---|---|---|---|---|
| Instant | router; else smallest installed model | off | no | 1 |
| Normal (default) | default model | off | auto when unsure | 5 |
| Deep | largest installed | on | yes, 2-3 searches, ~8 pages | 15 |
| Max | largest installed | on | yes, iterative | 40, cancellable, progress shown |
Set in settings or by voice ("max effort, ..."). Effort maps to whatever models the user installed.

### 5.6 Compute selection
- First-run benchmark (~20 s): test CPU, iGPU (Vulkan), dGPU (Vulkan/CUDA if downloaded). Pick fastest
  backend that also passes a correctness check (fixed prompt → expected answer).
- Default: iGPU when faster. Prompt processing on GPU, CPU threads left free for voice and user apps.
- Driver crash or garbage output → automatic fallback to CPU, notify once, remember per driver version.
- Settings: backend, GPU layers, CPU threads (default = physical cores − 2, min 2), GPU on/off.
- On battery: fewer threads, optional smaller model, wake word optional pause (user setting).
- When the user is active in another app: core runs at below-normal priority with Windows EcoQoS.
- Heavy background work (file indexing, summaries, embeddings) pauses when CPU is busy, a game or
  fullscreen app runs, or on battery; resumes when idle or charging.
- Idle unload: after N minutes without use (setting, default 10, "never" allowed) the LLM unloads;
  next request reloads it in the background while the island shows a subtle "waking" state.
- Keep llama.cpp context checkpoints / prompt cache so long conversations are never re-read from scratch.

### 5.7 Memory and context
- Rolling conversation: recent turns verbatim; older turns summarized; KV never exceeds configured ctx (default 8192, q8 cache).
- History retention: user-chosen. Default: full transcripts 7 days, then condensed summaries.
- Permanent memory (beta): **only when the user explicitly asks** ("remember…", "update your memory").
  Viewable, editable, deletable in Settings → Memory.
- Sensitive-data filter: never store passwords, card numbers, OTPs, API keys (regex + heuristics).
- All data in `%APPDATA%\EV\` : `ev.db` (SQLite WAL), `config.toml`, `logs/`, `models/` (models
  location changeable). Daily rotating DB backup, keep 3.

### 5.8 Video / long-media pipeline
1. URL with captions → yt-dlp captions. 2. Else ffmpeg audio → Parakeet. 3. **Muted or visual**:
scene-change keyframes (30-80/hour) → RapidOCR; vision only on frames without text or when asked.
4. Chunk with timestamps → embed → answer per question (5-10 s) with timestamps.
5. Full summary = background map-reduce with progress. Say clearly when a question cannot be answered
from available signals.

---

## 6. UI and design rules

### 6.1 The island
- Position: top-center, below the camera area. Never top-right (window controls live there).
- States: `idle` (a tiny drop of black liquid hanging from the top edge, ~16 × 13 px; user decision
  2026-10-17) → `hover` (the drop swells into a small capsule, shows a hint) →
  `listening` (live waveform/captions) → `thinking` → `speaking` → `panel` (~360 px wide,
  input + last reply + quick actions) → `confirm` (inline yes/no) → back to `idle`.
- Never steals focus except when the user opens it via hotkey or click.
- Idle: the drop itself is click-through too (it sits over browser tabs and title bars). It opens
  only when the pointer stays within a user-set distance for a user-set delay with no mouse button
  held (`island.reveal_distance`, `island.reveal_delay_ms`). An open shape takes clicks only inside
  itself. Implementation: window sized to max panel bounds + Rust-side cursor hit-testing toggling
  `set_ignore_cursor_events` (known Tauri issues #9250, #11461; shadow verified off).
- Auto-hide when a fullscreen app, game, or screen share/recording is active (setting).
- Multi-monitor: island on primary display by default; setting to choose. Handle DPI changes and
  display hot-plug without restart.

### 6.2 Motion
- Feel target: Apple Dynamic Island. Spring physics, not linear/ease tweens.
- Default spring: stiffness 400, damping 32, mass 1 (tune in Phase 2, record final values in DESIGN.md).
- Only animate `transform` and `opacity` (and clip-path where needed). Never animate width/height/top/left.
- Shape morph via a single element with `clip-path`/scale, content cross-fades on top.
- Interruptible: any animation can be reversed mid-flight from its current value (no snapping).
- Reduced motion (setting + respects Windows "Animation effects" off): cross-fades only, ≤ 150 ms.
- Animation strength setting: Full / Subtle / Reduced.

### 6.3 Visual system
- Design tokens are the only source of colors, radii, spacing, typography, shadows, durations,
  springs. No hard-coded values in components. Lint rule enforces it.
- A theme = one token file. Ship **Minimal** (light + dark, follows Windows theme + accent color).
  Brutalist, Glass, etc. come later as token files with zero component changes.
#### Art direction: "quiet hardware"
EV should feel like a physical object built into the screen, not a web app floating on it.
- **The island is always pure black (#000), in every theme**, like a camera cutout. Content on it is
  white at 3 opacity steps (100 / 64 / 40%). This is the signature; themes never change it.
  A faint light rim (1 px, 22% white) keeps it visible on black backgrounds such as dark browser
  tabs (user report, 2026-10-17); it is the one allowed border.
- Exactly **one accent color**, used only for live states (listening level, progress). Default is a
  warm off-white glow, not blue/purple. User may pick from a curated set of 6 or follow Windows accent.
- Depth comes from motion and blur, not from shadows, gradients or borders.
- Corner radii are continuous (squircle, superellipse via SVG path / `corner-shape` where supported),
  never plain `border-radius` circles-on-rectangles for the island.
- Settings window: calm, editorial, generous whitespace, strong typographic hierarchy, hairline
  dividers (1 px at 8% opacity), Mica background. Feels like a well-made system app, not a dashboard.

#### Typography
- **Primary: Instrument Sans** (SIL OFL, bundled, variable). Crisp, slightly condensed, premium,
  not overused. Tabular figures for all numbers (`font-variant-numeric: tabular-nums`).
- **Mono: Commit Mono** (MIT) only for code, commands, logs.
- Optical tightening: −1% letter-spacing at ≥ 20 px, 0 at body size. Weights used: 400, 500, 600 only.
- Type scale (px): 11 / 13 / 15 / 20 / 28. Island uses 13 and 15 only.
- Final pick confirmed in Phase 2 with a rendered specimen on Windows (ClearType, 100/125/150% DPI)
  shown to the user before it is locked. Alternatives on file: Hanken Grotesk, Schibsted Grotesk.
- **Banned fonts** (generic AI-app look): Inter, Geist, Poppins, Roboto, Montserrat, Open Sans,
  system-ui fallback as the design font.

#### Icons
- **Custom EV icon set**, drawn for this app: ~30 icons on a 20 px grid, 1.5 px stroke, rounded
  joins, optically balanced. Stored as SVG in `app/src/lib/icons/`. Every icon has a reason to exist.
- **Banned:** Lucide, Heroicons, Font Awesome, Material Icons, sparkle/magic-wand/brain "AI" icons.

#### Sound (earcons)
- Three subtle, short sounds designed for EV: wake (listening), done, error. Under 300 ms, soft,
  no musical jingles. Volume setting and off switch. Silent when Windows Focus/Do Not Disturb is on.

### 6.4 Anti-slop rules (reject in review)
- No purple-to-blue gradients, no glowing orbs, no sparkle ✨ icons, no "AI" badges.
- No emoji in UI copy. No exclamation marks in system copy.
- No generic card grids, no drop shadows stacked on everything, no centered hero layouts in settings.
- Every element must have a reason to exist. If removing it loses nothing, remove it.
- Copy is short, plain, specific. "Couldn't reach the web. Answering from memory." not "Oops! Something went wrong."
- Every state exists: empty, loading, error, offline, permission denied, disabled. Design each.
- No spinners. Loading is shown by the island's own motion (breathing, shimmer along the edge).
- No toasts stacking in a corner. All feedback lives in the island.
- No default component-library look (shadcn, Material, Bootstrap, Fluent defaults). Every component is
  built from EV tokens.
- No placeholder lorem ipsum, stock illustrations, or mascots.
- Review gate: every UI change ships with a screenshot/recording at 100% and 150% DPI, light and dark,
  and is checked against this list before merge.

### 6.5 Settings window
- Native-feeling Windows 11 layout: left nav, right content, Mica background.
- Sections: General, Voice, Models & Performance, Personality, Appearance, Hotkeys, Permissions,
  Memory & History, Routines, Web & Privacy, Advanced (open config file), Diagnostics, About.
- Every setting: label, one-line description, default, instant apply (no Save button), reset to default.

### 6.5.1 Required customization (all must exist in Settings and `config.toml`)
Effort default; models installed/default; CPU threads; compute backend; GPU on/off and layer limit;
voice, voice speed, voice volume; wake word phrase and sensitivity; wake word on/off (default on);
personality preset and custom prompt; island position (default top-center; display choice) and size
(Small/Default/Large); theme and accent color (default follows Windows); animation strength and
reduced motion; hotkeys; per-tool permissions (allow / ask / block); auto web search on/off and web
off; screen access (on request / auto); idle unload timer; battery behavior; history retention;
clipboard history on/off; clipboard actions (default off); auto-hide in fullscreen; routines and
custom commands; performance HUD; models folder location.
Advanced users edit `config.toml` directly; changes hot-reload and invalid values fall back to
defaults with a visible warning (never a crash).

### 6.6 Accessibility
- Full keyboard navigation, visible focus rings, screen reader labels (UIA properties), WCAG AA
  contrast in every theme, captions for everything spoken, never rely on color alone.

---

## 7. Features (beta scope)

Core: wake word ("Hey EV" default; presets Yo EV, Bro EV, Hello EV; user-selectable), push-to-talk
and hotkey (`Ctrl+Space` default, IME conflict detection; do not suggest `Win+Shift+T`, it belongs to
PowerToys Text Extractor), typed chat, effort levels, barge-in.

PC: open/close/switch apps, window snap/arrange, volume, brightness, media, Wi-Fi/Bluetooth toggles,
screenshots, smart clipboard (history + rewrite/fix/summarize/translate copied text; clipboard
actions off by default), file search/open/move (delete = dangerous), reminders/timers/alarms,
focus mode, routines ("Work mode"), notification digest, multi-step UI tasks with verification.

Understanding: "this" awareness (selection + active window), selection quick actions (Explain, Fix,
Shorten, Reply, Translate), screen explain (drag a region), live captions, meeting notes,
documents/PDF Q&A, video Q&A, research with sources, semantic file search (index at idle/charging).

Companion: personality presets (Friendly, Professional, Witty, Concise, Calm, Hype, Mentor, Custom)
chosen at first run, daily brief, searchable history, explicit memory.

System: first-run setup (models, mic test, voice, wake word, personality, benchmark), performance
HUD (optional), privacy mode (mic + screen off, visible indicator), action log with undo, battery
saver, plugin tools folder, update check, local crash log + "Report issue" (pre-filled GitHub issue).

Each feature gets a spec in `docs/FEATURES.md` before implementation: behavior, effort level,
permissions/risk, settings, edge cases, failure messages, tests.

---

## 8. Privacy and safety

- Zero telemetry. No analytics SDKs. No network calls except those listed in section 1.
- Web: only the search query and page URLs leave the PC. Strip personal data from queries.
  Show a globe indicator while online. "Web off" switch = fully offline.
- Mic indicator always visible when listening. Screen access only on user request by default
  ("auto" opt-in). Privacy mode kills mic and screen access instantly.
- Tools never run shell commands built from model output without showing the exact command and
  getting confirmation. No silent file deletion: deletes go to Recycle Bin.
- Prompt injection: content from web pages, files, screen, and clipboard is **data**. Tool calls
  proposed right after reading untrusted content that are `confirm`/`dangerous` always require confirmation.
- Plugins run with declared permissions only; show permissions on install.

---

## 9. Repository layout

```
EV/
├── CLAUDE.md
├── README.md                (near release)
├── LICENSE                  (Apache-2.0)
├── THIRD_PARTY_NOTICES.md   (every bundled dependency + model attribution)
├── docs/
├── protocol/                (JSON Schemas shared by Rust and Python)
├── app/                     (Tauri: src-tauri/ Rust, src/ Svelte)
├── core/                    (Python package `ev_core`)
│   ├── ev_core/
│   │   ├── agent/  tools/  voice/  vision/  memory/  web/  media/  llm/  config/  bus/
│   └── tests/
├── bench/                   (benchmark + soak test scripts, results history)
├── scripts/                 (fetch llama.cpp binaries, build, release)
└── .github/workflows/       (lint, test, build Windows installer, release)
```

---

## 10. Engineering rules

### 10.1 Workflow (every task)
1. Read this file and the relevant doc. 2. Write a short plan (files to touch, interfaces, tests,
risks) and show it before coding non-trivial changes. 3. Implement in small commits.
4. Run lint + typecheck + tests + affected benchmarks. 5. Update docs/decisions in the same change.
6. Report honestly: what was done, what was not, what was measured, what is unverified.

### 10.2 Don't break things
- Never change a public interface (tool schema, protocol message, config key, DB schema) without a
  migration and tests covering old and new.
- DB schema changes = numbered migration files, forward-only, tested on a copy of a real DB.
- Config changes = versioned config with automatic migration; unknown keys preserved.
- Fix root causes, not symptoms. If a fix touches another module, add a test there too.
- No dead code, no commented-out code, no TODO without an issue reference.

### 10.3 Code standards
- Rust: `cargo fmt`, `clippy -D warnings`, no `unwrap()` in non-test code.
- TypeScript/Svelte: strict mode, ESLint + Prettier, no `any`.
- Python 3.12: `ruff` (lint + format), `mypy --strict` on `ev_core`, type hints everywhere,
  `asyncio` for I/O; CPU-heavy work in threads/processes, never blocking the event loop.
- Errors: typed errors, user-facing message + technical detail logged. Never swallow exceptions.
- Logging: structured, rotating, local only, no personal content at INFO level.

### 10.4 Testing
- Unit tests for every module (fakes for LLM/voice). Contract tests for protocol schemas.
- Tool tests on Windows CI runners (`windows-latest`) for UIA tools against Notepad/Calculator/Explorer.
- Golden tests for the agent: fixed prompts → expected tool calls (run against the real 4B model
  nightly/manual, against fakes in CI).
- Benchmarks in `bench/` with stored history; budgets in section 4 checked automatically.
- 8 h soak test before every beta release.
- Manual test checklist per release on the user's real Windows 11 laptop (developer works on Linux).

### 10.5 Dev environment
- Development on Linux (Omarchy). Tauri UI and most of `ev_core` run on Linux; Windows-only modules
  sit behind interfaces with Linux fakes so the app runs end-to-end on Linux for development.
- Windows builds via GitHub Actions; the user tests installers on a separate Windows 11 laptop.
- Temporary experiments go in a scratch directory and are deleted afterward.

### 10.6 Versioning and releases
- Semantic Versioning: `MAJOR.MINOR.PATCH`, with pre-release tags.
- Beta: `0.1.0-beta.1`, `0.1.0-beta.2`, ... Each beta build increments the number.
  Feature sprint = next minor (`0.2.0-beta.1`). Bug-fix-only build = next patch.
- Public release: `1.0.0`. `0.x` signals pre-1.0; config/DB may change between minors (with migrations).
- One version, one source of truth: `app/src-tauri/tauri.conf.json` `version`; `Cargo.toml`,
  `package.json`, and `core/pyproject.toml` must match (CI check fails on mismatch).
- Every release: update `CHANGELOG.md` (Keep a Changelog format), git tag `vX.Y.Z[-beta.N]`,
  GitHub Release marked "pre-release" for betas, installer + SHA-256 checksums attached.
- Model files are versioned separately in `core/ev_core/models/manifest.json` (name, pinned URL,
  size, SHA-256), bundled with core.

### 10.7 Git
- Remote: https://github.com/SAKTHIVEL280/EV (default branch `main`).
- Commit directly to `main` and push it under the user's GitHub account. No feature branches and
  no pull requests (user decision, 2026-10-17).
- No `Co-Authored-By` or other AI attribution lines in commits or pull requests.
- Conventional commits (`feat:`, `fix:`, `perf:`, `docs:`, `refactor:`, `test:`, `chore:`).
- Never commit models, binaries, secrets, or personal data. `.gitignore` covers them.
- Commit/push only when the user asks.

---

## 11. Distribution

- Installer: NSIS via Tauri bundler, per-user install (no admin), Windows 11 x64 only.
- Models are not in the installer. First-run downloads from Hugging Face with SHA-256 verification,
  resume support, and progress. Offline install: user can point to a folder with model files.
- llama.cpp binaries fetched at build time from pinned official release (CPU + Vulkan); CUDA build is
  an optional in-app download.
- Updates: in-app check against GitHub Releases; user approves; signed update manifest (Tauri updater).
- Code signing: SignPath free OSS program at public release. Beta is unsigned (SmartScreen warning documented).
- Uninstall removes app; asks before deleting `%APPDATA%\EV` (models, memory).

---

## 12. Build order (roadmap summary)

Each phase ends with a "done when" check against section 4. Do not start the next phase until the
current one passes.

0. **Foundation & spikes:** repo scaffold, CI, protocol, config, logging. Spikes: island window on
   Windows 11 (click-through, no shadow, fullscreen detect, 60 fps morph), PyInstaller onedir sidecar,
   llama-server `-lm none` + Vulkan iGPU on Windows. Write ARCHITECTURE/DESIGN/PERFORMANCE/FEATURES/ROADMAP docs.
1. **Brain:** llama-server supervisor, agent loop, router, effort levels, typed chat in panel.
2. **Island:** all states and motion, settings window skeleton, themes/tokens, hotkey, tray.
3. **Tools:** PC control set, confirmations, action log, undo, verification.
4. **Voice:** STT streaming, TTS streaming, barge-in, then wake word.
5. **Vision & media:** screen explain, OCR, video/document pipeline.
6. **Memory & search:** history, explicit memory, file index, web search with sources.
7. **Companion features:** personality presets, daily brief, routines, digest, captions, meeting notes.
8. **First-run & system:** setup flow, benchmark, model downloader, updater, crash reports, privacy mode.
9. **Polish & beta:** performance tuning, accessibility pass, 8 h soak, docs, beta release.
10. **Public release:** feedback fixes, code signing, README, launch.

---

## 13. When unsure

- Unknown API, library behavior, or Windows quirk → search official docs/source, or write a tiny
  throwaway test, then decide. Record the finding in `docs/decisions.md`.
- Two reasonable options with user-visible impact → ask the user.
- Never claim something works without running it. Never invent benchmark numbers.
