# 三页仪表盘：数据机制与部署说明

## 一、三页概览

| 页面 | 文件 | Tab名 | 核心数据 |
|------|------|-------|----------|
| 运动 | `output/index.html` | 运动 | Strava 活动、年度/周目标、训练计划、趋势图、赛事倒计时 |
| 工作 | `output/work.html` | 工作 | Apple 提醒事项（工作相关）、会议日程 |
| 生活 | `output/life.html` | 生活 | 7天天气+降雨提醒、农历、Apple 提醒事项（生活相关）、生日纪念日、一言 |

## 二、每页数据来源

### 运动页 `/index.html`

| 板块 | 数据源 | 文件 | 更新频率 |
|------|--------|------|----------|
| 年度目标 | Strava API → process_data | `data/processed.json` | 每日 06:00 (GitHub Actions) |
| 本周目标 | Strava API → process_data | `data/processed.json` | 每日 06:00 |
| 关键指标 | Strava API → process_data + zones.json | `data/processed.json` | 每日 06:00 |
| 年度进度 | process_data + config.yaml | `data/processed.json` | 每日 06:00 |
| 周趋势/月趋势 | Strava API → process_data | `data/processed.json` | 每日 06:00 |
| 本周训练 | generate_training (规则/AI) | `data/training_plan.json` | 每日 06:00 |
| 训练区间 | Strava zones API | `data/zones.json` | 每日 06:00 |
| 赛事倒计时 | config.yaml races | `config.yaml` | 手动更新 |

### 工作页 `/work.html`

| 板块 | 数据源 | 文件 | 更新频率 |
|------|--------|------|----------|
| 今日待办 | Apple 提醒事项 | `data/reminders.json`（通过 EventKit 读取） | Mac 本地每日 07:00 + 20:00 |
| 本周待办 | Apple 提醒事项 | `data/reminders.json` | Mac 本地每日 07:00 + 20:00 |
| 今日会议 | config.yaml / 飞书 API | `data/feishu_tasks.json`（可选） | 手动 / 飞书触发 |
| 本周会议 | config.yaml / 飞书 API | `data/feishu_tasks.json`（可选） | 手动 / 飞书触发 |

> **待办筛选逻辑**：从 Apple 提醒事项中按关键词（周报/汇报/会议/评审/项目等）筛选出工作相关项。有截止日期的按"今日/本周"分类。

### 生活页 `/life.html`

| 板块 | 数据源 | 文件 | 更新频率 |
|------|--------|------|----------|
| 7天天气+降雨提醒 | Open-Meteo API | `data/weather.json` | 每次渲染时获取 |
| 农历 | lunar.py 计算 | — | 实时计算 |
| 生活待办 | Apple 提醒事项 | `data/reminders.json` | Mac 本地每日 07:00 + 20:00 |
| 连续运动天数 | Strava → process_data | `data/processed.json` | 每日 06:00 |
| 生日/纪念日 | Apple 提醒事项（含"生日""纪念日"的项） | `data/reminders.json` | Mac 本地每日 07:00 + 20:00 |
| 一言 | hitokoto.cn API | `data/quotes.json` | 每次渲染时获取 |

## 三、更新机制（两条管线）

### 管线 A：GitHub Actions（自动，不依赖 Mac）

```yaml
每天 06:00 CST (UTC 22:00) 触发
  ↓
1. fetch_strava.py    # 获取 Strava 活动/区间/资料
2. process_data.py    # 计算年度/周/月汇总、streak
3. generate_training  # AI或规则生成训练计划
4. fetch_weather.py   # 获取7天天气 + 降雨提醒
5. fetch_quotes.py    # 获取一言
6. render_html.py --all  # 渲染3个页面
7. Deploy to gh-pages     # 部署 Kindle 可访问
```

**运行位置**：GitHub 服务器（Ubuntu），无需自备机器
**不负责**：Apple 提醒事项（EventKit 需要 macOS）

### 管线 B：Mac launchd（需要 Mac 本地运行）

```
每天 07:00 / 20:00 (macOS launchd) 触发
  ↓
1. fetch_reminders.py  # Apple 提醒事项 (EventKit)
2. fetch_weather.py    # 天气
3. fetch_quotes.py     # 一言
4. render_html.py --all # 渲染3页
5. git commit + push    # 数据推送到 GitHub
```

**运行位置**：你的 Mac（需要 Reminders 权限）
**为什么需要**：Apple 提醒事项只能通过 macOS EventKit 读取

### 完整数据流

```
iPhone 提醒事项 ←→ iCloud ←→ Mac 提醒事项 App
                                  ↓ (EventKit, launchd 07:00/20:00)
                            data/reminders.json
                                  ↓
                            render_html.py ─→ output/*.html
                                  ↑
GitHub Actions (06:00) ─→ data/processed.json
                         data/training_plan.json
                         data/zones.json
                         data/weather.json
                         data/quotes.json
```

## 四、需要定期运行的脚本

### GitHub Actions（无需你管）

✅ 已经配置好，每天自动运行。负责 Strava 数据和大部分静态数据。

### Mac 本地（需要你操作一次）

✅ launchd 已注册，每天 07:00/20:00 自动运行。负责 Apple 提醒事项。
验证是否激活：

```bash
launchctl list | grep strava-dashboard
```

### 手动触发

```bash
# 完整刷新（推荐）
bash scripts/local-build.sh

# 或分步运行
python3 src/fetch_reminders.py   # 刷新提醒事项
python3 src/fetch_weather.py     # 刷新天气
python3 src/fetch_quotes.py      # 刷新一言
python3 src/render_html.py --all # 重新渲染
```

## 五、需要一台服务器吗？

**不需要买服务器。** 整个系统的运行依赖：

| 组件 | 需要什么 | 费用 |
|------|----------|------|
| GitHub Actions | GitHub 免费额度 | 免费（2000分钟/月，足够） |
| Mac 本地 launchd | 你的 Mac（睡眠不影响定时任务） | 已有 |
| iPhone ↔ 同步 | iCloud | 您的 Apple ID 自带 |
| Strava API | Strava 开发者账号 | 免费 |
| Open-Meteo 天气 | 无需 API Key | 免费 |
| Intervals.icu | 注册账号 | 免费 |
| 飞书 CLI | 仅当使用飞书任务 | 免费 |

**极简流程**：

```
1. Mac 每天 07:00 / 20:00 → launchd 自动跑 → 读取提醒事项 → 渲染 → git push
2. GitHub Actions 每天 06:00 → 跑 Strava → 渲染 → deploy
3. Kindle 浏览器打开 https://你的用户名.github.io/strava-dashboard/
```

Mac 睡眠时 launchd 会在唤醒后立即补执行。只要你的 Mac 不是长期关机，提醒事项数据就能自动更新。

## 六、配置文件参考

### config.yaml 新增会议配置

```yaml
# 会议日程（从飞书同步后自动填充）
# meetings:
#   today:
#     - time: "09:30"
#       title: "周例会"
#     - time: "14:00"
#       title: "产品评审"
#   week:
#     - time: "周三"
#       title: "技术方案讨论"
#     - time: "周五"
#       title: "Sprint Review"
```

### 待办事项的"工作/生活"分类

当前按关键词自动分类。工作关键词：`周报/汇报/会议/评审/项目/面谈/复盘/代码/技术/方案/需求`
不含这些关键词的自动归为生活待办。含"生日""纪念日"等词的自动归为生日提醒。