# shit — Development Guide

## Project Overview

LLM-powered command correction CLI. Fine-tuned Gemma 3 270M outputs edit operations (REPLACE/FLAG/PREPEND/NONE/FULL) applied to failed commands. Rust CLI with candle inference, Python training pipeline.

## Build & Run

```bash
# Stable release
cargo install shit

# Development (latest main)
cargo install --git https://github.com/avafloww/shit

# Or build from source
cargo build --release

# Run — model auto-downloads from GitHub Releases on first run (~253MB)
./target/release/shit --yes

# Model cached in ~/.local/share/shit/ (Linux), ~/Library/Application Support/shit/ (macOS)
# For local dev: place shit.gguf + tokenizer.json next to binary to skip download

# IMPORTANT: If the daemon is running, it caches the model in memory.
# After model updates or code changes, restart it:
shit daemon restart  # or: systemctl --user restart shitd
```

## Architecture

### Rust CLI (`src/`)
- `build.rs` — embeds `GITHUB_REPO`, `MODEL_SHA256`, `TOKENIZER_SHA256` at compile time
- `src/main.rs` — clap arg parsing, interactive UX (crossterm)
- `src/model/inference.rs` — GGUF inference via candle + auto-download from GitHub Releases + operation parser (`apply_op`)
- `src/shell/` — per-shell init scripts (fish, bash, zsh, powershell, tcsh)
- `src/prompt.rs` — formats `CommandContext` into `$ cmd\n> stderr\nOP:` prompt
- `src/config.rs` — `~/.config/shit/config.toml` handling
- `shells/` — shell init script templates (included via `include_str!`)
- `model/` — SHA256 checksum files for model assets (actual files distributed via GitHub Releases)

### Training pipeline (`training/`)
- `training/generate_data.py` — curated scenarios (Scenario dataclass) → `data/base_examples.jsonl`
- `training/augment.py` — template-based augmentation (swap branches, packages, paths, etc.) → `data/augmented.jsonl`
- `docs/training.md` step 3 — inline shuffle + train/test split → `data/{train,test}.jsonl`
- `docs/training.md` step 4 — inline `command_to_op()` converts full corrections to edit ops → `data/{train,test}_ops.jsonl`
- `training/train.py` — fine-tunes Gemma 3 270M on `_ops.jsonl` data (uses `OP:` format)
- `training/export.py` — converts HF checkpoint → GGUF bf16 → Q4_K_M via llama.cpp

## Model Format

The model outputs structured edit operations, NOT full corrected commands:
- `REPLACE old new` — swap one word
- `FLAG -x` — insert a flag after the command name
- `PREPEND sudo` — add prefix
- `FULL cmd args...` — completely different command
- `NONE` — can't fix

This is critical — the 270M model can't reliably generate arbitrary shell commands, but it handles small structured operations perfectly.

## Training Pipeline

See [docs/training.md](docs/training.md) for full instructions. Key points:
- 259 base scenarios in generate_data.py, augmented to 60K
- **Must tokenize prompt and completion separately** (tokenizer merges across boundaries)
- **Must save tokenizer manually** to checkpoints (HF Trainer doesn't)
- **Must use bf16, NOT f16** for GGUF export (Gemma weights overflow in IEEE float16)
- Q4_K_M gives identical accuracy to F32 for this model

## Testing

```bash
# Write a test context file
printf 'git psuh origin main\n128\ngit: ...' > /tmp/shit-$(whoami)-last

# Run
./target/release/shit --yes
```

## Releasing

See [docs/releasing.md](docs/releasing.md) for the full release workflow, model distribution details, and build-time env vars.

## Key Decisions

- **Edit operations over full generation** — 270M model has 256K vocab eating 170M params, only ~100M for transformer. Can't generate full commands reliably but handles REPLACE/FLAG/PREPEND perfectly.
- **candle over llama.cpp** — pure Rust, no C++ dependency. Uses quantized_gemma3 GGUF loader.
- **Stderr captured on demand** — shell hooks only record command + exit code. Stderr is re-captured when `shit` is invoked, avoiding complex shell redirection.

## Dependencies

### Rust
- candle-core, candle-transformers — GGUF model inference
- clap — arg parsing
- crossterm — terminal raw mode for Enter/^C
- tokenizers — Gemma tokenizer
- dirs — XDG directory lookup
- ureq — HTTP client for model download
- sha2 — SHA256 integrity verification
- serde, toml — config parsing

### Python (training/)
- transformers, datasets, torch — training
- sentencepiece, accelerate — tokenizer + training speed
- huggingface-hub — model download
- gguf — GGUF export (via llama.cpp convert script)
