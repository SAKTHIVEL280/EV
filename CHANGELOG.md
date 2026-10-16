# Changelog

All notable changes to EV (Edge Voice) are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versioning: [SemVer](https://semver.org/).

## [Unreleased]

### Added
- Project contract (`CLAUDE.md`), decisions log, feasibility and performance analysis.
- Apache-2.0 license.
- Phase 0 docs: architecture, design, performance, features index, roadmap, development guide.
- Wire protocol v1 (JSON Schema) with shared contract fixtures; generated Python and Rust types.
- `ev-core` Python sidecar: loopback WebSocket server with token auth, versioned hot-reloading
  config, JSON rotating logs, event bus, module registry.
- Tauri app: core supervisor with restart backoff, island window spike (click-through,
  no focus steal, fullscreen auto-hide, squircle spring morph with frame-time reporting).
- Tooling: version check, protocol and bindings codegen, PyInstaller build, pinned llama.cpp
  fetch, third-party notices with license policy, CI for Linux and Windows, Windows spike kit.
