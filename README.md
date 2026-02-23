# shit — LLM-powered command correction

A CLI tool that corrects failed commands using a fine-tuned Gemma 3 270M model. Type a wrong command, then type `shit` to fix it.

```
$ git psuh origin main
git: 'psuh' is not a git command. Did you mean 'push'?

$ shit
  git push origin main [Enter/^C]
```

## How it works

1. Shell hooks record the last failed command and its exit code
2. When you run `shit`, it re-runs the command to capture stderr
3. A small local model suggests a fix as a structured edit operation
4. You confirm and execute, or cancel

Falls back to built-in rule-based correction if the model isn't available.

## Install

### From source

```bash
cargo build --release
cp target/release/shit ~/.local/bin/
```

The model (~253MB) is automatically downloaded from GitHub Releases on first run and cached in:
- **Linux:** `~/.local/share/shit/`
- **macOS:** `~/Library/Application Support/shit/`
- **Windows:** `%LOCALAPPDATA%\shit\`

### Shell integration

Add to your shell config:

```bash
# Fish (~/.config/fish/config.fish)
eval "$(shit init fish)"

# Bash (~/.bashrc)
eval "$(shit init bash)"

# Zsh (~/.zshrc)
eval "$(shit init zsh)"
```

## Usage

```bash
# Show suggested fix, Enter to execute, Ctrl+C to cancel
shit

# Auto-execute without confirmation
shit --yes
shit -y
shit --hard
```

## License

MIT — see [LICENSE](LICENSE) for details.
