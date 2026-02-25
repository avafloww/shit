# Pretty CLI Design

## Goal

Make the `shit` CLI visually appealing — colors, loading spinners, arrow-key selection, and personality that matches the branding.

## Vibe

Playful & bold. Lean into the "shit" branding with emoji and personality.

## New Dependencies

- **`indicatif`** — spinner during inference, progress bar during download
- **`dialoguer`** — arrow-key selection menu for multi-fix
- **`console`** — colors and terminal styling (comes with dialoguer)

## Changes

### 1. `--help` branding

Add 💩 emoji to the clap `about` string so it shows in `--help` output.

### 2. Inference spinner (main.rs → run_correction)

- Braille-dot spinner while model loads + runs inference
- Message like `"thinking..."` in cyan/magenta
- Spinner clears when result is ready

### 3. Fix display (main.rs)

- Show the fix in **bold green** with a `✓` prefix
- "Can't fix" → `"💩 can't figure this one out"` in red
- All error messages use the 💩 prefix

### 4. Single fix confirmation (main.rs → wait_for_enter)

- Keep Enter/^C behavior but style the hint in dim gray
- Or use dialoguer Confirm — TBD based on feel

### 5. Multi-fix selection (main.rs)

- Replace manual `[1-N]:` with `dialoguer::Select`
- Arrow keys to navigate, Enter to confirm
- Each option shows the full corrected command

### 6. Download progress (inference.rs → download_file)

- Replace manual `eprint!` MB counter with `indicatif::ProgressBar`
- Progress bar with speed, ETA, percentage
- Styled to match theme

### 7. Color theme

| Color | Usage |
|-------|-------|
| Green/bold | Suggested fix, success |
| Red | Errors, "can't fix" (with 💩) |
| Yellow | Original failed command / changed parts |
| Dim/gray | Hints, secondary info |
| Cyan/magenta | Spinner text, branding accent |

## What stays the same

- `--yes` and `--dry-run` behavior
- Shell init scripts
- Model inference logic
- crossterm stays (dialoguer uses it internally)
