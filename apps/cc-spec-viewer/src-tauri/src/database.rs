// database.rs - PostgreSQL Docker 集成
//
// 功能:
// - 检测 Docker 是否安装
// - 启动/停止 PostgreSQL 容器
// - 连接字符串管理
// - Schema 初始化

use serde::{Deserialize, Serialize};
use std::process::Command;

/// 容器名称
const CONTAINER_NAME: &str = "cc-spec-postgres";
/// 默认端口
const DEFAULT_PORT: u16 = 5432;
/// 默认密码
const DEFAULT_PASSWORD: &str = "ccspec";
/// PostgreSQL 镜像
const POSTGRES_IMAGE: &str = "postgres:16-alpine";

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct DatabaseStatus {
    /// 是否已连接
    pub connected: bool,
    /// 数据库类型: "docker" | "remote" | "none"
    pub db_type: String,
    /// Docker 是否可用
    pub docker_available: bool,
    /// 容器状态: "running" | "stopped" | "not_found" | "unknown"
    pub container_status: String,
    /// 连接字符串 (已脱敏)
    pub connection_string: Option<String>,
    /// 错误信息
    pub error: Option<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct DockerContainerInfo {
    pub name: String,
    pub status: String,
    pub port: Option<u16>,
}

/// 检测 Docker 是否安装
fn is_docker_available() -> bool {
    Command::new("docker")
        .arg("info")
        .output()
        .map(|output| output.status.success())
        .unwrap_or(false)
}

/// 获取容器状态
fn get_container_status() -> String {
    let output = Command::new("docker")
        .args(["inspect", "-f", "{{.State.Status}}", CONTAINER_NAME])
        .output();

    match output {
        Ok(out) if out.status.success() => {
            String::from_utf8_lossy(&out.stdout).trim().to_string()
        }
        _ => "not_found".to_string(),
    }
}

/// 检查容器是否存在
fn container_exists() -> bool {
    let status = get_container_status();
    status != "not_found"
}

/// 测试数据库连接
fn test_connection(connection_string: &str) -> Result<bool, String> {
    // 使用 psql 测试连接
    let output = Command::new("docker")
        .args([
            "exec",
            CONTAINER_NAME,
            "psql",
            connection_string,
            "-c",
            "SELECT 1",
        ])
        .output();

    match output {
        Ok(out) => Ok(out.status.success()),
        Err(e) => Err(format!("连接测试失败: {}", e)),
    }
}

/// 生成连接字符串
fn build_connection_string(host: &str, port: u16, user: &str, password: &str, database: &str) -> String {
    format!(
        "postgresql://{}:{}@{}:{}/{}",
        user, password, host, port, database
    )
}

/// 脱敏连接字符串
fn mask_connection_string(conn: &str) -> String {
    // 隐藏密码
    if let Some(at_pos) = conn.find('@') {
        if let Some(colon_pos) = conn[..at_pos].rfind(':') {
            let prefix = &conn[..colon_pos + 1];
            let suffix = &conn[at_pos..];
            return format!("{}****{}", prefix, suffix);
        }
    }
    conn.to_string()
}

#[tauri::command]
pub async fn check_database_connection() -> Result<DatabaseStatus, String> {
    let docker_available = is_docker_available();
    let container_status = if docker_available {
        get_container_status()
    } else {
        "unknown".to_string()
    };

    let connected = container_status == "running";
    let connection_string = if connected {
        Some(mask_connection_string(&build_connection_string(
            "localhost",
            DEFAULT_PORT,
            "postgres",
            DEFAULT_PASSWORD,
            "ccspec",
        )))
    } else {
        None
    };

    Ok(DatabaseStatus {
        connected,
        db_type: if connected { "docker" } else { "none" }.to_string(),
        docker_available,
        container_status,
        connection_string,
        error: None,
    })
}

#[tauri::command]
pub async fn start_docker_postgres() -> Result<DatabaseStatus, String> {
    // 1. 检查 Docker 是否可用
    if !is_docker_available() {
        return Err("Docker 未安装或未启动。请先安装 Docker Desktop。".to_string());
    }

    // 2. 检查容器是否已存在
    if container_exists() {
        let status = get_container_status();
        if status == "running" {
            // 容器已在运行
            return Ok(DatabaseStatus {
                connected: true,
                db_type: "docker".to_string(),
                docker_available: true,
                container_status: "running".to_string(),
                connection_string: Some(mask_connection_string(&build_connection_string(
                    "localhost",
                    DEFAULT_PORT,
                    "postgres",
                    DEFAULT_PASSWORD,
                    "ccspec",
                ))),
                error: None,
            });
        } else {
            // 容器存在但未运行，启动它
            let output = Command::new("docker")
                .args(["start", CONTAINER_NAME])
                .output()
                .map_err(|e| format!("启动容器失败: {}", e))?;

            if !output.status.success() {
                let stderr = String::from_utf8_lossy(&output.stderr);
                return Err(format!("启动容器失败: {}", stderr.trim()));
            }
        }
    } else {
        // 3. 容器不存在，创建新容器
        let output = Command::new("docker")
            .args([
                "run",
                "-d",
                "--name",
                CONTAINER_NAME,
                "-e",
                &format!("POSTGRES_PASSWORD={}", DEFAULT_PASSWORD),
                "-e",
                "POSTGRES_DB=ccspec",
                "-p",
                &format!("{}:5432", DEFAULT_PORT),
                "-v",
                "cc-spec-pgdata:/var/lib/postgresql/data",
                POSTGRES_IMAGE,
            ])
            .output()
            .map_err(|e| format!("创建容器失败: {}", e))?;

        if !output.status.success() {
            let stderr = String::from_utf8_lossy(&output.stderr);
            return Err(format!("创建容器失败: {}", stderr.trim()));
        }

        // 等待数据库就绪
        std::thread::sleep(std::time::Duration::from_secs(3));
    }

    // 4. 初始化 Schema
    let init_sql = r#"
        -- cc-spec 基础 schema
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            title TEXT,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS runs (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL REFERENCES sessions(id),
            agent TEXT NOT NULL,
            purpose TEXT,
            status TEXT DEFAULT 'idle',
            pid INTEGER,
            started_at TIMESTAMP,
            ended_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS events (
            id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL REFERENCES runs(id),
            session_id TEXT NOT NULL,
            seq BIGINT NOT NULL,
            ts TIMESTAMP NOT NULL,
            type TEXT NOT NULL,
            source TEXT NOT NULL,
            payload JSONB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_events_run_id ON events(run_id);
        CREATE INDEX IF NOT EXISTS idx_events_session_id ON events(session_id);
        CREATE INDEX IF NOT EXISTS idx_events_seq ON events(seq);
    "#;

    let output = Command::new("docker")
        .args([
            "exec",
            "-i",
            CONTAINER_NAME,
            "psql",
            "-U",
            "postgres",
            "-d",
            "ccspec",
            "-c",
            init_sql,
        ])
        .output();

    let schema_error = match output {
        Ok(out) if !out.status.success() => {
            Some(String::from_utf8_lossy(&out.stderr).to_string())
        }
        Err(e) => Some(format!("Schema 初始化失败: {}", e)),
        _ => None,
    };

    Ok(DatabaseStatus {
        connected: true,
        db_type: "docker".to_string(),
        docker_available: true,
        container_status: "running".to_string(),
        connection_string: Some(mask_connection_string(&build_connection_string(
            "localhost",
            DEFAULT_PORT,
            "postgres",
            DEFAULT_PASSWORD,
            "ccspec",
        ))),
        error: schema_error,
    })
}

#[tauri::command]
pub async fn stop_docker_postgres() -> Result<(), String> {
    if !is_docker_available() {
        return Err("Docker 未安装".to_string());
    }

    let output = Command::new("docker")
        .args(["stop", CONTAINER_NAME])
        .output()
        .map_err(|e| format!("停止容器失败: {}", e))?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(format!("停止容器失败: {}", stderr.trim()));
    }

    Ok(())
}

#[tauri::command]
pub async fn get_docker_postgres_logs(lines: Option<u32>) -> Result<String, String> {
    if !is_docker_available() {
        return Err("Docker 未安装".to_string());
    }

    let line_count = lines.unwrap_or(50).to_string();
    let output = Command::new("docker")
        .args(["logs", "--tail", &line_count, CONTAINER_NAME])
        .output()
        .map_err(|e| format!("获取日志失败: {}", e))?;

    if output.status.success() {
        Ok(String::from_utf8_lossy(&output.stdout).to_string())
    } else {
        Ok(String::from_utf8_lossy(&output.stderr).to_string())
    }
}

/// 连接远程数据库
#[tauri::command]
pub async fn connect_remote_database(connection_string: String) -> Result<DatabaseStatus, String> {
    // 简单验证连接字符串格式
    if !connection_string.starts_with("postgresql://") && !connection_string.starts_with("postgres://") {
        return Err("无效的连接字符串格式。应以 postgresql:// 或 postgres:// 开头。".to_string());
    }

    // TODO: 实际测试连接
    // 这里需要添加 sqlx 或 tokio-postgres 依赖来测试连接

    Ok(DatabaseStatus {
        connected: true,
        db_type: "remote".to_string(),
        docker_available: is_docker_available(),
        container_status: "not_found".to_string(),
        connection_string: Some(mask_connection_string(&connection_string)),
        error: None,
    })
}