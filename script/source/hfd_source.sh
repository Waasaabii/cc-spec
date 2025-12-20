#!/bin/bash
# Color definitions
#sudo apt update
#sudo apt install -y aria2
#bash /mnt/data_public/script/check_dependencies.sh 

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # 无颜色

# 检测函数：检查命令是否存在
command_exists() {
    command -v "$1" &>/dev/null
}

# 检测函数：检查Python包是否安装
python_package_exists() {
    python3 -c "import $1" &>/dev/null || python -c "import $1" &>/dev/null
}

# 主程序
printf "${YELLOW}开始依赖检测...${NC}\n\n"

# 检测huggingface_hub Python依赖
printf "检测huggingface_hub依赖... "
if python_package_exists "huggingface_hub"; then
    # 检查是否为最新版本（可选）
    printf "${GREEN}已安装${NC}\n"
else
    printf "${RED}未安装${NC}\n"
    printf "  请执行以下命令安装：\n"
    printf "  ${GREEN}pip install -U huggingface_hub${NC}\n"
    printf "  \n"
    printf "  如按装速度缓慢，请执行以下命令更换源：\n"
    printf "  ${GREEN}pip_source${NC}\n"
    # 标记依赖缺失
    DEPENDENCY_MISSING=1
fi

# 检测aria2工具
printf "\n检测aria2工具... "
if command_exists "aria2c"; then
    # 显示版本信息（可选）
    ARIA2_VERSION=$(aria2c --version | head -n1 | awk '{print $3}')
    printf "${GREEN}已安装 (版本: $ARIA2_VERSION)${NC}\n"
else
    printf "${RED}未安装${NC}\n"
    printf "  请执行以下命令安装：\n"
    printf "  ${GREEN}sudo apt update && sudo apt install -y aria2${NC}\n"
    # 标记工具缺失
    TOOL_MISSING=1
fi

# 最终检测结果
printf "\n${YELLOW}检测完成${NC}\n"
if [[ -z $DEPENDENCY_MISSING && -z $TOOL_MISSING ]]; then
    printf "${GREEN}所有必要依赖和工具均已安装，可正常使用。${NC}\n"
else
    printf "${RED}存在未安装的依赖或工具，请根据上述提示安装后再试。${NC}\n"
    exit 1
fi
# 映射地址
export HF_ENDPOINT=https://hf-mirror.com



# 限速设置
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m' # No Color

trap 'printf "${YELLOW}\nDownload interrupted. You can resume by re-running the command.\n${NC}"; exit 1' INT

display_help() {
    cat << EOF
Usage:
  hfd_source <REPO_ID> [--include include_pattern1 include_pattern2 ...] [--exclude exclude_pattern1 exclude_pattern2 ...] [--hf_username username] [--hf_token token] [--tool aria2c|wget] [-x threads] [-j jobs] [--dataset] [--local-dir path] [--revision rev]
Description:
  Downloads a model or dataset from Hugging Face using the provided repo ID.
Arguments:
  REPO_ID         The Hugging Face repo ID (Required)
                  Format: 'org_name/repo_name' or legacy format (e.g., gpt2)
Options:
  include/exclude_pattern The patterns to match against file path, supports wildcard characters.
                  e.g., '--exclude *.safetensor *.md', '--include vae/*'.
  --include       (Optional) Patterns to include files for downloading (supports multiple patterns).
  --exclude       (Optional) Patterns to exclude files from downloading (supports multiple patterns).
  --hf_username   (Optional) Hugging Face username for authentication (not email).
  --hf_token      (Optional) Hugging Face token for authentication.
  --tool          (Optional) Download tool to use: aria2c (default) or wget.
  -x              (Optional) Number of download threads for aria2c (default: 4).
  -j              (Optional) Number of concurrent downloads for aria2c (default: 5).
  --dataset       (Optional) Flag to indicate downloading a dataset.
  --local-dir     (Optional) Directory path to store the downloaded data.
                             Defaults to the current directory with a subdirectory named 'repo_name'
                             if REPO_ID is is composed of 'org_name/repo_name'.
  --revision      (Optional) Model/Dataset revision to download (default: main).
Example:
  hfd_source gpt2
  hfd_source bigscience/bloom-560m --exclude *.safetensors
  hfd_source meta-llama/Llama-2-7b --hf_username myuser --hf_token mytoken -x 4
  hfd_source lavita/medical-qa-shared-task-v1-toy --dataset
  hfd_source bartowski/Phi-3.5-mini-instruct-exl2 --revision 5_0
EOF
    exit 1
}

[[ -z "$1" || "$1" =~ ^-h || "$1" =~ ^--help ]] && display_help

REPO_ID=$1
shift

# Default values
TOOL="aria2c"
THREADS=4
CONCURRENT=5
HF_ENDPOINT=${HF_ENDPOINT:-"https://huggingface.co"}
INCLUDE_PATTERNS=()
EXCLUDE_PATTERNS=()
REVISION="main"

# 新增：时间区间限速默认参数
DAY_START=8          # 白天起始小时（默认8:00）
DAY_END=22           # 白天结束小时（默认20:00）
DAY_LIMIT="1M"       # 白天限速（默认1MB/s）
NIGHT_LIMIT="3M"     # 夜间限速（默认5MB/s）

# 新增：验证小时参数（0-23）
validate_hour() {
    [[ "$2" =~ ^[0-2]?[0-9]$ && "$2" -ge 0 && "$2" -le 23 ]] || { 
        printf "${RED}[Error] $1 must be an integer between 0 and 23${NC}\n"; exit 1; 
    }
}

# 原有：验证数字参数
validate_number() {
    [[ "$2" =~ ^[1-9][0-9]*$ && "$2" -le "$3" ]] || { 
        printf "${RED}[Error] $1 must be 1-$3${NC}\n"; exit 1; 
    }
}

# 新增：验证限速值格式（支持 K/M 单位）
validate_speed() {
    [[ "$2" =~ ^[0-9]+[KM]$ ]] || { 
        printf "${RED}[Error] $1 must be in format <number>[K|M] (e.g., 500K, 2M)${NC}\n"; exit 1; 
    }
}

# Argument parsing (新增时间和限速参数解析)
while [[ $# -gt 0 ]]; do
    case $1 in
        --include) shift; while [[ $# -gt 0 && ! ($1 =~ ^--) && ! ($1 =~ ^-[^-]) ]]; do INCLUDE_PATTERNS+=("$1"); shift; done ;;
        --exclude) shift; while [[ $# -gt 0 && ! ($1 =~ ^--) && ! ($1 =~ ^-[^-]) ]]; do EXCLUDE_PATTERNS+=("$1"); shift; done ;;
        --hf_username) HF_USERNAME="$2"; shift 2 ;;
        --hf_token) HF_TOKEN="$2"; shift 2 ;;
        --tool)
            case $2 in
                aria2c|wget) TOOL="$2" ;;
                *) printf "%b[Error] Invalid tool. Use 'aria2c' or 'wget'.%b\n" "$RED" "$NC"; exit 1 ;;
            esac
            shift 2 ;;
        -x) validate_number "threads (-x)" "$2" 10; THREADS="$2"; shift 2 ;;
        -j) validate_number "concurrent downloads (-j)" "$2" 10; CONCURRENT="$2"; shift 2 ;;
        --dataset) DATASET=1; shift ;;
        --local-dir) LOCAL_DIR="$2"; shift 2 ;;
        --revision) REVISION="$2"; shift 2 ;;
        # 新增：时间区间参数
        --day-start) validate_hour "day start hour (--day-start)" "$2"; DAY_START="$2"; shift 2 ;;
        --day-end) validate_hour "day end hour (--day-end)" "$2"; DAY_END="$2"; shift 2 ;;
        # 新增：限速值参数
        --day-limit) validate_speed "day speed limit (--day-limit)" "$2"; DAY_LIMIT="$2"; shift 2 ;;
        --night-limit) validate_speed "night speed limit (--night-limit)" "$2"; NIGHT_LIMIT="$2"; shift 2 ;;
        *) display_help ;;
    esac
done

# 新增：检查时间区间有效性（确保 day_start < day_end）
if [[ "$DAY_START" -ge "$DAY_END" ]]; then
    printf "${RED}[Error] --day-start must be less than --day-end (e.g., --day-start 8 --day-end 20)${NC}\n"
    exit 1
fi

# 新增：获取当前时间并判断限速区间
current_hour=$(date +%H)                  # 获取当前小时（00-23）
current_hour=$((10#$current_hour))        # 转换为整数（处理前导零，如 08 → 8）
# 确定当前限速值
if [[ $current_hour -ge $DAY_START && $current_hour -lt $DAY_END ]]; then
    CURRENT_LIMIT="$DAY_LIMIT"
#    printf "%b[Time-based Limit] Current time is DAY ($DAY_START:00-$DAY_END:00), speed limit: $CURRENT_LIMIT%b\n" "$YELLOW" "$NC"
else
    CURRENT_LIMIT="$NIGHT_LIMIT"
#   printf "%b[Time-based Limit] Current time is NIGHT ($DAY_END:00-次日$DAY_START:00), speed limit: $CURRENT_LIMIT%b\n" "$YELLOW" "$NC"
fi

# Generate current command string (原有逻辑保留)
generate_command_string() {
    local cmd_string="REPO_ID=$REPO_ID"
    cmd_string+=" TOOL=$TOOL"
    cmd_string+=" INCLUDE_PATTERNS=${INCLUDE_PATTERNS[*]}"
    cmd_string+=" EXCLUDE_PATTERNS=${EXCLUDE_PATTERNS[*]}"
    cmd_string+=" DATASET=${DATASET:-0}"
    cmd_string+=" HF_USERNAME=${HF_USERNAME:-}"
    cmd_string+=" HF_TOKEN=${HF_TOKEN:-}"
    cmd_string+=" HF_TOKEN=${HF_ENDPOINT:-}"
    cmd_string+=" REVISION=$REVISION"
    # 新增：将时间限速参数加入命令字符串（用于缓存判断）
    cmd_string+=" DAY_START=$DAY_START DAY_END=$DAY_END DAY_LIMIT=$DAY_LIMIT NIGHT_LIMIT=$NIGHT_LIMIT"
    echo "$cmd_string"
}

# Check if aria2, wget, curl are installed (原有逻辑保留)
check_command() {
    if ! command -v $1 &>/dev/null; then
        printf "%b%s is not installed. Please install it first.%b\n" "$RED" "$1" "$NC"
        exit 1
    fi
}

check_command curl; check_command "$TOOL"

LOCAL_DIR="${LOCAL_DIR:-${REPO_ID#*/}}"
mkdir -p "$LOCAL_DIR/.hfd"

if [[ "$DATASET" == 1 ]]; then
    METADATA_API_PATH="datasets/$REPO_ID"
    DOWNLOAD_API_PATH="datasets/$REPO_ID"
    CUT_DIRS=5
else
    METADATA_API_PATH="models/$REPO_ID"
    DOWNLOAD_API_PATH="$REPO_ID"
    CUT_DIRS=4
fi

if [[ "$REVISION" != "main" ]]; then
    METADATA_API_PATH="$METADATA_API_PATH/revision/$REVISION"
fi
API_URL="$HF_ENDPOINT/api/$METADATA_API_PATH"

METADATA_FILE="$LOCAL_DIR/.hfd/repo_metadata.json"

# Fetch and save metadata (原有逻辑保留)
fetch_and_save_metadata() {
    status_code=$(curl -L -s -w "%{http_code}" -o "$METADATA_FILE" ${HF_TOKEN:+-H "Authorization: Bearer $HF_TOKEN"} "$API_URL")
    RESPONSE=$(cat "$METADATA_FILE")
    if [ "$status_code" -eq 200 ]; then
        printf "%s\n" "$RESPONSE"
    else
        printf "%b[Error] Failed to fetch metadata from $API_URL. HTTP status code: $status_code.%b\n$RESPONSE\n" "${RED}" "${NC}" >&2
        rm $METADATA_FILE
        exit 1
    fi
}

check_authentication() {
    local response="$1"
    if command -v jq &>/dev/null; then
        local gated
        gated=$(echo "$response" | jq -r '.gated // false')
        if [[ "$gated" != "false" && ( -z "$HF_TOKEN" || -z "$HF_USERNAME" ) ]]; then
            printf "${RED}The repository requires authentication, but --hf_username and --hf_token is not passed. Please get token from https://huggingface.co/settings/tokens.\nExiting.\n${NC}"
            exit 1
        fi
    else
        if echo "$response" | grep -q '"gated":[^f]' && [[ -z "$HF_TOKEN" || -z "$HF_USERNAME" ]]; then
            printf "${RED}The repository requires authentication, but --hf_username and --hf_token is not passed. Please get token from https://huggingface.co/settings/tokens.\nExiting.\n${NC}"
            exit 1
        fi
    fi
}

if [[ ! -f "$METADATA_FILE" ]]; then
    printf "%bFetching repo metadata...%b\n" "$YELLOW" "$NC"
    RESPONSE=$(fetch_and_save_metadata) || exit 1
    check_authentication "$RESPONSE"
else
    printf "%bUsing cached metadata: $METADATA_FILE%b\n" "$GREEN" "$NC"
    RESPONSE=$(cat "$METADATA_FILE")
    check_authentication "$RESPONSE"
fi

should_regenerate_filelist() {
    local command_file="$LOCAL_DIR/.hfd/last_download_command"
    local current_command=$(generate_command_string)
    
    if [[ ! -f "$LOCAL_DIR/$fileslist_file" ]]; then
        echo "$current_command" > "$command_file"
        return 0
    fi
    
    if [[ ! -f "$command_file" ]]; then
        echo "$current_command" > "$command_file"
        return 0
    fi
    
    local saved_command=$(cat "$command_file")
    if [[ "$current_command" != "$saved_command" ]]; then
        echo "$current_command" > "$command_file"
        return 0
    fi
    
    return 1
}

fileslist_file=".hfd/${TOOL}_urls.txt"

if should_regenerate_filelist; then
    [[ -f "$LOCAL_DIR/$fileslist_file" ]] && rm "$LOCAL_DIR/$fileslist_file"
    
    printf "%bGenerating file list...%b\n" "$YELLOW" "$NC"
    
    INCLUDE_REGEX=""
    EXCLUDE_REGEX=""
    if ((${#INCLUDE_PATTERNS[@]})); then
        INCLUDE_REGEX=$(printf '%s\n' "${INCLUDE_PATTERNS[@]}" | sed 's/\./\\./g; s/\*/.*/g' | paste -sd '|' -)
    fi
    if ((${#EXCLUDE_PATTERNS[@]})); then
        EXCLUDE_REGEX=$(printf '%s\n' "${EXCLUDE_PATTERNS[@]}" | sed 's/\./\\./g; s/\*/.*/g' | paste -sd '|' -)
    fi

    if command -v jq &>/dev/null; then
        process_with_jq() {
            if [[ "$TOOL" == "aria2c" ]]; then
                printf "%s" "$RESPONSE" | jq -r \
                    --arg endpoint "$HF_ENDPOINT" \
                    --arg repo_id "$DOWNLOAD_API_PATH" \
                    --arg token "$HF_TOKEN" \
                    --arg include_regex "$INCLUDE_REGEX" \
                    --arg exclude_regex "$EXCLUDE_REGEX" \
                    --arg revision "$REVISION" \
                    '
                    .siblings[]
                    | select(
                        .rfilename != null
                        and ($include_regex == "" or (.rfilename | test($include_regex)))
                        and ($exclude_regex == "" or (.rfilename | test($exclude_regex) | not))
                      )
                    | [
                        ($endpoint + "/" + $repo_id + "/resolve/" + $revision + "/" + .rfilename),
                        " dir=" + (.rfilename | split("/")[:-1] | join("/")),
                        " out=" + (.rfilename | split("/")[-1]),
                        if $token != "" then " header=Authorization: Bearer " + $token else empty end,
                        ""
                      ]
                    | join("\n")
                    '
            else
                printf "%s" "$RESPONSE" | jq -r \
                    --arg endpoint "$HF_ENDPOINT" \
                    --arg repo_id "$DOWNLOAD_API_PATH" \
                    --arg include_regex "$INCLUDE_REGEX" \
                    --arg exclude_regex "$EXCLUDE_REGEX" \
                    --arg revision "$REVISION" \
                    '
                    .siblings[]
                    | select(
                        .rfilename != null
                        and ($include_regex == "" or (.rfilename | test($include_regex)))
                        and ($exclude_regex == "" or (.rfilename | test($exclude_regex) | not))
                      )
                    | ($endpoint + "/" + $repo_id + "/resolve/" + $revision + "/" + .rfilename)
                    '
            fi
        }
        result=$(process_with_jq)
        printf "%s\n" "$result" > "$LOCAL_DIR/$fileslist_file"
    else
        printf "%b[Warning] jq not installed, using grep/awk for metadata json parsing (slower). Consider installing jq for better parsing performance.%b\n" "$YELLOW" "$NC"
        process_with_grep_awk() {
            local include_pattern=""
            local exclude_pattern=""
            local output=""
            
	    if ((${#INCLUDE_PATTERNS[@]})); then
                include_pattern=$(printf '%s\n' "${INCLUDE_PATTERNS[@]}" | sed 's/\./\\./g; s/\*/.*/g' | paste -sd '|' -)
            fi
            if ((${#EXCLUDE_PATTERNS[@]})); then
                exclude_pattern=$(printf '%s\n' "${EXCLUDE_PATTERNS[@]}" | sed 's/\./\\./g; s/\*/.*/g' | paste -sd '|' -)
            fi

            local files=$(printf '%s' "$RESPONSE" | grep -o '"rfilename":"[^"]*"' | awk -F'"' '{print $4}')
            
            if [[ -n "$include_pattern" ]]; then
                files=$(printf '%s\n' "$files" | grep -E "$include_pattern")
            fi
            if [[ -n "$exclude_pattern" ]]; then
                files=$(printf '%s\n' "$files" | grep -vE "$exclude_pattern")
            fi

            while IFS= read -r file; do
                if [[ -n "$file" ]]; then
                    if [[ "$TOOL" == "aria2c" ]]; then
                        output+="$HF_ENDPOINT/$DOWNLOAD_API_PATH/resolve/$REVISION/$file"$'\n'
                        output+=" dir=$(dirname "$file")"$'\n'
                        output+=" out=$(basename "$file")"$'\n'
                        [[ -n "$HF_TOKEN" ]] && output+=" header=Authorization: Bearer $HF_TOKEN"$'\n'
                        output+=$'\n'
                    else
                        output+="$HF_ENDPOINT/$DOWNLOAD_API_PATH/resolve/$REVISION/$file"$'\n'
                    fi
                fi
            done <<< "$files"

            printf '%s' "$output"
        }

        result=$(process_with_grep_awk)
        printf "%s\n" "$result" > "$LOCAL_DIR/$fileslist_file"
    fi
else
    printf "%bResume from file list: $LOCAL_DIR/$fileslist_file%b\n" "$GREEN" "$NC"
fi

# Perform download (核心修改：添加限速参数)
printf "${YELLOW}Starting download with $TOOL to $LOCAL_DIR...\n${NC}"

cd "$LOCAL_DIR"
if [[ "$TOOL" == "aria2c" ]]; then
    # 新增：添加 --max-download-limit 参数应用当前限速
    aria2c --console-log-level=error --file-allocation=none \
           -x "$THREADS" -j "$CONCURRENT" -s "$THREADS" -k 1M -c \
           -i "$fileslist_file" --save-session="$fileslist_file" \
           --max-download-limit="$CURRENT_LIMIT"  # 时间动态限速参数
elif [[ "$TOOL" == "wget" ]]; then
    # 新增：添加 --limit-rate 参数应用当前限速
    wget -x -nH --cut-dirs="$CUT_DIRS" \
         ${HF_TOKEN:+--header="Authorization: Bearer $HF_TOKEN"} \
         --input-file="$fileslist_file" --continue \
         --limit-rate="$CURRENT_LIMIT"  # 时间动态限速参数
fi

if [[ $? -eq 0 ]]; then
    printf "${GREEN}Download completed successfully. Repo directory: $PWD\n${NC}"
else
    printf "${RED}Download encountered errors.\n${NC}"
    exit 1
fi
