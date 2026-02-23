# Auto-Download Model Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Auto-download the GGUF model from GitHub Release assets on first run, cached locally with SHA256 verification.

**Architecture:** `build.rs` embeds GitHub org/repo (parsed from git remote) and LFS pointer SHA256 hashes (for cache validation). Version comes from `CARGO_PKG_VERSION` (free). Download URL: `https://github.com/{repo}/releases/download/v{version}/shit.gguf`. At runtime, `find_model()` checks local cache, downloads if missing/stale with integrity verification, falls back to rule-based inference on failure. Safetensors inference path removed entirely.

**Tech Stack:** Rust, ureq 3.x (HTTP client), sha2 (integrity verification), dirs (XDG paths), candle (GGUF inference)

---

### Task 1: Add model GGUF to repo via LFS

The Q4 GGUF needs to be in the LFS-tracked `model/` directory for development. `.gitattributes` already tracks `model/**/*.gguf`. For distribution, it will be uploaded as a GitHub Release asset.

**Files:**
- Create: `model/shit.gguf` (copy from `training/model/shit-ops.q4.gguf`)

**Step 1: Copy the Q4 GGUF into the LFS-tracked directory**

```bash
cp training/model/shit-ops.q4.gguf model/shit.gguf
```

**Step 2: Verify LFS is tracking it**

```bash
git lfs pointer --file=model/shit.gguf
```

Expected: output containing `oid sha256:...` and `size ...`

**Step 3: Commit**

```bash
git add model/shit.gguf
git commit -m "feat: add Q4_K_M GGUF to model/ for LFS-based distribution"
```

---

### Task 2: Create build.rs to embed repo URL and LFS content hashes

`build.rs` embeds three things:
- `GITHUB_REPO` — org/repo parsed from git remote (e.g. `avafloww/shit`), overridable via `SHIT_GITHUB_REPO` env var at build time, hardcoded fallback `avafloww/shit`
- `MODEL_SHA256` — from LFS pointer (or computed from blob if LFS is pulled)
- `TOKENIZER_SHA256` — same for tokenizer.json

Note: version comes for free via `env!("CARGO_PKG_VERSION")` — no build.rs work needed.

**Files:**
- Create: `cli/build.rs`
- Modify: `cli/Cargo.toml` (add `sha2` as build-dependency)

**Step 1: Add sha2 as build-dependency in Cargo.toml**

```toml
[build-dependencies]
sha2 = "0.10"
```

**Step 2: Write build.rs**

```rust
use sha2::{Sha256, Digest};
use std::process::Command;

fn main() {
    // Parse GitHub org/repo from git remote, overridable via env var
    let repo = std::env::var("SHIT_GITHUB_REPO").unwrap_or_else(|_| {
        parse_github_repo().unwrap_or_else(|| "avafloww/shit".to_string())
    });
    println!("cargo:rustc-env=GITHUB_REPO={}", repo);

    // Get content hashes for model files
    let model_hash = file_sha256("../model/shit.gguf")
        .unwrap_or_else(|| "unknown".to_string());
    println!("cargo:rustc-env=MODEL_SHA256={}", model_hash);

    let tok_hash = file_sha256("../model/tokenizer.json")
        .unwrap_or_else(|| "unknown".to_string());
    println!("cargo:rustc-env=TOKENIZER_SHA256={}", tok_hash);

    // Rerun if these change
    println!("cargo:rerun-if-changed=../model/shit.gguf");
    println!("cargo:rerun-if-changed=../model/tokenizer.json");
    println!("cargo:rerun-if-env-changed=SHIT_GITHUB_REPO");
}

/// Get SHA256 for a file — either from LFS pointer or by streaming the blob.
fn file_sha256(path: &str) -> Option<String> {
    use std::io::Read;

    let mut file = std::fs::File::open(path).ok()?;

    // Read first 512 bytes to check if it's an LFS pointer
    let mut header = [0u8; 512];
    let n = file.read(&mut header).ok()?;
    let header_str = std::str::from_utf8(&header[..n]).ok()?;

    if header_str.starts_with("version https://git-lfs.github.com/spec/v1") {
        for line in header_str.lines() {
            if let Some(oid) = line.strip_prefix("oid sha256:") {
                return Some(oid.trim().to_string());
            }
        }
        return None;
    }

    // Actual blob — stream into hasher (avoids loading 253MB into memory)
    let mut hasher = Sha256::new();
    hasher.update(&header[..n]);
    std::io::copy(&mut file, &mut hasher).ok()?;
    Some(format!("{:x}", hasher.finalize()))
}

/// Parse GitHub org/repo from the origin remote URL.
/// Handles SCP-style (host:org/repo.git) and URL-style (scheme://host/org/repo.git)
fn parse_github_repo() -> Option<String> {
    let output = Command::new("git")
        .args(["remote", "get-url", "origin"])
        .output()
        .ok()?;
    let url = String::from_utf8(output.stdout).ok()?;
    let url = url.trim();

    // SCP-style: git@host:org/repo.git or host-alias:org/repo.git
    if !url.contains("://") {
        let path = url.split_once(':').map(|(_, path)| path)?;
        return Some(path.trim_end_matches(".git").to_string());
    }

    // URL-style: https://host/org/repo.git — extract last two path segments
    let parts: Vec<&str> = url.trim_end_matches('/').rsplit('/').take(2).collect();
    if parts.len() == 2 {
        return Some(
            format!("{}/{}", parts[1], parts[0])
                .trim_end_matches(".git")
                .to_string(),
        );
    }
    None
}
```

**Step 3: Verify it compiles**

```bash
cd cli && cargo build 2>&1 | tail -5
```

Expected: successful build

**Step 4: Commit**

```bash
git add cli/build.rs cli/Cargo.toml cli/Cargo.lock
git commit -m "feat: build.rs embeds repo URL and LFS content hashes"
```

---

### Task 3: Add ureq and sha2 runtime dependencies, remove candle-nn

**Files:**
- Modify: `cli/Cargo.toml`

**Step 1: Update Cargo.toml**

Add to `[dependencies]`:
- `ureq = "3.2"` — HTTP client for downloading (rustls TLS enabled by default)
- `sha2 = "0.10"` — SHA256 verification of downloaded files

Remove from `[dependencies]`:
- `candle-nn = "0.9.2"` — no longer needed without safetensors

**Step 2: Commit (won't compile yet — Task 4 removes the candle-nn usage)**

```bash
git add cli/Cargo.toml cli/Cargo.lock
git commit -m "chore: add ureq + sha2, remove candle-nn"
```

---

### Task 4: Rewrite inference.rs — remove safetensors, add download with integrity check

Rewrite `cli/src/model/inference.rs` to:
1. Remove `ModelSource` enum, safetensors inference, `candle-nn` imports
2. Add `download_file()` with progress display and SHA256 verification
3. Update `find_model()` to check cache hash and trigger download from GitHub Release assets
4. Set connection/read timeouts on ureq

**Files:**
- Modify: `cli/src/model/inference.rs`

**Step 1: Write the new inference.rs**

Replace the entire file. Key changes from current code:

**Constants:**
```rust
const MAX_GENERATED_TOKENS: usize = 30;
const GITHUB_REPO: &str = env!("GITHUB_REPO");
const VERSION: &str = env!("CARGO_PKG_VERSION");
const MODEL_SHA256: &str = env!("MODEL_SHA256");
const TOKENIZER_SHA256: &str = env!("TOKENIZER_SHA256");
```

**find_model() — check cache, download from release assets if needed:**
```rust
struct ModelPaths {
    model_path: PathBuf,
    tokenizer_path: PathBuf,
}

fn find_model() -> Result<ModelPaths> {
    // 1. Check next to binary (local dev override)
    if let Ok(exe) = std::env::current_exe() {
        let dir = exe.parent().unwrap();
        if dir.join("shit.gguf").exists() && dir.join("tokenizer.json").exists() {
            return Ok(ModelPaths {
                model_path: dir.join("shit.gguf"),
                tokenizer_path: dir.join("tokenizer.json"),
            });
        }
    }

    // 2. Check/populate XDG data dir cache
    let data_dir = dirs::data_dir()
        .ok_or_else(|| anyhow::anyhow!("Could not determine data directory"))?;
    let dir = data_dir.join("shit");
    let model_path = dir.join("shit.gguf");
    let tokenizer_path = dir.join("tokenizer.json");
    let hash_path = dir.join(".model-hash");

    // Check if cached files match expected hashes (check both model + tokenizer)
    let expected_hash = format!("{} {}", MODEL_SHA256, TOKENIZER_SHA256);
    let cached_hash = std::fs::read_to_string(&hash_path).unwrap_or_default();
    if cached_hash.trim() == expected_hash
        && model_path.exists()
        && tokenizer_path.exists()
    {
        return Ok(ModelPaths { model_path, tokenizer_path });
    }

    // Download from GitHub Release assets
    std::fs::create_dir_all(&dir)?;
    let base = format!(
        "https://github.com/{}/releases/download/v{}",
        GITHUB_REPO, VERSION
    );

    download_file(
        &format!("{}/shit.gguf", base),
        &model_path,
        MODEL_SHA256,
    )?;
    download_file(
        &format!("{}/tokenizer.json", base),
        &tokenizer_path,
        TOKENIZER_SHA256,
    )?;

    // Write hash file LAST — acts as atomic "download complete" marker
    std::fs::write(&hash_path, format!("{} {}", MODEL_SHA256, TOKENIZER_SHA256))?;

    Ok(ModelPaths { model_path, tokenizer_path })
}
```

**download_file() — with progress and SHA256 verification:**
```rust
fn download_file(url: &str, dest: &PathBuf, expected_sha256: &str) -> Result<()> {
    use sha2::{Sha256, Digest};
    use std::time::Duration;

    let filename = dest.file_name().unwrap().to_string_lossy();
    eprint!("shit: downloading {}...", filename);

    let agent = ureq::Agent::config_builder()
        .timeout_connect(Some(Duration::from_secs(10)))
        .timeout_global(Some(Duration::from_secs(600)))
        .build()
        .new_agent();

    let response = agent.get(url).call()?;
    let total: Option<u64> = response
        .headers()
        .get("content-length")
        .and_then(|v| v.to_str().ok())
        .and_then(|v| v.parse().ok());

    let mut reader = response.into_body().into_reader();
    let tmp = dest.with_extension("part");
    let mut file = std::fs::File::create(&tmp)?;
    let mut hasher = Sha256::new();
    let mut downloaded: u64 = 0;
    let mut buf = [0u8; 64 * 1024];
    let mut last_report = 0u64;

    loop {
        let n = reader.read(&mut buf)?;
        if n == 0 { break; }
        file.write_all(&buf[..n])?;
        hasher.update(&buf[..n]);
        downloaded += n as u64;

        if downloaded - last_report > 5_000_000 {
            if let Some(total) = total {
                eprint!("\rshit: downloading {}... {}/{}MB",
                    filename, downloaded / 1_000_000, total / 1_000_000);
            }
            last_report = downloaded;
        }
    }
    drop(file);

    // Verify integrity before accepting
    let actual_hash = format!("{:x}", hasher.finalize());
    if actual_hash != expected_sha256 {
        let _ = std::fs::remove_file(&tmp);
        bail!("SHA256 mismatch for {}: expected {}, got {}",
            filename, expected_sha256, actual_hash);
    }

    std::fs::rename(&tmp, dest)?;
    eprintln!("\rshit: downloaded {}              ", filename);
    Ok(())
}
```

**infer_model() — simplified:**
```rust
fn infer_model(prompt: &str) -> Result<String> {
    let paths = find_model()?;
    infer_gguf(prompt, &paths.model_path, &paths.tokenizer_path)
}
```

**Remove entirely:** `infer_safetensors()`, `ModelSource` enum, all `candle_nn` imports.

**Keep unchanged:** `apply_op()`, `generate_tokens()`, `infer_gguf()`, `infer_rules()`, `extract_single_quoted_after()`, `infer()`.

**Step 2: Also check if serde_json is still needed**

`serde_json` was used in `infer_safetensors()` to parse `config.json`. Check if anything else uses it — if not, remove from `Cargo.toml`.

**Step 3: Verify it compiles**

```bash
cd cli && cargo build 2>&1 | tail -10
```

Expected: successful build

**Step 4: Commit**

```bash
git add cli/src/model/inference.rs cli/Cargo.toml cli/Cargo.lock
git commit -m "feat: auto-download model from GitHub releases with SHA256 verification"
```

---

### Task 5: Smoke test

Note: Full download testing requires a GitHub Release to exist with model assets. For local testing, place model files next to the binary (existing dev workflow). The download path can be tested once the first release is created.

**Step 1: Verify local dev path still works**

```bash
cp model/shit.gguf cli/target/debug/
cp model/tokenizer.json cli/target/debug/
cd cli && cargo build && printf 'git psuh origin main\n128\ngit: ...' > /tmp/shit-$(whoami)-last && ./target/debug/shit --yes
```

Expected: uses local model files, suggests `git push origin main`.

**Step 2: Verify rule-based fallback works without model**

```bash
rm -f cli/target/debug/shit.gguf cli/target/debug/tokenizer.json
rm -rf ~/.local/share/shit/
printf 'git psuh origin main\n128\ngit: '\''psuh'\'' is not a git command. Did you mean '\''push'\''?' > /tmp/shit-$(whoami)-last
cd cli && ./target/debug/shit --yes
```

Expected: download fails (no release yet), falls back to rule-based, suggests `git push origin main` from the "Did you mean" pattern.

**Step 3: Commit any fixups**

---

### Task 6: Update CLAUDE.md and README

**Files:**
- Modify: `CLAUDE.md` — update "Build & Run" section
- Modify: `README.md` — update installation/usage

**Step 1: Update CLAUDE.md**

In the "Build & Run" section:
- Note model auto-downloads from GitHub Releases on first run (~253MB)
- Cached in `~/.local/share/shit/` (Linux), `~/Library/Application Support/shit/` (macOS), `AppData\Local\shit\` (Windows)
- Falls back to rule-based inference if offline or release not found
- `SHIT_GITHUB_REPO` env var overrides repo at build time

**Step 2: Update README.md**

Add section about:
- First-run download behavior and cache location
- Release process: `gh release create v{version} model/shit.gguf model/tokenizer.json`
- `SHIT_GITHUB_REPO` build-time override for forks

**Step 3: Commit**

```bash
git add CLAUDE.md README.md
git commit -m "docs: update for auto-download model behavior"
```
