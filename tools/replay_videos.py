"""定点重播指定章节的视频（用修复后的99.9%完整播放判定）。
用法: python tools/replay_videos.py [course] node1 node2 ...
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.auth import Session
from core.course_runner import open_course, enter_chapter, find_all_video_frames
from core.video import monitor_playback
from core.database import Database

COURSE = sys.argv[1] if len(sys.argv) > 1 else "ai_tools"
NODES = sys.argv[2:] if len(sys.argv) > 2 else [
    "1221807941", "1221807973", "1221807979", "1221807990",
]
STATE = str(Path(f"data/storage_state{'_principle' if COURSE=='ai_principle' else ''}.json").resolve())

print(f"=== 定点重播 {COURSE}: {len(NODES)} 章 ===", flush=True)
db = Database()
with Session(headless=True, state_file=STATE) as s:
    if not s.ensure_login():
        print("登录失败"); sys.exit(1)
    for node in NODES:
        print(f"\n===== 章节 {node} =====", flush=True)
        try:
            fr = open_course(s, COURSE)
            title = enter_chapter(s.page, fr, node)
            players = find_all_video_frames(s.page, timeout=30)
            print(f"章节 {node} {title}: 发现 {len(players)} 个视频", flush=True)
            if not players:
                print(f"  无视频，跳过", flush=True)
                continue
            all_ok = True
            for i, player in enumerate(players):
                player.wait_for_load_state("domcontentloaded", timeout=20000)
                r = monitor_playback(s.page, player, progress_threshold=99.9, poll=5)
                print(f"  视频{i+1}: ok={r.get('ok')} reason={r.get('reason')} "
                      f"final={r.get('final',{}).get('progress_pct')}%", flush=True)
                if not r.get("ok"):
                    all_ok = False
                    break
            if all_ok:
                db.update_task_state(COURSE, node, "COMPLETED", "定点重播视频至片尾")
                print(f"  章节 {node} 视频重播完成", flush=True)
            else:
                print(f"  章节 {node} 视频重播未达标", flush=True)
        except Exception as e:
            print(f"章节 {node} 异常: {e}", flush=True)
db.close()
print("\n=== 重播结束 ===", flush=True)
