use anyhow::Result;
use serde::Deserialize;

#[derive(Deserialize, Default)]
pub struct Config {
    pub auto_execute: Option<bool>,
}

pub fn load_config() -> Result<Config> {
    let Some(config_dir) = dirs::config_dir() else {
        return Ok(Config::default());
    };

    let config_path = config_dir.join("shit").join("config.toml");
    if !config_path.exists() {
        return Ok(Config::default());
    }

    let contents = std::fs::read_to_string(&config_path)?;
    let config: Config = toml::from_str(&contents)?;
    Ok(config)
}
