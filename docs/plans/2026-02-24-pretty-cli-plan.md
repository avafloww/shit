# Pretty CLI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the `shit` CLI visually appealing with colors, spinners, arrow-key selection, and playful branding.

**Architecture:** Add `indicatif` for spinners/progress bars, `dialoguer` for interactive selection, and `console` for colors. All changes are in `main.rs` (UX flow) and `model/inference.rs` (download progress). The model inference API boundary stays the same but gains a callback for spinner coordination.

**Tech Stack:** indicatif 0.18, dialoguer 0.12, console 0.16

---

### Task 1: Add dependencies

**Files:**
- Modify: `Cargo.toml`

**Step 1: Add the three new crates to Cargo.toml**

Add to `[dependencies]`:
```toml
console = "0.16.2"
dialoguer = { version = "0.12.0", features = ["fuzzy-select"] }
indicatif = "0.18.4"
```

**Step 2: Verify it compiles**

Run: `cargo check`
Expected: compiles with no errors (just downloads new deps)

**Step 3: Commit**

```bash
git add Cargo.toml Cargo.lock
git commit -m "add indicatif, dialoguer, console deps for pretty CLI"
```

---

### Task 2: Add 💩 to --help and error messages

**Files:**
- Modify: `src/main.rs:10` (clap about string)
- Modify: `src/main.rs:59` (no-fix error message)

**Step 1: Update clap about string**

Change line 10:
```rust
#[command(name = "shit", version, about = "💩 LLM-powered command correction")]
```

**Step 2: Update the "can't fix" message**

Change line 59:
```rust
eprintln!("💩 can't figure this one out");
```

**Step 3: Verify**

Run: `cargo run -- --help`
Expected: shows `💩 LLM-powered command correction`

**Step 4: Commit**

```bash
git add src/main.rs
git commit -m "add 💩 emoji to --help and error messages"
```

---

### Task 3: Add colored fix display

**Files:**
- Modify: `src/main.rs` (fix display in `run_correction`)

**Step 1: Add console import and color the fix output**

At top of main.rs, add:
```rust
use console::Style;
```

For the single-fix display (currently line 64), replace:
```rust
eprintln!("  {}", fixes[0]);
```
with:
```rust
let green_bold = Style::new().green().bold();
eprintln!("  ✓ {}", green_bold.apply_to(&fixes[0]));
```

For the multi-fix display (currently lines 74-76), replace:
```rust
for (i, fix) in fixes.iter().enumerate() {
    eprintln!("  {} {}", i + 1, fix);
}
```
This will be replaced entirely in Task 5 (dialoguer Select), so skip styling it now — just leave it as-is for the moment.

**Step 2: Color the confirmation hint**

Replace line 69:
```rust
eprintln!("  [Enter to execute / ^C to cancel]");
```
with:
```rust
let dim = Style::new().dim();
eprintln!("  {}", dim.apply_to("[Enter ↵ execute / ^C cancel]"));
```

**Step 3: Verify**

Run: `printf 'git psuh origin main\n128\ngit: '"'"'psuh'"'"' is not a git command.\n' > /tmp/shit-$(whoami)-last && cargo run`
Expected: fix shows in green bold with ✓ prefix, hint in dim gray

**Step 4: Commit**

```bash
git add src/main.rs
git commit -m "add colored fix display with green bold and dim hints"
```

---

### Task 4: Add inference spinner

**Files:**
- Modify: `src/main.rs` (wrap `model::infer` call)
- Modify: `src/model/inference.rs` (no API changes needed — spinner wraps the call in main.rs)

**Step 1: Add spinner around inference call**

Replace line 56 in main.rs:
```rust
let fixes = model::infer(&formatted)?;
```
with:
```rust
let spinner = indicatif::ProgressBar::new_spinner();
spinner.set_style(
    indicatif::ProgressStyle::default_spinner()
        .tick_strings(&["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"])
        .template("{spinner:.cyan} {msg}")
        .unwrap(),
);
spinner.set_message("thinking...");
spinner.enable_steady_tick(std::time::Duration::from_millis(80));
let fixes = model::infer(&formatted);
spinner.finish_and_clear();
let fixes = fixes?;
```

Add `use indicatif` at top if not already imported (or use full paths as above).

**Step 2: Verify**

Run: `printf 'git psuh origin main\n128\ngit: '"'"'psuh'"'"' is not a git command.\n' > /tmp/shit-$(whoami)-last && cargo run`
Expected: braille spinner shows "thinking..." during inference, clears when done, then shows fix

**Step 3: Commit**

```bash
git add src/main.rs
git commit -m "add braille spinner during model inference"
```

---

### Task 5: Replace multi-fix selection with dialoguer Select

**Files:**
- Modify: `src/main.rs` (multi-fix branch in `run_correction`)

**Step 1: Replace the multi-fix else branch**

Replace the entire multi-fix block (lines 73-89):
```rust
} else {
    for (i, fix) in fixes.iter().enumerate() {
        eprintln!("  {} {}", i + 1, fix);
    }
    if dry_run {
        return Ok(());
    }
    if auto_execute {
        fixes[0].clone()
    } else {
        eprint!("  [1-{}]: ", fixes.len());
        let mut input = String::new();
        std::io::stdin().read_line(&mut input)?;
        let idx: usize = input.trim().parse().unwrap_or(1);
        let idx = idx.saturating_sub(1).min(fixes.len() - 1);
        fixes[idx].clone()
    }
};
```

with:
```rust
} else {
    if dry_run {
        let green_bold = Style::new().green().bold();
        for fix in &fixes {
            eprintln!("  ✓ {}", green_bold.apply_to(fix));
        }
        return Ok(());
    }
    if auto_execute {
        let green_bold = Style::new().green().bold();
        eprintln!("  ✓ {}", green_bold.apply_to(&fixes[0]));
        fixes[0].clone()
    } else {
        let selection = dialoguer::Select::with_theme(&dialoguer::theme::ColorfulTheme::default())
            .items(&fixes)
            .default(0)
            .interact()?;
        fixes[selection].clone()
    }
};
```

**Step 2: Add dialoguer import**

At top of main.rs (or use full path as above — full path is fine to avoid cluttering imports).

**Step 3: Verify**

Test multi-fix scenario — this requires the model to output multiple fixes. If that's hard to trigger, verify at minimum that single-fix still works. The dialoguer Select can also be verified by temporarily duplicating fixes:
```rust
let mut fixes = fixes; fixes.push(fixes[0].clone()); // TEMP for testing
```

**Step 4: Commit**

```bash
git add src/main.rs
git commit -m "replace number input with dialoguer arrow-key selection"
```

---

### Task 6: Pretty download progress bar

**Files:**
- Modify: `src/model/inference.rs` (replace manual eprint progress with indicatif)

**Step 1: Replace download_file progress reporting**

In `download_file`, replace the manual progress tracking with indicatif. The key changes:

Replace the setup (around lines 107-108):
```rust
let filename = dest.file_name().unwrap().to_string_lossy();
eprint!("shit: downloading {}...", filename);
```

And the progress loop body (lines 139-149) and completion message (line 166).

New implementation of `download_file`:
```rust
fn download_file(url: &str, dest: &PathBuf, expected_sha256: &str) -> Result<()> {
    use sha2::{Digest, Sha256};
    use std::io::{Read, Write};
    use std::time::Duration;

    let filename = dest.file_name().unwrap().to_string_lossy();

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

    let pb = if let Some(total) = total {
        indicatif::ProgressBar::new(total)
    } else {
        indicatif::ProgressBar::new_spinner()
    };
    pb.set_style(
        indicatif::ProgressStyle::default_bar()
            .template("  {spinner:.cyan} {msg} [{bar:30.cyan/dim}] {bytes}/{total_bytes} ({eta})")
            .unwrap()
            .progress_chars("━╸─"),
    );
    pb.set_message(format!("downloading {filename}"));
    pb.enable_steady_tick(Duration::from_millis(100));

    let mut reader = response.into_body().into_reader();
    let tmp = dest.with_extension("part");
    let mut file = std::fs::File::create(&tmp)?;
    let mut hasher = Sha256::new();
    let mut buf = [0u8; 64 * 1024];

    loop {
        let n = reader.read(&mut buf)?;
        if n == 0 {
            break;
        }
        file.write_all(&buf[..n])?;
        hasher.update(&buf[..n]);
        pb.inc(n as u64);
    }
    drop(file);
    pb.finish_and_clear();

    let green = console::Style::new().green();
    eprintln!("  ✓ {}", green.apply_to(format!("downloaded {filename}")));

    // Verify integrity before accepting
    let actual_hash = format!("{:x}", hasher.finalize());
    if actual_hash != expected_sha256 {
        let _ = std::fs::remove_file(&tmp);
        bail!(
            "SHA256 mismatch for {}: expected {}, got {}",
            filename,
            expected_sha256,
            actual_hash
        );
    }

    std::fs::rename(&tmp, dest)?;
    Ok(())
}
```

**Step 2: Update download_file_with_fallback**

Replace the `eprint!("\r");` on line 91 — the progress bar handles its own cleanup now, so just remove that line.

```rust
fn download_file_with_fallback(
    url: &str,
    fallback_url: &str,
    dest: &PathBuf,
    expected_sha256: &str,
) -> Result<()> {
    match download_file(url, dest, expected_sha256) {
        Ok(()) => Ok(()),
        Err(e) => {
            if e.to_string().contains("404") || e.to_string().contains("http status") {
                download_file(fallback_url, dest, expected_sha256)
            } else {
                Err(e)
            }
        }
    }
}
```

**Step 3: Verify**

Delete cached model to trigger re-download:
```bash
rm -rf ~/.local/share/shit/
printf 'git psuh origin main\n128\ngit: ...' > /tmp/shit-$(whoami)-last
cargo run
```
Expected: shows progress bar during download with bytes/total/ETA

**Step 4: Commit**

```bash
git add src/model/inference.rs
git commit -m "replace manual download progress with indicatif progress bar"
```

---

### Task 7: Final polish and cleanup

**Files:**
- Modify: `src/main.rs` (remove unused crossterm import if no longer needed)

**Step 1: Check if crossterm is still needed**

crossterm is used in `wait_for_enter()` for the single-fix Enter/^C handling. This function is still used, so crossterm stays. No cleanup needed unless we replace `wait_for_enter` with dialoguer — but the current behavior (raw Enter/^C) is nicer for the single-fix case.

**Step 2: Full flow verification**

Test the complete flow:
```bash
# Single fix
printf 'git psuh origin main\n128\ngit: '"'"'psuh'"'"' is not a git command.\n' > /tmp/shit-$(whoami)-last
cargo run

# --help
cargo run -- --help

# --dry-run
cargo run -- --dry-run

# --yes
cargo run -- --yes
```

**Step 3: Final commit if any tweaks needed**

```bash
git add -A
git commit -m "final polish for pretty CLI"
```
