mod bash;
mod fish;
mod powershell;
mod tcsh;
mod zsh;

use anyhow::{bail, Result};

pub struct CommandContext {
    pub command: String,
    pub exit_code: i32,
    pub stderr: String,
}

pub fn get_init_script(shell: &str) -> Result<&'static str> {
    match shell {
        "fish" => Ok(fish::init_script()),
        "bash" => Ok(bash::init_script()),
        "zsh" => Ok(zsh::init_script()),
        "powershell" | "pwsh" => Ok(powershell::init_script()),
        "tcsh" => Ok(tcsh::init_script()),
        _ => bail!("unsupported shell: {shell}"),
    }
}

pub fn read_command_context() -> Result<CommandContext> {
    let username = std::env::var("USER").or_else(|_| std::env::var("USERNAME"))?;
    let path = format!("/tmp/shit-{username}-last");
    let contents = std::fs::read_to_string(&path)
        .map_err(|_| anyhow::anyhow!("no recent failed command found (is shell integration set up?)"))?;

    let mut lines = contents.lines();
    let command = lines.next().unwrap_or("").to_string();
    let exit_code: i32 = lines.next().unwrap_or("1").parse().unwrap_or(1);
    let stderr: String = lines.collect::<Vec<_>>().join("\n");

    Ok(CommandContext {
        command,
        exit_code,
        stderr,
    })
}
