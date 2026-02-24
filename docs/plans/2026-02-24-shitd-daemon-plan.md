# shitd Daemon Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a persistent daemon mode (`shitd`) that keeps the model in memory between invocations, with systemd/launchd service management.

**Architecture:** Extract model loading into a reusable `Engine` struct. Add an HTTP server (tiny_http) behind a `daemon` feature flag. The CLI tries the daemon first when a port file exists, falls back to local inference otherwise.

**Tech Stack:** Rust, tiny_http (HTTP server), serde_json (wire format), existing ureq (HTTP client)

**Design doc:** `docs/plans/2026-02-24-shitd-daemon-design.md`

---

### Task 1: Extract Engine struct from inference.rs

The foundation everything else builds on. Pull model loading + inference into a struct that can be held in memory.

**Files:**
- Create: `src/model/engine.rs`
- Modify: `src/model/inference.rs`
- Modify: `src/model/mod.rs`

**Step 1: Create `src/model/engine.rs` with the Engine struct**

Move model loading and inference into a reusable struct. The key types from candle we need are `ModelWeights` and the `Device`. The tokenizer is from the `tokenizers` crate.

```rust
use anyhow::{bail, Result};
use candle_core::{DType, Device, Tensor};
use candle_transformers::generation::LogitsProcessor;
use candle_transformers::models::quantized_gemma3::ModelWeights;
use std::path::PathBuf;
use tokenizers::Tokenizer;

const MAX_GENERATED_TOKENS: usize = 30;

pub struct Engine {
    model: ModelWeights,
    tokenizer: Tokenizer,
    device: Device,
}

impl Engine {
    pub fn new(model_path: &PathBuf, tokenizer_path: &PathBuf) -> Result<Self> {
        let device = Device::Cpu;
        let mut file = std::fs::File::open(model_path)?;
        let content = candle_core::quantized::gguf_file::Content::read(&mut file)?;
        let model = ModelWeights::from_gguf(content, &mut file, &device)?;
        let tokenizer = Tokenizer::from_file(tokenizer_path).map_err(anyhow::Error::msg)?;

        Ok(Self {
            model,
            tokenizer,
            device,
        })
    }

    pub fn infer(&mut self, prompt: &str) -> Result<String> {
        let encoding = self.tokenizer.encode(prompt, true).map_err(anyhow::Error::msg)?;
        let prompt_tokens = encoding.get_ids().to_vec();

        let device = &self.device;
        let model = &mut self.model;

        generate_tokens(&prompt_tokens, &self.tokenizer, &mut |tokens, pos| {
            let input = Tensor::new(tokens, device)?.unsqueeze(0)?;
            let logits = model.forward(&input, pos)?;
            Ok(logits.squeeze(0)?)
        })
    }
}
```

Move `generate_tokens`, `extract_last_logits` into this file as private functions (copy them verbatim from current `inference.rs`).

**Step 2: Simplify `src/model/inference.rs`**

Remove `infer_gguf`, `generate_tokens`, `extract_last_logits`. Keep `find_model`, `apply_op`, `infer`, `download_*` functions. Change `infer_model` to use `Engine`:

```rust
fn infer_model(prompt: &str) -> Result<String> {
    let paths = find_model()?;
    let mut engine = Engine::new(&paths.model_path, &paths.tokenizer_path)?;
    engine.infer(prompt)
}
```

Add `use super::engine::Engine;` and keep `ModelPaths` + `find_model` + `apply_op` + `download_*` here.

**Step 3: Update `src/model/mod.rs`**

```rust
pub mod engine;
mod inference;

pub use engine::Engine;
pub use inference::{find_model, infer};
```

Note: `find_model` needs to become `pub` in inference.rs (it's currently private). The daemon server will call `find_model()` then `Engine::new()`.

**Step 4: Build and verify**

Run: `cargo build 2>&1`
Expected: compiles cleanly, no behavior change.

**Step 5: Commit**

```bash
git add src/model/engine.rs src/model/inference.rs src/model/mod.rs
git commit -m "refactor: extract Engine struct from inference"
```

---

### Task 2: Add daemon feature flag and dependencies

**Files:**
- Modify: `Cargo.toml`

**Step 1: Add feature flag and optional deps**

Check latest stable versions of `tiny_http` and `serde_json` before adding:
```bash
cargo search tiny_http --limit 1
cargo search serde_json --limit 1
```

Add to `Cargo.toml`:

```toml
[features]
default = ["daemon"]
daemon = ["dep:tiny_http", "dep:serde_json"]

[dependencies]
# ... existing deps ...
tiny_http = { version = "<latest>", optional = true }
serde_json = { version = "<latest>", optional = true }
```

**Step 2: Verify both feature configs build**

Run: `cargo build 2>&1`
Expected: builds with daemon feature (default)

Run: `cargo build --no-default-features 2>&1`
Expected: builds without daemon feature

**Step 3: Commit**

```bash
git add Cargo.toml Cargo.lock
git commit -m "feat: add daemon feature flag with tiny_http and serde_json deps"
```

---

### Task 3: Daemon server

**Files:**
- Create: `src/daemon/mod.rs`
- Create: `src/daemon/server.rs`

**Step 1: Create `src/daemon/server.rs`**

The server loads the Engine once and handles HTTP requests in a loop. Uses `tiny_http` bound to `127.0.0.1:0` (OS-assigned port). Writes port to a file so the client can find it.

```rust
use anyhow::Result;
use std::io::Read;
use std::path::PathBuf;

use crate::model::{find_model, Engine};

/// Returns the path where the daemon writes its port number.
/// Linux: $XDG_RUNTIME_DIR/shitd.port
/// macOS: ~/Library/Application Support/shit/shitd.port
/// Fallback: /tmp/shitd-$USER.port
pub fn port_file_path() -> PathBuf {
    if let Ok(runtime_dir) = std::env::var("XDG_RUNTIME_DIR") {
        return PathBuf::from(runtime_dir).join("shitd.port");
    }
    if let Some(data_dir) = dirs::data_dir() {
        // macOS: ~/Library/Application Support/shit/
        let dir = data_dir.join("shit");
        let _ = std::fs::create_dir_all(&dir);
        return dir.join("shitd.port");
    }
    let user = std::env::var("USER").unwrap_or_else(|_| "unknown".into());
    PathBuf::from(format!("/tmp/shitd-{}.port", user))
}

pub fn run_server() -> Result<()> {
    let paths = find_model()?;
    eprintln!("shitd: loading model...");
    let mut engine = Engine::new(&paths.model_path, &paths.tokenizer_path)?;
    eprintln!("shitd: model loaded");

    let server = tiny_http::Server::http("127.0.0.1:0")
        .map_err(|e| anyhow::anyhow!("failed to bind: {}", e))?;
    let port = server.server_addr().to_ip().unwrap().port();

    let port_file = port_file_path();
    std::fs::write(&port_file, port.to_string())?;
    eprintln!("shitd: listening on 127.0.0.1:{}", port);

    // Clean up port file on shutdown
    let _guard = PortFileGuard(port_file);

    for request in server.incoming_requests() {
        match (request.method(), request.url()) {
            (tiny_http::Method::Get, "/health") => {
                let response = tiny_http::Response::from_string("ok");
                let _ = request.respond(response);
            }
            (tiny_http::Method::Post, "/infer") => {
                handle_infer(request, &mut engine);
            }
            _ => {
                let response = tiny_http::Response::from_string("not found")
                    .with_status_code(404);
                let _ = request.respond(response);
            }
        }
    }

    Ok(())
}

fn handle_infer(mut request: tiny_http::Request, engine: &mut Engine) {
    let mut body = String::new();
    if request.as_reader().read_to_string(&mut body).is_err() {
        let resp = tiny_http::Response::from_string(r#"{"error":"bad request"}"#)
            .with_status_code(400);
        let _ = request.respond(resp);
        return;
    }

    let parsed: Result<serde_json::Value, _> = serde_json::from_str(&body);
    let prompt = match parsed {
        Ok(v) => v["prompt"].as_str().unwrap_or("").to_string(),
        Err(_) => {
            let resp = tiny_http::Response::from_string(r#"{"error":"invalid json"}"#)
                .with_status_code(400);
            let _ = request.respond(resp);
            return;
        }
    };

    // Run inference using the shared Engine
    // Engine::infer returns the raw operation string; we need to apply it
    // to get fixes, same as inference::infer does
    let result = crate::model::infer_with_engine(engine, &prompt);
    let fixes = match result {
        Ok(fixes) => fixes,
        Err(e) => {
            let resp = tiny_http::Response::from_string(
                serde_json::json!({"error": e.to_string()}).to_string(),
            ).with_status_code(500);
            let _ = request.respond(resp);
            return;
        }
    };

    let resp_body = serde_json::json!({"fixes": fixes}).to_string();
    let response = tiny_http::Response::from_string(resp_body)
        .with_header("Content-Type: application/json".parse().unwrap());
    let _ = request.respond(response);
}

/// RAII guard that removes the port file when the server shuts down.
struct PortFileGuard(PathBuf);

impl Drop for PortFileGuard {
    fn drop(&mut self) {
        let _ = std::fs::remove_file(&self.0);
    }
}
```

**Step 2: Create `src/daemon/mod.rs`**

```rust
pub mod server;
```

**Step 3: Add `infer_with_engine` to `src/model/inference.rs`**

This is the same logic as `infer()` but takes a mutable Engine reference instead of creating a new one:

```rust
pub fn infer_with_engine(engine: &mut Engine, prompt: &str) -> Result<Vec<String>> {
    let command = prompt
        .lines()
        .find_map(|line| line.strip_prefix("$ "))
        .unwrap_or("");

    let op = engine.infer(prompt)?;
    let op = op.trim();
    if op == "NONE" || op.is_empty() {
        return Ok(vec![]);
    }
    if let Some(fix) = apply_op(command, op) {
        return Ok(vec![fix]);
    }
    if op.starts_with("FULL ") {
        return Ok(vec![op[5..].to_string()]);
    }
    Ok(vec![])
}
```

Export it from `src/model/mod.rs`:
```rust
pub use inference::infer_with_engine;
```

**Step 4: Wire daemon module into `src/main.rs`**

Add conditional module declaration:

```rust
#[cfg(feature = "daemon")]
mod daemon;
```

**Step 5: Build**

Run: `cargo build 2>&1`
Expected: compiles. Server code exists but isn't called yet.

**Step 6: Commit**

```bash
git add src/daemon/ src/model/inference.rs src/model/mod.rs src/main.rs
git commit -m "feat: add daemon HTTP server with /infer and /health endpoints"
```

---

### Task 4: Daemon client — try daemon first, fall back to local

**Files:**
- Modify: `src/model/inference.rs`

**Step 1: Add daemon client logic**

Add a function to try the daemon, and modify `infer_model` to use it:

```rust
#[cfg(feature = "daemon")]
fn try_daemon(prompt: &str) -> Option<String> {
    use crate::daemon::server::port_file_path;

    let port_file = port_file_path();
    if !port_file.exists() {
        return None; // daemon never installed, silent fallback
    }

    let port_str = std::fs::read_to_string(&port_file).ok()?;
    let port: u16 = port_str.trim().parse().ok()?;

    let url = format!("http://127.0.0.1:{}/infer", port);
    let body = serde_json::json!({"prompt": prompt}).to_string();

    let agent = ureq::Agent::new_with_defaults();
    match agent
        .post(&url)
        .header("Content-Type", "application/json")
        .send_bytes(body.as_bytes())
    {
        Ok(response) => {
            let text = response.into_body().read_to_string().ok()?;
            Some(text)
        }
        Err(_) => {
            eprintln!("shit: daemon not responding, loading model locally...");
            None
        }
    }
}
```

Update `infer()` to try daemon first:

```rust
pub fn infer(prompt: &str) -> Result<Vec<String>> {
    // Try daemon first if feature enabled
    #[cfg(feature = "daemon")]
    if let Some(response) = try_daemon(prompt) {
        if let Ok(v) = serde_json::from_str::<serde_json::Value>(&response) {
            if let Some(fixes) = v["fixes"].as_array() {
                let fixes: Vec<String> = fixes
                    .iter()
                    .filter_map(|f| f.as_str().map(|s| s.to_string()))
                    .collect();
                return Ok(fixes);
            }
        }
    }

    // Fallback: load model locally
    let command = prompt
        .lines()
        .find_map(|line| line.strip_prefix("$ "))
        .unwrap_or("");

    let op = infer_model(prompt)?;
    let op = op.trim();
    if op == "NONE" || op.is_empty() {
        return Ok(vec![]);
    }
    if let Some(fix) = apply_op(command, op) {
        return Ok(vec![fix]);
    }
    if op.starts_with("FULL ") {
        return Ok(vec![op[5..].to_string()]);
    }
    Ok(vec![])
}
```

**Step 2: Build both feature configs**

Run: `cargo build 2>&1`
Expected: builds with daemon

Run: `cargo build --no-default-features 2>&1`
Expected: builds without daemon (no daemon client code compiled)

**Step 3: Commit**

```bash
git add src/model/inference.rs
git commit -m "feat: try daemon for inference, fall back to local model"
```

---

### Task 5: CLI subcommands for daemon management

**Files:**
- Modify: `src/main.rs`
- Modify: `src/daemon/mod.rs`

**Step 1: Add Daemon subcommand to clap**

In `src/main.rs`, add a `Daemon` variant to the `Command` enum (behind feature gate):

```rust
#[derive(Subcommand)]
enum Command {
    /// Output shell init script
    Init {
        /// Shell to generate init script for (fish, bash, zsh, powershell, tcsh)
        shell: String,
    },
    #[cfg(feature = "daemon")]
    /// Manage the shit daemon (shitd)
    Daemon {
        #[command(subcommand)]
        action: DaemonCommand,
    },
}

#[cfg(feature = "daemon")]
#[derive(Subcommand)]
enum DaemonCommand {
    /// Start the daemon server (foreground)
    Start,
    /// Install as a system service (systemd/launchd)
    Install,
    /// Uninstall the system service
    Uninstall,
    /// Check if the daemon is running
    Status,
}
```

Add the match arm in `main()`:

```rust
#[cfg(feature = "daemon")]
Some(Command::Daemon { action }) => {
    daemon::handle(action)?;
}
```

**Step 2: Wire up `daemon::handle` in `src/daemon/mod.rs`**

```rust
pub mod server;
pub mod service;

use anyhow::Result;
use crate::DaemonCommand;

pub fn handle(action: DaemonCommand) -> Result<()> {
    match action {
        DaemonCommand::Start => server::run_server(),
        DaemonCommand::Install => service::install(),
        DaemonCommand::Uninstall => service::uninstall(),
        DaemonCommand::Status => status(),
    }
}

fn status() -> Result<()> {
    let port_file = server::port_file_path();
    if !port_file.exists() {
        eprintln!("shitd: not running (no port file)");
        return Ok(());
    }

    let port_str = std::fs::read_to_string(&port_file)?;
    let port: u16 = port_str.trim().parse()?;

    let url = format!("http://127.0.0.1:{}/health", port);
    let agent = ureq::Agent::new_with_defaults();
    match agent.get(&url).call() {
        Ok(_) => eprintln!("shitd: running on port {}", port),
        Err(_) => eprintln!("shitd: not responding (port file exists but server unreachable)"),
    }

    Ok(())
}
```

**Step 3: Build**

Run: `cargo build 2>&1`
Expected: compiles (service module will be a stub initially, create empty file).

Create `src/daemon/service.rs` as a stub:
```rust
use anyhow::Result;

pub fn install() -> Result<()> {
    todo!("service install")
}

pub fn uninstall() -> Result<()> {
    todo!("service uninstall")
}
```

**Step 4: Commit**

```bash
git add src/main.rs src/daemon/
git commit -m "feat: add shit daemon start/install/uninstall/status subcommands"
```

---

### Task 6: Service management — systemd and launchd

**Files:**
- Modify: `src/daemon/service.rs`

**Step 1: Implement service install/uninstall**

```rust
use anyhow::{bail, Result};
use std::path::PathBuf;

enum ServiceManager {
    Systemd,
    Launchd,
}

fn detect_service_manager() -> Result<ServiceManager> {
    if cfg!(target_os = "macos") {
        return Ok(ServiceManager::Launchd);
    }
    if std::path::Path::new("/run/systemd/system").exists() {
        return Ok(ServiceManager::Systemd);
    }
    bail!("no supported service manager found (need systemd or launchd)")
}

fn binary_path() -> Result<PathBuf> {
    std::env::current_exe().map_err(|e| anyhow::anyhow!("could not determine binary path: {}", e))
}

pub fn install() -> Result<()> {
    match detect_service_manager()? {
        ServiceManager::Systemd => install_systemd(),
        ServiceManager::Launchd => install_launchd(),
    }
}

pub fn uninstall() -> Result<()> {
    match detect_service_manager()? {
        ServiceManager::Systemd => uninstall_systemd(),
        ServiceManager::Launchd => uninstall_launchd(),
    }
}

fn systemd_unit_path() -> Result<PathBuf> {
    let config_dir = dirs::config_dir()
        .ok_or_else(|| anyhow::anyhow!("could not determine config directory"))?;
    let dir = config_dir.join("systemd").join("user");
    std::fs::create_dir_all(&dir)?;
    Ok(dir.join("shitd.service"))
}

fn install_systemd() -> Result<()> {
    let bin = binary_path()?;
    let unit_path = systemd_unit_path()?;

    let unit = format!(
        "[Unit]\n\
         Description=shit daemon — keeps model in memory for fast inference\n\
         \n\
         [Service]\n\
         ExecStart={bin} daemon start\n\
         Restart=on-failure\n\
         \n\
         [Install]\n\
         WantedBy=default.target\n",
        bin = bin.display()
    );

    std::fs::write(&unit_path, &unit)?;
    eprintln!("shitd: wrote {}", unit_path.display());

    let status = std::process::Command::new("systemctl")
        .args(["--user", "daemon-reload"])
        .status()?;
    if !status.success() {
        bail!("systemctl daemon-reload failed");
    }

    let status = std::process::Command::new("systemctl")
        .args(["--user", "enable", "--now", "shitd"])
        .status()?;
    if !status.success() {
        bail!("systemctl enable --now failed");
    }

    eprintln!("shitd: service installed and started");
    Ok(())
}

fn uninstall_systemd() -> Result<()> {
    let _ = std::process::Command::new("systemctl")
        .args(["--user", "disable", "--now", "shitd"])
        .status();

    let unit_path = systemd_unit_path()?;
    if unit_path.exists() {
        std::fs::remove_file(&unit_path)?;
        eprintln!("shitd: removed {}", unit_path.display());
    }

    let _ = std::process::Command::new("systemctl")
        .args(["--user", "daemon-reload"])
        .status();

    eprintln!("shitd: service uninstalled");
    Ok(())
}

const LAUNCHD_LABEL: &str = "dev.ava.shitd";

fn launchd_plist_path() -> Result<PathBuf> {
    let home = dirs::home_dir()
        .ok_or_else(|| anyhow::anyhow!("could not determine home directory"))?;
    Ok(home.join("Library").join("LaunchAgents").join(format!("{}.plist", LAUNCHD_LABEL)))
}

fn install_launchd() -> Result<()> {
    let bin = binary_path()?;
    let plist_path = launchd_plist_path()?;

    let plist = format!(
        r#"<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{label}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{bin}</string>
        <string>daemon</string>
        <string>start</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
"#,
        label = LAUNCHD_LABEL,
        bin = bin.display()
    );

    std::fs::write(&plist_path, &plist)?;
    eprintln!("shitd: wrote {}", plist_path.display());

    let status = std::process::Command::new("launchctl")
        .args(["load", &plist_path.to_string_lossy()])
        .status()?;
    if !status.success() {
        bail!("launchctl load failed");
    }

    eprintln!("shitd: service installed and started");
    Ok(())
}

fn uninstall_launchd() -> Result<()> {
    let plist_path = launchd_plist_path()?;

    if plist_path.exists() {
        let _ = std::process::Command::new("launchctl")
            .args(["unload", &plist_path.to_string_lossy()])
            .status();
        std::fs::remove_file(&plist_path)?;
        eprintln!("shitd: removed {}", plist_path.display());
    }

    eprintln!("shitd: service uninstalled");
    Ok(())
}
```

**Step 2: Build**

Run: `cargo build 2>&1`
Expected: compiles cleanly.

**Step 3: Commit**

```bash
git add src/daemon/service.rs
git commit -m "feat: implement systemd and launchd service install/uninstall"
```

---

### Task 7: Tests

**Files:**
- Create: `tests/apply_op.rs`
- Create: `tests/daemon_protocol.rs`

**Step 1: Add unit tests for apply_op**

`apply_op` is currently private. Make it `pub(crate)` or add `#[cfg(test)]` module tests inside `inference.rs`. Easiest is to add a test module at the bottom of `src/model/inference.rs`:

```rust
#[cfg(test)]
mod tests {
    use super::apply_op;

    #[test]
    fn test_replace_op() {
        assert_eq!(
            apply_op("git psuh origin main", "REPLACE psuh push"),
            Some("git push origin main".to_string())
        );
    }

    #[test]
    fn test_replace_missing_word() {
        assert_eq!(apply_op("git push", "REPLACE psuh push"), None);
    }

    #[test]
    fn test_flag_op() {
        assert_eq!(
            apply_op("rm myfile", "FLAG -f"),
            Some("rm -f myfile".to_string())
        );
    }

    #[test]
    fn test_flag_op_no_args() {
        assert_eq!(
            apply_op("ls", "FLAG -la"),
            Some("ls -la".to_string())
        );
    }

    #[test]
    fn test_prepend_op() {
        assert_eq!(
            apply_op("apt install foo", "PREPEND sudo"),
            Some("sudo apt install foo".to_string())
        );
    }

    #[test]
    fn test_full_op() {
        assert_eq!(
            apply_op("sl", "FULL ls"),
            Some("ls".to_string())
        );
    }

    #[test]
    fn test_none_op() {
        assert_eq!(apply_op("git push", "NONE"), None);
    }

    #[test]
    fn test_unknown_op() {
        assert_eq!(apply_op("git push", "UNKNOWN something"), None);
    }
}
```

**Step 2: Run tests**

Run: `cargo test 2>&1`
Expected: all tests pass.

**Step 3: Add daemon protocol tests (behind feature flag)**

Create `tests/daemon_protocol.rs` for JSON serialization round-trip tests:

```rust
#![cfg(feature = "daemon")]

#[test]
fn test_infer_request_format() {
    let prompt = "$ git psuh\n> git: 'psuh' is not a git command\nOP:";
    let body = serde_json::json!({"prompt": prompt});
    let serialized = body.to_string();
    let parsed: serde_json::Value = serde_json::from_str(&serialized).unwrap();
    assert_eq!(parsed["prompt"].as_str().unwrap(), prompt);
}

#[test]
fn test_infer_response_format() {
    let fixes = vec!["git push"];
    let body = serde_json::json!({"fixes": fixes});
    let serialized = body.to_string();
    let parsed: serde_json::Value = serde_json::from_str(&serialized).unwrap();
    let result: Vec<String> = parsed["fixes"]
        .as_array()
        .unwrap()
        .iter()
        .map(|v| v.as_str().unwrap().to_string())
        .collect();
    assert_eq!(result, vec!["git push".to_string()]);
}
```

**Step 4: Run all tests**

Run: `cargo test 2>&1`
Expected: all tests pass.

**Step 5: Commit**

```bash
git add src/model/inference.rs tests/
git commit -m "test: add apply_op unit tests and daemon protocol tests"
```

---

### Task 8: Final build verification and cleanup

**Step 1: Full build check**

Run: `cargo build --release 2>&1`
Expected: release build succeeds.

Run: `cargo build --release --no-default-features 2>&1`
Expected: minimal build succeeds without daemon code.

Run: `cargo test 2>&1`
Expected: all tests pass.

**Step 2: Check binary size difference**

Run: `ls -lh target/release/shit`
Note the size for reference.

**Step 3: Verify subcommands work**

Run: `./target/release/shit daemon status`
Expected: prints "shitd: not running (no port file)"

Run: `./target/release/shit --help`
Expected: shows `daemon` subcommand in help text.

Run: `./target/release/shit daemon --help`
Expected: shows start/install/uninstall/status subcommands.

**Step 4: Commit any cleanup**

If any adjustments were needed, commit them.
