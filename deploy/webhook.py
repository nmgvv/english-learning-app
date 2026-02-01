#!/usr/bin/env python3
"""
GitHub Webhook 接收器

监听 GitHub push 事件，自动触发部署脚本。
运行在 9000 端口，由 systemd 管理。

安全特性：
- HMAC-SHA256 签名验证
- 只响应 main 分支的 push 事件
- 日志记录

Usage:
    # 直接运行测试
    python webhook.py

    # 生产环境由 systemd 管理
    sudo systemctl start webhook
"""

import hmac
import hashlib
import subprocess
import os
import logging
from datetime import datetime
from flask import Flask, request, jsonify

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/log/webhook.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# 从环境变量读取配置
WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "")
DEPLOY_SCRIPT = os.getenv("DEPLOY_SCRIPT", "/var/www/english-app/deploy/deploy.sh")
ALLOWED_BRANCH = os.getenv("ALLOWED_BRANCH", "refs/heads/main")


def verify_signature(payload: bytes, signature: str) -> bool:
    """
    验证 GitHub Webhook 签名

    Args:
        payload: 请求体原始字节
        signature: X-Hub-Signature-256 头部值

    Returns:
        签名是否有效
    """
    if not signature or not WEBHOOK_SECRET:
        logger.warning("签名验证失败: 缺少签名或密钥")
        return False

    expected = "sha256=" + hmac.new(
        WEBHOOK_SECRET.encode('utf-8'),
        payload,
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(expected, signature)


@app.route("/webhook", methods=["POST"])
def webhook():
    """处理 GitHub Webhook 请求"""

    # 记录请求信息
    event = request.headers.get("X-GitHub-Event", "unknown")
    delivery_id = request.headers.get("X-GitHub-Delivery", "unknown")
    logger.info(f"收到 Webhook: event={event}, delivery_id={delivery_id}")

    # 1. 验证签名
    signature = request.headers.get("X-Hub-Signature-256")
    if not verify_signature(request.data, signature):
        logger.warning(f"签名验证失败: delivery_id={delivery_id}")
        return jsonify({"error": "Invalid signature"}), 403

    # 2. 检查事件类型
    if event == "ping":
        logger.info("收到 ping 事件，Webhook 配置正确")
        return jsonify({"message": "pong"}), 200

    if event != "push":
        logger.info(f"忽略非 push 事件: {event}")
        return jsonify({"message": f"Ignored event: {event}"}), 200

    # 3. 解析请求体
    try:
        data = request.json
    except Exception as e:
        logger.error(f"JSON 解析失败: {e}")
        return jsonify({"error": "Invalid JSON"}), 400

    # 4. 检查分支
    ref = data.get("ref", "")
    if ref != ALLOWED_BRANCH:
        logger.info(f"忽略非 main 分支: {ref}")
        return jsonify({"message": f"Ignored branch: {ref}"}), 200

    # 5. 获取提交信息
    pusher = data.get("pusher", {}).get("name", "unknown")
    commits = data.get("commits", [])
    commit_count = len(commits)
    latest_commit = commits[-1].get("message", "") if commits else "N/A"

    logger.info(f"开始部署: pusher={pusher}, commits={commit_count}, message={latest_commit[:50]}")

    # 6. 执行部署脚本
    try:
        result = subprocess.run(
            ["bash", DEPLOY_SCRIPT],
            capture_output=True,
            text=True,
            timeout=300,  # 5分钟超时
            cwd="/var/www/english-app"
        )

        if result.returncode == 0:
            logger.info("部署成功")
            return jsonify({
                "message": "Deploy successful",
                "commit": latest_commit[:100],
                "pusher": pusher,
                "output": result.stdout[-500:] if result.stdout else ""
            }), 200
        else:
            logger.error(f"部署失败: {result.stderr}")
            return jsonify({
                "error": "Deploy failed",
                "returncode": result.returncode,
                "stderr": result.stderr[-500:] if result.stderr else ""
            }), 500

    except subprocess.TimeoutExpired:
        logger.error("部署超时")
        return jsonify({"error": "Deploy timeout"}), 500
    except FileNotFoundError:
        logger.error(f"部署脚本不存在: {DEPLOY_SCRIPT}")
        return jsonify({"error": "Deploy script not found"}), 500
    except Exception as e:
        logger.error(f"部署异常: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/health", methods=["GET"])
def health():
    """健康检查端点"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "webhook_secret_configured": bool(WEBHOOK_SECRET)
    }), 200


@app.route("/", methods=["GET"])
def index():
    """根路径"""
    return jsonify({
        "service": "GitHub Webhook Receiver",
        "endpoints": {
            "/webhook": "POST - GitHub Webhook",
            "/health": "GET - Health check"
        }
    }), 200


if __name__ == "__main__":
    # 检查配置
    if not WEBHOOK_SECRET:
        logger.warning("GITHUB_WEBHOOK_SECRET 未设置，签名验证将失败！")

    logger.info(f"启动 Webhook 服务器...")
    logger.info(f"部署脚本: {DEPLOY_SCRIPT}")
    logger.info(f"监听分支: {ALLOWED_BRANCH}")

    app.run(host="0.0.0.0", port=9000, debug=False)
