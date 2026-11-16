# 学习通页面结构分析（真实页面采集）

> 采集时间：2026-11-16
> 采集账号：某高校在校学生（已脱敏）
> 目标课程：以两门示例课程为例（课程 ID 可在配置中自行替换）
> 说明：所有结构基于真实登录页面采集，仅用于正常网页操作的自动化。

## 1. 登录

| 元素 | 选择器 |
|---|---|
| 手机号 | `#phone` |
| 密码 | `#pwd` |
| 登录按钮 | `#loginBtn` |
| 协议勾选 | `input[type=checkbox]`（按需） |
| 登录成功判定 | URL 离开 `passport2.chaoxing.com`，跳到 `i.mooc.chaoxing.com/space/index` |

## 2. 课程列表

- 入口：`https://mooc2-ans.chaoxing.com/visit/interaction`
- 课程卡片：`div.course`，含隐藏字段 `input.courseId` / `input.clazzId`
- 课程名：`span.course-name[title]`
- 课程链接：`a[href*="stucoursemiddle"]`

| 课程 | courseid | clazzid | cpi |
|---|---|---|---|
| 人人都能上手的AI工具 | 268560848 | 158282453 | 575101306 |
| 生成式人工智能原理及其影响和应用 | 268560836 | 158282442 | 575101306 |

## 3. 课程主页（章节目录）

- 入口（**必须从中间页跳转，带动态 enc；直接构造会报"无效的参数"**）：
  `mooc1.chaoxing.com/visit/stucoursemiddle?courseid=&clazzid=&cpi=&ismooc2=1&v=2`
- 跳转后：`mooc2-ans.chaoxing.com/mooc2-ans/mycourse/stu?...&enc=<动态>`
- 首次进入有课程须知弹窗：`div.coursenoticepop` → 点 `div.start-study.readclosecoursepop`（"我已阅读, 开始学习"）
- 章节目录在 iframe：`iframe#frame_content-zj`，src=`/mooc2-ans/mycourse/studentcourse?...`

### 章节节点（`div.chapter_item`）

```
div.chapter_item#cur<nodeId>
  onclick = toOld('<courseid>', '<nodeId>', '<clazzid>', 0)
  .catalog_sbar           章节号，如 "2.1"
  .catalog_name           章节标题
  input.knowledgeJobCount[value]    任务点数量
  .catalog_jindu / .catalog_points_yi / .bntHoverTips   完成状态
```

- `node_id` 为空 → 分组标题（非任务，如 "AI写作"）
- `node_id` 有值 → 真实章节任务
- 未完成样式类：`catalog_tishi120` / `catalog_points_yi`
- 完成后的样式类：待实际播放完成后采集

## 4. 章节内容页

- URL：`mooc1.chaoxing.com/mycourse/studentstudy?chapterId=<nodeId>&courseId=&clazzid=&cpi=&enc=<动态>&mooc2=1`
- 页面顶部显示该节任务构成，如 "1视频 / 2测验"，与目录 job_count 对应
- 知识卡片 iframe：`iframe#iframe`，src=`/mooc-ans/knowledge/cards?...knowledgeid=<nodeId>...`

### 内容类型元素

| 类型 | 选择器 | 备注 |
|---|---|---|
| 视频容器 | `div.videoContainer` | |
| 视频任务点图标 | `div.ans-job-video` | `aria-label="任务点未完成"` / 完成后变化 |
| 视频播放器 | `iframe.ans-attach-online.ans-insertvideo-online` | src=`/ananas/modules/video/index.html`，播放状态在嵌套 iframe 内 |
| 音频 | `<audio>` | |
| 视频弹题 | `div.trans-question-box` | 播放中弹出的题目 |
| 课件/文档 | 待采集 | |

### 视频元数据（播放器 iframe 的 `data` 属性，JSON）

```json
{
  "name": "认识AI写作.mp4",
  "type": ".mp4",
  "size": 188238432,
  "hsize": "179.52 MB",
  "jobid": "1716974825920873",
  "mid": "12669186286371716974825586",
  "doublespeed": 1,
  "switchwindow": "true",
  "fastforward": "true"
}
```

`jobid` 是任务点 ID，是完成上报与状态判定的关键标识。

## 5. 平台规则（重要约束）

课程须知明示：
> 系统会按日复核学习结果数据，异常学习数据将被自动回退为未完成状态。
> 观看时长需 ≥ 总时长的 90%；未完成任务点前，当前视频不可拖拽、观看时不可离开或将页面最小化。

**因此本项目的策略：**
- 只做正常网页操作（真实播放、正常点击）。
- 不伪造观看记录、不绕过平台检测、不自动提交考试/考核。
- 题目只生成答案建议，等待用户确认后再由用户本人作答。
- 无法自动处理的情况记录为 NEEDS_REVIEW / ERROR，不伪装成 COMPLETED。

## 6. 采集踩坑记录

1. **多进程并发访问同一 profile 会 Cookie 冲突**，导致登录态失效被踢回登录页。→ 必须在单个会话内完成登录+访问；运行前清理残留 msedge 进程。
2. **不要用一个脚本 login() 后返回 page**：`with sync_playwright()` 退出会销毁实例。→ 用 Session 类持有生命周期。
3. **`no_viewport=True` 会导致元素 outside viewport 点击失败**。→ 用固定 viewport 1440x900。
4. 课程须知弹窗会拦截点击，必须先关掉。
5. 登录页两个 Python 环境混乱 → 统一用 `.venv/Scripts/python` 和 `python -m pip`。
