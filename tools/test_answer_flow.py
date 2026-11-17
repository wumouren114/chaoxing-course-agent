"""端到端验证 answer_quiz 完整流程（抓题→入队→等作答→提交→核验）。
用法: python tools/test_answer_flow.py [course] [node_id] [wait]
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from playwright.sync_api import sync_playwright
from core import chapter_quiz as cq
from core import question_queue as qq
from core.auth import Session
from core.course_runner import open_course, enter_chapter
from core.database import Database

COURSE = sys.argv[1] if len(sys.argv) > 1 else "ai_tools"
NODE = sys.argv[2] if len(sys.argv) > 2 else "1221808029"
WAIT = int(sys.argv[3]) if len(sys.argv) > 3 else 600

STATE = str(Path(f"data/storage_state{'_principle' if COURSE=='ai_principle' else ''}.json").resolve())

with Session(headless=True, state_file=STATE) as s:
    if not s.ensure_login():
        print("登录失败"); sys.exit(1)
    page = s.page
    fr = open_course(s, COURSE)
    enter_chapter(page, fr, NODE)
    print(f"进入章节 {NODE}, 有测验={cq.has_quiz(page)}", flush=True)
    result = cq.answer_quiz(page, COURSE, NODE, wait_seconds=WAIT)
    print(f"\n=== answer_quiz 结果 ===", flush=True)
    print(result, flush=True)
