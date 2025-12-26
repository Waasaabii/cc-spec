// translation.rs - 本地翻译功能 (多模型支持)
//
// 功能:
// - HuggingFace API 动态查询翻译模型
// - 多模型下载和管理
// - 完整的下载进度追踪（字节级别）
// - 模型加载/卸载/切换
// - 资源占用监控

use candle_core::{DType, Device, Tensor};
use candle_nn::VarBuilder;
use candle_transformers::models::t5::{Config, T5ForConditionalGeneration};
use futures_util::StreamExt;
use once_cell::sync::OnceCell;
use reqwest::Client;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::{Arc, Mutex, RwLock};
use sysinfo::System;
use tauri::Emitter;
use tokenizers::Tokenizer;

// ============================================================================
// 常量定义
// ============================================================================

/// HuggingFace API 端点（使用镜像，国内访问更快）
const HF_API_BASE: &str = "https://hf-mirror.com/api/models";
const HF_MIRROR_BASE: &str = "https://hf-mirror.com";
const HF_OFFICIAL_BASE: &str = "https://huggingface.co";

/// 默认最大模型大小 (500MB)
const DEFAULT_MAX_MODEL_SIZE: u64 = 500 * 1024 * 1024;

/// 最大输入/输出 token 数
const MAX_INPUT_TOKENS: usize = 256;
const MAX_OUTPUT_TOKENS: usize = 128;

/// 模型所需文件
const MODEL_REQUIRED_FILES: &[&str] = &[
    "model.safetensors",
    "config.json",
    "tokenizer.json",
    "spiece.model",
];

// ============================================================================
// 数据结构
// ============================================================================

/// 翻译模型信息（来自 HuggingFace API）
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct TranslationModelInfo {
    pub id: String,
    pub name: String,
    pub description: String,
    pub size: u64,
    pub downloads: u64,
    pub likes: u32,
    pub tags: Vec<String>,
    pub supports_en_zh: bool,
    pub is_recommended: bool,
}

/// 本地模型状态
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub enum ModelState {
    NotDownloaded,
    Downloading,
    Downloaded,
    Loading,
    Loaded,
    Error(String),
}

/// 本地模型记录
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct LocalModelRecord {
    pub id: String,
    pub name: String,
    pub size: u64,
    pub state: ModelState,
    pub path: Option<String>,
    pub downloaded_at: Option<String>,
    pub last_used_at: Option<String>,
    pub files: Vec<ModelFileStatus>,
}

/// 模型文件状态
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ModelFileStatus {
    pub name: String,
    pub exists: bool,
    pub size: Option<u64>,
    pub expected_size: Option<u64>,
}

/// 下载进度（字节级别）
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct DownloadProgress {
    pub model_id: String,
    pub status: String,
    pub current_file: String,
    pub current_file_index: usize,
    pub total_files: usize,
    pub file_downloaded: u64,
    pub file_total: u64,
    pub total_downloaded: u64,
    pub total_size: u64,
    pub speed_bps: u64,
    pub eta_seconds: Option<u64>,
    pub progress_percent: f32,
}

/// 资源占用信息
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ResourceUsage {
    pub memory_mb: f64,
    pub cpu_percent: f32,
    pub model_loaded: bool,
    pub active_model_id: Option<String>,
    pub cache_entries: usize,
    pub cache_size_bytes: u64,
    pub device: String,
}

/// 模型管理器状态
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ModelManagerStatus {
    pub available_models: Vec<TranslationModelInfo>,
    pub local_models: Vec<LocalModelRecord>,
    pub active_model_id: Option<String>,
    pub resource_usage: ResourceUsage,
    pub last_updated: String,
}

/// HuggingFace API 响应
#[derive(Debug, Deserialize)]
struct HfModelResponse {
    #[serde(rename = "modelId", alias = "id")]
    model_id: String,
    downloads: Option<u64>,
    likes: Option<u32>,
    tags: Option<Vec<String>>,
    #[serde(rename = "pipeline_tag")]
    pipeline_tag: Option<String>,
    siblings: Option<Vec<HfSibling>>,
}

#[derive(Debug, Clone, Deserialize)]
struct HfSibling {
    rfilename: String,
    size: Option<u64>,
}

// ============================================================================
// 全局状态
// ============================================================================

/// 翻译缓存
static TRANSLATION_CACHE: Mutex<Option<HashMap<String, String>>> = Mutex::new(None);

/// 当前加载的模型
static LOADED_MODEL: OnceCell<Arc<Mutex<LoadedModel>>> = OnceCell::new();

/// 模型注册表
static MODEL_REGISTRY: OnceCell<Arc<RwLock<ModelRegistry>>> = OnceCell::new();

/// HTTP 客户端
static HTTP_CLIENT: OnceCell<Client> = OnceCell::new();

/// 系统监控实例（持久化以获取准确的 CPU 使用率）
static SYSTEM_MONITOR: OnceCell<Mutex<System>> = OnceCell::new();

/// 可用模型列表缓存（避免每次都请求 HuggingFace API）
static AVAILABLE_MODELS_CACHE: OnceCell<Mutex<ModelsCache>> = OnceCell::new();

/// 缓存有效期（5分钟）
const CACHE_TTL_SECS: u64 = 300;

struct ModelsCache {
    models: Vec<TranslationModelInfo>,
    fetched_at: std::time::Instant,
}

struct LoadedModel {
    id: String,
    model: T5ForConditionalGeneration,
    tokenizer: Tokenizer,
    device: Device,
}

struct ModelRegistry {
    models: HashMap<String, LocalModelRecord>,
    active_model_id: Option<String>,
}

// ============================================================================
// 初始化函数
// ============================================================================

fn get_http_client() -> &'static Client {
    HTTP_CLIENT.get_or_init(|| {
        Client::builder()
            .timeout(std::time::Duration::from_secs(30))
            .build()
            .unwrap_or_default()
    })
}

fn get_model_registry() -> Arc<RwLock<ModelRegistry>> {
    Arc::clone(MODEL_REGISTRY.get_or_init(|| {
        Arc::new(RwLock::new(ModelRegistry {
            models: HashMap::new(),
            active_model_id: None,
        }))
    }))
}

fn get_models_base_dir() -> PathBuf {
    let local_app_data = std::env::var("LOCALAPPDATA")
        .unwrap_or_else(|_| std::env::var("HOME").unwrap_or(".".to_string()));
    PathBuf::from(local_app_data)
        .join("cc-spec-tools")
        .join("models")
}

fn get_model_dir(model_id: &str) -> PathBuf {
    let safe_name = model_id.replace('/', "_");
    get_models_base_dir().join(safe_name)
}

// ============================================================================
// HuggingFace API 查询
// ============================================================================

/// 获取或初始化可用模型缓存
fn get_models_cache() -> &'static Mutex<ModelsCache> {
    AVAILABLE_MODELS_CACHE.get_or_init(|| {
        Mutex::new(ModelsCache {
            models: Vec::new(),
            fetched_at: std::time::Instant::now() - std::time::Duration::from_secs(CACHE_TTL_SECS + 1),
        })
    })
}

/// 从 HuggingFace 查询翻译模型列表
///
/// 筛选条件：
/// - pipeline_tag = translation
/// - 有 safetensors 格式文件
/// - 支持英中翻译（tags 包含 en 和 zh）
/// - 文件大小在限制范围内
///
/// 使用缓存机制，缓存有效期 5 分钟
#[tauri::command]
pub async fn list_translation_models(
    max_size_mb: Option<u32>,
    _include_non_safetensors: Option<bool>,
) -> Result<Vec<TranslationModelInfo>, String> {
    let max_size = max_size_mb
        .map(|mb| (mb as u64) * 1024 * 1024)
        .unwrap_or(DEFAULT_MAX_MODEL_SIZE);

    // 检查缓存是否有效
    {
        let cache = get_models_cache().lock().map_err(|e| e.to_string())?;
        let elapsed = cache.fetched_at.elapsed().as_secs();
        if elapsed < CACHE_TTL_SECS && !cache.models.is_empty() {
            eprintln!("[translation] Using cached models (age: {}s)", elapsed);
            // 根据 max_size 过滤缓存的模型
            let filtered: Vec<TranslationModelInfo> = cache.models
                .iter()
                .filter(|m| m.size <= max_size)
                .cloned()
                .collect();
            return Ok(filtered);
        }
        eprintln!("[translation] Cache expired or empty, fetching from API...");
    }

    // 缓存无效，从 API 获取
    let models = fetch_models_from_api().await?;

    // 更新缓存
    {
        let mut cache = get_models_cache().lock().map_err(|e| e.to_string())?;
        cache.models = models.clone();
        cache.fetched_at = std::time::Instant::now();
        eprintln!("[translation] Cache updated with {} models", cache.models.len());
    }

    // 根据 max_size 过滤
    let filtered: Vec<TranslationModelInfo> = models
        .into_iter()
        .filter(|m| m.size <= max_size)
        .collect();

    Ok(filtered)
}

/// 从 HuggingFace API 获取模型列表（内部函数，不带缓存）
async fn fetch_models_from_api() -> Result<Vec<TranslationModelInfo>, String> {
    let client = get_http_client();

    // 查询 HuggingFace API - 获取翻译模型，按下载量排序
    // 使用 full=true 获取完整信息（包括 siblings）
    let url = format!(
        "{}?pipeline_tag=translation&sort=downloads&direction=-1&limit=100&full=true",
        HF_API_BASE
    );

    eprintln!("[translation] Fetching models from: {}", url);

    let response = client
        .get(&url)
        .header("User-Agent", "cc-spec-tools/0.1.0")
        .send()
        .await;

    match response {
        Ok(resp) if resp.status().is_success() => {
            let models: Vec<HfModelResponse> = resp.json().await.map_err(|e| {
                eprintln!("[translation] Failed to parse response: {}", e);
                e.to_string()
            })?;

            eprintln!("[translation] Retrieved {} models from HuggingFace", models.len());

            let mut result: Vec<TranslationModelInfo> = Vec::new();

            // 不在这里过滤大小，保存所有符合条件的模型到缓存
            // 大小过滤在调用时进行
            let max_cache_size: u64 = 2 * 1024 * 1024 * 1024; // 2GB 作为缓存上限

            for model in models {
                let tags = model.tags.clone().unwrap_or_default();

                // 筛选支持英中翻译的模型
                let has_en = tags.iter().any(|t| t == "en" || t.contains("en-"));
                let has_zh = tags.iter().any(|t| t == "zh" || t.contains("-zh") || t.contains("chinese"));
                let supports_en_zh = has_en && has_zh;

                // 计算 safetensors 文件大小
                let siblings = model.siblings.clone().unwrap_or_default();
                let has_safetensors = siblings.iter().any(|s| s.rfilename.ends_with(".safetensors"));

                // 如果没有 safetensors，跳过
                if !has_safetensors {
                    continue;
                }

                // 计算模型总大小（只计算主要文件）
                // 注意：HF API 的 siblings 可能不包含 size 字段
                let size: u64 = siblings
                    .iter()
                    .filter(|s| {
                        s.rfilename.ends_with(".safetensors")
                            || s.rfilename.ends_with(".json")
                            || s.rfilename.ends_with(".model")
                            || s.rfilename.ends_with(".txt")
                    })
                    .filter_map(|s| s.size)
                    .sum();

                // 如果 API 没返回 size，设置一个估计值（基于模型类型）
                let estimated_size = if size == 0 {
                    // 根据模型名估计大小
                    if model.model_id.contains("small") { 250_000_000 }  // ~250MB
                    else if model.model_id.contains("base") { 900_000_000 }  // ~900MB
                    else if model.model_id.contains("large") { 3_000_000_000 }  // ~3GB
                    else { 500_000_000 }  // 默认 ~500MB
                } else {
                    size
                };

                // 过滤大小（最大 max_cache_size）
                if estimated_size > max_cache_size {
                    continue;
                }

                // 生成描述
                let description = if supports_en_zh {
                    format!("英中翻译 | {} 下载", format_download_count(model.downloads.unwrap_or(0)))
                } else {
                    format!("通用翻译 | {} 下载", format_download_count(model.downloads.unwrap_or(0)))
                };

                // 推荐模型：t5-small 或下载量最高的英中翻译模型
                let is_recommended = model.model_id == "google-t5/t5-small"
                    || model.model_id == "Helsinki-NLP/opus-mt-en-zh"
                    || model.model_id == "Helsinki-NLP/opus-mt-zh-en";

                result.push(TranslationModelInfo {
                    id: model.model_id.clone(),
                    name: model.model_id.split('/').last().unwrap_or(&model.model_id).to_string(),
                    description,
                    size: estimated_size,
                    downloads: model.downloads.unwrap_or(0),
                    likes: model.likes.unwrap_or(0),
                    tags,
                    supports_en_zh,
                    is_recommended,
                });
            }

            // 排序：推荐的在前，然后按下载量降序
            result.sort_by(|a, b| {
                match (a.is_recommended, b.is_recommended) {
                    (true, false) => std::cmp::Ordering::Less,
                    (false, true) => std::cmp::Ordering::Greater,
                    _ => b.downloads.cmp(&a.downloads),
                }
            });

            // 限制返回数量（缓存更多，显示时再限制）
            result.truncate(50);

            eprintln!("[translation] Filtered to {} models for caching", result.len());

            Ok(result)
        }
        Ok(resp) => {
            let status = resp.status();
            eprintln!("[translation] HuggingFace API error: {}", status);
            Err(format!("HuggingFace API error: {}", status))
        }
        Err(e) => {
            eprintln!("[translation] Failed to connect: {}", e);
            Err(format!("Failed to connect to HuggingFace API: {}", e))
        }
    }
}

/// 格式化下载次数
fn format_download_count(count: u64) -> String {
    if count >= 1_000_000 {
        format!("{:.1}M", count as f64 / 1_000_000.0)
    } else if count >= 1_000 {
        format!("{:.1}K", count as f64 / 1_000.0)
    } else {
        count.to_string()
    }
}

// ============================================================================
// 模型下载（带完整进度）
// ============================================================================

/// 下载指定模型
#[tauri::command]
pub async fn download_model(
    app_handle: tauri::AppHandle,
    model_id: String,
) -> Result<(), String> {
    let model_dir = get_model_dir(&model_id);
    std::fs::create_dir_all(&model_dir)
        .map_err(|e| format!("Failed to create model directory: {}", e))?;

    // 更新注册表状态
    {
        let registry = get_model_registry();
        let mut reg = registry.write().map_err(|e| e.to_string())?;
        reg.models.insert(model_id.clone(), LocalModelRecord {
            id: model_id.clone(),
            name: model_id.split('/').last().unwrap_or(&model_id).to_string(),
            size: 0,
            state: ModelState::Downloading,
            path: Some(model_dir.to_string_lossy().to_string()),
            downloaded_at: None,
            last_used_at: None,
            files: Vec::new(),
        });
    }

    let _ = app_handle.emit("translation.download.started", serde_json::json!({
        "model_id": &model_id,
    }));

    let client = get_http_client();
    let files = MODEL_REQUIRED_FILES;
    let total_files = files.len();
    let mut total_downloaded: u64 = 0;
    let mut total_size: u64 = 0;

    // 先获取所有文件大小
    for filename in files {
        let mirror_url = format!("{}/{}/resolve/main/{}", HF_MIRROR_BASE, model_id, filename);
        if let Ok(resp) = client.head(&mirror_url).send().await {
            if let Some(len) = resp.headers().get("content-length") {
                if let Ok(size) = len.to_str().unwrap_or("0").parse::<u64>() {
                    total_size += size;
                }
            }
        }
    }

    for (file_index, filename) in files.iter().enumerate() {
        let file_path = model_dir.join(filename);

        // 检查文件是否已存在
        if file_path.exists() {
            let existing_size = std::fs::metadata(&file_path).map(|m| m.len()).unwrap_or(0);
            total_downloaded += existing_size;

            let _ = app_handle.emit("translation.download.progress", DownloadProgress {
                model_id: model_id.clone(),
                status: "skipped".to_string(),
                current_file: filename.to_string(),
                current_file_index: file_index + 1,
                total_files,
                file_downloaded: existing_size,
                file_total: existing_size,
                total_downloaded,
                total_size,
                speed_bps: 0,
                eta_seconds: None,
                progress_percent: (total_downloaded as f32 / total_size.max(1) as f32) * 100.0,
            });
            continue;
        }

        // 尝试镜像和官方源
        let urls = vec![
            format!("{}/{}/resolve/main/{}", HF_MIRROR_BASE, model_id, filename),
            format!("{}/{}/resolve/main/{}", HF_OFFICIAL_BASE, model_id, filename),
        ];

        let mut download_success = false;

        for url in urls {
            let result = download_file_with_progress(
                &app_handle,
                &client,
                &url,
                &file_path,
                &model_id,
                filename,
                file_index,
                total_files,
                total_downloaded,
                total_size,
            ).await;

            if let Ok(file_size) = result {
                total_downloaded += file_size;
                download_success = true;
                break;
            }
        }

        if !download_success {
            // 更新状态为错误
            let registry = get_model_registry();
            if let Ok(mut reg) = registry.write() {
                if let Some(record) = reg.models.get_mut(&model_id) {
                    record.state = ModelState::Error(format!("Failed to download {}", filename));
                }
            }

            let _ = app_handle.emit("translation.download.completed", serde_json::json!({
                "success": false,
                "model_id": &model_id,
                "error": format!("Failed to download {}", filename),
            }));

            return Err(format!("Failed to download {}", filename));
        }
    }

    // 更新注册表
    {
        let registry = get_model_registry();
        let mut reg = registry.write().map_err(|e| e.to_string())?;
        if let Some(record) = reg.models.get_mut(&model_id) {
            record.state = ModelState::Downloaded;
            record.size = total_downloaded;
            record.downloaded_at = Some(chrono::Utc::now().to_rfc3339());
            record.files = files.iter().map(|f| {
                let path = model_dir.join(f);
                ModelFileStatus {
                    name: f.to_string(),
                    exists: path.exists(),
                    size: std::fs::metadata(&path).ok().map(|m| m.len()),
                    expected_size: None,
                }
            }).collect();
        }
    }

    let _ = app_handle.emit("translation.download.completed", serde_json::json!({
        "success": true,
        "model_id": &model_id,
        "path": model_dir.to_string_lossy().to_string(),
        "total_size": total_downloaded,
    }));

    Ok(())
}

/// 下载单个文件并报告进度
async fn download_file_with_progress(
    app_handle: &tauri::AppHandle,
    client: &Client,
    url: &str,
    file_path: &PathBuf,
    model_id: &str,
    filename: &str,
    file_index: usize,
    total_files: usize,
    base_downloaded: u64,
    total_size: u64,
) -> Result<u64, String> {
    let response = client
        .get(url)
        .send()
        .await
        .map_err(|e| e.to_string())?;

    if !response.status().is_success() {
        return Err(format!("HTTP {}", response.status()));
    }

    let file_total = response
        .headers()
        .get("content-length")
        .and_then(|v| v.to_str().ok())
        .and_then(|v| v.parse::<u64>().ok())
        .unwrap_or(0);

    let mut file = std::fs::File::create(file_path)
        .map_err(|e| format!("Failed to create file: {}", e))?;

    let mut stream = response.bytes_stream();
    let mut file_downloaded: u64 = 0;
    let start_time = std::time::Instant::now();
    let mut last_report = std::time::Instant::now();

    use std::io::Write;

    while let Some(chunk) = stream.next().await {
        let chunk = chunk.map_err(|e| e.to_string())?;
        file.write_all(&chunk).map_err(|e| e.to_string())?;
        file_downloaded += chunk.len() as u64;

        // 每 100ms 报告一次进度
        if last_report.elapsed().as_millis() >= 100 {
            let elapsed = start_time.elapsed().as_secs_f64();
            let speed_bps = if elapsed > 0.0 {
                (file_downloaded as f64 / elapsed) as u64
            } else {
                0
            };

            let remaining = file_total.saturating_sub(file_downloaded);
            let eta_seconds = if speed_bps > 0 {
                Some(remaining / speed_bps)
            } else {
                None
            };

            let current_total = base_downloaded + file_downloaded;
            let progress_percent = (current_total as f32 / total_size.max(1) as f32) * 100.0;

            let _ = app_handle.emit("translation.download.progress", DownloadProgress {
                model_id: model_id.to_string(),
                status: "downloading".to_string(),
                current_file: filename.to_string(),
                current_file_index: file_index + 1,
                total_files,
                file_downloaded,
                file_total,
                total_downloaded: current_total,
                total_size,
                speed_bps,
                eta_seconds,
                progress_percent,
            });

            last_report = std::time::Instant::now();
        }
    }

    Ok(file_downloaded)
}

// ============================================================================
// 模型加载与卸载
// ============================================================================

/// 加载模型到内存
#[tauri::command]
pub async fn load_model(model_id: String) -> Result<bool, String> {
    let model_dir = get_model_dir(&model_id);

    // 检查文件完整性
    for filename in MODEL_REQUIRED_FILES {
        let path = model_dir.join(filename);
        if !path.exists() {
            return Err(format!("Model file missing: {}", filename));
        }
    }

    // 更新状态
    {
        let registry = get_model_registry();
        let mut reg = registry.write().map_err(|e| e.to_string())?;
        if let Some(record) = reg.models.get_mut(&model_id) {
            record.state = ModelState::Loading;
        }
    }

    // 在后台线程加载模型
    let model_id_clone = model_id.clone();
    let result = tokio::task::spawn_blocking(move || {
        load_model_sync(&model_id_clone, &model_dir)
    })
    .await
    .map_err(|e| format!("Failed to load model task: {}", e))?;

    match result {
        Ok(loaded) => {
            // 更新注册表
            let registry = get_model_registry();
            let mut reg = registry.write().map_err(|e| e.to_string())?;
            if let Some(record) = reg.models.get_mut(&model_id) {
                record.state = ModelState::Loaded;
                record.last_used_at = Some(chrono::Utc::now().to_rfc3339());
            }
            reg.active_model_id = Some(model_id.clone());

            // 存储到全局
            let _ = LOADED_MODEL.set(Arc::new(Mutex::new(loaded)));

            Ok(true)
        }
        Err(e) => {
            let registry = get_model_registry();
            if let Ok(mut reg) = registry.write() {
                if let Some(record) = reg.models.get_mut(&model_id) {
                    record.state = ModelState::Error(e.clone());
                }
            }
            Err(e)
        }
    }
}

/// 获取最佳可用设备（有 CUDA 用 CUDA，没有用 CPU）
fn get_best_device() -> Device {
    #[cfg(feature = "cuda")]
    {
        match Device::cuda_if_available(0) {
            Ok(device) => {
                eprintln!("[translation] Using CUDA device");
                device
            }
            Err(_) => {
                eprintln!("[translation] CUDA not available, using CPU");
                Device::Cpu
            }
        }
    }
    #[cfg(not(feature = "cuda"))]
    {
        eprintln!("[translation] CUDA feature not enabled, using CPU");
        Device::Cpu
    }
}

fn load_model_sync(model_id: &str, model_dir: &PathBuf) -> Result<LoadedModel, String> {
    let device = get_best_device();

    // 加载配置
    let config_path = model_dir.join("config.json");
    let config_str = std::fs::read_to_string(&config_path)
        .map_err(|e| format!("Failed to read config.json: {}", e))?;
    let config: Config = serde_json::from_str(&config_str)
        .map_err(|e| format!("Failed to parse config.json: {}", e))?;

    // 加载模型权重
    let model_path = model_dir.join("model.safetensors");
    let vb = unsafe {
        VarBuilder::from_mmaped_safetensors(&[model_path], DType::F32, &device)
            .map_err(|e| format!("Failed to load model weights: {}", e))?
    };

    let model = T5ForConditionalGeneration::load(vb, &config)
        .map_err(|e| format!("Failed to create model: {}", e))?;

    // 加载 tokenizer
    let tokenizer_path = model_dir.join("tokenizer.json");
    let tokenizer = Tokenizer::from_file(&tokenizer_path)
        .map_err(|e| format!("Failed to load tokenizer: {}", e))?;

    Ok(LoadedModel {
        id: model_id.to_string(),
        model,
        tokenizer,
        device,
    })
}

/// 卸载当前模型
#[tauri::command]
pub async fn unload_model() -> Result<bool, String> {
    // 由于 OnceCell 不支持重置，这里只能标记状态
    // 实际卸载需要重启应用
    let registry = get_model_registry();
    let mut reg = registry.write().map_err(|e| e.to_string())?;

    if let Some(model_id) = reg.active_model_id.take() {
        if let Some(record) = reg.models.get_mut(&model_id) {
            record.state = ModelState::Downloaded;
        }
    }

    // 清空缓存
    let mut cache = TRANSLATION_CACHE.lock().unwrap();
    *cache = None;

    Ok(true)
}

// ============================================================================
// 翻译功能
// ============================================================================

/// 执行翻译
#[tauri::command]
pub async fn translate_text(text: String) -> Result<String, String> {
    // 检查缓存
    {
        let cache = TRANSLATION_CACHE.lock().unwrap();
        if let Some(ref map) = *cache {
            if let Some(cached) = map.get(&text) {
                return Ok(cached.clone());
            }
        }
    }

    // 检查是否有模型加载
    let model_arc = LOADED_MODEL
        .get()
        .ok_or("No model loaded. Please load a model first.")?;

    let text_clone = text.clone();
    let result = tokio::task::spawn_blocking(move || {
        let mut model = model_arc.lock().map_err(|e| format!("Failed to acquire model lock: {}", e))?;
        translate_sync(&mut model, &text_clone)
    })
    .await
    .map_err(|e| format!("Translation task failed: {}", e))??;

    // 缓存结果
    {
        let mut cache = TRANSLATION_CACHE.lock().unwrap();
        if cache.is_none() {
            *cache = Some(HashMap::new());
        }
        if let Some(ref mut map) = *cache {
            map.insert(text, result.clone());
        }
    }

    Ok(result)
}

fn translate_sync(model: &mut LoadedModel, text: &str) -> Result<String, String> {
    let input_text = format!("translate English to Chinese: {}", text);

    let encoding = model.tokenizer
        .encode(input_text.clone(), true)
        .map_err(|e| format!("Tokenization failed: {}", e))?;

    let mut input_ids: Vec<u32> = encoding.get_ids().to_vec();
    if input_ids.len() > MAX_INPUT_TOKENS {
        input_ids.truncate(MAX_INPUT_TOKENS);
    }

    let input_tensor = Tensor::new(input_ids.as_slice(), &model.device)
        .map_err(|e| format!("Failed to create input tensor: {}", e))?
        .unsqueeze(0)
        .map_err(|e| format!("Failed to unsqueeze dimension: {}", e))?;

    let mut decoder_input_ids = vec![0u32];
    let eos_token_id = 1u32;

    for _ in 0..MAX_OUTPUT_TOKENS {
        let decoder_tensor = Tensor::new(decoder_input_ids.as_slice(), &model.device)
            .map_err(|e| format!("Failed to create decoder input: {}", e))?
            .unsqueeze(0)
            .map_err(|e| format!("Failed to unsqueeze dimension: {}", e))?;

        let output = model.model
            .forward(&input_tensor, &decoder_tensor)
            .map_err(|e| format!("Model forward pass failed: {}", e))?;

        let seq_len = output.dim(1).map_err(|e| format!("Failed to get sequence length: {}", e))?;
        let last_logits = output
            .narrow(1, seq_len - 1, 1)
            .map_err(|e| format!("Failed to narrow last logits: {}", e))?
            .squeeze(1)
            .map_err(|e| format!("Failed to squeeze dimension: {}", e))?;

        let next_token = last_logits
            .argmax(1)
            .map_err(|e| format!("Argmax failed: {}", e))?
            .to_scalar::<u32>()
            .map_err(|e| format!("Failed to convert to scalar: {}", e))?;

        if next_token == eos_token_id {
            break;
        }

        decoder_input_ids.push(next_token);
    }

    let output_text = model.tokenizer
        .decode(&decoder_input_ids[1..], true)
        .map_err(|e| format!("Decoding failed: {}", e))?;

    Ok(output_text)
}

// ============================================================================
// 资源监控
// ============================================================================

/// 获取或初始化系统监控实例
fn get_system_monitor() -> &'static Mutex<System> {
    SYSTEM_MONITOR.get_or_init(|| {
        let mut sys = System::new_all();
        sys.refresh_all();
        Mutex::new(sys)
    })
}

/// 获取资源占用情况
#[tauri::command]
pub async fn get_resource_usage() -> Result<ResourceUsage, String> {
    let current_pid = std::process::id();
    let pid = sysinfo::Pid::from_u32(current_pid);

    // 使用持久化的 System 实例，这样 CPU 使用率才准确
    let (memory_mb, cpu_percent) = {
        let mut sys = get_system_monitor().lock().map_err(|e| e.to_string())?;
        // 刷新当前进程信息
        sys.refresh_process(pid);

        if let Some(process) = sys.process(pid) {
            (
                // memory() 返回字节数
                process.memory() as f64 / (1024.0 * 1024.0),
                // CPU 使用率（多核情况下可能超过 100%，这里限制最大值）
                process.cpu_usage().min(100.0),
            )
        } else {
            (0.0, 0.0)
        }
    };

    let model_loaded = LOADED_MODEL.get().is_some();
    let active_model_id = {
        let registry = get_model_registry();
        registry.read().ok().and_then(|r| r.active_model_id.clone())
    };

    let (cache_entries, cache_size_bytes) = {
        let cache = TRANSLATION_CACHE.lock().unwrap();
        if let Some(ref map) = *cache {
            let entries = map.len();
            let size: u64 = map.iter()
                .map(|(k, v)| (k.len() + v.len()) as u64)
                .sum();
            (entries, size)
        } else {
            (0, 0)
        }
    };

    // 获取当前设备类型
    let device = if let Some(loaded) = LOADED_MODEL.get() {
        if let Ok(m) = loaded.lock() {
            match &m.device {
                Device::Cpu => "CPU".to_string(),
                Device::Cuda(_) => "CUDA".to_string(),
                Device::Metal(_) => "Metal".to_string(),
            }
        } else {
            "CPU".to_string()
        }
    } else {
        "CPU".to_string()
    };

    Ok(ResourceUsage {
        memory_mb,
        cpu_percent,
        model_loaded,
        active_model_id,
        cache_entries,
        cache_size_bytes,
        device,
    })
}

// ============================================================================
// 模型管理
// ============================================================================

/// 扫描本地模型（内部函数）
fn scan_local_models() -> Vec<LocalModelRecord> {
    let base_dir = get_models_base_dir();
    let mut local_models: Vec<LocalModelRecord> = Vec::new();

    if base_dir.exists() {
        if let Ok(entries) = std::fs::read_dir(&base_dir) {
            for entry in entries.flatten() {
                if entry.file_type().map(|t| t.is_dir()).unwrap_or(false) {
                    let model_name = entry.file_name().to_string_lossy().to_string();
                    let model_id = model_name.replace('_', "/");
                    let model_dir = entry.path();

                    let files: Vec<ModelFileStatus> = MODEL_REQUIRED_FILES
                        .iter()
                        .map(|f| {
                            let path = model_dir.join(f);
                            ModelFileStatus {
                                name: f.to_string(),
                                exists: path.exists(),
                                size: std::fs::metadata(&path).ok().map(|m| m.len()),
                                expected_size: None,
                            }
                        })
                        .collect();

                    let all_exist = files.iter().all(|f| f.exists);
                    let total_size: u64 = files.iter().filter_map(|f| f.size).sum();

                    let is_loaded = LOADED_MODEL.get()
                        .map(|m| m.lock().ok().map(|l| l.id == model_id).unwrap_or(false))
                        .unwrap_or(false);

                    let state = if is_loaded {
                        ModelState::Loaded
                    } else if all_exist {
                        ModelState::Downloaded
                    } else {
                        ModelState::NotDownloaded
                    };

                    local_models.push(LocalModelRecord {
                        id: model_id,
                        name: model_name,
                        size: total_size,
                        state,
                        path: Some(model_dir.to_string_lossy().to_string()),
                        downloaded_at: None,
                        last_used_at: None,
                        files,
                    });
                }
            }
        }
    }

    local_models
}

/// 获取本地模型列表（快速，不请求网络）
#[tauri::command]
pub async fn get_local_models() -> Result<Vec<LocalModelRecord>, String> {
    Ok(scan_local_models())
}

/// 获取模型管理器完整状态（本地数据优先，不等待 HF API）
#[tauri::command]
pub async fn get_model_manager_status() -> Result<ModelManagerStatus, String> {
    let local_models = scan_local_models();
    let resource_usage = get_resource_usage().await?;

    // 只返回缓存的模型列表，不主动请求 HF API
    // 前端应单独调用 list_translation_models 异步获取
    let available_models = {
        let cache = get_models_cache().lock().map_err(|e| e.to_string())?;
        if !cache.models.is_empty() {
            cache.models.clone()
        } else {
            Vec::new()
        }
    };

    Ok(ModelManagerStatus {
        available_models,
        local_models,
        active_model_id: resource_usage.active_model_id.clone(),
        resource_usage,
        last_updated: chrono::Utc::now().to_rfc3339(),
    })
}

/// 删除模型
#[tauri::command]
pub async fn delete_model(model_id: String) -> Result<(), String> {
    // 检查是否是当前加载的模型
    if let Some(loaded) = LOADED_MODEL.get() {
        if let Ok(model) = loaded.lock() {
            if model.id == model_id {
                return Err("Cannot delete model in use. Please unload it first.".to_string());
            }
        }
    }

    let model_dir = get_model_dir(&model_id);
    if model_dir.exists() {
        std::fs::remove_dir_all(&model_dir)
            .map_err(|e| format!("Failed to delete model directory: {}", e))?;
    }

    // 从注册表移除
    let registry = get_model_registry();
    if let Ok(mut reg) = registry.write() {
        reg.models.remove(&model_id);
    }

    Ok(())
}

/// 切换活动模型
#[tauri::command]
pub async fn switch_model(model_id: String) -> Result<bool, String> {
    // 先卸载当前模型（标记状态）
    unload_model().await?;

    // 加载新模型
    load_model(model_id).await
}

// ============================================================================
// 兼容性命令（保留旧接口）
// ============================================================================

#[tauri::command]
pub async fn check_translation_model() -> Result<serde_json::Value, String> {
    let status = get_model_manager_status().await?;

    // 查找 t5-small 或第一个已下载的模型
    let model = status.local_models.iter()
        .find(|m| m.id == "google-t5/t5-small")
        .or_else(|| status.local_models.first());

    Ok(serde_json::json!({
        "downloaded": model.map(|m| m.state == ModelState::Downloaded || m.state == ModelState::Loaded).unwrap_or(false),
        "model_path": model.and_then(|m| m.path.clone()),
        "model_size": model.map(|m| m.size),
        "model_version": model.map(|m| m.id.clone()),
        "files": model.map(|m| &m.files).cloned().unwrap_or_default(),
        "ready": model.map(|m| m.state == ModelState::Downloaded || m.state == ModelState::Loaded).unwrap_or(false),
        "loaded": model.map(|m| m.state == ModelState::Loaded).unwrap_or(false),
    }))
}

#[tauri::command]
pub async fn download_translation_model(app_handle: tauri::AppHandle) -> Result<(), String> {
    download_model(app_handle, "google-t5/t5-small".to_string()).await
}

#[tauri::command]
pub async fn preload_translation_model() -> Result<bool, String> {
    load_model("google-t5/t5-small".to_string()).await
}

#[tauri::command]
pub async fn clear_translation_cache() -> Result<(), String> {
    let mut cache = TRANSLATION_CACHE.lock().unwrap();
    *cache = None;
    Ok(())
}

#[tauri::command]
pub async fn delete_translation_model() -> Result<(), String> {
    delete_model("google-t5/t5-small".to_string()).await
}

#[tauri::command]
pub async fn get_translation_cache_stats() -> Result<serde_json::Value, String> {
    let usage = get_resource_usage().await?;
    Ok(serde_json::json!({
        "cached_count": usage.cache_entries,
        "model_ready": usage.model_loaded,
        "model_loaded": usage.model_loaded,
    }))
}
