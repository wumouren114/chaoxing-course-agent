"""
内容识别模块 —— 识别章节内的视频/音频/测验/资料等任务点
基于知识卡片 iframe（/mooc-ans/knowledge/cards）的 DOM 结构
"""
import json
import re
from typing import List, Dict


def parse_knowledge_html(html: str) -> Dict:
    """从知识卡片 HTML 解析内容清单（纯解析，便于离线测试）"""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    items = []

    # 视频：iframe.ans-insertvideo-online，元数据在 data 属性（HTML 实体编码的 JSON）
    for vf in soup.select("iframe.ans-insertvideo-online, iframe.ans-attach-online"):
        data_raw = vf.get("data", "")
        meta = {}
        if data_raw:
            try:
                from html import unescape
                meta = json.loads(unescape(data_raw))
            except Exception:
                meta = {}
        # 找同容器里的任务点状态图标
        container = vf.find_parent(class_="videoContainer") or vf.parent
        job_icon = container.select_one(".ans-job-video") if container else None
        status = job_icon.get("aria-label", "") if job_icon else ""
        items.append({
            "type": "video",
            "jobid": meta.get("jobid", vf.get("jobid", "")),
            "name": meta.get("name", ""),
            "size": meta.get("size", 0),
            "duration_hint": "",
            "status": status,
            "completed": "未完成" not in status if status else False,
            "meta": {k: meta.get(k) for k in ("mid", "doublespeed", "objectid", "hsize")},
        })

    # 音频任务点（必须是真正的任务：带 jobid 或在任务容器内；排除页面翻译朗读等 UI 音频）
    for af in soup.find_all("audio"):
        jobid = af.get("jobid", "")
        in_task = af.find_parent(class_=lambda x: x and any(
            k in str(x) for k in ("audioContainer", "ans-job", "task", "job")))
        if not jobid and not in_task:
            continue
        items.append({
            "type": "audio", "jobid": jobid,
            "name": af.get("title", ""), "status": "", "completed": False, "meta": {},
        })

    # 测验/作业题（注意：.trans-question-box 是页面自带 AI 问答输入框，不是测验，必须排除）
    # 真正的测验通常是题库/作业 H5 或有明确题型的容器
    for q in soup.select(".ans-attach-homework, .homework-box, .question-list, .exam-box, [class*=zuoye]"):
        text = q.get_text(" ", strip=True)[:100]
        if text:
            items.append({
                "type": "quiz", "jobid": q.get("jobid", ""), "name": text,
                "status": "", "completed": False, "meta": {},
            })

    # 文档/PPT/资料（iframe 非视频类，或 pdf/doc 链接）
    for doc in soup.select("iframe.ans-attach-online:not(.ans-insertvideo-online), [class*=ans-attach-doc], a[href$='.pdf']"):
        items.append({
            "type": "document", "jobid": doc.get("jobid", ""),
            "name": doc.get("title", "") or doc.get_text(strip=True)[:60],
            "status": "", "completed": False, "meta": {},
        })

    types = sorted(set(i["type"] for i in items))
    return {"count": len(items), "types": types, "items": items}


def classify_from_frame(kcards_frame) -> Dict:
    """从真实知识卡片 frame 提取内容清单"""
    html = kcards_frame.evaluate("() => document.body.innerHTML")
    return parse_knowledge_html(html)


if __name__ == "__main__":
    from pathlib import Path
    ROOT = Path(__file__).resolve().parent.parent
    snap = ROOT / "data" / "snapshots" / "07_knowledge_cards.html"
    if snap.exists():
        result = parse_knowledge_html(snap.read_text(encoding="utf-8"))
        print("内容识别结果:")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        assert any(i["type"] == "video" for i in result["items"]), "应识别出视频"
        print("\n✅ 内容识别测试通过（识别出视频任务点）")
    else:
        print("无快照，跳过测试")
