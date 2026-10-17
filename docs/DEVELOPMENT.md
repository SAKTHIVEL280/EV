# EV — Development

How to set up, run and check EV. Rules live in `CLAUDE.md` §10; this file is the how-to.

## 1. Toolchain

| Tool | Version | Install (Arch / Omarchy) |
|---|---|---|
| Rust | 1.99.1 (pinned in `rust-toolchain.toml`, with rustfmt + clippy) | `pacman -S rustup`, then `rustup default stable` |
| Python | 3.12 (managed by uv) | `pacman -S uv`, then `uv python install 3.12` |
| uv | 0.12.10 | `pacman -S uv` |
| Node.js | ≥ 24 | system package |
| pnpm | 11.3.0 (pinned in `app/package.json` `packageManager`) | `pacman -S pnpm` |
| Tauri Linux libraries | — | `pacman -S --needed webkit2gtk-4.1 base-devel curl wget file openssl appmenu-gtk-module libayatana-appindicator librsvg xdotool` |
| Linters for CI files | actionlint, shellcheck | `pacman -S actionlint shellcheck` |

Optional: `rustup target add x86_64-pc-windows-msvc` to type-check and lint the Windows-only
code from Linux (`cargo clippy --target x86_64-pc-windows-msvc`).

## 2. First setup

```sh
cd core && uv sync                       # core/.venv (dev tools included)
cd ../app && pnpm install --frozen-lockfile
```

## 3. Model for development

```sh
scripts/fetch-llama-cpp ubuntu-x64        # pinned llama.cpp for Linux, into vendor/ (git-ignored)
mkdir -p ~/.local/share/EV/models
curl -L -o ~/.local/share/EV/models/Qwen3.5-4B-Q4_K_M.gguf \
  https://huggingface.co/unsloth/Qwen3.5-4B-GGUF/resolve/e87f176479d0855a907a41277aca2f8ee7a09523/Qwen3.5-4B-Q4_K_M.gguf
echo "00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4  $HOME/.local/share/EV/models/Qwen3.5-4B-Q4_K_M.gguf" | sha256sum -c
```

Then set `model_default = "Qwen3.5-4B-Q4_K_M.gguf"` in the `[llm]` section of
`~/.local/share/EV/config.toml` (or of `$EV_DATA_DIR/config.toml`). Debug builds pass
`vendor/llama.cpp/<platform>` to core as `EV_LLAMA_DIR`. Without a model, chat answers
"No model installed" and the time and date questions still work (router).

## 4. Run the app

```sh
cd app && pnpm tauri dev
```

Debug builds start core from `core/.venv`. Data, config and logs go to `~/.local/share/EV`
(override with `EV_DATA_DIR=/some/dir`). Logs: `logs/app.log` (Rust) and `logs/core.log` (Python),
one JSON object per line.

On Linux the island is a development stand-in. Wayland compositors decide window placement, and
always-on-top and click-through behave differently from Windows. Island behavior is judged on
Windows 11 only (spike S1). The pointer rules, panel, chat, model download and Settings can still
be exercised end to end here: see `bench/linux-e2e/README.md` (`bench/linux-e2e/run.sh`).

Smoke test (also in CI on Linux and Windows): the real app starts core, opens Settings through the
button's command, waits for core's settings on screen and quits; a hang fails it.

```sh
cd app && pnpm build && cd src-tauri && cargo build --features custom-protocol
EV_SMOKE_TEST=1 EV_DATA_DIR=$(mktemp -d) GDK_BACKEND=x11 timeout 180 target/debug/ev
```

## 5. Checks (all must pass before a commit)

```sh
# Python core
cd core && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest

# Rust app (needs app/dist: run `pnpm build` once)
cd app/src-tauri && cargo fmt --check && cargo clippy --all-targets -- -D warnings && cargo test

# Frontend
cd app && pnpm lint && pnpm check && pnpm format:check && pnpm test && pnpm build

# Repository
python3 scripts/check-versions
cd core && uv run python ../scripts/third-party-notices --check
actionlint .github/workflows/*.yml
```

Before pushing, build and test the commit from a clean clone. It catches files that exist locally
but never reached git (this happened once: `.gitignore` hid `app/src/lib/models/`):

```sh
git clone -q . /tmp/ev-clean && (cd /tmp/ev-clean/app && pnpm install --frozen-lockfile && pnpm build \
  && pnpm test) && (cd /tmp/ev-clean/core && uv sync --frozen && uv run pytest -q); rm -rf /tmp/ev-clean
```

## 6. Generated code

| Output | Source | Regenerate | Guard |
|---|---|---|---|
| `core/ev_core/protocol/generated.py` | `protocol/ev-protocol.schema.json` | `scripts/codegen-protocol` | Python contract test |
| Rust protocol types | same schema | automatic (`build.rs`) | Rust contract tests |
| `app/src/lib/bindings.ts` | Rust commands and events | `scripts/codegen-bindings` | Rust test `bindings_are_up_to_date` |
| `THIRD_PARTY_NOTICES.md` | Cargo, uv and pnpm dependency graphs | `cd core && uv run python ../scripts/third-party-notices` | CI `--check` |

## 7. Packaging

```sh
scripts/build-core                       # core/dist/ev-core/ (PyInstaller onedir, runtime deps only)
VC_REDIST_DIR=... scripts/stage-llama-runtime  # build/llama-runtime/ (llama-server + its DLLs)
cd app && pnpm tauri build --config src-tauri/tauri.installer.conf.json  # Windows: NSIS installer
```

Windows installers are built by `.github/workflows/windows-build.yml` (artifact
`ev-windows-spike-kit`). Pinned llama.cpp builds: `scripts/fetch-llama-cpp` (SHA-256 verified,
into `vendor/llama.cpp/`, git-ignored).

## 8. Versions

`app/src-tauri/tauri.conf.json` `version` is the single source of truth. `Cargo.toml`,
`app/package.json` and `core/pyproject.toml` must match (`scripts/check-versions`; CI enforces).
Python normalizes `0.1.0-beta.1` to `0.1.0b1` at runtime (PEP 440); both mean the same release.
