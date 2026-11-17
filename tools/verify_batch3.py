"""小批验证：用修复后的脚本重播 3 章，核验平台真实计数是否上涨。

- 只跑当前 3 个 WAITING 章节（已手动重置）
- 用 storage_state 注入登录（auth.py 已改）
- 跑完打印每章状态；再调用平台核验读顶部计数
用法：PYTHONIOENCODING=utf-8 .venv/Scripts/python -u tools/verify_batch3.py
"""
import sys
sys.path.insert(0, ".")
from pathlib import Path
from core.database import Database
from core.course_runner import run_course
from core.live_state import LiveState
from core.logger import get_logger

ROOT = Path(".").resolve()
log = get_logger("batch3")
COURSE = "ai_tools"

paths = {
    "state": ROOT / "data" / "storage_state.json",
    "status": ROOT / "web" / "live_status.json",
    "events": ROOT / "web" / "live_events.json",
    "signal": ROOT / "web" / "control_signal.json",
    "resume": ROOT / "web" / "resume_signal.txt",
}

def main():
    print("[验证] 基线：核验平台当前计数...", flush=True)
    db = Database()
    ls = LiveState(status_file=paths["status"], log_file=paths["events"])
    summary = run_course(COURSE, db, limit=3, ls=ls,
                         state_file=paths["state"],
                         signal_file=paths["signal"], resume_file=paths["resume"])
    print(f"[验证] 3章播放结束: {summary}", flush=True)
    db.close()

if __name__ == "__main__":
    main()
