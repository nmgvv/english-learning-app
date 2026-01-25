#!/bin/bash
# =============================================================================
# English Learning App 服务器初始化脚本
# 在阿里云 ECS Ubuntu 20.04/22.04 上运行
# =============================================================================

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() { echo -e "${GREEN}[INFO]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# 配置
APP_NAME="english-learning-app"
APP_DIR="/opt/$APP_NAME"
GITHUB_REPO=""  # 将在运行时询问

echo -e "${BLUE}"
echo "=============================================="
echo "  English Learning App 服务器初始化"
echo "=============================================="
echo -e "${NC}"

# 检查是否为 root
if [ "$EUID" -ne 0 ]; then
    error "请使用 sudo 运行此脚本"
fi

# 询问 GitHub 仓库地址
read -p "请输入 GitHub 仓库地址 (如 https://github.com/username/repo.git): " GITHUB_REPO
if [ -z "$GITHUB_REPO" ]; then
    error "仓库地址不能为空"
fi

# 1. 更新系统
log "步骤 1/8: 更新系统..."
apt update && apt upgrade -y

# 2. 安装依赖
log "步骤 2/8: 安装依赖..."
apt install -y python3.10 python3.10-venv python3-pip nginx git curl

# 3. 创建应用目录
log "步骤 3/8: 创建应用目录..."
mkdir -p $APP_DIR
chown $SUDO_USER:$SUDO_USER $APP_DIR

# 4. 克隆仓库
log "步骤 4/8: 克隆仓库..."
sudo -u $SUDO_USER git clone $GITHUB_REPO $APP_DIR

# 5. 创建虚拟环境并安装依赖
log "步骤 5/8: 创建虚拟环境..."
cd $APP_DIR
sudo -u $SUDO_USER python3.10 -m venv venv
sudo -u $SUDO_USER $APP_DIR/venv/bin/pip install --upgrade pip
sudo -u $SUDO_USER $APP_DIR/venv/bin/pip install -r requirements.txt
sudo -u $SUDO_USER $APP_DIR/venv/bin/pip install flask  # webhook 需要

# 6. 创建 .env 文件
log "步骤 6/8: 配置环境变量..."
if [ ! -f "$APP_DIR/.env" ]; then
    cp $APP_DIR/.env.example $APP_DIR/.env
    chown $SUDO_USER:$SUDO_USER $APP_DIR/.env
    chmod 600 $APP_DIR/.env
    warn "请编辑 $APP_DIR/.env 填入真实的 API Key"
fi

# 创建数据目录
mkdir -p $APP_DIR/data $APP_DIR/static/audio $APP_DIR/static/recordings
chown -R www-data:www-data $APP_DIR/data $APP_DIR/static/audio $APP_DIR/static/recordings

# 设置部署脚本权限
chmod +x $APP_DIR/deploy/deploy.sh

# 7. 安装 systemd 服务
log "步骤 7/8: 配置 systemd 服务..."
cp $APP_DIR/deploy/english-learning.service /etc/systemd/system/
cp $APP_DIR/deploy/webhook.service /etc/systemd/system/

# 创建日志文件
touch /var/log/english-learning-deploy.log /var/log/webhook.log
chown www-data:www-data /var/log/english-learning-deploy.log /var/log/webhook.log

# 允许 www-data 执行 systemctl restart
echo "www-data ALL=(ALL) NOPASSWD: /bin/systemctl restart english-learning" >> /etc/sudoers.d/english-learning

systemctl daemon-reload
systemctl enable english-learning webhook

# 8. 配置 Nginx
log "步骤 8/8: 配置 Nginx..."
cp $APP_DIR/deploy/nginx.conf /etc/nginx/sites-available/english-learning
ln -sf /etc/nginx/sites-available/english-learning /etc/nginx/sites-enabled/

# 删除默认配置（如果存在）
rm -f /etc/nginx/sites-enabled/default

nginx -t && systemctl reload nginx

# 配置防火墙
if command -v ufw &> /dev/null; then
    ufw allow 80
    ufw allow 443
    ufw allow 22
    log "防火墙已配置"
fi

echo ""
echo -e "${GREEN}=============================================="
echo "  初始化完成！"
echo "==============================================${NC}"
echo ""
echo "后续步骤："
echo ""
echo "1. 编辑环境变量:"
echo "   nano $APP_DIR/.env"
echo ""
echo "2. 修改 Webhook Secret:"
echo "   nano /etc/systemd/system/webhook.service"
echo "   # 修改 GITHUB_WEBHOOK_SECRET 的值"
echo "   systemctl daemon-reload"
echo ""
echo "3. 启动服务:"
echo "   systemctl start english-learning webhook"
echo ""
echo "4. 查看服务状态:"
echo "   systemctl status english-learning"
echo "   systemctl status webhook"
echo ""
echo "5. 查看日志:"
echo "   journalctl -u english-learning -f"
echo "   journalctl -u webhook -f"
echo ""
echo "6. 在 GitHub 仓库设置 Webhook:"
echo "   - URL: http://YOUR_SERVER_IP/webhook"
echo "   - Content type: application/json"
echo "   - Secret: 与 webhook.service 中的值一致"
echo ""
