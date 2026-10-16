# EV — Architecture

Expands `CLAUDE.md` §5. If this file and `CLAUDE.md` disagree, `CLAUDE.md` wins and this file is
fixed. Items marked **(spike)** are provisional until the Phase 0 spike result is recorded in
`docs/decisions.md`.

## 1. Processes

```
ev.exe (Tauri 2, Rust)
 │  windows, island, tray, hotkeys, Win32 calls, supervisor, logs
 ├── WebView2 (Svelte 5 UI)      pure presentation; talks only to Rust
 ├── ev-core (Python 3.12)       agent loop, tools, voice, memory, web
 └── llama-server                LLM + vision (Phase 1)
```

| Process | Owner | Binds | Restart policy |
|---|---|---|---|
| `ev.exe` | user | — | — |
| `ev-core` | Rust supervisor | `127.0.0.1:<random>` | 1 s, 2 s, 5 s, then stop and report |
| `llama-server` | `ev-core` (Phase 1) | `127.0.0.1:<random>` + API key | same policy, owned by core |

Rules: every child binds 127.0.0.1 only, never `0.0.0.0`; every connection carries a per-session
secret; children are killed when the parent exits (Windows Job Object with
`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` **(spike S2)**; process group on Linux).

## 2. Core startup handshake

1. Rust generates a 256-bit random token (hex) and spawns core with environment variables
   `EV_CORE_TOKEN=<token>` and `EV_DATA_DIR=<path>`. The token never appears on a command line
   (command lines are visible to other processes).
2. Core loads config, binds a WebSocket server on `127.0.0.1:0`, and writes exactly one line to
   stdout: `{"event":"listening","port":<int>,"protocol":<int>}`. All other core output goes to
   the log file, never stdout.
3. Rust connects to `ws://127.0.0.1:<port>/` with header `Authorization: Bearer <token>`.
   Core rejects the upgrade with HTTP 401 on a missing or wrong token, and with HTTP 403 when an
   `Origin` header is present (browsers always send one; Rust does not). Token comparison is
   constant-time.
4. Rust sends `hello`; core answers `hello.ack` with its version, protocol version and module
   status. A protocol version mismatch is a fatal, user-visible error (no silent degradation).
5. Liveness: Rust sends `ping` every 5 s; three missed `pong`s or a closed socket counts as a
   crash and enters the restart policy.

Startup timeout: if the `listening` line does not arrive within 10 s, the attempt counts as a crash.

## 3. Protocol

- Location: `protocol/schemas/*.schema.json` (JSON Schema draft 2020-12). One envelope schema and
  one schema per message `type`.
- Envelope: `v` (protocol version, integer), `type` (string), `id` (UUID v4 string), `payload`
  (object), optional `reply_to` (the `id` this message answers). Unknown top-level fields are
  rejected; unknown `payload` fields are ignored by receivers (forward compatibility).
- Generated code: Python (pydantic v2 models) in `core/ev_core/protocol/generated.py`; Rust
  (serde types) in `app/src-tauri/src/protocol/generated.rs`. Generated files are committed and
  CI regenerates them and fails on any diff.
- Changes are additive. Removing or renaming a field bumps `v` and updates both sides in the same
  change, with tests for old and new.
- Contract tests: shared fixtures in `protocol/fixtures/` (valid and invalid messages) are
  validated by the schema, by the Python models, and by the Rust types.

Phase 0 message set:

| type | direction | payload |
|---|---|---|
| `hello` | Rust → core | `app_version`, `protocol` |
| `hello.ack` | core → Rust | `core_version`, `protocol`, `modules[]` (`name`, `status`, `detail`) |
| `ping` / `pong` | Rust → core / core → Rust | `{}` |
| `error` | either | `code`, `message` (user-facing), `detail` (technical, logged) |
| `shutdown` | Rust → core | `reason` |

## 4. Core (`ev_core`)

```
core/ev_core/
├── __main__.py      entry point (python -m ev_core / ev-core.exe)
├── app.py           composition root: config → logging → bus → registry → server
├── protocol/        generated models + envelope helpers
├── server/          WebSocket server, auth, dispatch
├── bus/             in-process async event bus
├── modules/         Module base class, registry, status
├── config/          schema, load/validate/migrate/save, hot reload
├── logging/         structured JSON logs, rotation
├── paths.py         data directory resolution
└── agent/ tools/ voice/ vision/ memory/ web/ media/ llm/   (created by their phases)
```

### 4.1 Modules (plug-and-play)
- Every feature is a `Module` subclass with `name`, `config_section`, async `start(ctx)` and
  `stop()`. `ctx` exposes only the event bus, its own config section and a logger — never other
  modules.
- The registry starts modules in isolation: an exception in `start` marks that module `failed`
  with a user-facing message, logs the traceback, and continues. Status is one of
  `starting | ready | disabled | failed`. Disabled = turned off by its feature flag.
- Modules never import each other (enforced by an import-linter rule in CI from Phase 1, when the
  first two feature modules exist).
- Engine interfaces (`SttEngine`, `TtsEngine`, `LlmBackend`, …) are added by the phase that first
  implements them, each with a fake implementation for tests.

### 4.2 Event bus
- Async publish/subscribe keyed by event type. Handlers run as tasks; one handler failing is
  logged and does not affect other handlers or the publisher.
- Events are immutable dataclasses. The bus is in-process only; the WebSocket protocol is the
  only cross-process channel.

### 4.3 Config
- File: `<data dir>/config.toml`, top-level `config_version = <int>`.
- Validation: pydantic models; on an invalid value, that key falls back to its default and a
  warning is recorded (surfaced in Settings → Diagnostics, logged). Invalid TOML syntax → whole
  file falls back to defaults in memory, the file is left untouched, warning recorded. Never a crash.
- Migration: ordered functions `migrate_N_to_N+1` run on load; the pre-migration file is backed up
  as `config.toml.bak-v<N>` before the migrated file is written.
- Unknown keys are preserved on write (tomlkit keeps comments and ordering).
- Hot reload: file watcher debounced 300 ms; a changed section publishes `ConfigChanged(section)`
  on the bus.

### 4.4 Data directory
| Platform | Path |
|---|---|
| Windows | `%APPDATA%\EV\` |
| Linux (dev) | `$XDG_DATA_HOME/EV` (default `~/.local/share/EV`) |
| Override | `EV_DATA_DIR` (tests, portable runs) |

Contents: `config.toml`, `ev.db` (Phase 6), `logs/`, `models/` (location configurable, Phase 8).

### 4.5 Logging
- JSON lines, one object per record: `ts`, `level`, `logger`, `msg`, plus structured fields.
- Files: `logs/core.log`, rotated at 5 MB, 5 files kept. Rust writes `logs/app.log` with the same
  policy and format.
- No personal content (transcripts, prompts, file contents, clipboard) at INFO or above.

## 5. App (`app/`)

```
app/
├── src/                Svelte 5 + TS (strict)
│   ├── lib/bindings.ts generated by tauri-specta (committed)
│   ├── lib/icons/      custom EV icon set (Phase 2)
│   └── island/ settings/
└── src-tauri/src/
    ├── main.rs, lib.rs
    ├── supervisor/     core process lifecycle and restart policy
    ├── core_client/    WebSocket client, handshake, ping
    ├── protocol/       generated types
    ├── island/         window creation, hit-testing, fullscreen detection
    ├── platform/       Windows implementations + Linux fakes behind traits
    └── logging.rs
```

- Platform code sits behind traits (`CursorSource`, `FullscreenDetector`, …) with a Windows
  implementation and a Linux fake, so the app runs end-to-end on Linux.
- No `unwrap()`/`expect()` outside tests; errors are `thiserror` enums with a user-facing message.

### 5.1 Island window **(spike S1)**
- One transparent, undecorated, always-on-top, skip-taskbar window, shadow disabled, created
  hidden and shown without activation.
- Sized to the maximum panel bounds and placed top-center of the chosen display's work area.
- Click-through: the window ignores cursor events by default. A Rust loop samples the global
  cursor position (≈60 Hz while near the window, slower when far) and compares it with the pill's
  current interactive rectangle, which the UI reports through a Tauri command on every shape
  change. Inside → accept events; outside → ignore.
- Fullscreen detection (Windows): `SHQueryUserNotificationState` (busy, D3D fullscreen,
  presentation mode) plus a foreground-window-covers-monitor check.

### 5.2 Sidecar packaging **(spike S2)**
- Production: PyInstaller onedir folder shipped as Tauri bundle resources; Rust spawns
  `ev-core.exe` from the resource directory. Development: Rust spawns
  `uv run --project core python -m ev_core`.

## 6. Security boundaries (Phase 0 scope)
- Loopback only, token auth, Origin rejected, constant-time compare.
- Token held in memory only; never logged.
- Core accepts one authenticated client at a time; a second connection is refused.
- Untrusted content handling (web, files, screen, clipboard) is defined in `CLAUDE.md` §8 and
  applies from Phase 3.
