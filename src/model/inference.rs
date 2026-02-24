use anyhow::{bail, Result};
use candle_core::{DType, Device, Tensor};
use candle_transformers::generation::LogitsProcessor;
use std::path::PathBuf;
use tokenizers::Tokenizer;

const MAX_GENERATED_TOKENS: usize = 30;
const GITHUB_REPO: &str = env!("GITHUB_REPO");
const VERSION: &str = env!("CARGO_PKG_VERSION");
const MODEL_SHA256: &str = env!("MODEL_SHA256");
const TOKENIZER_SHA256: &str = env!("TOKENIZER_SHA256");

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

    // Download from GitHub Release assets
    std::fs::create_dir_all(&dir)?;
    let base = format!(
        "https://github.com/{}/releases/download/v{}",
        GITHUB_REPO, VERSION
    );

    download_file(&format!("{}/shit-ops.q4.gguf", base), &model_path, MODEL_SHA256)?;
    download_file(
        &format!("{}/tokenizer.json", base),
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

/// Run inference and return suggested fixes.
pub fn infer(prompt: &str) -> Result<Vec<String>> {
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

fn infer_model(prompt: &str) -> Result<String> {
    let paths = find_model()?;
    infer_gguf(prompt, &paths.model_path, &paths.tokenizer_path)
}

/// Generate tokens from a model with greedy decoding.
fn generate_tokens(
    prompt_tokens: &[u32],
    tokenizer: &Tokenizer,
    forward_fn: &mut dyn FnMut(&[u32], usize) -> Result<Tensor>,
) -> Result<String> {
    let mut logits_processor = LogitsProcessor::new(0, None, None);

    let logits = forward_fn(prompt_tokens, 0)?;
    let logits = logits.to_dtype(DType::F32)?;
    let mut next_logits = extract_last_logits(&logits)?;
    let mut next_token = logits_processor.sample(&next_logits)?;

    let mut generated_tokens = vec![next_token];
    let mut pos = prompt_tokens.len();

    for _ in 0..MAX_GENERATED_TOKENS {
        let logits = forward_fn(&[next_token], pos)?;
        let logits = logits.to_dtype(DType::F32)?;
        next_logits = extract_last_logits(&logits)?;
        next_token = logits_processor.sample(&next_logits)?;

        if next_token == 1 || next_token == 0 {
            break;
        }
        let decoded = tokenizer.decode(&[next_token], true).unwrap_or_default();
        if decoded.contains('\n') {
            break;
        }
        generated_tokens.push(next_token);
        pos += 1;
    }

    let output = tokenizer
        .decode(&generated_tokens, true)
        .map_err(anyhow::Error::msg)?
        .trim()
        .to_string();

    Ok(output)
}

/// Extract the last position's logits from a tensor of varying shape.
/// Handles [vocab], [seq_len, vocab], etc.
fn extract_last_logits(logits: &Tensor) -> Result<Tensor> {
    let dims = logits.dims();
    match dims.len() {
        1 => Ok(logits.clone()),                        // [vocab] — single position
        2 => Ok(logits.get(dims[0] - 1)?),              // [seq_len, vocab] — last position
        _ => bail!("unexpected logits shape: {:?}", dims),
    }
}

/// GGUF inference via candle quantized_gemma3.
fn infer_gguf(prompt: &str, model_path: &PathBuf, tokenizer_path: &PathBuf) -> Result<String> {
    use candle_transformers::models::quantized_gemma3::ModelWeights;

    let device = Device::Cpu;
    let mut file = std::fs::File::open(model_path)?;
    let content = candle_core::quantized::gguf_file::Content::read(&mut file)?;
    let mut model = ModelWeights::from_gguf(content, &mut file, &device)?;

    let tokenizer = Tokenizer::from_file(tokenizer_path).map_err(anyhow::Error::msg)?;
    let encoding = tokenizer.encode(prompt, true).map_err(anyhow::Error::msg)?;
    let prompt_tokens = encoding.get_ids().to_vec();

    generate_tokens(&prompt_tokens, &tokenizer, &mut |tokens, pos| {
        let input = Tensor::new(tokens, &device)?.unsqueeze(0)?;
        let logits = model.forward(&input, pos)?;
        Ok(logits.squeeze(0)?)
    })
}

