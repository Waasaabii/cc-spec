// translation.rs - 本地翻译功能 (Candle T5)
//
// 功能:
// - 翻译模型下载（hf-mirror 优先，回退官方）
// - 模型文件完整性检查
// - Candle T5 本地翻译推理
// - 翻译结果缓存

use candle_core::{DType, Device, Tensor};
use candle_nn::VarBuilder;
use candle_transformers::models::t5::{self, Config, T5ForConditionalGeneration};
use once_cell::sync::OnceCell;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::{Arc, Mutex};
use tauri::Emitter;
use tokenizers::Tokenizer;

/// 翻译缓存
static TRANSLATION_CACHE: Mutex<Option<HashMap<String, String>>> = Mutex::new(None);

/// 全局模型实例（使用 Mutex 因为 forward 需要 &mut self）
static MODEL_INSTANCE: OnceCell<Arc<Mutex<TranslationModel>>> = OnceCell::new();

/// 模型文件列表
const MODEL_FILES: &[(&str, &str)] = &[
    ("model.safetensors", "https://hf-mirror.com/google-t5/t5-small/resolve/main/model.safetensors"),
    ("config.json", "https://hf-mirror.com/google-t5/t5-small/resolve/main/config.json"),
    ("tokenizer.json", "https://hf-mirror.com/google-t5/t5-small/resolve/main/tokenizer.json"),
    ("spiece.model", "https://hf-mirror.com/google-t5/t5-small/resolve/main/spiece.model"),
];

/// 官方镜像 URL 前缀
const OFFICIAL_URL_PREFIX: &str = "https://huggingface.co/google-t5/t5-small/resolve/main/";

/// 最大输入 token 数
const MAX_INPUT_TOKENS: usize = 256;

/// 最大生成 token 数
const MAX_OUTPUT_TOKENS: usize = 128;

/// 翻译模型包装
struct TranslationModel {
    model: T5ForConditionalGeneration,
    tokenizer: Tokenizer,
    device: Device,
}

impl TranslationModel {
    fn new(model_dir: &PathBuf) -> Result<Self, String> {
        // 使用 CPU 设备
        let device = Device::Cpu;

        // 加载配置
        let config_path = model_dir.join("config.json");
        let config_str = std::fs::read_to_string(&config_path)
            .map_err(|e| format!("读取 config.json 失败: {}", e))?;
        let config: Config = serde_json::from_str(&config_str)
            .map_err(|e| format!("解析 config.json 失败: {}", e))?;

        // 加载模型权重
        let model_path = model_dir.join("model.safetensors");
        let vb = unsafe {
            VarBuilder::from_mmaped_safetensors(&[model_path], DType::F32, &device)
                .map_err(|e| format!("加载模型权重失败: {}", e))?
        };

        // 创建模型
        let model = T5ForConditionalGeneration::load(vb, &config)
            .map_err(|e| format!("创建模型失败: {}", e))?;

        // 加载 tokenizer
        let tokenizer_path = model_dir.join("tokenizer.json");
        let tokenizer = Tokenizer::from_file(&tokenizer_path)
            .map_err(|e| format!("加载 tokenizer 失败: {}", e))?;

        Ok(Self {
            model,
            tokenizer,
            device,
        })
    }

    fn translate(&mut self, text: &str) -> Result<String, String> {
        // 构建翻译提示
        let input_text = format!("translate English to Chinese: {}", text);

        // 分词
        let encoding = self.tokenizer
            .encode(input_text.clone(), true)
            .map_err(|e| format!("分词失败: {}", e))?;

        let mut input_ids: Vec<u32> = encoding.get_ids().to_vec();
        
        // 截断输入
        if input_ids.len() > MAX_INPUT_TOKENS {
            input_ids.truncate(MAX_INPUT_TOKENS);
        }

        // 转换为 Tensor
        let input_tensor = Tensor::new(input_ids.as_slice(), &self.device)
            .map_err(|e| format!("创建输入张量失败: {}", e))?
            .unsqueeze(0)
            .map_err(|e| format!("扩展维度失败: {}", e))?;

        // 生成翻译
        let mut decoder_input_ids = vec![0u32]; // 开始 token
        let eos_token_id = 1u32; // 结束 token

        for _ in 0..MAX_OUTPUT_TOKENS {
            let decoder_tensor = Tensor::new(decoder_input_ids.as_slice(), &self.device)
                .map_err(|e| format!("创建解码器输入失败: {}", e))?
                .unsqueeze(0)
                .map_err(|e| format!("扩展维度失败: {}", e))?;

            // 前向传播 (需要 &mut self)
            let output = self.model
                .forward(&input_tensor, &decoder_tensor)
                .map_err(|e| format!("模型前向传播失败: {}", e))?;

            // 获取最后一个 token 的 logits
            let seq_len = output.dim(1).map_err(|e| format!("获取序列长度失败: {}", e))?;
            let last_logits = output
                .narrow(1, seq_len - 1, 1)
                .map_err(|e| format!("获取最后 logits 失败: {}", e))?
                .squeeze(1)
                .map_err(|e| format!("压缩维度失败: {}", e))?;

            // Greedy decoding: 取最大概率的 token
            let next_token = last_logits
                .argmax(1)
                .map_err(|e| format!("argmax 失败: {}", e))?
                .to_scalar::<u32>()
                .map_err(|e| format!("转换标量失败: {}", e))?;

            // 检查是否结束
            if next_token == eos_token_id {
                break;
            }

            decoder_input_ids.push(next_token);
        }

        // 解码输出
        let output_text = self.tokenizer
            .decode(&decoder_input_ids[1..], true) // 跳过开始 token
            .map_err(|e| format!("解码失败: {}", e))?;

        Ok(output_text)
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct TranslationProgress {
    pub status: String,
    pub progress: f32,
    pub message: String,
    pub current_file: Option<String>,
    pub current_file_progress: Option<f32>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct TranslationModelStatus {
    pub downloaded: bool,
    pub model_path: Option<String>,
    pub model_size: Option<u64>,
    pub model_version: Option<String>,
    pub files: Vec<ModelFileStatus>,
    pub ready: bool,
    pub loaded: bool,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ModelFileStatus {
    pub name: String,
    pub exists: bool,
    pub size: Option<u64>,
}

fn new_model_dir() -> PathBuf {
    let local_app_data = std::env::var("LOCALAPPDATA")
        .unwrap_or_else(|_| std::env::var("HOME").unwrap_or(".".to_string()));
    PathBuf::from(local_app_data)
        .join("cc-spec-tools")
        .join("models")
        .join("t5-small")
}

fn legacy_model_dir() -> PathBuf {
    let local_app_data = std::env::var("LOCALAPPDATA")
        .unwrap_or_else(|_| std::env::var("HOME").unwrap_or(".".to_string()));
    PathBuf::from(local_app_data)
        .join("cc-spec-viewer")
        .join("models")
        .join("t5-small")
}

fn get_model_dir() -> PathBuf {
    let new_dir = new_model_dir();
    let legacy_dir = legacy_model_dir();
    if !new_dir.exists() && legacy_dir.exists() {
        if std::fs::rename(&legacy_dir, &new_dir).is_err() {
            return legacy_dir;
        }
    }
    new_dir
}

fn get_model_file_path(filename: &str) -> PathBuf {
    get_model_dir().join(filename)
}

fn check_all_files_exist() -> bool {
    MODEL_FILES.iter().all(|(name, _)| {
        get_model_file_path(name).exists()
    })
}

fn get_total_downloaded_size() -> u64 {
    MODEL_FILES.iter()
        .map(|(name, _)| {
            let path = get_model_file_path(name);
            std::fs::metadata(&path).map(|m| m.len()).unwrap_or(0)
        })
        .sum()
}

/// 加载或获取模型实例
fn get_or_load_model() -> Result<Arc<Mutex<TranslationModel>>, String> {
    if let Some(model) = MODEL_INSTANCE.get() {
        return Ok(Arc::clone(model));
    }

    let model_dir = get_model_dir();
    if !check_all_files_exist() {
        return Err("模型文件不完整，请先下载模型".to_string());
    }

    let model = TranslationModel::new(&model_dir)?;
    let model = Arc::new(Mutex::new(model));

    // 尝试设置全局实例（可能被其他线程抢先）
    match MODEL_INSTANCE.set(Arc::clone(&model)) {
        Ok(()) => Ok(model),
        Err(_) => {
            // 其他线程已设置，使用已有的
            Ok(Arc::clone(MODEL_INSTANCE.get().unwrap()))
        }
    }
}

#[tauri::command]
pub async fn check_translation_model() -> Result<TranslationModelStatus, String> {
    let model_dir = get_model_dir();

    let files: Vec<ModelFileStatus> = MODEL_FILES.iter()
        .map(|(name, _)| {
            let path = get_model_file_path(name);
            let exists = path.exists();
            let size = if exists {
                std::fs::metadata(&path).ok().map(|m| m.len())
            } else {
                None
            };
            ModelFileStatus {
                name: name.to_string(),
                exists,
                size,
            }
        })
        .collect();

    let all_exist = files.iter().all(|f| f.exists);
    let total_size = get_total_downloaded_size();
    let loaded = MODEL_INSTANCE.get().is_some();

    Ok(TranslationModelStatus {
        downloaded: all_exist,
        model_path: if all_exist {
            Some(model_dir.to_string_lossy().to_string())
        } else {
            None
        },
        model_size: if total_size > 0 { Some(total_size) } else { None },
        model_version: if all_exist {
            Some("t5-small-v1".to_string())
        } else {
            None
        },
        files,
        ready: all_exist,
        loaded,
    })
}

#[tauri::command]
pub async fn download_translation_model(app_handle: tauri::AppHandle) -> Result<(), String> {
    let model_dir = get_model_dir();
    std::fs::create_dir_all(&model_dir)
        .map_err(|e| format!("创建模型目录失败: {}", e))?;

    let _ = app_handle.emit("translation.download.started", serde_json::json!({
        "total_files": MODEL_FILES.len(),
    }));

    let total_files = MODEL_FILES.len();

    for (index, (filename, mirror_url)) in MODEL_FILES.iter().enumerate() {
        let file_path = get_model_file_path(filename);

        if file_path.exists() {
            let _ = app_handle.emit("translation.download.progress", serde_json::json!({
                "progress": ((index + 1) as f32 / total_files as f32) * 100.0,
                "message": format!("{} 已存在，跳过", filename),
                "current_file": filename,
                "file_index": index + 1,
                "total_files": total_files,
            }));
            continue;
        }

        let _ = app_handle.emit("translation.download.progress", serde_json::json!({
            "progress": (index as f32 / total_files as f32) * 100.0,
            "message": format!("正在下载 {} ({}/{})", filename, index + 1, total_files),
            "current_file": filename,
            "file_index": index + 1,
            "total_files": total_files,
        }));

        let urls = vec![
            mirror_url.to_string(),
            format!("{}{}", OFFICIAL_URL_PREFIX, filename),
        ];

        let mut download_success = false;

        for (url_index, url) in urls.iter().enumerate() {
            let source_name = if url_index == 0 { "镜像" } else { "官方" };

            let result = tokio::task::spawn_blocking({
                let url = url.clone();
                let path = file_path.clone();
                move || {
                    std::process::Command::new("curl")
                        .args(["-L", "-o", path.to_str().unwrap(), &url])
                        .output()
                }
            })
            .await
            .map_err(|e| format!("下载任务失败: {}", e))?;

            if let Ok(output) = result {
                if output.status.success() && file_path.exists() {
                    let _ = app_handle.emit("translation.download.progress", serde_json::json!({
                        "progress": ((index + 1) as f32 / total_files as f32) * 100.0,
                        "message": format!("{} 下载成功 ({})", filename, source_name),
                        "current_file": filename,
                        "file_index": index + 1,
                        "total_files": total_files,
                    }));
                    download_success = true;
                    break;
                }
            }
        }

        if !download_success {
            let _ = app_handle.emit("translation.download.completed", serde_json::json!({
                "success": false,
                "error": format!("下载 {} 失败", filename),
            }));
            return Err(format!("下载 {} 失败", filename));
        }
    }

    let _ = app_handle.emit("translation.download.completed", serde_json::json!({
        "success": true,
        "path": model_dir.to_string_lossy().to_string(),
        "total_size": get_total_downloaded_size(),
    }));

    Ok(())
}

/// 预加载模型（可选，加速首次翻译）
#[tauri::command]
pub async fn preload_translation_model() -> Result<bool, String> {
    if MODEL_INSTANCE.get().is_some() {
        return Ok(true); // 已加载
    }

    // 在后台线程加载模型
    tokio::task::spawn_blocking(|| {
        get_or_load_model()
    })
    .await
    .map_err(|e| format!("加载任务失败: {}", e))?
    .map(|_| true)
}

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

    // 检查模型是否完整
    if !check_all_files_exist() {
        return Err("翻译模型未完整下载。请先在设置中下载模型。".to_string());
    }

    // 在后台线程执行翻译（避免阻塞 async runtime）
    let text_clone = text.clone();
    let result = tokio::task::spawn_blocking(move || {
        let model_arc = get_or_load_model()?;
        let mut model = model_arc.lock().map_err(|e| format!("获取模型锁失败: {}", e))?;
        model.translate(&text_clone)
    })
    .await
    .map_err(|e| format!("翻译任务失败: {}", e))??;

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

#[tauri::command]
pub async fn clear_translation_cache() -> Result<(), String> {
    let mut cache = TRANSLATION_CACHE.lock().unwrap();
    *cache = None;
    Ok(())
}

#[tauri::command]
pub async fn delete_translation_model() -> Result<(), String> {
    let model_dir = get_model_dir();
    if model_dir.exists() {
        std::fs::remove_dir_all(&model_dir)
            .map_err(|e| format!("删除模型目录失败: {}", e))?;
    }
    let mut cache = TRANSLATION_CACHE.lock().unwrap();
    *cache = None;
    // 注意：无法卸载已加载的模型（OnceCell 限制），需要重启应用
    Ok(())
}

#[tauri::command]
pub async fn get_translation_cache_stats() -> Result<serde_json::Value, String> {
    let cache = TRANSLATION_CACHE.lock().unwrap();
    let count = cache.as_ref().map(|m| m.len()).unwrap_or(0);
    Ok(serde_json::json!({
        "cached_count": count,
        "model_ready": check_all_files_exist(),
        "model_loaded": MODEL_INSTANCE.get().is_some(),
    }))
}
