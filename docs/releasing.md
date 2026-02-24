# Releasing

## CLI Distribution

No prebuilt binaries — users install via cargo:

```bash
cargo install shit                                          # stable release
cargo install --git https://github.com/avafloww/shit       # latest main
```

## Model Distribution

Model files (shit.gguf + tokenizer.json) are distributed via GitHub Release assets, NOT stored in the repo. The repo only contains SHA256 checksum files (`model/*.sha256`) used by `build.rs` at compile time.

GitHub Releases exist solely for hosting model assets. The CLI auto-downloads from the release matching its version tag.

## Release Workflow

### CLI-only release (no model changes)

```bash
# 1. Bump version in Cargo.toml, commit, tag
git add Cargo.toml && git commit -m "release: v0.X.0"
git tag v0.X.0
git push origin main v0.X.0
```

### Model release

Model releases are named incrementally: "Model v1", "Model v2", etc. Check the latest with `gh release list` and increment.

Each model release is attached to the latest CLI version tag at the time of release, so the CLI can find its model assets.

```bash
# 1. Update checksums
sha256sum training/model/shit-ops.q4.gguf | cut -d' ' -f1 > model/shit.gguf.sha256
sha256sum training/model/tokenizer.json | cut -d' ' -f1 > model/tokenizer.json.sha256

# 2. Bump version in Cargo.toml (if not already), commit, tag
git add model/*.sha256 Cargo.toml && git commit -m "release: v0.X.0"
git tag v0.X.0
git push origin main v0.X.0

# 3. Find the latest model release number and increment
gh release list  # look for "Model vN"

# 4. Create GitHub Release with model assets on the CLI version tag
gh release create v0.X.0 \
  --title "Model vN" \
  training/model/shit-ops.q4.gguf#shit.gguf \
  training/model/tokenizer.json
```

Forks can override the download source at build time: `SHIT_GITHUB_REPO=user/fork cargo build`

## Build-time Env Vars

- `GITHUB_REPO` — parsed from git remote, override with `SHIT_GITHUB_REPO` env var
- `MODEL_SHA256` / `TOKENIZER_SHA256` — read from `model/*.sha256` files
- `CARGO_PKG_VERSION` — used for release download URL (`v{version}`)
