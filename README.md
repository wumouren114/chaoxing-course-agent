# 课程学习自动化管理 Agent（Chaoxing / 超星尔雅）

一个基于 **Playwright + SQLite** 的课程学习自动化管理程序。它不是简单的点击脚本，而是一个带**状态机、任务调度、异常恢复、断点续跑和桌面控制面板**的 Agent。

> ⚠️ **免责与使用边界**：本项目仅用于学习自动化技术的研究与个人合法使用。请遵守所在平台的服务条款与所在机构的相关规定。程序**只做正常网页操作**（真实播放、正常点击）：**不伪造观看记录、不绕过平台检测、不自动提交考试/考核**。因使用本工具产生的任何后果由使用者自行承担。

---

## 功能特性

- **状态机驱动**：每个任务点严格经历 `WAITING / RUNNING / COMPLETED / NEEDS_REVIEW / ERROR / SKIPPED` 六种状态；`SKIPPED ≠ COMPLETED`，只有平台真实反馈完成才置为 `COMPLETED`。
- **目录自动解析**：从课程章节 iframe 提取章节节点、任务点数量、完成状态，建立任务列表并持久化到 SQLite。
- **内容识别与播放**：自动区分视频 / 课件 / 资料 / 练习，对视频做安静播放监测；以平台反馈（顶部完成任务点计数、目录样式、aria-label）为完成依据，而非播放器进度。
- **完整播放**：视频以 `ended` / 真正到片尾为准判定完成，不会在 90% 处提前跳下一节。
- **章节测验自动答题**：视频播完后自动检测章节内"测验"tab，抓取单选/判断题（题干经平台字体加密，但选项为明文），进入协作队列由助手作答后自动点选提交并核验成绩。**考试/考核类拒绝自动作答**。
  - `QUIZ_WAIT_SECONDS=N` 环境变量开启答题等待（默认 0 不阻塞）；`tools/answer_queue.py` 查看/写入答案。
- **自动检测复查**：`tools/audit_course.py` 批量核验每章"视频 isPassed + 测验完成"的服务端权威状态。
- **断点恢复**：每处理完一个任务点即落库，异常单节隔离后继续，重启后从中断处续跑。
- **多课程并行**：通过独立的浏览器 profile / storage_state / 状态文件隔离，支持多门课同时挂载。
- **桌面控制面板**：本地 Web 面板实时展示进度、当前视频状态、待答题提醒，并提供 开始 / 暂停 / 继续 / 停止 控制。

---

## 项目结构

```
config/
  credentials.example.json   # 账号配置示例（复制为 credentials.json，已 gitignore）
  ai_config.example.json     # AI 答案建议接口示例（可选）
core/
  auth.py          # 会话生命周期 / 登录态管理
  catalog.py       # 章节目录解析
  content.py       # 内容类型识别
  state_machine.py # 任务状态机（核心规则）
  scheduler.py     # 调度器（开始/暂停/继续/停止）
  course_runner.py # 整门课批量播放器
  video.py         # 播放器 iframe 定位与播放监测
  question.py / quiz_handler.py / question_queue.py  # 弹题解析、作答、协作队列
  database.py      # SQLite 持久化
  control.py       # 控制信号处理 / 人工环节挂起
  live_state.py    # 面板实时状态
  report.py / logger.py  # 报告与日志
web/
  monitor.html     # 监控面板前端
  serve.py         # 面板后端（默认 8765）
tools/
  run_full_course.py  # 全量运行入口
  watch_queue.py      # 待答题守望脚本
  import_course_catalog.py  # 目录导入
  explore_*.py / verify_*.py  # 页面结构探查与验证脚本
tests/             # 单元测试
docs/PAGE_STRUCTURE.md  # 真实页面结构分析（已脱敏）
```

---

## 快速开始

### 1. 环境

```bash
python -m venv .venv
# Windows
.venv\Scripts\python -m pip install -r requirements.txt
# macOS / Linux
source .venv/bin/activate && pip install -r requirements.txt

# 安装浏览器（项目使用系统 Edge，可按需安装 Chromium）
python -m playwright install msedge
```

### 2. 配置

```bash
# 账号（复制示例并填入自己的信息；该文件已被 gitignore，不会入库）
cp config/credentials.example.json config/credentials.json

# 可选：AI 答案建议接口。不填则题目辅助降级为规则提示，不猜答案。
cp config/ai_config.example.json config/ai_config.json
```

> 目标课程的 `courseid / clazzid / cpi` 在 `core/catalog.py` 与 `core/course_runner.py` 中配置。请替换为**你自己有权限访问的课程**，不要使用示例中的课程 ID。

### 3. 首次登录

持久化浏览器 profile 保存登录态，登录一次后即可复用：

```bash
.venv\Scripts\python tools\launch_login.py
```

### 4. 导入目录并运行

```bash
# 导入某门课的章节目录到数据库
.venv\Scripts\python tools\import_course_catalog.py

# 启动监控面板（浏览器打开 http://localhost:8765）
.venv\Scripts\python web\serve.py

# 全量运行（按面板信号 开始/暂停/继续/停止）
.venv\Scripts\python tools\run_full_course.py

# 另开一个终端：守望待答题队列并在面板提醒
.venv\Scripts\python tools\watch_queue.py
```

---

## 状态机

| 状态 | 含义 |
|---|---|
| `WAITING` | 等待调度 |
| `RUNNING` | 正在处理 |
| `COMPLETED` | 平台已确认完成 |
| `NEEDS_REVIEW` | 无法可靠自动处理，需人工复核 |
| `ERROR` | 发生异常（可重试 `ERROR → RUNNING`） |
| `SKIPPED` | 无任务点/无需处理（**绝不等于完成**） |

---

## 技术要点（来自真实页面采集）

- 课程目录位于 iframe `frame_content-zj`；知识卡片位于 `iframe#iframe`；视频播放器位于 `/ananas/modules/video/index.html` 嵌套 iframe。
- 课程主页必须从 `stucoursemiddle` 中间页带动态 `enc` 跳转，直接构造 URL 会报“无效的参数”。
- 有头模式下截图/失焦可能触发播放暂停，因此正式运行采用无头安静播放 + 低频状态读取。
- 平台会按日复核学习数据；观看时长需达总时长 90%。详见 `docs/PAGE_STRUCTURE.md`。

更多细节见 [docs/PAGE_STRUCTURE.md](docs/PAGE_STRUCTURE.md)。

---

## 许可

MIT License — 详见 [LICENSE](LICENSE)。
