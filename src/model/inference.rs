use anyhow::{bail, Result};
use std::path::PathBuf;

use super::engine::Engine;

const GITHUB_REPO: &str = env!("GITHUB_REPO");
const VERSION: &str = env!("CARGO_PKG_VERSION");
const MODEL_SHA256: &str = env!("MODEL_SHA256");
const TOKENIZER_SHA256: &str = env!("TOKENIZER_SHA256");

pub struct ModelPaths {
    pub model_path: PathBuf,
    pub tokenizer_path: PathBuf,
}

pub fn find_model() -> Result<ModelPaths> {
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
    let data_dir =
        dirs::data_dir().ok_or_else(|| anyhow::anyhow!("Could not determine data directory"))?;
    let dir = data_dir.join("shit");
    let model_path = dir.join("shit.gguf");
    let tokenizer_path = dir.join("tokenizer.json");
    let hash_path = dir.join(".model-hash");

    // Check if cached files match expected hashes (both model + tokenizer)
    let expected_hash = format!("{} {}", MODEL_SHA256, TOKENIZER_SHA256);
    let cached_hash = std::fs::read_to_string(&hash_path).unwrap_or_default();
    if cached_hash.trim() == expected_hash && model_path.exists() && tokenizer_path.exists() {
        return Ok(ModelPaths {
            model_path,
            tokenizer_path,
        });
    }

    // Download from GitHub Release assets — try exact version, fall back to latest
    std::fs::create_dir_all(&dir)?;
    let versioned_base = format!(
        "https://github.com/{}/releases/download/v{}",
        GITHUB_REPO, VERSION
    );
    let latest_base = format!(
        "https://github.com/{}/releases/latest/download",
        GITHUB_REPO
    );

    download_file_with_fallback(
        &format!("{}/shit-ops.q4.gguf", versioned_base),
        &format!("{}/shit-ops.q4.gguf", latest_base),
        &model_path,
        MODEL_SHA256,
    )?;
    download_file_with_fallback(
        &format!("{}/tokenizer.json", versioned_base),
        &format!("{}/tokenizer.json", latest_base),
        &tokenizer_path,
        TOKENIZER_SHA256,
    )?;

    // Write hash file LAST — acts as atomic "download complete" marker
    std::fs::write(&hash_path, format!("{} {}", MODEL_SHA256, TOKENIZER_SHA256))?;

    Ok(ModelPaths {
        model_path,
        tokenizer_path,
    })
}

fn download_file_with_fallback(
    url: &str,
    fallback_url: &str,
    dest: &PathBuf,
    expected_sha256: &str,
) -> Result<()> {
    match download_file(url, dest, expected_sha256) {
        Ok(()) => Ok(()),
        Err(e) => {
            // Clear the progress line from the failed attempt
            eprint!("\r");
            if e.to_string().contains("404") || e.to_string().contains("http status") {
                download_file(fallback_url, dest, expected_sha256)
            } else {
                Err(e)
            }
        }
    }
}

fn download_file(url: &str, dest: &PathBuf, expected_sha256: &str) -> Result<()> {
    use sha2::{Digest, Sha256};
    use std::io::{Read, Write};
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
        if n == 0 {
            break;
        }
        file.write_all(&buf[..n])?;
        hasher.update(&buf[..n]);
        downloaded += n as u64;

        if downloaded - last_report > 5_000_000 {
            if let Some(total) = total {
                eprint!(
                    "\rshit: downloading {}... {}/{}MB",
                    filename,
                    downloaded / 1_000_000,
                    total / 1_000_000
                );
            }
            last_report = downloaded;
        }
    }
    drop(file);

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
    eprintln!("\rshit: downloaded {}              ", filename);
    Ok(())
}

/// Apply an edit operation to the original command.
fn apply_op(command: &str, op: &str) -> Option<String> {
    let parts: Vec<&str> = op.splitn(3, ' ').collect();
    match parts.first().copied() {
        Some("REPLACE") if parts.len() >= 3 => {
            let old = parts[1];
            let new = parts[2];
            if command.contains(old) {
                Some(command.replacen(old, new, 1))
            } else {
                None
            }
        }
        Some("FLAG") if parts.len() >= 2 => {
            let flag = parts[1];
            let cmd_parts: Vec<&str> = command.splitn(2, ' ').collect();
            if cmd_parts.len() == 2 {
                Some(format!("{} {} {}", cmd_parts[0], flag, cmd_parts[1]))
            } else {
                Some(format!("{} {}", command, flag))
            }
        }
        Some("PREPEND") if parts.len() >= 2 => Some(format!("{} {}", parts[1], command)),
        Some("FULL") => Some(parts[1..].join(" ")),
        Some("NONE") => None,
        _ => None,
    }
}

fn infer_from_op(prompt: &str, op: &str) -> Vec<String> {
    let command = prompt
        .lines()
        .find_map(|line| line.strip_prefix("$ "))
        .unwrap_or("");

    let op = op.trim();
    if op == "NONE" || op.is_empty() {
        return vec![];
    }
    if let Some(fix) = apply_op(command, op) {
        return vec![fix];
    }
    if op.starts_with("FULL ") {
        return vec![op[5..].to_string()];
    }
    vec![]
}

/// Try the daemon for inference. Returns Some(fixes) on success, None on failure.
#[cfg(feature = "daemon")]
fn try_daemon(prompt: &str) -> Option<Vec<String>> {
    use std::time::Duration;

    let port_file = crate::daemon::server::port_file_path();
    if !port_file.exists() {
        return None; // no daemon installed, silent fallback
    }

    let port_str = std::fs::read_to_string(&port_file).ok()?;
    let port: u16 = port_str.trim().parse().ok()?;

    let url = format!("http://127.0.0.1:{}/infer", port);
    let body = serde_json::json!({"prompt": prompt}).to_string();

    let agent = ureq::Agent::config_builder()
        .timeout_connect(Some(Duration::from_secs(2)))
        .timeout_global(Some(Duration::from_secs(30)))
        .build()
        .new_agent();
    match agent
        .post(&url)
        .header("Content-Type", "application/json")
        .send(body.as_str())
    {
        Ok(response) => {
            let text: String = response.into_body().read_to_string().ok()?;
            let v: serde_json::Value = serde_json::from_str(&text).ok()?;
            let fixes = v["fixes"]
                .as_array()?
                .iter()
                .filter_map(|f| f.as_str().map(|s| s.to_string()))
                .collect();
            Some(fixes)
        }
        Err(_) => {
            eprintln!("shit: daemon not responding, loading model locally...");
            None
        }
    }
}

/// Run inference and return suggested fixes.
pub fn infer(prompt: &str) -> Result<Vec<String>> {
    // Try daemon first if feature enabled
    #[cfg(feature = "daemon")]
    if let Some(fixes) = try_daemon(prompt) {
        return Ok(fixes);
    }

    // Fallback: load model locally
    let paths = find_model()?;
    let mut engine = Engine::new(&paths.model_path, &paths.tokenizer_path)?;
    let op = engine.infer(prompt)?;
    Ok(infer_from_op(prompt, &op))
}

/// Run inference using an existing engine and return suggested fixes.
pub fn infer_with_engine(engine: &mut Engine, prompt: &str) -> Result<Vec<String>> {
    let op = engine.infer(prompt)?;
    Ok(infer_from_op(prompt, &op))
}

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
        assert_eq!(apply_op("ls", "FLAG -la"), Some("ls -la".to_string()));
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
        assert_eq!(apply_op("sl", "FULL ls"), Some("ls".to_string()));
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
