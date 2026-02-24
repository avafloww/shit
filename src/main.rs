mod config;
#[cfg(feature = "daemon")]
mod daemon;
mod model;
mod prompt;
mod shell;

use anyhow::Result;
use clap::{Parser, Subcommand};

#[derive(Parser)]
#[command(name = "shit", version, about = "LLM-powered command correction")]
struct Cli {
    #[command(subcommand)]
    command: Option<Command>,

    /// Auto-execute the suggested fix without confirmation
    #[arg(short = 'y', long = "yes", visible_alias = "hard")]
    yes: bool,

    /// Show the suggested fix without executing
    #[arg(long = "dry-run")]
    dry_run: bool,
}

#[derive(Subcommand)]
enum Command {
    /// Output shell init script
    Init {
        /// Shell to generate init script for (fish, bash, zsh, powershell, tcsh)
        shell: String,
    },
    #[cfg(feature = "daemon")]
    /// Manage the shit daemon (shitd)
    Daemon {
        #[command(subcommand)]
        action: DaemonCommand,
    },
}

#[cfg(feature = "daemon")]
#[derive(Subcommand)]
pub enum DaemonCommand {
    /// Start the daemon server (foreground)
    Start,
    /// Install as a system service (systemd/launchd)
    Install,
    /// Uninstall the system service
    Uninstall,
    /// Check if the daemon is running
    Status,
}

fn main() -> Result<()> {
    let cli = Cli::parse();

    match cli.command {
        Some(Command::Init { shell }) => {
            let script = shell::get_init_script(&shell)?;
            print!("{script}");
        }
        #[cfg(feature = "daemon")]
        Some(Command::Daemon { action }) => {
            daemon::handle(action)?;
        }
        None => {
            let auto_execute = cli.yes;
            run_correction(auto_execute, cli.dry_run)?;
        }
    }

    Ok(())
}

fn run_correction(auto_execute: bool, dry_run: bool) -> Result<()> {
    let config = config::load_config()?;
    let auto_execute = auto_execute || config.auto_execute.unwrap_or(false);

    let context = shell::read_command_context()?;
    let formatted = prompt::format_prompt(&context);
    let fixes = model::infer(&formatted)?;

    if fixes.is_empty() {
        eprintln!("shit: can't figure this one out");
        return Ok(());
    }

    let chosen = if fixes.len() == 1 {
        eprintln!("  {}", fixes[0]);
        if dry_run {
            return Ok(());
        }
        if !auto_execute {
            eprintln!("  [Enter to execute / ^C to cancel]");
            wait_for_enter()?;
        }
        fixes[0].clone()
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

    execute_command(&chosen)
}

fn wait_for_enter() -> Result<()> {
    use crossterm::event::{self, Event, KeyCode, KeyModifiers};
    use crossterm::terminal;

    terminal::enable_raw_mode()?;
    let result = loop {
        if let Event::Key(key) = event::read()? {
            if key.code == KeyCode::Enter {
                break Ok(());
            }
            if key.code == KeyCode::Char('c') && key.modifiers.contains(KeyModifiers::CONTROL) {
                break Err(anyhow::anyhow!("cancelled"));
            }
        }
    };
    terminal::disable_raw_mode()?;
    eprintln!();
    result
}

fn execute_command(cmd: &str) -> Result<()> {
    let shell = std::env::var("SHELL").unwrap_or_else(|_| "sh".to_string());
    let status = std::process::Command::new(&shell)
        .arg("-c")
        .arg(cmd)
        .status()?;
    std::process::exit(status.code().unwrap_or(1));
}
