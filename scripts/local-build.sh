#!/bin/bash
# ==============================================================
# strava-dashboard local build (Mac 专用)
#
# 作用：
#   1. 读取 Apple 提醒事项 (EventKit, 仅 macOS, iCloud同步)
#   2. 获取天气 + 一言
#   3. 渲染 3 个页面
#   4. 部署 output/ 到 gh-pages 分支（即时更新网站）
#
# 触发方式：
#   - launchd 每天 07:00 / 20:00
#   - 手动: bash scripts/local-build.sh
#
# 注意：
#   不提交到 main 分支（避免和 GitHub Actions 冲突）
#   只直接部署 output/ 到 gh-pages
# ==============================================================

set -e
cd /Users/linyf/strava-dashboard
export NO_PROXY="*"

echo "[$(date)] ====== 本地构建开始 ======"

# 1. Apple 提醒事项 (iCloud 同步 iPhone→Mac)
python3 src/fetch_reminders.py 2>&1 || echo "[WARN] fetch_reminders 失败"

# 2. 天气 + 一言
python3 src/fetch_weather.py 2>&1 || echo "[WARN] fetch_weather 失败"
python3 src/fetch_quotes.py 2>&1 || echo "[WARN] fetch_quotes 失败"

# 3. 飞书任务 (可选)
python3 src/fetch_feishu.py 2>&1 || echo "[WARN] fetch_feishu 失败"

# 4. 渲染 3 个页面
python3 src/render_html.py --all 2>&1

# 4b. 渲染屏保图片 (Surface 横屏)
python3 src/render_screensaver.py 2>&1 || echo "[WARN] render_screensaver 失败 (需要 playwright)"

# 5. 部署 output/ 到 gh-pages 分支
echo "[$(date)] 🚀 部署到 GitHub Pages..."

GH_PAGES_DIR=$(mktemp -d)
# 确保 .nojekyll 存在（GitHub Pages 处理下划线目录需要）
touch output/.nojekyll

# 获取 gh-pages 分支，或创建新分支
if git rev-parse --verify origin/gh-pages 2>/dev/null; then
    git fetch origin gh-pages 2>&1
    git worktree add "$GH_PAGES_DIR" origin/gh-pages 2>&1
    # 清空旧文件
    rm -rf "$GH_PAGES_DIR"/*
else
    git worktree add --detach "$GH_PAGES_DIR" 2>&1
    rm -rf "$GH_PAGES_DIR"/*
fi

# 复制渲染好的文件
cp -R output/* "$GH_PAGES_DIR/"

# 提交并推送
cd "$GH_PAGES_DIR"
git add .
if ! git diff --staged --quiet 2>/dev/null; then
    git commit -m "deploy: $(date +%Y-%m-%d-%H:%M)"
    git push origin HEAD:gh-pages --force 2>&1
    echo "[$(date)] ✅ GitHub Pages 已更新"
else
    echo "[$(date)] ℹ️  无变化"
fi

# 清理临时目录
cd /Users/linyf/strava-dashboard
git worktree remove "$GH_PAGES_DIR" 2>&1 || true
rm -rf "$GH_PAGES_DIR" 2>&1 || true

echo "[$(date)] ====== 本地构建完成 ======"