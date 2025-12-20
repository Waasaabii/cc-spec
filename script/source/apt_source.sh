#!/bin/bash

set -e

. /etc/os-release

SOURCE="/etc/apt/sources.list"

# 备份源文件
if [ ! -f "${SOURCE}_bk" ] ; then
    cp "${SOURCE}" "${SOURCE}_bk"
fi

echo "请选择您要切换的源的数字编号, 然后按回车"
echo "(0) 阿里云(aliyun)"
echo "(1) 中国科技大学(ustc)"
echo "(2) 163源(163)"
echo "(3) 清华大学(tsinghua)"
echo "(4) 浙江大学(zju)"
echo "(5) 腾讯云(tencent)"
echo "(6) 华为云(huawei)"
echo "(7) 官方源(ubuntu)"
echo "(8) CUDA官方源(nvidia)"
echo "取消输入: Ctrl + C"

read -p "请输入编号: " index

if [ "${index}" -lt 0 ] || [ "${index}" -gt 8 ]; then
    echo "请输入有效的源编号 (0-8)"
    exit 1
fi

# 清空现有源文件
> "${SOURCE}"

case "${index}" in
    0)
        echo "切换到阿里云镜像源"
        MIRROR="http://mirrors.aliyun.com/ubuntu"
        ;;
    1)
        echo "切换到中国科技大学镜像源"
        MIRROR="https://mirrors.ustc.edu.cn/ubuntu"
        ;;
    2)
        echo "切换到163镜像源"
        MIRROR="http://mirrors.163.com/ubuntu"
        ;;
    3)
        echo "切换到清华大学镜像源"
        MIRROR="https://mirrors.tuna.tsinghua.edu.cn/ubuntu"
        ;;
    4)
        echo "切换到浙江大学镜像源"
        MIRROR="http://mirrors.zju.edu.cn/ubuntu"
        ;;
    5)
        echo "切换到腾讯云镜像源"
        MIRROR="http://mirrors.cloud.tencent.com/ubuntu"
        ;;
    6)
        echo "切换到华为云镜像源"
        MIRROR="https://repo.huaweicloud.com/ubuntu"
        ;;
    7)
        echo "切换到官方镜像源"
        MIRROR="http://archive.ubuntu.com/ubuntu"
        ;;
    8)
        echo "切换CUDA到官方镜像源"
        echo "配置 CUDA 源中..."
        CUDA_SOURCE="/etc/apt/sources.list.d/cuda.list"

        # 添加 CUDA 源，动态获取版本号
        echo "deb https://developer.download.nvidia.com/compute/cuda/repos/ubuntu${VERSION_ID//./}/x86_64/ /" > "${CUDA_SOURCE}"

        # 添加公钥
        wget -q https://developer.download.nvidia.com/compute/cuda/repos/ubuntu${VERSION_ID//./}/x86_64/3bf863cc.pub -O /tmp/3bf863cc.pub
        apt-key add /tmp/3bf863cc.pub

        # 更新 apt 缓存
        apt update
        echo "CUDA 源配置完成"
        exit 1
        ;;
esac

# 写入镜像源内容
cat <<EOF > "${SOURCE}"
deb ${MIRROR} ${VERSION_CODENAME} main restricted universe multiverse
deb ${MIRROR} ${VERSION_CODENAME}-security main restricted universe multiverse
deb ${MIRROR} ${VERSION_CODENAME}-updates main restricted universe multiverse
deb ${MIRROR} ${VERSION_CODENAME}-backports main restricted universe multiverse
deb-src ${MIRROR} ${VERSION_CODENAME} main restricted universe multiverse
deb-src ${MIRROR} ${VERSION_CODENAME}-security main restricted universe multiverse
deb-src ${MIRROR} ${VERSION_CODENAME}-updates main restricted universe multiverse
deb-src ${MIRROR} ${VERSION_CODENAME}-backports main restricted universe multiverse
EOF

echo "APT 镜像源切换完成"

# 更新 apt 缓存
apt update

echo "脚本执行完成"
