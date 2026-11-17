"""批量抓取指定章节的测验题，dump 到本地 JSON（只抓不提交）。
用于一次性收集所有待答题目，助手集中作答后再批量提交。
用法: python tools/dump_all_quizzes.py [course] [nodes.txt]
输出: data/quiz_dump_<course>.json
"""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.auth import Session
from core.course_runner import open_course, enter_chapter
from core import chapter_quiz as cq

COURSE = sys.argv[1] if len(sys.argv) > 1 else "ai_tools"
NODESFILE = sys.argv[2] if len(sys.argv) > 2 else "data/fix_quiz_nodes.txt"
NODES = [x.strip() for x in Path(NODESFILE).read_text().split() if x.strip()]
STATE = str(Path(f"data/storage_state{'_principle' if COURSE=='ai_principle' else ''}.json").resolve())
OUT = Path(f"data/quiz_dump_{COURSE}.json")

print(f"=== 批量抓题 {COURSE}: {len(NODES)} 章 ===", flush=True)
dump = []
with Session(headless=True, state_file=STATE) as s:
    if not s.ensure_login():
        print("登录失败"); sys.exit(1)
    for node in NODES:
        try:
            fr = open_course(s, COURSE)
            title = enter_chapter(s.page, fr, node)
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
            s.page.wait_for_timeout(1500)
            info = cq.parse_quiz(qf)
            qs = info["questions"]
            if not qs:
                print(f"  {node} 未解析到题目（可能已完成）", flush=True)
                continue
            st = cq.check_quiz_status(qf)
            entry = {"node": node, "title": title, "status": st, "questions": []}
            for q in qs:
                entry["questions"].append({
                    "qid": q["qid"], "qtype": q["qtype"], "type_name": q["type_name"],
                    "stem": q["stem"],
                    "options": [{"key": o["key"], "text": o["text"]} for o in q["options"]],
                })
            dump.append(entry)
            print(f"  {node} {title[:16]}: {len(qs)}题 状态={st}", flush=True)
        except Exception as e:
            print(f"  {node} 异常: {str(e)[:60]}", flush=True)

OUT.write_text(json.dumps(dump, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n=== 已保存 {len(dump)} 章题目到 {OUT} ===", flush=True)
