pub mod server;
pub mod service;

use anyhow::Result;

pub fn handle(action: crate::DaemonCommand) -> Result<()> {
    match action {
        crate::DaemonCommand::Run => server::run_server(),
        crate::DaemonCommand::Start => start(),
        crate::DaemonCommand::Stop => service::stop(),
        crate::DaemonCommand::Restart => service::restart(),
        crate::DaemonCommand::Status => status(),
        crate::DaemonCommand::Logs { follow } => service::logs(follow),
        crate::DaemonCommand::Uninstall => {
            let _ = service::stop();
            service::uninstall()
        }
    }
}

fn start() -> Result<()> {
    if !service::is_installed()? {
        eprintln!("shitd: service not installed, installing now...");
        service::install()?;
    }
    service::start()
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
