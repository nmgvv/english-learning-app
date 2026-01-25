#!/bin/bash
# =============================================================================
# English Learning App 自动部署脚本
# 在阿里云 ECS Ubuntu 服务器上运行
# =============================================================================

set -e  # 遇到错误立即退出

# 配置
APP_DIR="/opt/english-learning-app"
SERVICE_NAME="english-learning"
BRANCH="main"
LOG_FILE="/var/log/english-learning-deploy.log"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
    echo "[ERROR] $1" >> "$LOG_FILE"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
    echo "[WARN] $1" >> "$LOG_FILE"
}

# 检查是否在正确的目录
if [ ! -d "$APP_DIR" ]; then
    error "应用目录不存在: $APP_DIR"
    exit 1
fi

cd "$APP_DIR"

log "=== 开始部署 English Learning App ==="
log "分支: $BRANCH"

# 1. 拉取最新代码
log "步骤 1/4: 拉取最新代码..."
git fetch origin
git reset --hard origin/$BRANCH

# 获取最新提交信息
COMMIT_MSG=$(git log -1 --pretty=format:"%h - %s (%an)")
log "最新提交: $COMMIT_MSG"

# 2. 激活虚拟环境并安装依赖
log "步骤 2/4: 检查并安装依赖..."
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
else
    error "虚拟环境不存在，请先创建: python3 -m venv venv"
    exit 1
fi

# 检查 requirements.txt 是否有变化
if git diff HEAD~1 --name-only | grep -q "requirements.txt"; then
    log "检测到 requirements.txt 变化，更新依赖..."
    pip install -r requirements.txt --quiet
else
    log "依赖无变化，跳过安装"
fi

# 3. 重启服务
log "步骤 3/4: 重启服务..."
sudo systemctl restart $SERVICE_NAME

# 4. 检查服务状态
log "步骤 4/4: 验证服务状态..."
sleep 3

if systemctl is-active --quiet $SERVICE_NAME; then
    log "${GREEN}✓ 部署成功！${NC}"
    log "服务状态: $(systemctl is-active $SERVICE_NAME)"

    # 检查端口是否在监听
    if ss -tlnp | grep -q ":8000"; then
        log "端口 8000 正在监听"
    else
        warn "端口 8000 未监听，请检查应用日志"
    fi
else
    error "✗ 部署失败！服务未能启动"
    error "查看日志: journalctl -u $SERVICE_NAME -n 50"
    exit 1
fi

log "=== 部署完成 ==="
