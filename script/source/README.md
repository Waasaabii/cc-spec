# 环境配置脚本

本目录包含用于配置开发环境的实用脚本，主要针对国内用户提供更快的下载速度。

## 脚本说明

### 1. apt_source.sh - Ubuntu APT 源切换
自动切换 Ubuntu 系统的 APT 源到国内镜像源。

**支持的镜像源：**
- 阿里云 mirrors.aliyun.com
- 中科大 mirrors.ustc.edu.cn
- 163 mirrors.163.com
- 清华大学 mirrors.tuna.tsinghua.edu.cn
- 浙江大学 mirrors.zju.edu.cn
- 腾讯云 mirrors.cloud.tencent.com
- 华为云 mirrors.huaweicloud.com
- Ubuntu 官方源
- NVIDIA CUDA 官方源

**使用方法：**
```bash
sudo bash apt_source.sh
```

### 2. conda_source.sh - Conda 源切换
配置 Conda 包管理器的国内镜像源。

**支持的镜像源：**
- 清华大学 TUNA 镜像
- 上海交通大学镜像
- 北京外国语大学镜像
- 南京大学镜像
- 其他高校镜像

**使用方法：**
```bash
bash conda_source.sh
```

### 3. pip_source.sh - Pip 源切换
配置 Python pip 的国内镜像源。

**支持的镜像源：**
- 阿里云 PyPI 镜像
- 中科大 PyPI 镜像
- 豆瓣 PyPI 镜像
- 清华大学 PyPI 镜像
- 腾讯云 PyPI 镜像
- 浙江大学 PyPI 镜像
- 163 PyPI 镜像

**使用方法：**
```bash
bash pip_source.sh
```

### 4. hfd_source.sh - Hugging Face 下载工具
强大的 Hugging Face 模型和数据集下载工具，支持多线程下载和国内镜像。

**特性：**
- 使用 aria2c 多线程下载
- 支持文件过滤（包含/排除模式）
- 支持 HF 认证
- 自动使用国内镜像 (hf-mirror.com)
- 支持指定 revision 和本地目录

**安装依赖：**
```bash
pip install -U huggingface_hub
sudo apt update && sudo apt install -y aria2
```

**使用示例：**
```bash
# 下载 GPT-2 模型
./hfd_source.sh gpt2

# 下载 Llama-2 模型（需要认证）
./hfd_source.sh meta-llama/Llama-2-7b --hf_username myuser --hf_token mytoken -x 4

# 下载数据集
./hfd_source.sh lavita/medical-qa-shared-task-v1-toy --dataset

# 排除特定文件
./hfd_source.sh bigscience/bloom-560m --exclude *.safetensors

# 指定本地目录和 revision
./hfd_source.sh bartowski/Phi-3.5-mini-instruct-exl2 --local-dir ./models --revision 5_0
```

**参数说明：**
- `--include`: 包含文件模式
- `--exclude`: 排除文件模式
- `--tool`: 下载工具（aria2c 或 wget）
- `-x`: aria2c 线程数（默认 4）
- `-j`: 并发下载数（默认 5）
- `--dataset`: 下载标志（数据集）
- `--local-dir`: 本地存储路径
- `--revision`: 模型/数据集版本
- `--hf_username`: HF 用户名
- `--hf_token`: HF 访问令牌

## 注意事项

1. 运行 APT 源切换脚本需要 sudo 权限
2. HFD 工具需要先安装 huggingface_hub 和 aria2c
3. 脚本会自动备份原始配置文件
4. 国内镜像源提供更快的下载速度，但可能有同步延迟