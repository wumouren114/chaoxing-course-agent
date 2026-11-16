"""
题目协作队列 —— 脚本抓题 与 助手作答 之间的桥梁

机制（实现"助手直接作答、脚本自动提交"）：
  1. 脚本遇到弹题 → enqueue() 写入 pending_questions.json（含题干/选项/截图/上下文）
  2. 助手在对话中读取待答题，直接作答 → answer() 写回答案
  3. 脚本轮询 get_answered() 取到答案 → 在页面填选提交 → mark_submitted()
  4. 全程在 answers 表留痕（含助手答案、解析、提交状态）

这样即使脚本在后台独立运行，也能用上助手的作答能力。
"""
import json
import time
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

ROOT = Path(__file__).resolve().parent.parent
QUEUE_FILE = ROOT / "web" / "pending_questions.json"
SHOT_DIR = ROOT / "web" / "qshots"
SHOT_DIR.mkdir(parents=True, exist_ok=True)


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _load() -> List[Dict]:
    if QUEUE_FILE.exists():
        try:
            return json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _save(items: List[Dict]):
    QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
    QUEUE_FILE.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def enqueue(course: str, node_id: str, stem: str, options: List[str],
            qtype: str = "unknown", context: str = "", screenshot: str = "") -> str:
    """脚本抓到题目后入队，返回题目 id"""
    items = _load()
    qid = f"{course}_{node_id}_{int(time.time()*1000)}"
    items.append({
        "id": qid,
        "course": course,
        "node_id": node_id,
        "stem": stem,
        "options": options,
        "qtype": qtype,
        "context": context,
        "screenshot": screenshot,
        "status": "PENDING",     # PENDING / ANSWERED / SUBMITTED / SKIPPED
        "answer": "",
        "analysis": "",
        "created_at": _now(),
        "answered_at": "",
    })
    _save(items)
    return qid


def get_pending() -> List[Dict]:
    return [q for q in _load() if q["status"] in ("PENDING",)]


def answer(qid: str, answer: str, analysis: str = "") -> bool:
    """助手作答：写入答案，状态置 ANSWERED（等待脚本提交）"""
    items = _load()
    for q in items:
        if q["id"] == qid:
            q["answer"] = answer
            q["analysis"] = analysis
            q["status"] = "ANSWERED"
            q["answered_at"] = _now()
            _save(items)
            return True
    return False


def get_answered() -> List[Dict]:
    return [q for q in _load() if q["status"] == "ANSWERED"]


def mark_submitted(qid: str, ok: bool = True) -> bool:
    items = _load()
    for q in items:
        if q["id"] == qid:
            q["status"] = "SUBMITTED" if ok else "SKIPPED"
            _save(items)
            return True
    return False


def all_items() -> List[Dict]:
    return _load()


def persist_to_db(q: Dict):
    """把作答结果留痕到 answers 表"""
    from core.database import Database
    db = Database()
    try:
        db.save_answer(q["course"], q["node_id"], q["stem"], q["options"],
                       q.get("answer", ""), q.get("analysis", ""))
    finally:
        db.close()


if __name__ == "__main__":
    # 离线测试
    import os
    if QUEUE_FILE.exists():
        os.remove(QUEUE_FILE)
    qid = enqueue("ai_tools", "1221807919",
                  "人工智能的英文缩写是？", ["AI", "ML", "DL", "NLP"],
                  qtype="single", context="2.1 认识AI写作")
    print("入队:", qid)
    assert len(get_pending()) == 1
    assert answer(qid, "A", "AI = Artificial Intelligence")
    assert len(get_pending()) == 0
    assert len(get_answered()) == 1
    assert mark_submitted(qid, True)
    assert len(get_answered()) == 0
    print("队列流转:", [(q["stem"][:12], q["status"]) for q in all_items()])
    print("✅ 题目协作队列测试通过")
