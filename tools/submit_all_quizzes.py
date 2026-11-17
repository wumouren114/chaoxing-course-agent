"""批量提交测验：读 data/quiz_answers.json，逐章进入→打开测验→按答案点选提交。
不依赖协作队列等待（答案已离线确定）。
用法: python tools/submit_all_quizzes.py [course]
"""
import sys, json, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.auth import Session
from core.course_runner import open_course, enter_chapter
from core import chapter_quiz as cq
from core.database import Database

COURSE = sys.argv[1] if len(sys.argv) > 1 else "ai_tools"
STATE = str(Path(f"data/storage_state{'_principle' if COURSE=='ai_principle' else ''}.json").resolve())
DUMP = Path(f"data/quiz_dump_{COURSE}.json")
ANS = Path("data/quiz_answers.json")

dump = json.loads(DUMP.read_text(encoding="utf-8"))
answers = json.loads(ANS.read_text(encoding="utf-8"))
print(f"=== 批量提交 {COURSE}: {len(dump)} 章 ===", flush=True)

db = Database()
ok_cnt = 0
with Session(headless=True, state_file=STATE) as s:
    if not s.ensure_login():
        print("登录失败"); sys.exit(1)
    for e in dump:
        node = e["node"]
        qa = answers.get(node)
        if not qa:
            print(f"  {node} 无答案，跳过", flush=True)
            continue
        try:
            fr = open_course(s, COURSE)
            title = enter_chapter(s.page, fr, node)
            # 已完成则跳过
            if not cq.has_quiz(s.page):
                print(f"  {node} 无测验tab", flush=True)
                continue
            qf = cq.open_quiz(s.page)
            if not qf:
                print(f"  {node} 未加载题目iframe", flush=True)
                continue
            try:
                qf.wait_for_selector("li[qid][qtype]", timeout=12000)
            except Exception:
                pass
            s.page.wait_for_timeout(1200)
            info = cq.parse_quiz(qf)
            qs = info["questions"]
            if not qs:
                print(f"  {node} 未解析到题目（可能已完成）", flush=True)
                continue
            if len(qa) != len(qs):
                print(f"  {node} 答案数{len(qa)}≠题数{len(qs)}，跳过", flush=True)
                continue
            # 按 qid 映射答案
            answers_by_qid = {q["qid"]: qa[i] for i, q in enumerate(qs)}
            fresh_qf = cq.find_quiz_frame(s.page) or qf
            ok = cq.select_and_submit(s.page, fresh_qf, info, answers_by_qid)
            if ok:
                db.update_task_state(COURSE, node, "COMPLETED", "章节测验批量提交")
                ok_cnt += 1
            print(f"  {node} {title[:14]}: {'✅提交成功' if ok else '❌提交失败'} ({len(qs)}题)", flush=True)
        except Exception as ex:
            print(f"  {node} 异常: {str(ex)[:70]}", flush=True)
db.close()
print(f"\n=== 批量提交结束: {ok_cnt}/{len(dump)} 章成功 ===", flush=True)
