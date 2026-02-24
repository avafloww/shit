# shitd — Persistent Daemon for Faster Inference

## Problem

Every `shit` invocation loads the ~253MB GGUF model + tokenizer from disk, parses it, and builds the model weights in memory. This takes noticeable time. A persistent daemon that keeps the model hot in memory eliminates this startup cost.

## Design

### Architecture

Single binary with a `daemon` Cargo feature flag (default-enabled). All daemon code is behind `#[cfg(feature = "daemon")]`. Disable with `--no-default-features` for minimal builds.

Core refactor: extract inference into a reusable `Engine` struct that holds the loaded model + tokenizer in memory:

```
Engine::new()          → loads model + tokenizer once
Engine::infer(prompt)  → runs inference, returns Vec<String> of fixes
```

Both direct mode and daemon mode use the same `Engine`. No code duplication.

### Execution Flows

**Without daemon (current behavior, or daemon feature disabled):**
```
shit → Engine::new() → Engine::infer() → display fixes → exit
```

**With daemon running:**
```
shitd: shit daemon start → Engine::new() → HTTP server loop
shit:  HTTP POST to shitd → get fixes → display fixes → exit
```

**Fallback logic:**
1. Port file exists + connection succeeds → use daemon (fast path)
2. Port file exists + connection fails → warn `shit: daemon not responding, loading model locally...`, fall back to local Engine
3. No port file → silent fall back to local Engine

### HTTP Protocol

Server: `tiny_http` on `127.0.0.1` with OS-assigned port. Port written to `$XDG_RUNTIME_DIR/shitd.port` (Linux) or `~/Library/Application Support/shit/shitd.port` (macOS).

**Endpoints:**
- `POST /infer` — request: `{"prompt": "..."}`, response: `{"fixes": [...]}`
- `GET /health` — returns 200, used by `shit daemon status`

JSON via `serde_json`.

### CLI Subcommands

All behind `daemon` feature:
- `shit daemon start` — run server in foreground (for service managers)
- `shit daemon install` — auto-detect platform, install + enable service
- `shit daemon uninstall` — stop + disable + remove service files
- `shit daemon status` — check if daemon is running (via /health)

### Service Management

`shit daemon install` auto-detects platform:
- Linux: systemd (checks `/run/systemd/system`)
- macOS: launchd

**systemd** — user unit at `~/.config/systemd/user/shitd.service`:
- `ExecStart=/path/to/shit daemon start`
- `Restart=on-failure`
- `WantedBy=default.target`
- Installed via `systemctl --user daemon-reload && systemctl --user enable --now shitd`

**launchd** — plist at `~/Library/LaunchAgents/dev.ava.shitd.plist`:
- Label: `dev.ava.shitd`
- `RunAtLoad` + `KeepAlive` enabled

Both resolve the binary path via `std::env::current_exe()` at install time.

`shit daemon uninstall` reverses: stops, disables, removes the service file.

### Feature Flag & Dependencies

```toml
[features]
default = ["daemon"]
daemon = ["dep:tiny_http", "dep:serde_json"]
```

Without the `daemon` feature:
- No `shit daemon *` subcommands
- No client connection attempt (no "try daemon first" logic)
- No `tiny_http` or `serde_json` dependencies
- `shit` behaves exactly as it does today

### File Layout

New/modified files:
- `src/model/engine.rs` — `Engine` struct (model + tokenizer loaded once)
- `src/model/inference.rs` — simplified: try daemon client, fall back to local Engine
- `src/daemon/mod.rs` — subcommand dispatch
- `src/daemon/server.rs` — tiny_http server with /infer + /health
- `src/daemon/service.rs` — systemd/launchd templates, install/uninstall logic

### Non-Goals

- Windows service support (future work)
- Idle timeout / model unloading
- Multiple concurrent model versions
- Authentication (localhost-only, single-user)
