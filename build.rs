use std::process::Command;

fn main() {
    // Parse GitHub org/repo from git remote, overridable via env var
    let repo = std::env::var("SHIT_GITHUB_REPO").unwrap_or_else(|_| {
        parse_github_repo().unwrap_or_else(|| "avafloww/shit".to_string())
    });
    println!("cargo:rustc-env=GITHUB_REPO={}", repo);

    // Read content hashes from checksum files
    let model_hash = read_checksum("model/shit.gguf.sha256")
        .unwrap_or_else(|| "unknown".to_string());
    println!("cargo:rustc-env=MODEL_SHA256={}", model_hash);

    let tok_hash = read_checksum("model/tokenizer.json.sha256")
        .unwrap_or_else(|| "unknown".to_string());
    println!("cargo:rustc-env=TOKENIZER_SHA256={}", tok_hash);

    // Rerun if these change
    println!("cargo:rerun-if-changed=../model/shit.gguf.sha256");
    println!("cargo:rerun-if-changed=../model/tokenizer.json.sha256");
    println!("cargo:rerun-if-env-changed=SHIT_GITHUB_REPO");
}

fn read_checksum(path: &str) -> Option<String> {
    let content = std::fs::read_to_string(path).ok()?;
    Some(content.trim().to_string())
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
