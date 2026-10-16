# EV — Feasibility & Performance Budget

All numbers are **estimates** for a typical 2022+ laptop CPU (8 cores, DDR4/DDR5), no GPU,
Qwen3.5-4B Q4_K_M. They must be confirmed with `llama-bench` and EV's own benchmark suite on
real hardware before release. Where an estimate fails, the design changes, not the target.

## Reference throughput (CPU-only, 4B Q4)
| Metric | DDR4 laptop | DDR5 desktop |
|---|---|---|
| Prompt processing (reading) | ~40-80 tok/s | ~100-200 tok/s |
| Generation (writing) | ~8-12 tok/s | ~15-25 tok/s |
| STT Parakeet, long audio | ~15-30x realtime | ~30-60x realtime |
| TTS Kokoro, first audio | ~300-600 ms | ~200-400 ms |

Rule that follows from this: **reading is the bottleneck on CPU**. Every feature is designed to
keep the prompt small (cached system prompt, short tool schemas, retrieval instead of stuffing).

## RAM budget (steady state)
| Component | RAM |
|---|---|
| Qwen3.5-4B Q4 + vision projector | ~3.0 GB |
| KV cache (8K ctx, q8 cache) | ~0.5 GB |
| STT (Moonshine live; Parakeet loaded on demand) | 0.1-0.7 GB |
| TTS Kokoro int8 | ~0.3 GB |
| Embeddings EmbeddingGemma | ~0.2 GB |
| Python core + tools | ~0.3 GB |
| Tauri / WebView2 UI | ~0.15-0.3 GB |
| **Total** | **~4.5-5.3 GB** (hard cap target: 5.5 GB) |

Windows + user apps keep ~10 GB. Idle >N min (setting): unload LLM -> EV idles at ~400 MB.

## Latency targets by effort level
| Effort | What it does | Target |
|---|---|---|
| Instant | Rule router, no LLM ("volume 30", "open Spotify", timers) | < 300 ms |
| Normal | LLM, no web, short answer, voice starts on first sentence | first word 1-2 s, done 3-6 s |
| Normal + web (auto when unsure) | 1 search, top 3 pages, ~600 tokens of extracted snippets | 6-10 s |
| Deep | 2-3 searches, ~8 pages, reranked, cited summary | 30-90 s |
| Max | Multi-step research / long tasks, progress shown in panel | minutes, cancellable |

How "Normal + web" hits <10 s: search ~1 s, parallel fetch + extract ~2 s, embed+rerank
snippets ~0.5 s, read 600-800 tokens ~4-6 s, generate ~60 tokens ~3 s, TTS streams in parallel.

"Unsure" detection: model emits a `needs_search` signal for time-sensitive, niche, factual
or low-confidence questions; user can force "search it" or disable auto-search.

## Scenario: running for 1 hour (and 8 hours)
Risks and controls:
- **Context growth** -> conversation is rolling: last turns kept verbatim, older turns summarized
  into memory. KV cache never exceeds configured ctx. No unbounded growth.
- **Memory leaks** -> soak test in CI-like harness: 8 h scripted session, RSS sampled every
  minute; fail if growth > 50 MB/h.
- **CPU when idle** -> wake word only: ~1-3% of one core. LLM threads sleep. Target idle total < 3% CPU.
- **Thermals / battery** -> on battery: fewer threads, Lite model optional, wake word can pause.
- **Crashes** -> sidecar and llama-server supervised; auto-restart, UI shows "reconnecting".
Expected: flat RAM, near-zero idle CPU, no slowdown at hour 1 vs minute 1.

## Scenario: "watch this 1-hour video and answer questions"
EV does not "watch" in real time. Pipeline:
1. **YouTube / online video with captions** -> fetch captions with yt-dlp (no download). ~2-5 s.
2. **Local file or no captions** -> extract audio (ffmpeg), Parakeet transcribes: ~1-4 min for 1 h.
3. **Visual content (slides, code on screen)** -> scene-change detection picks ~20-60 keyframes;
   OCR text from them (cheap); Qwen vision only on frames the user asks about.
   Full vision captioning of every frame is **not** feasible on CPU and is not attempted.
4. Transcript (~10-12k words) is chunked with timestamps and embedded (~30-60 s).
5. Each question: retrieve top chunks (~800 tokens) -> answer with timestamps in **5-10 s**.
6. "Summarize the whole video" = map-reduce over chunks in background: ~3-8 min, progress shown.
Total for a 1 h local video: ready to answer in ~2-6 min, then each answer in 5-10 s.
RAM stays in budget because Parakeet is loaded only during transcription.

## Other scenarios checked
| Task | Approach | Feasible on CPU? |
|---|---|---|
| "What's on my screen?" | UIA text first; screenshot -> vision (~1.5k image tokens, ~10-25 s) | Yes, vision is the slow path |
| Read a 50-page PDF | chunk + embed (~20-40 s), then Q&A 5-10 s | Yes |
| Live captions for 1 h meeting | Moonshine streaming, ~1 core | Yes |
| Multi-step UI task (10 steps) | UIA tree per step, ~3-6 s/step | Yes, with confirmations |
| Games / canvas apps control | vision every step | Slow; marked experimental |
| Summarize 30 browser tabs | sequential extract + map-reduce | Minutes; Deep effort only |

## Web search
- DuckDuckGo via the `ddgs` Python package: headless, no browser window, no API key.
- Caveat: unofficial and can rate-limit. Mitigations: caching, backoff, optional user-configured
  free backends (self-hosted SearXNG, Brave free tier key) in settings.

## Known hard limits (stated honestly in docs)
- A 4B model makes mistakes on long multi-step tasks; EV verifies each step and asks when unsure.
- Vision on CPU is 10-25 s per image; used as fallback, never in a loop by default.
- Island window (top-center, transparent, click-through) relies on Tauri features with known Windows issues (#9250, #11461); verified in Phase 0 spike before UI work.
