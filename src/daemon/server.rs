use anyhow::Result;
use log::{error, info, warn};
use std::path::PathBuf;
use std::time::Duration;

use crate::model::{find_model, Engine};

/// Returns the path where the daemon writes its port number.
/// Linux: $XDG_RUNTIME_DIR/shitd.port
/// macOS: ~/Library/Application Support/shit/shitd.port
/// Fallback: /tmp/shitd-$USER.port
pub fn port_file_path() -> PathBuf {
    if let Ok(runtime_dir) = std::env::var("XDG_RUNTIME_DIR") {
        return PathBuf::from(runtime_dir).join("shitd.port");
    }
    if let Some(data_dir) = dirs::data_dir() {
        let dir = data_dir.join("shit");
        let _ = std::fs::create_dir_all(&dir);
        return dir.join("shitd.port");
    }
    let user = std::env::var("USER").unwrap_or_else(|_| "unknown".into());
    PathBuf::from(format!("/tmp/shitd-{}.port", user))
}

pub fn run_server() -> Result<()> {
    env_logger::Builder::from_env(env_logger::Env::default().default_filter_or("info"))
        .format_target(false)
        .init();

    const MAX_RETRIES: u32 = 10;
    const INITIAL_BACKOFF: Duration = Duration::from_secs(2);

    let paths = {
        let mut attempt = 0;
        loop {
            match find_model() {
                Ok(paths) => break paths,
                Err(e) => {
                    attempt += 1;
                    if attempt > MAX_RETRIES {
                        return Err(e.context("failed to find/download model after 10 retries"));
                    }
                    let delay = INITIAL_BACKOFF * 2u32.pow(attempt - 1).min(32);
                    warn!(
                        "model not available ({}), retrying in {}s ({}/{})",
                        e,
                        delay.as_secs(),
                        attempt,
                        MAX_RETRIES
                    );
                    std::thread::sleep(delay);
                }
            }
        }
    };
    info!("loading model...");
    let mut engine = Engine::new(&paths.model_path, &paths.tokenizer_path)?;
    info!("model loaded");

    let server = tiny_http::Server::http("127.0.0.1:0")
        .map_err(|e| anyhow::anyhow!("failed to bind: {}", e))?;
    let port = server.server_addr().to_ip().unwrap().port();

    let port_file = port_file_path();
    std::fs::write(&port_file, port.to_string())?;
    info!("listening on 127.0.0.1:{}", port);

    // Clean up port file on shutdown
    let _guard = PortFileGuard(port_file);

    for request in server.incoming_requests() {
        match (request.method(), request.url()) {
            (tiny_http::Method::Get, "/health") => {
                let response = tiny_http::Response::from_string("ok");
                let _ = request.respond(response);
            }
            (tiny_http::Method::Post, "/infer") => {
                handle_infer(request, &mut engine);
            }
            _ => {
                let response =
                    tiny_http::Response::from_string("not found").with_status_code(404);
                let _ = request.respond(response);
            }
        }
    }

    Ok(())
}

fn handle_infer(mut request: tiny_http::Request, engine: &mut Engine) {
    let mut body = String::new();
    if request.as_reader().read_to_string(&mut body).is_err() {
        let resp =
            tiny_http::Response::from_string(r#"{"error":"bad request"}"#).with_status_code(400);
        let _ = request.respond(resp);
        return;
    }

    let parsed: Result<serde_json::Value, _> = serde_json::from_str(&body);
    let prompt = match parsed {
        Ok(v) => v["prompt"].as_str().unwrap_or("").to_string(),
        Err(_) => {
            let resp = tiny_http::Response::from_string(r#"{"error":"invalid json"}"#)
                .with_status_code(400);
            let _ = request.respond(resp);
            return;
        }
    };

    let result = crate::model::infer_with_engine(engine, &prompt);
    let fixes = match result {
        Ok(fixes) => fixes,
        Err(e) => {
            error!("inference failed: {}", e);
            let resp = tiny_http::Response::from_string(
                serde_json::json!({"error": e.to_string()}).to_string(),
            )
            .with_status_code(500);
            let _ = request.respond(resp);
            return;
        }
    };

    let resp_body = serde_json::json!({"fixes": fixes}).to_string();
    let response = tiny_http::Response::from_string(resp_body)
        .with_header("Content-Type: application/json".parse::<tiny_http::Header>().unwrap());
    let _ = request.respond(response);
}

/// RAII guard that removes the port file when the server shuts down.
struct PortFileGuard(PathBuf);

impl Drop for PortFileGuard {
    fn drop(&mut self) {
        let _ = std::fs::remove_file(&self.0);
    }
}
