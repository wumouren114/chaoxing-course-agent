"""
守望脚本 —— 持续监测待答队列，一旦有题入队就：
1. 在守望日志高亮记录（助手在对话中据此作答）
2. 更新实时状态文件的 quiz_pending 字段，让监控面板弹出提示
只读，不干扰播放。
"""
import time
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WATCH_LOG = ROOT / "data" / "watch_queue.log"
STATUS = ROOT / "web" / "live_status.json"
NOTIFY = ROOT / "web" / "quiz_notify.json"


def log(msg):
    from datetime import datetime
    ts = datetime.now().strftime("%H:%M:%S")
    with open(WATCH_LOG, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {msg}\n")
    print(f"[{ts}] {msg}", flush=True)


def main():
    from core.question_queue import all_items
    log("守望启动：每20秒检查待答队列")
    seen = set()
    while True:
        try:
            items = all_items()
            pending = [q for q in items if q["status"] == "PENDING"]
            # 新题入队
            for q in pending:
                if q["id"] not in seen:
                    seen.add(q["id"])
                    log(f"🔔 新弹题待作答 [{q['id']}]: {q['stem'][:80]}")
                    log(f"   选项: {q['options']}")
            # 写通知文件（面板读取）
            notify = {
                "pending_count": len(pending),
                "questions": [{"id": q["id"], "stem": q["stem"],
                               "options": q["options"], "qtype": q["qtype"]}
                              for q in pending],
            }
            NOTIFY.write_text(json.dumps(notify, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            log(f"检查异常: {e}")
        time.sleep(20)


if __name__ == "__main__":
    main()
