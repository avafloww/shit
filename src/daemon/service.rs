use anyhow::{bail, Result};
use std::path::PathBuf;

enum ServiceManager {
    Systemd,
    Launchd,
}

fn detect_service_manager() -> Result<ServiceManager> {
    if cfg!(target_os = "macos") {
        return Ok(ServiceManager::Launchd);
    }
    if PathBuf::from("/run/systemd/system").exists() {
        return Ok(ServiceManager::Systemd);
    }
    bail!("unsupported platform: neither systemd nor launchd detected")
}

fn binary_path() -> Result<PathBuf> {
    Ok(std::env::current_exe()?)
}

// --- public API ---

pub fn is_installed() -> Result<bool> {
    match detect_service_manager()? {
        ServiceManager::Systemd => Ok(systemd_unit_path()?.exists()),
        ServiceManager::Launchd => Ok(launchd_plist_path()?.exists()),
    }
}

pub fn install() -> Result<()> {
    match detect_service_manager()? {
        ServiceManager::Systemd => install_systemd(),
        ServiceManager::Launchd => install_launchd(),
    }
}

pub fn uninstall() -> Result<()> {
    match detect_service_manager()? {
        ServiceManager::Systemd => uninstall_systemd(),
        ServiceManager::Launchd => uninstall_launchd(),
    }
}

pub fn start() -> Result<()> {
    match detect_service_manager()? {
        ServiceManager::Systemd => start_systemd(),
        ServiceManager::Launchd => start_launchd(),
    }
}

pub fn stop() -> Result<()> {
    match detect_service_manager()? {
        ServiceManager::Systemd => stop_systemd(),
        ServiceManager::Launchd => stop_launchd(),
    }
}

pub fn restart() -> Result<()> {
    match detect_service_manager()? {
        ServiceManager::Systemd => restart_systemd(),
        ServiceManager::Launchd => {
            let _ = stop_launchd();
            start_launchd()
        }
    }
}

pub fn logs(follow: bool) -> Result<()> {
    match detect_service_manager()? {
        ServiceManager::Systemd => logs_systemd(follow),
        ServiceManager::Launchd => logs_launchd(follow),
    }
}

// --- systemd ---

fn systemd_unit_path() -> Result<PathBuf> {
    let home = dirs::home_dir().ok_or_else(|| anyhow::anyhow!("cannot determine home directory"))?;
    let dir = home.join(".config/systemd/user");
    std::fs::create_dir_all(&dir)?;
    Ok(dir.join("shitd.service"))
}

fn install_systemd() -> Result<()> {
    let bin = binary_path()?;
    let unit_path = systemd_unit_path()?;

    let unit = format!(
        "[Unit]\n\
         Description=shit daemon — keeps model in memory for fast inference\n\
         \n\
         [Service]\n\
         ExecStart={} daemon run\n\
         Restart=on-failure\n\
         \n\
         [Install]\n\
         WantedBy=default.target\n",
        bin.display()
    );

    std::fs::write(&unit_path, unit)?;
    eprintln!("shitd: wrote {}", unit_path.display());

    let status = std::process::Command::new("systemctl")
        .args(["--user", "daemon-reload"])
        .status()?;
    if !status.success() {
        bail!("systemctl daemon-reload failed");
    }

    let status = std::process::Command::new("systemctl")
        .args(["--user", "enable", "shitd"])
        .status()?;
    if !status.success() {
        bail!("systemctl enable shitd failed");
    }

    eprintln!("shitd: service installed and enabled");
    Ok(())
}

fn uninstall_systemd() -> Result<()> {
    let unit_path = systemd_unit_path()?;

    let _ = std::process::Command::new("systemctl")
        .args(["--user", "disable", "shitd"])
        .status();

    if unit_path.exists() {
        std::fs::remove_file(&unit_path)?;
        eprintln!("shitd: removed {}", unit_path.display());
    }

    let _ = std::process::Command::new("systemctl")
        .args(["--user", "daemon-reload"])
        .status();

    eprintln!("shitd: service uninstalled");
    Ok(())
}

fn start_systemd() -> Result<()> {
    let status = std::process::Command::new("systemctl")
        .args(["--user", "start", "shitd"])
        .status()?;
    if !status.success() {
        bail!("systemctl start shitd failed");
    }
    eprintln!("shitd: started");
    Ok(())
}

fn stop_systemd() -> Result<()> {
    let status = std::process::Command::new("systemctl")
        .args(["--user", "stop", "shitd"])
        .status()?;
    if !status.success() {
        bail!("systemctl stop shitd failed");
    }
    eprintln!("shitd: stopped");
    Ok(())
}

fn restart_systemd() -> Result<()> {
    let status = std::process::Command::new("systemctl")
        .args(["--user", "restart", "shitd"])
        .status()?;
    if !status.success() {
        bail!("systemctl restart shitd failed");
    }
    eprintln!("shitd: restarted");
    Ok(())
}

fn logs_systemd(follow: bool) -> Result<()> {
    let mut args = vec!["--user", "-u", "shitd", "-n", "50", "--no-pager"];
    if follow {
        args.push("-f");
    }
    let status = std::process::Command::new("journalctl")
        .args(&args)
        .status()?;
    if !status.success() {
        bail!("journalctl failed");
    }
    Ok(())
}

// --- launchd ---

const LAUNCHD_LABEL: &str = "dev.ava.shitd";

fn launchd_plist_path() -> Result<PathBuf> {
    let home = dirs::home_dir().ok_or_else(|| anyhow::anyhow!("cannot determine home directory"))?;
    let dir = home.join("Library/LaunchAgents");
    std::fs::create_dir_all(&dir)?;
    Ok(dir.join("dev.ava.shitd.plist"))
}

fn install_launchd() -> Result<()> {
    let bin = binary_path()?;
    let plist_path = launchd_plist_path()?;

    let plist = format!(
        r#"<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{label}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{bin}</string>
        <string>daemon</string>
        <string>run</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
"#,
        label = LAUNCHD_LABEL,
        bin = bin.display()
    );

    std::fs::write(&plist_path, plist)?;
    eprintln!("shitd: wrote {}", plist_path.display());
    eprintln!("shitd: service installed");
    Ok(())
}

fn uninstall_launchd() -> Result<()> {
    let plist_path = launchd_plist_path()?;

    if plist_path.exists() {
        std::fs::remove_file(&plist_path)?;
        eprintln!("shitd: removed {}", plist_path.display());
    }

    eprintln!("shitd: service uninstalled");
    Ok(())
}

fn start_launchd() -> Result<()> {
    let plist_path = launchd_plist_path()?;
    let status = std::process::Command::new("launchctl")
        .args(["load", &plist_path.to_string_lossy()])
        .status()?;
    if !status.success() {
        bail!("launchctl load failed");
    }
    eprintln!("shitd: started");
    Ok(())
}

fn stop_launchd() -> Result<()> {
    let plist_path = launchd_plist_path()?;
    let status = std::process::Command::new("launchctl")
        .args(["unload", &plist_path.to_string_lossy()])
        .status()?;
    if !status.success() {
        bail!("launchctl unload failed");
    }
    eprintln!("shitd: stopped");
    Ok(())
}

fn logs_launchd(follow: bool) -> Result<()> {
    let predicate = format!("process == \"{}\"", "shit");
    let status = if follow {
        std::process::Command::new("log")
            .args(["stream", "--predicate", &predicate, "--style", "compact"])
            .status()?
    } else {
        std::process::Command::new("log")
            .args(["show", "--predicate", &predicate, "--style", "compact", "--last", "5m"])
            .status()?
    };
    if !status.success() {
        bail!("log {} failed", if follow { "stream" } else { "show" });
    }
    Ok(())
}
