pub mod server;
pub mod service;

use anyhow::Result;

pub fn handle(action: crate::DaemonCommand) -> Result<()> {
    match action {
        crate::DaemonCommand::Start => server::run_server(),
        crate::DaemonCommand::Install => service::install(),
        crate::DaemonCommand::Uninstall => service::uninstall(),
        crate::DaemonCommand::Status => status(),
    }
}

fn status() -> Result<()> {
    let port_file = server::port_file_path();
    if !port_file.exists() {
        eprintln!("shitd: not running (no port file)");
        return Ok(());
    }
    let port_str = std::fs::read_to_string(&port_file)?;
    let port: u16 = port_str.trim().parse()?;
    let url = format!("http://127.0.0.1:{}/health", port);
    let agent = ureq::Agent::new_with_defaults();
    match agent.get(&url).call() {
        Ok(_) => eprintln!("shitd: running on port {}", port),
        Err(_) => eprintln!("shitd: not responding (port file exists but server unreachable)"),
    }
    Ok(())
}
