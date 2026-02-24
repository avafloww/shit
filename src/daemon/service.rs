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
         ExecStart={} daemon start\n\
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
        .args(["--user", "enable", "--now", "shitd"])
        .status()?;
    if !status.success() {
        bail!("systemctl enable --now shitd failed");
    }

    eprintln!("shitd: service installed and started");
    Ok(())
}

fn uninstall_systemd() -> Result<()> {
    let unit_path = systemd_unit_path()?;

    let _ = std::process::Command::new("systemctl")
        .args(["--user", "stop", "shitd"])
        .status();

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

// --- launchd ---

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
    <string>dev.ava.shitd</string>
    <key>ProgramArguments</key>
    <array>
        <string>{}</string>
        <string>daemon</string>
        <string>start</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
"#,
        bin.display()
    );

    std::fs::write(&plist_path, plist)?;
    eprintln!("shitd: wrote {}", plist_path.display());

    let status = std::process::Command::new("launchctl")
        .args(["load", &plist_path.to_string_lossy()])
        .status()?;
    if !status.success() {
        bail!("launchctl load failed");
    }

    eprintln!("shitd: service installed and started");
    Ok(())
}

fn uninstall_launchd() -> Result<()> {
    let plist_path = launchd_plist_path()?;

    if plist_path.exists() {
        let _ = std::process::Command::new("launchctl")
            .args(["unload", &plist_path.to_string_lossy()])
            .status();

        std::fs::remove_file(&plist_path)?;
        eprintln!("shitd: removed {}", plist_path.display());
    }

    eprintln!("shitd: service uninstalled");
    Ok(())
}
