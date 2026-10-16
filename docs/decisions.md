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
