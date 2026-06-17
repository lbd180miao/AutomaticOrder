use serde::{Deserialize, Serialize};
use std::env;
use std::fs;

#[derive(Debug, Serialize, Deserialize)]
pub struct EnvConfig {
    pub envs: Vec<EnvItem>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct EnvItem {
    pub key: String,
    pub value: String,
}

impl EnvConfig {
    /// 从 Env.json 加载配置
    pub fn load() -> Result<Self, Box<dyn std::error::Error>> {
        let content = fs::read_to_string("Env.json")?;
        let config: EnvConfig = serde_json::from_str(&content)?;
        Ok(config)
    }

    /// 设置环境变量
    pub fn apply(&self) -> Result<(), Box<dyn std::error::Error>> {
        for env_item in &self.envs {
            unsafe {
                env::set_var(&env_item.key, &env_item.value);
            }
            println!("设置环境变量: {} = {}", env_item.key, env_item.value);
        }
        Ok(())
    }
}
