# Releasing

## Model Distribution

Model files (shit.gguf + tokenizer.json) are distributed via GitHub Release assets, NOT stored in the repo. The repo only contains SHA256 checksum files (`model/*.sha256`) used by `build.rs` at compile time.

## Release Workflow

```bash
# 1. Update checksums if model changed
sha256sum training/model/shit-ops.q4.gguf | cut -d' ' -f1 > model/shit.gguf.sha256
sha256sum training/model/tokenizer.json | cut -d' ' -f1 > model/tokenizer.json.sha256

# 2. Bump version in Cargo.toml, commit, tag
git add model/*.sha256 Cargo.toml && git commit -m "release: v0.X.0"
git tag v0.X.0

# 3. Create GitHub Release with model assets
gh release create v0.X.0 \
  training/model/shit-ops.q4.gguf#shit.gguf \
  training/model/tokenizer.json

# 4. Binary built from this tag will auto-download from v0.X.0 release
```

Forks can override the download source at build time: `SHIT_GITHUB_REPO=user/fork cargo build`

## Build-time Env Vars

- `GITHUB_REPO` — parsed from git remote, override with `SHIT_GITHUB_REPO` env var
- `MODEL_SHA256` / `TOKENIZER_SHA256` — read from `model/*.sha256` files
- `CARGO_PKG_VERSION` — used for release download URL (`v{version}`)
