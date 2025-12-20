#! /bin/bash

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# pip folder and file
PIP_PATH=${HOME}/".pip"
PIP_CONF=${HOME}/".pip/pip.conf"
PIP_PATH2=${HOME}/".config/pip"
PIP_CONF2=${HOME}/".config/pip/pip.conf"

# make sure the folder and file are exist
if [ ! -d ${PIP_PATH} ]; then
    mkdir ${PIP_PATH}
else
    if [ -f ${PIP_CONF} ]; then
        cp ${PIP_CONF} ${PIP_CONF}_bk
    else
	touch ${PIP_CONF}
    fi
fi


if [ ! -d ${PIP_PATH2} ]; then
    mkdir ${PIP_PATH2}
else
    if [ -f ${PIP_CONF2} ]; then
        cp ${PIP_CONF2} ${PIP_CONF2}_bk
    else
	touch ${PIP_CONF2}
    fi
fi


# source array
SOURCES=(
    "http://mirrors.aliyun.com/pypi/simple/"
    "https://pypi.mirrors.ustc.edu.cn/simple/"
    "https://pypi.doubanio.com/simple/"
    "https://pypi.tuna.tsinghua.edu.cn/simple/"
    "https://mirrors.cloud.tencent.com/pypi/simple/"
    "http://mirrors.zju.edu.cn/pypi/web/simple/"
    "http://mirrors.163.com/pypi/simple/"
    "https://repo.huaweicloud.com/repository/pypi/simple"
    "https://mirrors.bfsu.edu.cn/pypi/web/simple/"
    "https://mirrors.sjtug.sjtu.edu.cn/pypi/web/simple"
    "https://mirrors.nju.edu.cn/pypi/web/simple/"
    "https://pypi.org/simple/"
)

# trust-host array
HOST=(
    "mirrors.aliyun.com"
    "pypi.mirrors.ustc.edu.cn"
    "pypi.doubanio.com"
    "pypi.tuna.tsinghua.edu.cn"
    "mirrors.cloud.tencent.com"
    "mirrors.zju.edu.cn"
    "mirrors.163.com"
    "repo.huaweicloud.com"
    "mirrors.bfsu.edu.cn"
    "mirrors.sjtug.sjtu.edu.cn"
    "mirrors.nju.edu.cn"
    "pypi.org"
)

read -p "请选择您要切换的源的数字编号, 然后按回车
(0) 阿里云(aliyun)
(1) 中国科技大学(ustc)
(2) 豆瓣(douban)
(3) 清华大学(tsinghua)
(4) 腾讯云(tencent)
(5) 浙江大学(zju)
(6) 网易(163)
(7) 华为云(huawei)
(8) 北京外国语大学(bfsu)
(9) 上海交通大学(sjtug)
(10) 南京大学(nju)
(11) 官方源 (pypi)
取消输入: Ctrl + C
" INDEX

if [ ${INDEX} -ge ${#SOURCES[@]} ] || [ ${INDEX} -lt 0 ]; then
    echo "请输入有效的源编号"
    exit 1
fi

# overwrite file
echo "[global]
timeout = 6000
index-url = ${SOURCES[${INDEX}]}
trusted-host = ${HOST[${INDEX}]}" >${PIP_CONF}

echo "[global]
index-url = ${SOURCES[${INDEX}]}" > ${PIP_CONF2}

echo "切换完成"
