# EV — Performance

Budgets are defined in `CLAUDE.md` §4 and are hard limits. This file defines **how** each budget
is measured, where results are stored, and what has been measured so far. Never record a number
that was not measured; estimates live in `docs/feasibility.md` and are labelled as estimates.

## 1. Reference machine
| Item | Dev machine (baseline numbers in §4.1–4.2) | Windows 11 test laptop |
|---|---|---|
| CPU | Intel i7-11800H (8C/16T), DDR4 | to be recorded |
| RAM | 32 GB installed (budgets target a 16 GB machine) | to be recorded |
| GPU | Intel UHD (TigerLake-H GT1) iGPU + NVIDIA RTX 3050 Ti Mobile; baseline runs were CPU-only | to be recorded |
| OS | Linux (Omarchy) | Windows 11 x64 |

Linux numbers are labelled `linux-dev` and are never used to pass a Windows budget. Budgets are
judged on the Windows 11 test laptop; its specification is recorded here before the first spike
measurement.

## 2. Budgets and measurement method

| Budget | Target | Method | Phase |
|---|---|---|---|
| Total RAM, 4B loaded, steady | ≤ 5.0 GB (cap 5.5) | Sum of private working sets of `ev.exe`, WebView2 children, `ev-core`, `llama-server`, sampled 1/min for 10 min after warm-up | 1 |
| RAM, model unloaded | ≤ 450 MB | Same sum after idle unload | 1 |
| Idle CPU (wake word only) | ≤ 3% total | Sum of process CPU over 10 min idle, normalized to all logical cores | 4 |
| RAM growth, 8 h soak | < 50 MB/h | Linear regression slope of the RAM sum over the soak script | 9 |
| Hover → panel | ≤ 120 ms first frame, ≤ 350 ms complete | `performance.now()` from pointerenter to first rAF with new shape; animation end event | 2 |
| Animation | 60 fps, 0 dropped frames | rAF frame deltas during scripted morphs; frame > 20 ms = dropped | 0 (S1), 2 |
| Hotkey → panel focused | ≤ 150 ms | Rust hotkey timestamp → UI focus event timestamp | 2 |
| Instant effort | ≤ 300 ms | input received → tool result | 1 |
| Normal first spoken word | ≤ 2 s | input received → first TTS audio buffer played | 4 |
| Normal + web | first word ≤ 6 s, complete ≤ 10 s | as above, web path | 6 |
| Wake → chime | ≤ 250 ms | wake detection → earcon playback start | 4 |
| Barge-in → TTS stops | ≤ 100 ms | voice activity detected → audio output stopped | 4 |
| Cold start → island visible | ≤ 1.5 s | process start → island first paint | 0 (S2), 2 |
| Installer size (no models) | ≤ 150 MB | NSIS output file size | 0, 9 |

A change that worsens a budget metric by more than 5% must explain why in its PR description.

## 3. Benchmark storage
- Scripts: `bench/` (one script per budget group).
- Budgets as data: `bench/budgets.toml`, created in Phase 1 together with the first automated
  benchmark that reads it. Phase 0 measurements are manual spikes (`bench/spikes/`).
- Results: `bench/results/<date>-<machine>-<os>.json`, append-only, committed. Each result records
  git commit, EV version, llama.cpp build, model file SHA-256, backend, thread count.

## 4. Measured results

### 4.1 LLM (CPU, llama.cpp b11696, 8 threads, i7-11800H, measured 2026-10-16, linux-dev)
| Model | Prompt | Generate | RSS |
|---|---|---|---|
| Qwen3.5-4B Q4_K_M | 120 tok/s | 13.6 tok/s | 2.9 GB with `-lm none` (4.3 GB default) |
| Qwen3.5-2B Q4_K_M | 329 tok/s | 29 tok/s | ~1.4 GB |
| 4B vision, 720p, 256 image tokens | ~7 s per image | — | +0.6 GB (F16 mmproj) |

### 4.2 TTS (CPU, onnxruntime, i7-11800H, measured 2026-10-16, linux-dev)
| Model | Short sentence | Speed | RAM |
|---|---|---|---|
| Kokoro int8 | 0.9 s | 2.7x realtime | ~460 MB |
| Supertonic 3 | 0.6 s | 6x realtime | ~650 MB |
| KittenTTS micro 0.8 | 0.3 s | 15x realtime | ~360 MB (quality unverified) |

### 4.3 Phase 0 (dev machine, linux-dev, measured 2026-10-17)
Development numbers only; they never pass a Windows budget.

| Measurement | Result | Notes |
|---|---|---|
| App start → core `hello.ack` (debug build, dev venv) | ~200 ms | `app.log` timestamps |
| App start → core `hello.ack` (release build, packaged onedir core) | 294 ms | |
| Packaged core: spawn → listening line / `hello.ack` | 171 ms / 173 ms | PyInstaller onedir, Linux |
| Core crash (SIGKILL) → restarted core ready | 1.1 s | 1 s backoff + start |
| Process start → first island frame painted (debug, Vite dev server) | 377 ms | `spike s2 island painted` |
| Packaged core onedir size | 42 MB | Linux; most is `libpython` (31 MB) |
| Release app binary | 4.8 MB | Linux, LTO, `opt-level = "s"` |

Spring settle time (computed with the shipped integrator, 60 fps, rest at 0.5 px):

| Spring (stiffness / damping / mass) | 240 px (idle → panel) | 80 px |
|---|---|---|
| 400 / 32 / 1 (contract default) | ~417 ms | ~350 ms |
| 500 / 40 / 1 | ~300 ms | ~267 ms |
| 600 / 44 / 1 | ~283 ms | ~250 ms |

The contract default misses the ≤ 350 ms "animation complete" budget for the largest morph. Phase 2
tunes the spring (CLAUDE.md §6.2) and records the final values in `DESIGN.md`. See
`docs/decisions.md` (Phase 0).

### 4.5 Phase 1 brain (dev machine, linux-dev, measured 2026-10-17)
Qwen3.5-4B Q4_K_M, llama.cpp b11696 CPU, 8 threads, 8K context, q8 KV cache, `--load-mode none`.
Wall times measured over the WebSocket, as the app sees them.

| Measurement | Result | Budget |
|---|---|---|
| Model load (llama-server start → healthy) | 2.3–2.5 s | warms in background |
| Static prefix (system prompt + tool list) | 410 tokens | ≤ 1,000 |
| Router answer ("What time is it?") | 1 ms | Instant ≤ 300 ms |
| Normal, first token, cold prefix (418-token prompt) | 3.5 s | (spoken word ≤ 2 s, Phase 4) |
| Normal, first token, cached prefix ("what is a GPU?") | 0.42 s | |
| Normal, total, 32 tokens | 2.8 s | |
| Normal with one tool step (time question), first token / total | 2.2 s / 3.1 s | |
| Max effort (thinking), "17 × 23", 174 tokens | 13.7 s | Max: minutes, cancellable |
| Prompt read / generate speed | 118 tok/s / 13.2 tok/s | baseline 120 / 13.6 |
| RSS: llama-server / core | 3.2–3.4 GB / 51 MB | total ≤ 5.0 GB |

The cached-prefix numbers depend on the warm-up request sent when a model becomes ready
(docs/decisions.md, Phase 1).

### 4.4 Pending (Phase 0 spikes, Windows 11)
| Measurement | Spike | Result |
|---|---|---|
| `-lm none` RSS on Windows, 4B | S3 | not yet measured |
| Vulkan iGPU prompt/generate, 4B | S3 | not yet measured |
| Island morph frame times, 100% / 150% DPI | S1 | not yet measured |
| Hover → panel first frame (budget ≤ 120 ms) | S1 | not yet measured |
| Cold start → island visible, onedir core | S2 | not yet measured |
| Installer size (app + core, no models) | S2 | not yet measured |

## 5. Design rules that follow from the numbers
- Prompt reading is the CPU bottleneck: static prefix (system prompt + tools) ≤ 1,000 tokens and
  cached; memory ≤ 300 tokens; context ≤ 300 tokens.
- Always start llama-server with `-lm none` (re-verify on Windows in S3).
- Vision (~7 s/image) is a fallback, never a loop.
- Heavy background work pauses on battery, busy CPU, or fullscreen.
