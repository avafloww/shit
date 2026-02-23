# Auto-Download Model from GitHub Releases

## Problem

The CLI currently requires model files (`shit.gguf` + `tokenizer.json`) to be manually placed next to the binary or in `~/.local/share/shit/`. We want the model to be automatically downloaded on first run.

## Design

### Distribution: GitHub Release Assets (not LFS raw URLs)

Model files are stored in the repo via Git LFS for development, but distributed via **GitHub Release assets** to avoid LFS bandwidth limits (1GB/month free — would be exhausted after ~4 downloads of the 253MB model).

Download URL: `https://github.com/{repo}/releases/download/v{version}/shit.gguf`

Release process: `gh release create v{version} model/shit.gguf model/tokenizer.json`

### Build Time

`build.rs` embeds:

- **`GITHUB_REPO`** — org/repo parsed from git remote origin (e.g. `avafloww/shit`). Overridable via `SHIT_GITHUB_REPO` env var. Hardcoded fallback: `avafloww/shit`.
- **`MODEL_SHA256`** — from LFS pointer file or computed from blob. Cache key to avoid redundant downloads.
- **`TOKENIZER_SHA256`** — same for tokenizer.json.

Version comes for free via `env!("CARGO_PKG_VERSION")` — no build.rs work needed.

### Runtime Flow

1. Check for model next to binary (local dev override)
2. Check cache dir (`dirs::data_dir()/shit/`)
3. If cached: read `.model-hash` file, compare to embedded `MODEL_SHA256`
   - Match → use cached model
   - Mismatch → redownload
4. If not cached or hash mismatch: download from GitHub Release, SHA256-verify, write files + `.model-hash` (hash written last as atomic completion marker)
5. On download failure: fall back to rule-based inference (existing behavior)

### Integrity Verification

Downloaded files are SHA256-verified during streaming (hash computed incrementally, verified before renaming `.part` → final file). Corrupted or interrupted downloads are rejected.

### Cache Layout

```
~/.local/share/shit/                 # Linux (dirs::data_dir)
~/Library/Application Support/shit/  # macOS
C:\Users\X\AppData\Local\shit\      # Windows

  shit.gguf                          # 253MB Q4_K_M model
  tokenizer.json                     # tokenizer
  .model-hash                        # contains MODEL_SHA256 value
```

Flat layout — one version cached at a time, overwritten on update.

### Download UX

- `shit: downloading {filename}... {downloaded}/{total}MB` to stderr with `\r` progress
- Connection timeout: 10s. Global timeout: 600s.
- On failure: print error, fall back to rule-based inference

### Simplifications

- **Remove safetensors inference path** — GGUF-only. Drops `candle-nn`, `serde_json` deps.
- **Remove `ModelSource` enum** — just a `ModelPaths` struct with two `PathBuf`s.

### Dependencies

- **Add `ureq` 3.x** — lightweight blocking HTTP client (rustls TLS by default). No async runtime needed.
- **Add `sha2`** — SHA256 for download verification (also build-dep for LFS pointer/blob hashing).
- **Remove `candle-nn`** — no longer needed without safetensors inference.

### File Changes

| File | Change |
|------|--------|
| `cli/build.rs` | **New.** Embed `GITHUB_REPO`, `MODEL_SHA256`, `TOKENIZER_SHA256` |
| `cli/Cargo.toml` | Add `ureq`, `sha2`; remove `candle-nn`; add `sha2` build-dep |
| `cli/src/model/inference.rs` | Add download logic, remove safetensors code |
| `model/shit.gguf` | **New.** Copy Q4 GGUF into LFS-tracked dir |

### Trade-offs

- **253MB download on first run** — unavoidable, happens once per model version
- **Requires internet on first run** — falls back to rules if offline
- **Requires GitHub Release to exist** — model won't auto-download until release is created
- **`ureq` over `reqwest`** — no tokio dep, much smaller compile footprint
- **LFS pointer parsing in build.rs** — slightly unusual but avoids needing LFS pulled at build time
