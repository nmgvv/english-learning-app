#!/bin/bash
# =============================================================================
# 双远端推送脚本：同时推送到 GitHub 和 Codeup
# 用法: bash deploy/push.sh
# =============================================================================

BRANCH="main"

echo "=== 推送到双远端 ==="

# 推送到 GitHub
echo "推送到 GitHub (origin)..."
if git push origin $BRANCH 2>/dev/null; then
    echo "✓ GitHub 推送成功"
else
    echo "✗ GitHub 推送失败（可忽略，国内网络问题）"
fi

# 推送到 Codeup
echo "推送到 Codeup..."
if git push codeup $BRANCH 2>/dev/null; then
    echo "✓ Codeup 推送成功"
else
    echo "✗ Codeup 推送失败"
    exit 1
fi

echo "=== 推送完成 ==="
