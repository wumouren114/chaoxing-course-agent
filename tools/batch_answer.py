"""批量答题：对指定章节依次 抓题→等助手作答→提交。
配合 web/pending_questions.json 协作队列，助手在对话里写答案即可。
用法: python tools/batch_answer.py [course] node1 node2 ...
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.auth import Session
from core.course_runner import open_course, enter_chapter
from core import chapter_quiz as cq
from core.database import Database

COURSE = sys.argv[1] if len(sys.argv) > 1 else "ai_tools"
NODES = sys.argv[2:] if len(sys.argv) > 2 else [
    "1221807941", "1221807944", "1221807973", "1221807979",
    "1221807983", "1221807987", "1221807990",
]
WAIT = int(__import__("os").environ.get("ANSWER_WAIT", "900"))
STATE = str(Path(f"data/storage_state{'_principle' if COURSE=='ai_principle' else ''}.json").resolve())

print(f"=== 批量答题 {COURSE}: {len(NODES)} 章, 每章等待{WAIT}s ===", flush=True)
db = Database()
with Session(headless=True, state_file=STATE) as s:
    if not s.ensure_login():
        print("登录失败"); sys.exit(1)
    for node in NODES:
        print(f"\n===== 章节 {node} =====", flush=True)
        try:
            fr = open_course(s, COURSE)
            enter_chapter(s.page, fr, node)
            r = cq.answer_quiz(s.page, COURSE, node, wait_seconds=WAIT)
            print(f"结果 {node}: {r.get('status')} - {r.get('reason')}", flush=True)
            if r.get("status") == "answered":
                db.update_task_state(COURSE, node, "COMPLETED", "章节测验已作答提交")
        except Exception as e:
            print(f"章节 {node} 异常: {e}", flush=True)
db.close()
print("\n=== 批量答题结束 ===", flush=True)
