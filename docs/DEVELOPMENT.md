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

## 3. Run the app

```sh
cd app && pnpm tauri dev
```

Debug builds start core from `core/.venv`. Data, config and logs go to `~/.local/share/EV`
(override with `EV_DATA_DIR=/some/dir`). Logs: `logs/app.log` (Rust) and `logs/core.log` (Python),
one JSON object per line.

On Linux the island is a development stand-in. Wayland compositors decide window placement, and
always-on-top and click-through behave differently from Windows. Island behavior is judged on
Windows 11 only (spike S1).

## 4. Checks (all must pass before a commit)

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

## 5. Generated code

| Output | Source | Regenerate | Guard |
|---|---|---|---|
| `core/ev_core/protocol/generated.py` | `protocol/ev-protocol.schema.json` | `scripts/codegen-protocol` | Python contract test |
| Rust protocol types | same schema | automatic (`build.rs`) | Rust contract tests |
| `app/src/lib/bindings.ts` | Rust commands and events | `scripts/codegen-bindings` | Rust test `bindings_are_up_to_date` |
| `THIRD_PARTY_NOTICES.md` | Cargo, uv and pnpm dependency graphs | `cd core && uv run python ../scripts/third-party-notices` | CI `--check` |

## 6. Packaging

```sh
scripts/build-core          # core/dist/ev-core/ (PyInstaller onedir, runtime deps only)
cd app && pnpm tauri build  # on Windows: NSIS installer with the core as resources
```

Windows installers are built by `.github/workflows/windows-build.yml` (artifact
`ev-windows-spike-kit`). Pinned llama.cpp builds: `scripts/fetch-llama-cpp` (SHA-256 verified,
into `vendor/llama.cpp/`, git-ignored).

## 7. Versions

`app/src-tauri/tauri.conf.json` `version` is the single source of truth. `Cargo.toml`,
`app/package.json` and `core/pyproject.toml` must match (`scripts/check-versions`; CI enforces).
Python normalizes `0.1.0-beta.1` to `0.1.0b1` at runtime (PEP 440); both mean the same release.
