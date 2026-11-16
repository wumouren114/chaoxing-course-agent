"""
进度报告模块 —— 结束时生成课程进度报告（Markdown + JSON）
严格区分 COMPLETED / SKIPPED / NEEDS_REVIEW / ERROR，不混淆
"""
import json
from pathlib import Path
from datetime import datetime
from core.database import Database

ROOT = Path(__file__).resolve().parent.parent
REPORT_DIR = ROOT / "data" / "reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

COURSE_NAMES = {
    "ai_tools": "人人都能上手的AI工具",
    "ai_principle": "生成式人工智能原理及其影响和应用",
}

STATE_LABELS = {
    "COMPLETED": "已完成",
    "SKIPPED": "已跳过（不等于完成）",
    "NEEDS_REVIEW": "需人工处理",
    "ERROR": "执行异常",
    "RUNNING": "处理中",
    "WAITING": "等待执行",
}


def generate_report(db: Database, course: str) -> Path:
    summary = db.summary(course)
    tasks = db.get_tasks(course)
    anomalies = db.get_anomalies(course)
    name = COURSE_NAMES.get(course, course)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        f"# 课程进度报告：{name}",
        "",
        f"> 生成时间：{ts}",
        "",
        "## 总览",
        "",
        f"- 任务总数：**{summary['total']}**",
        f"- 已完成：**{summary['completed']}**",
        f"- 已跳过（≠完成）：**{summary['skipped']}**",
        f"- 需人工处理：**{summary['needs_review']}**",
        f"- 执行异常：**{summary['errors']}**",
        f"- 完成进度：**{summary['progress_pct']}%**",
        "",
        "## 状态分布",
        "",
        "| 状态 | 数量 |",
        "|---|---|",
    ]
    for st, n in summary["counts"].items():
        lines.append(f"| {STATE_LABELS.get(st, st)} | {n} |")

    lines += ["", "## 需人工处理 / 异常的任务", ""]
    attention = [t for t in tasks if t["state"] in ("NEEDS_REVIEW", "ERROR", "SKIPPED")]
    if attention:
        lines.append("| 章节 | 状态 | 原因 |")
        lines.append("|---|---|---|")
        for t in attention:
            reason = (t["reason"] or "").replace("|", "/")[:60]
            lines.append(f"| {t.get('number','')} {t['title']} | "
                         f"{STATE_LABELS.get(t['state'], t['state'])} | {reason} |")
    else:
        lines.append("无。")

    lines += ["", "## 异常记录", ""]
    if anomalies:
        for a in anomalies:
            lines.append(f"- [{a['ts']}] {a.get('node_id','')} {a['kind']}: {a['reason']}")
    else:
        lines.append("无。")

    lines += [
        "",
        "---",
        "",
        "*本报告由自动化 Agent 生成。所有完成状态均以平台真实反馈为准；"
        "跳过、异常、需人工处理的任务均未被标记为完成。*",
        "",
    ]

    md = "\n".join(lines)
    md_path = REPORT_DIR / f"report_{course}_{datetime.now():%Y%m%d_%H%M%S}.md"
    md_path.write_text(md, encoding="utf-8")
    # 同时存 JSON
    json_path = md_path.with_suffix(".json")
    json_path.write_text(
        json.dumps({"course": course, "name": name, "generated_at": ts,
                    "summary": summary, "tasks": tasks, "anomalies": anomalies},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return md_path


if __name__ == "__main__":
    db = Database()
    p = generate_report(db, "ai_tools")
    print(f"✅ 报告已生成: {p}")
    print(p.read_text(encoding="utf-8")[:600])
