"""
整门课全量播放入口
后台运行，支持侧边栏监控 + 控制面板 开始/暂停/停止。
用法：python tools/run_full_course.py [course]

多课程并行：每门课用独立 profile / state / 状态文件，避免 Cookie 与面板数据冲突。
"""
import sys
sys.path.insert(0, ".")
from pathlib import Path
from core.database import Database
from core.course_runner import run_course
from core.report import generate_report
from core.logger import get_logger
from core.live_state import LiveState

log = get_logger("full")
ROOT = Path(".").resolve()

# 每门课独立的会话与状态路径
COURSE_PATHS = {
    "ai_tools": {
        "profile": ROOT / "data" / "browser_profile",
        "state": ROOT / "data" / "storage_state.json",
        "status": ROOT / "web" / "live_status.json",
        "events": ROOT / "web" / "live_events.json",
        "signal": ROOT / "web" / "control_signal.json",
        "resume": ROOT / "web" / "resume_signal.txt",
        "log": ROOT / "data" / "full_run.log",
    },
    "ai_principle": {
        "profile": ROOT / "data" / "browser_profile_principle",
        "state": ROOT / "data" / "storage_state_principle.json",
        "status": ROOT / "web" / "live_status_principle.json",
        "events": ROOT / "web" / "live_events_principle.json",
        "signal": ROOT / "web" / "control_signal_principle.json",
        "resume": ROOT / "web" / "resume_signal_principle.txt",
        "log": ROOT / "data" / "full_run_principle.log",
    },
}


def main():
    course = sys.argv[1] if len(sys.argv) > 1 else "ai_tools"
    paths = COURSE_PATHS.get(course, COURSE_PATHS["ai_tools"])
    db = Database()
    print(f"[全量] 开始整门课播放: {course}", flush=True)

    # 首次运行第二门课：用主登录态初始化独立 profile
    if course == "ai_principle" and not paths["profile"].exists():
        import shutil
        src = COURSE_PATHS["ai_tools"]["profile"]
        if src.exists():
            print(f"[全量] 初始化 {course} 独立 profile（复制自主 profile）...", flush=True)
            shutil.copytree(src, paths["profile"])

    # 初始化独立控制信号（默认 start）
    if not paths["signal"].exists():
        paths["signal"].write_text('{"command":"start","ts":0}', encoding="utf-8")

    ls = LiveState(status_file=paths["status"], log_file=paths["events"])
    summary = run_course(course, db, limit=None, ls=ls,
                         profile=paths["profile"], state_file=paths["state"],
                         signal_file=paths["signal"], resume_file=paths["resume"])
    print(f"[全量] 播放结束: {summary}", flush=True)
    report = generate_report(db, course)
    print(f"[全量] 报告: {report}", flush=True)
    db.close()


if __name__ == "__main__":
    main()
