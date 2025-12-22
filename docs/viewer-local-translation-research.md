# cc-spec-viewer 本地翻译功能调研报告

> 调研日期: 2024-12-22
> 调研目标: 评估在 cc-spec-viewer 中嵌入本地小模型进行翻译的可行性

## 1. 需求概述

在 cc-spec-viewer (Tauri 桌面应用) 中集成本地翻译功能，要求：

- 使用 Candle (HuggingFace Rust ML 框架) 作为推理引擎
- 从 HuggingFace 动态查询和筛选翻译模型
- 默认推荐占用最小的合适模型
- 使用 `hfd_source.sh` 脚本加速模型下载（hf-mirror.com 镜像）

## 2. HuggingFace API 调研

### 2.1 API 可用性

| 能力 | 状态 | 说明 |
|------|------|------|
| 查询翻译模型列表 | ✅ 可用 | `?filter=translation` 参数 |
| 筛选 safetensors 格式 | ✅ 可用 | `?filter=safetensors` 参数 |
| 获取模型文件大小 | ✅ 可用 | 通过 `siblings` 字段获取 |
| 按下载量排序 | ✅ 可用 | `?sort=downloads` 参数 |
| 按文件大小排序 | ⚠️ 需客户端实现 | API 不直接支持 |

### 2.2 API 端点

**查询翻译模型列表：**
```
GET https://huggingface.co/api/models?filter=translation&filter=safetensors&sort=downloads&limit=30
```

**获取模型详情（含文件大小）：**
```
GET https://huggingface.co/api/models/{model_id}?expand[]=siblings
```

### 2.3 返回数据结构

```json
{
  "modelId": "google-t5/t5-small",
  "id": "google-t5/t5-small",
  "downloads": 2602781,
  "likes": 521,
  "tags": ["safetensors", "translation", "en", "fr", "de", ...],
  "pipeline_tag": "translation",
  "library_name": "transformers",
  "siblings": [
    {
      "rfilename": "model.safetensors",
      "size": 253755680
    },
    ...
  ]
}
```

### 2.4 筛选条件设计

| 条件 | 参数/逻辑 | 说明 |
|------|-----------|------|
| 任务类型 | `filter=translation` | 翻译任务模型 |
| 文件格式 | `filter=safetensors` | Candle 原生支持 |
| 模型大小 | 客户端筛选 `< 500MB` | 通过 siblings 计算 |
| 语言支持 | 客户端筛选 tags | 检查 zh/en 标签 |

## 3. Candle 框架调研

### 3.1 框架概述

[Candle](https://github.com/huggingface/candle) 是 HuggingFace 官方的 Rust ML 框架，核心特点：

- 纯 Rust 实现，无 Python 依赖
- 支持 CPU/CUDA/Metal 加速
- 原生支持 safetensors 格式
- 适合嵌入到桌面应用

### 3.2 支持的翻译模型

| 模型类型 | 支持状态 | 说明 |
|----------|----------|------|
| T5 系列 | ✅ 官方支持 | 包括 t5-small/base/large |
| Marian MT | ✅ 官方支持 | Helsinki-NLP 系列 |
| MADLAD400 | ✅ 官方支持 | 400+ 语言翻译 |

### 3.3 支持的模型格式

| 格式 | 支持状态 | 推荐度 |
|------|----------|--------|
| safetensors | ✅ 原生支持 | ⭐⭐⭐ 推荐 |
| GGUF | ✅ 支持 | ⭐⭐ 量化模型 |
| PyTorch (.bin) | ⚠️ 需转换 | ⭐ |

## 4. 翻译模型对比

### 4.1 支持 safetensors 的翻译模型（按大小排序）

| 模型 | safetensors 大小 | 下载量 | 语言支持 | Candle 支持 |
|------|------------------|--------|----------|-------------|
| **google-t5/t5-small** | **242 MB** | 2.6M | 多语言 | ✅ 官方 |
| google-t5/t5-base | ~850 MB | 2.1M | 多语言 | ✅ 官方 |
| alirezamsh/small100 | 1.33 GB | 4K | 101种语言 | ⚠️ 需验证 |
| facebook/mbart-large-50 | ~2.3 GB | 365K | 50种语言 | ⚠️ 需验证 |

### 4.2 推荐模型

**默认推荐：`google-t5/t5-small`**

- 大小：242 MB（最小）
- Candle 官方支持
- 下载量最高（2.6M）
- 支持多语言翻译任务

## 5. 技术实现方案

### 5.1 架构设计

```
┌─────────────────────────────────────────────────────────┐
│  cc-spec-viewer (Tauri)                                 │
├─────────────────────────────────────────────────────────┤
│  前端 (React/TypeScript)                                │
│  ├─ 设置页面                                            │
│  │   ├─ 翻译开关                                        │
│  │   ├─ 模型列表（从 HuggingFace 动态获取）             │
│  │   └─ 下载进度                                        │
│  └─ 翻译按钮（内容区域）                                │
├─────────────────────────────────────────────────────────┤
│  后端 (Rust/Tauri)                                      │
│  ├─ HuggingFace API 客户端                              │
│  │   ├─ 查询模型列表                                    │
│  │   └─ 筛选 & 排序                                     │
│  ├─ 模型下载器                                          │
│  │   └─ 调用 hfd_source.sh                              │
│  └─ Candle 推理引擎                                     │
│       └─ T5/MarianMT 翻译                               │
└─────────────────────────────────────────────────────────┘
```

### 5.2 模型筛选流程

```
1. 调用 HuggingFace API
   GET /api/models?filter=translation&filter=safetensors

2. 获取每个模型的 siblings（文件列表）
   GET /api/models/{id}?expand[]=siblings

3. 计算 safetensors 文件大小
   sum(siblings.filter(f => f.rfilename.endsWith('.safetensors')).size)

4. 按大小升序排序
   models.sort((a, b) => a.size - b.size)

5. 默认推荐最小的模型
   recommended = models[0]
```

### 5.3 模型下载流程

```bash
# 使用 hfd_source.sh 下载（hf-mirror.com 加速）
hfd_source google-t5/t5-small \
  --include "*.safetensors" "*.json" "spiece.model" \
  --local-dir ~/.cc-spec/models/t5-small
```

### 5.4 Tauri 命令设计

```rust
// 查询可用模型
#[tauri::command]
async fn list_translation_models(
    max_size_mb: Option<u32>,  // 默认 500MB
) -> Result<Vec<TranslationModel>, String>

// 下载模型
#[tauri::command]
async fn download_model(
    model_id: String,
) -> Result<DownloadProgress, String>

// 翻译文本
#[tauri::command]
async fn translate(
    text: String,
    source_lang: String,
    target_lang: String,
) -> Result<String, String>
```

## 6. 依赖项

### 6.1 Rust 依赖 (Cargo.toml)

```toml
[dependencies]
candle-core = "0.8"
candle-nn = "0.8"
candle-transformers = "0.8"
hf-hub = "0.3"  # HuggingFace Hub 客户端
tokenizers = "0.20"
```

### 6.2 外部依赖

- `hfd_source.sh` - 模型下载脚本（已存在于 `scripts/source/`）
- `aria2c` - 多线程下载工具

## 7. 风险与挑战

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 模型文件较大 | 首次下载耗时 | 使用镜像加速、显示进度 |
| Candle 模型兼容性 | 部分模型不支持 | 只推荐官方支持的模型 |
| 推理速度 | CPU 推理较慢 | 支持 GPU 加速（可选） |
| 内存占用 | 加载模型占用内存 | 按需加载、支持卸载 |

## 8. 结论

**可行性评估：✅ 完全可行**

### 8.1 技术可行性

- HuggingFace API 完全满足动态查询和筛选需求
- Candle 官方支持 T5 翻译模型
- `hfd_source.sh` 可用于加速下载

### 8.2 推荐实现路径

1. **Phase 1**: 设置页面 UI（模型列表、下载、开关）
2. **Phase 2**: HuggingFace API 集成（查询、筛选、排序）
3. **Phase 3**: 模型下载功能（调用 hfd_source.sh）
4. **Phase 4**: Candle 推理集成（T5 翻译）

### 8.3 默认配置

- **推荐模型**: `google-t5/t5-small` (242 MB)
- **最大模型限制**: 500 MB
- **默认状态**: 翻译功能关闭（可选开启）

## 参考资料

- [HuggingFace Hub API](https://huggingface.co/docs/hub/api)
- [Candle GitHub](https://github.com/huggingface/candle)
- [Candle Documentation](https://huggingface.github.io/candle/)
- [HuggingFace Models - Translation](https://huggingface.co/models?filter=translation)
- [How to get model size - HF Forums](https://discuss.huggingface.co/t/how-to-get-model-size/11038)
