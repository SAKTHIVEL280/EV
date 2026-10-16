# EV — Decisions Log

Status: **planning**. No application code yet. Started 2026-10-16.

## Product
- Free, open-source, fully local AI companion for **Windows** (Linux later).
- Target hardware: **16 GB RAM + modern CPU, no GPU assumed**. GPU used only if present; user can cap or disable it.
- English only.
- Installer ships the app only; models are downloaded on first run, chosen by the user (Lite/Standard/Smart).
- Quality bar: premium, clean, intentional. Not vibe-coded: design system, tests, CI, measured performance budgets.

## Stack (all free, permissive licenses)
| Layer | Choice |
|---|---|
| LLM | Qwen3.5-4B Q4_K_M (default), Qwen3.5-9B optional, 2B "Lite" |
| Runtime | llama.cpp `llama-server` (CPU + Vulkan builds), bundled |
| PC control | Windows-MCP / pywinauto UIA; screenshot -> Qwen vision as fallback |
| STT | Moonshine (live), Parakeet TDT 0.6B v3 (long audio / accuracy) |
| TTS | Kokoro int8 via sherpa-onnx (Piper dropped: GPL) |
| Wake word | openWakeWord (custom model trained for EV's wake phrase) |
| Memory / RAG | EmbeddingGemma-308M + SQLite + sqlite-vec |
| Web | DuckDuckGo via `ddgs` (headless, no UI), page text via trafilatura |
| UI | Tauri 2 + Svelte + Rive |
| Core | Python sidecar launched by Tauri |

## UI
- Tiny "punch-hole" pill at **top-center** (camera-notch style). Not top-right (window close buttons live there).
- Idle: few px, click-through. Hover/wake: morphs into ~360px panel. Auto-hides in fullscreen / screen share.
- Theming via design tokens; Minimal theme first, more (Brutalist, Glass) later as token files. Reduced-motion option.
- No orb. Must never block or steal focus/space from other apps.

## Behavior
- Effort levels: Instant / Normal / Deep / Max (setting + voice: "max effort ...").
- Unsure -> search the web before answering (grounded answers with sources).
- Risky actions (delete, send, shell, install) require confirmation; all actions logged with undo where possible.

## Name & wake word
- EV = **Edge Voice**. Wake word user-chosen; presets "Hey EV", "Yo EV", "Bro EV", "Hello EV".

## Models & effort
- User chooses which models to download (2B / 4B / 9B). Effort levels map onto whatever is installed.
- Effort set by voice ("max effort ...") or settings. Unclear request -> ask a short written question; unknown fact -> web search.

## Measured (2026-10-16, i7-11800H, DDR4, CPU-only llama.cpp b11696, 8 threads)
| Model | Prompt read | Generate | RSS |
|---|---|---|---|
| Qwen3.5-4B Q4_K_M | 120 tok/s | 13.6 tok/s | 2.9 GB with `-lm none` (4.3 GB default mmap+repack) |
| Qwen3.5-2B Q4_K_M | 329 tok/s | 29 tok/s | ~1.4 GB |
| 4B vision, 720p, 256 img tokens | ~7 s/image, exact text transcription | | +0.6 GB (F16 mmproj) |

## Dev / test
- Develop on Linux; user tests builds on a separate Windows laptop. No VM.

## Input
- Default hotkey `Ctrl+Space` (detect IME conflict, suggest alternative). Not `Win+Shift+T` (PowerToys Text Extractor).
- Wake word ON by default with visible mic indicator. Voice chosen in first-run setup.

## Compute
- Default: integrated GPU via Vulkan when the first-run benchmark shows it is faster; CPU fallback; user can override/limit.
- Rejected for now: NPU (slower/unreliable, no tool calling), OpenVINO backend (preview), speculative decoding (no CPU gain shown).

## Speech
- STT live: Moonshine v2 streaming. Long audio: Parakeet. OCR for video frames: RapidOCR.
- TTS measured 2026-10-16 (i7-11800H, CPU, onnxruntime):
  | Model | Short sentence | Long (8 s audio) | Speed | RAM | License |
  |---|---|---|---|---|---|
  | Kokoro int8 | 891 ms | 2.9 s | 2.5-2.7x realtime | ~460 MB | Apache-2.0 |
  | Supertonic 3 | 594 ms | 1.4 s | 5-6x realtime | ~650 MB | OpenRAIL (use restrictions) |
  | KittenTTS micro 0.8 | 313 ms | 0.9 s | ~15x realtime | ~360 MB | Apache-2.0 (quality unverified) |

## Memory & history
- History retention user-chosen. Default: full transcripts kept 7 days, then condensed to a summary.
- Important facts kept permanently in a "Memory" list the user can view, edit and delete.

## Features (accepted)
"This" awareness, selection quick actions, notification digest, meeting notes, searchable history, clipboard actions (off by default),
plus earlier list (screen explain, smart clipboard, live captions, daily brief, file finder, focus mode, routines, action log/undo,
battery saver, first-run benchmark, performance HUD, privacy mode, plugin tools folder).

## Optimization (accepted)
Thinking off for Instant/Normal; grammar-constrained tool calls; cached <1k-token system prompt; low priority + Windows EcoQoS when user is active;
barge-in; single sherpa-onnx voice runtime; panel <200 ms, background model warmup; context checkpoints; `-lm none` load mode.

## Beta decisions (2026-10-17)
- Voice: Kokoro default; KittenTTS fast option if it passes a listening test; Supertonic optional download.
- Memory (beta): explicit only. EV saves/updates permanent memory only when the user says so ("remember this", "update your memory").
- Plan: private beta first, public release after feedback.
- Windows 11 only.
- Code signing: SignPath free OSS signing at public release; beta unsigned.
- Personality: 5-10 preset system prompts; first-run asks user's preferred style; switchable anytime (adaptive later).
- Privacy: zero telemetry, no servers. Bug reports: local crash log + "Report issue" opens pre-filled GitHub issue for user to review/submit.
- Web: only search queries + page fetches leave the PC; personal data stripped from queries; web can be disabled.
- Screen access: only when asked (hotkey/command) by default; "auto" opt-in setting.
- Design: Dynamic Island-level motion and feel (not a copy). Settings UI clean, modern, intentional. No generic AI-slop patterns.

## Design direction (2026-10-17)
- "Quiet hardware": island always pure black in every theme, one accent, depth from motion/blur, squircle corners.
- Fonts: Instrument Sans (OFL-1.1) + Commit Mono (MIT), bundled. Banned: Inter, Geist, Poppins, Roboto, Montserrat, Open Sans. Final specimen shown to user in Phase 2.
- Icons: custom EV set (~30, 20 px grid, 1.5 px stroke). Banned: Lucide, Heroicons, Font Awesome, Material.
- Earcons: wake / done / error, under 300 ms, respects Do Not Disturb.

## Phase 0 (2026-10-17)
- Scope confirmed with user: Phase 0 only (foundation + spikes), stop at the Phase 0 gate for Windows verification.
- Git: work on `feat/phase-0-foundation`, local commits only, no push until the user asks.
- Toolchain: rustup, uv, pnpm from pacman (Arch `extra`); Rust stable via rustup; Python 3.12 via `uv python install`.
- Tauri issues #9250 (cursor position API) and #11461 (`setIgnoreCursorEvents`) are both **closed** as of 2026-10-17. Spike S1 still verifies click-through on Windows 11.
- Pinned llama.cpp `b11696` Windows assets (GitHub release digests):
  - `llama-b11696-bin-win-cpu-x64.zip` sha256 `1e7c47dff58467540d53e6cf302d83951bcb165afb252c2952ed3872190fc60d`
  - `llama-b11696-bin-win-vulkan-x64.zip` sha256 `f62bbf1ce154911ce37a381b9b308893b064301ecb7512f30c7c2abf7f812e75`
- `tauri-specta` for Tauri 2 exists only as `2.0.0-rc.25` (with `specta 2.0.0-rc.25`); no stable release. Pinned exactly (`=`), upgraded deliberately.
- Protocol v1 is a single JSON Schema file (`protocol/ev-protocol.schema.json`) with a `oneOf` union discriminated by `type`. Envelope adds optional `reply_to` (id of the message answered) to the required `v`, `type`, `id`, `payload`. Envelope rejects unknown fields; payloads ignore unknown fields (forward compatibility). `v` is validated at runtime (error `protocol_mismatch`), not by schema `const`, so a mismatch produces a clear error instead of a parse failure.
- Core handshake: token in env var `EV_CORE_TOKEN` (never on the command line), core binds `127.0.0.1:0` and prints one JSON line with the port; WebSocket auth via `Authorization: Bearer`; any `Origin` header rejected (blocks browser pages). Details in `docs/ARCHITECTURE.md` §2.
- Reference numbers in `CLAUDE.md` §3 were taken on the dev machine (i7-11800H, 32 GB, Linux, CPU-only); labelled `linux-dev` in `docs/PERFORMANCE.md`. Budgets are judged on the Windows 11 test laptop.
- Doc consistency: panel latency follows `CLAUDE.md` §4 (≤ 120 ms first frame) over the earlier "< 200 ms" note above. EmbeddingGemma "300M" and "308M" refer to the same model (`embeddinggemma-300m`, 308M parameters).
- PyInstaller is GPL-2.0-or-later **with the bootloader exception**, which permits distributing bundled apps under any license; it is a build tool, not shipped library code. Allowed.

## Phase 0 implementation (2026-10-17)
Made without the user present (user asked for no questions overnight); each has its reason.

Identity and versions
- In-tree version `0.1.0-beta.1` (the release this work leads to). Python normalizes it to `0.1.0b1` (PEP 440); same release.
- App identifier `io.github.sakthivel280.ev` (reverse-DNS of the GitHub owner). It names the WebView2 data folder and the future updater identity, so changing it later needs a migration.
- App icon: black squircle (superellipse n = 5) with a white pill, the island itself. No stock or "AI" imagery.

Dependencies (licenses, release dates checked 2026-10-17; all pinned exactly; lockfiles committed)
- Python runtime: pydantic 2.14.1 (MIT), tomlkit 0.15.2 (MIT, keeps comments and unknown keys), websockets 17.2 (BSD-3). Not added: watchfiles (1 s polling is enough), platformdirs (a few lines of stdlib).
- Python dev: ruff 0.17.1, mypy 2.4.0, pytest 9.1.1, pytest-asyncio 1.4.0, jsonschema 4.26.0 + types-jsonschema, datamodel-code-generator 0.85.0. Packaging: PyInstaller 6.22.3.
- Rust: tauri 2.12.4, tauri-specta/specta 2.0.0-rc.25 (RC, see above), tokio 1.53.3, tokio-tungstenite 0.30.0, futures-util 0.3.34, thiserror 2.0.21, tracing 0.1.44, tracing-subscriber 0.3.23 (registry only), getrandom 0.4.3 (OS RNG for tokens/UUIDs; `rand` not needed), regress 0.12.0 (required by typify's pattern validation), windows-sys 0.61.2. Build: typify 0.8.0, schemars 0.8.22, syn 3.0.9, prettyplease 0.3.0. Dev: tempfile 3.27.0. Toolchain pinned to Rust 1.99.1 (`rust-toolchain.toml`).
- JavaScript: svelte 5.57.2, @tauri-apps/api 2.12.4, vite 8.3.4, TypeScript **6.0.3** (7.0 is out, but typescript-eslint supports `<6.1.0` and svelte-check `^6`), eslint 10.12.0 and svelte-check 4.7.6. pnpm 11's release-age safeguard is kept: the newest versions were under a day old, so the previous settled releases were pinned instead of adding exclusions. Also vitest 5.0.4.
- `svelte` is a runtime dependency (its runtime ships in the bundle), so license accounting includes it.
- Arch replaced `libappindicator-gtk3` with `libayatana-appindicator` (Tauri supports both).

Protocol and process model
- Rust protocol types are generated by `build.rs` (typify) into `OUT_DIR` on every build, not committed, so they cannot drift. Python's generated models are committed with a staleness test.
- typify ignores `const`: its untagged union would decode a `pong` as `ping`. The Rust decoder dispatches on `type` first; a test covers it.
- Orphan protection: core exits when its stdin pipe closes, which happens however the app dies. No Job Object needed. Verified on Linux by SIGKILLing the app.
- Restart policy: 1 s / 2 s / 5 s, then stop and show an error. The count resets after 60 s of healthy uptime, so rare crashes never add up to "stopped". Protocol mismatch and core exit code 2 (bad environment) are fatal: restarting cannot fix them.
- Liveness: ping every 5 s; 3 unanswered pings = crash.
- Packaged core uses the console subsystem (real stdin/stdout pipes) and is spawned with `CREATE_NO_WINDOW`. It is built in a separate `core/.venv-package` with runtime deps only, so dev tools never leak in (they did on the first attempt: mypy was bundled).

Config and logging
- Config values are validated one key at a time in strict JSON mode: no `"5"` → `5` or `true` → `1` coercion; enum strings accepted.
- Hot reload polls mtime+size once per second; publishes only on real changes.
- `app.log` uses a small size-rotating writer (5 MB × 5) with core's JSON record shape; tracing-appender rotates by time only. A panic hook logs panics before abort.

UI spike
- `HitRect` and frame stats use integers: specta types `f64` as `number | null` (JSON has no NaN), which is wrong for command inputs.
- Show the island before enabling click-through: tao's Linux backend unwraps the native window, which exists only after show (crash found and fixed in Phase 0). Placement width = logical width × monitor scale (Wayland reports 0×0 before first paint). Monitor fallback: primary → current → first.
- **Spring finding:** the contract default (400 / 32 / 1) needs ~417 ms to settle the 240 px idle → panel morph at a 0.5 px rest threshold, over the 350 ms "animation complete" budget. Kept as specified (CLAUDE.md assigns tuning to Phase 2). Candidates that meet the budget: 500 / 40 (~300 ms), 600 / 44 (~283 ms). Tests pin both facts.
- Spike instrumentation: morph frame stats (frames, dropped > 20 ms, worst, p95, input → first frame, settle) and first-paint time are logged to `app.log`. The panel's spike controls are replaced in Phase 2.
- ESLint rejects raw colors and `any` in script code now; stylelint for `<style>` blocks comes in Phase 2. Only Instrument Sans is bundled; Commit Mono is added when first used (no unused assets).

Quality gates
- Clippy `all` + `pedantic`, with `unwrap`/`expect`/`panic` denied outside tests and every `unsafe` block documented. `needless_pass_by_value` is allowed only in `commands.rs`, because Tauri injects arguments by value.
- Windows-only Rust code is linted from Linux with `--target x86_64-pc-windows-msvc`. Linking and runtime are verified on Windows CI and the laptop.
- `THIRD_PARTY_NOTICES.md` is generated from the Cargo (Windows target, normal deps), uv and pnpm graphs; CI fails on stale notices or a GPL/AGPL/SSPL/non-commercial license without an allowed alternative. LGPL is allowed (the contract accepts an LGPL ffmpeg build). The PyInstaller bootloader (GPL with bootloader exception) is a reviewed exception.
- GitHub Actions are pinned to commit SHAs. CI uses Node 24 LTS. `.gitattributes` forces LF so byte-exact generated-code checks pass on Windows runners.
- Focus return (found in code review): Windows keeps keyboard focus on a window that just became non-activating, so closing the panel would leave typing going nowhere. On close, if the island still has focus, it is hidden and re-shown without activation, which hands focus to the previously active app. Verified by S1 check 6 on Windows.

## Phase 1 — Brain (provisional, started 2026-10-17)
- **Deviation from CLAUDE.md §12:** Phase 1 started before the Phase 0 gate passed, because the gate waits on the user (push approval, Windows spikes) and the user asked for progress without questions overnight. It lives on its own branch, `feat/phase-1-brain`, stacked on `feat/phase-0-foundation`, so it can be discarded or rebased if the spikes change the design. The specs (F-001 to F-003) were written before the code.
- Dev model: `unsloth/Qwen3.5-4B-GGUF` at revision `e87f176479d0855a907a41277aca2f8ee7a09523`, `Qwen3.5-4B-Q4_K_M.gguf` (2,740,937,888 bytes, sha256 `00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4`, Apache-2.0). Qwen publishes no official GGUF for this model. The download source for users is decided with the model manifest (Phase 8).
- New dependencies: aiohttp 3.14.5 (Apache-2.0 AND MIT) chosen over httpx, which had no release since 2024-12; psutil 7.2.2 (BSD-3) for physical cores and memory; types-psutil (dev). The Linux llama.cpp build `ubuntu-x64` (b11696, sha256 `6a04629c…f802`) is pinned for development.
- Module isolation: shared contracts live in `ev_core/interfaces/` (`LlmBackend`, `LlmProvider`, `Tool`, bus events); the `llm` and `agent` modules never import each other, and `app.py` wires them.
- Tool calling uses llama-server's native OpenAI `tools` with `--jinja` (llama.cpp constrains the call JSON with a grammar). Verified with Qwen3.5-4B: it called `current_time` correctly. Thinking is switched per request with `chat_template_kwargs.enable_thinking`; with it off, no reasoning text was produced (verified).
- Prompt-prefix warm-up: when a model becomes ready, the agent sends the system prompt + tool list with `max_tokens = 1`. Measured on the dev machine: first token 3.5 s cold vs 0.27–0.42 s with the cached prefix. The static prefix is 410 tokens (budget ≤ 1,000).
- HTTP to llama-server uses a fresh connection per request (`force_close`). llama-server closes the connection after a streamed reply, and reusing it failed with `ServerDisconnectedError` (found with the real model).
- Instant effort, when the router does not match, gets no tools: one step cannot follow up on a tool result.
- History is in memory, verbatim, budgeted at 3 characters per token. Summaries and persistence arrive with memory (Phase 6).
- Tools with risk `confirm` or `dangerous` are refused, and the model is told so, until the island confirm state exists (Phase 3).
- Child processes: llama-server is owned by core. Windows: Job Object with kill-on-close. Linux: `setpriv --pdeathsig KILL`. A `preexec_fn` was tried first; it is unsafe in a multi-threaded process (aiohttp resolver threads) and Python 3.12 warns about it. Verified: SIGKILL of core leaves no llama-server.
- **Bug found and fixed:** `EventBus.drain()` spun forever when only finished tasks remained, because Python 3.12's `gather()` completes eagerly without yielding. Core calls `drain()` on shutdown, so this was a real hang. A regression test was added.
- **Windows llama.cpp runtime:** the official b11696 Windows build dynamically imports `MSVCP140.dll`, `VCRUNTIME140.dll` and `VCRUNTIME140_1.dll`, which a clean Windows 11 may lack. Decision: app-local deployment of these three Microsoft-redistributable DLLs next to llama-server, copied from the CI runner's Visual Studio redistributable folder. `ev.exe` already contains the same runtime through Tauri's default static linking, and per-user install needs no admin. These DLLs are not open source. **Flagged for user review.** The alternative is building llama.cpp from the pinned tag with a static runtime (`CMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded`), which departs from "official release" (§11).
- The shipped llama.cpp set is only llama-server's import closure plus all `ggml-cpu-*` variants (loaded by CPU features): 43 MB, 24 files instead of 48 MB / 51. `scripts/stage-llama-runtime` checks every import with `objdump` (negative-tested). The llama.cpp MIT and LLVM OpenMP license texts ship alongside; `THIRD_PARTY_NOTICES.md` ships in the installer.
- Island window 420 × 300 logical px, panel 360 × 240 (room for chat; tune P2).
- Thinking cost: Max effort answered "17 × 23" correctly in 13.7 s (174 tokens, mostly reasoning). Reasoning budgets per effort are tuned with web search (Phase 6) and in polish (Phase 9).

## Phase 2 — Island (provisional, started 2026-10-17)
- **Deviation from CLAUDE.md §12 (same as Phase 1):** started before the Phase 0 gate, on `feat/phase-2-island` stacked on `feat/phase-1-brain`. Only work that does not depend on the Windows island spike (S1) or on user approval was done: the settings plumbing, the Settings window skeleton and the Minimal theme. Not started: island geometry and motion tuning, the global hotkey, the tray, multi-monitor and DPI handling (all need Windows to verify), and the font lock (needs the user's approval of a rendered specimen).
- Settings are generic: each config key declares a label (`title`) and its Settings section (`nav`) in the pydantic schema. Core sends descriptors (kind, options, bounds, default, value) in `config.state`, so a new key in a later phase needs no UI code.
- Settings changes go through core (`config.set` / `config.reset`). Core validates the key with the same strict rules as loading, writes atomically with tomlkit (comments and unknown keys kept), applies the change at once and answers with the full state; an invalid value gets `config.rejected` with the allowed range in plain words, and the file is unchanged. A hand edit pushes a fresh state within the 1 s poll.
- Rust opens `config.toml` and the logs folder with `tauri-plugin-opener` 2.7.2 (Apache-2.0 OR MIT). Rust side only; no JS package.
- **Contrast finding:** CLAUDE.md §6.3 sets the island's text opacities to 100 / 64 / 40 %, but 40 % white on black is 3.66:1, below the WCAG AA 4.5:1 that §6.6 requires for text. Decision: island text uses only the 100 % and 64 % steps (8.3:1); the 40 % step is kept for non-text and disabled elements, which WCAG exempts. Minimal theme: light tertiary text at 60 % (≈ 4.8:1 on #f6f6f4), dark at 52 % (≈ 5.0:1 on #1b1b1a). **Flagged for user review** (it changes the §6.3 palette's use).
- Settings window: a normal focusable window, 880 × 600 (minimum 720 × 480), one instance (focused if opened again), opened from the island panel. Mica is deferred to the Windows design pass, because it needs Windows to verify; until then the window uses the Minimal theme's solid surface.
- Sections without settings yet show one plain line naming the feature that brings them (no "coming soon").
- Paths use the platform monospace font until Commit Mono is bundled (bundled when first needed, CLAUDE.md §6.3).
