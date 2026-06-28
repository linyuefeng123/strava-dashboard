@echo off
REM ==============================================================
REM strava-dashboard Windows 定时任务脚本
REM 24小时开机的 Windows 机器上使用，替代 Mac launchd
REM
REM 使用方式：
REM   1. 安装 Python 3.11+：https://www.python.org/downloads/
REM   2. 安装依赖：pip install requests pyyaml jinja2
REM   3. 配置计划任务（每次开机自动运行）：
REM      - 搜索"任务计划程序" → 创建基本任务
REM      - 触发器：每天，重复间隔 6 小时
REM      - 操作：启动此 bat 文件
REM
REM 注意：
REM   - 无法读取 Apple 提醒事项（需要 macOS）
REM   - 待办数据从 config.yaml 读取
REM   - iPhone 编辑：Safari 打开 github.com 修改 config.yaml
REM ==============================================================

cd /d %USERPROFILE%\strava-dashboard

echo [%date% %time%] ==== Windows Build Start ====

REM 1. 拉取最新代码（含 config.yaml 可能有的待办更新）
git pull origin main

REM 2. 获取天气 + 名言 + 飞书任务
python src\fetch_weather.py
python src\fetch_quotes.py
python src\fetch_feishu.py

REM 3. 渲染 3 个页面
python src\render_html.py --all

REM 4. 提交数据 + 部署到 gh-pages
git add data\
git diff --staged --quiet || git commit -m "chore: windows build %date%"
git push origin main

echo [%date% %time%] ==== Deploy to gh-pages ====
REM 部署 output 到 gh-pages 分支
git fetch origin gh-pages
git checkout gh-pages
REM 清空旧文件（保留 .nojekyll）
git rm -r --cached . 2>nul || git rm -r . 2>nul
copy /Y output\* .
echo .nojekyll > .nojekyll
git add .
git diff --staged --quiet || git commit -m "deploy: windows %date%"
git push origin gh-pages --force
git checkout main

echo [%date% %time%] ==== Build Complete ====