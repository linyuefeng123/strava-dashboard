# 踩坑记录

## 1. git reset --hard 会丢失所有未提交的修改

**场景**：执行 `git reset --hard origin/main` 后，本地的模板修改、代码修改、数据文件全部丢失。

**后果**：
- 重新创建了 3 个模板文件（work.html、life.html、dashboard.html）
- 重新改了一遍 render_html.py（加了 3 页 context 函数）
- 重新改了一遍 fetch_weather.py（7 天预报、降雨提醒）

**教训**：`git reset --hard` 前先 `git stash` 或 `git commit`。

## 2. 数据文件被 git 覆盖后不会自动恢复

**场景**：reminders.json、weather.json、quotes.json 是运行时生成的数据文件，`git reset` 后变成旧版本或空文件。

**后果**：
- 生活页天气不对（旧数据）
- 生活页没有待办（reminders.json 空了）
- 用户反馈后才手动重新 fetch

**教训**：git 操作后一定要重新获取数据：
```bash
python3 src/fetch_weather.py
python3 src/fetch_reminders.py
python3 src/fetch_quotes.py
python3 src/render_html.py --all
```

## 3. 代码修改必须提交到 main，否则 GitHub Actions 会覆盖 gh-pages

**场景**：模板和渲染器改了，但只通过本地构建脚本推到 gh-pages，没提交到 main。

**后果**：GitHub Actions 每天 06:00 用旧代码运行，覆盖了 gh-pages 上正确的新页面，导致用户访问 404。

**教训**：修改模板/代码后必须先 `git commit + git push main`，再部署 gh-pages。

## 4. 验证 gh-pages 分支内容

**场景**：部署后以为成功了，但 gh-pages 分支可能没有新文件。

**检查命令**：
```bash
git ls-tree -r origin/gh-pages --name-only
```

**期望输出**：包含 index.html、work.html、life.html、.nojekyll（不包含旧的 weather.html、todo.html、guide.html）

## 5. launchd 定时任务需要手动激活

**场景**：创建了 `.plist` 文件但没运行 `launchctl load`，或者 load 后 Mac 重启可能丢失。

**检查命令**：
```bash
launchctl list | grep strava-dashboard
```

**如果不在列表中**：
```bash
launchctl load ~/Library/LaunchAgents/com.strava-dashboard.local-build.plist
```