# bench

Benchmarks and spike measurement scripts for the budgets in `CLAUDE.md` §4. Method and results:
`docs/PERFORMANCE.md`.

| Path | What |
|---|---|
| `spikes/` | Phase 0 Windows spikes (S1 island, S2 packaged core, S3 llama.cpp); checklist in `spikes/README.md` |
| `honesty/` | Does EV say "not sure" instead of inventing facts (F-416); run before any prompt or model change |
| `linux-e2e/` | Run the real app on Linux for pointer, panel, chat and Settings checks |

Automated benchmarks, `budgets.toml` and `results/` history start in Phase 1.
