"""
自动检测复查工具：批量核验一门课所有章节的真实完成状态。
对每个有任务点的章节：
  视频：knowledge/cards 的 mArg.attachments[].isPassed
  测验：点"测验"tab 后题目 iframe 是否显示"已完成/本次成绩"
输出总览：已完成任务点数 / 未完成任务点清单。
用法: python tools/audit_course.py [course] [limit]
  course = ai_tools | ai_principle
  limit  = 最多检查前 N 个有任务点章节（默认全部）
"""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from playwright.sync_api import sync_playwright
from core import chapter_quiz as cq
from core.auth import Session
from core.course_runner import open_course
from core.database import Database
from core.logger import get_logger

log = get_logger("audit")
COURSE = sys.argv[1] if len(sys.argv) > 1 else "ai_tools"
LIMIT = int(sys.argv[2]) if len(sys.argv) > 2 else 0

STATE = str(Path(f"data/storage_state{'_principle' if COURSE=='ai_principle' else ''}.json").resolve())


def check_node(page, s, node_id, course):
    """返回 (video_done, quiz_status, quiz_score)"""
    video_done = False
    quiz_status = "none"   # none / pending / completed
    quiz_score = ""
    try:
        fr = open_course(s, course)
        nd = fr.locator(f"div.chapter_item#cur{node_id}")
        if nd.count() == 0:
            return None
        nd.locator(".clicktitle").click()
        page.wait_for_timeout(6000)
        # 视频状态
        kf = next((f for f in page.frames if "knowledge/cards" in (f.url or "")), None)
        if kf:
            try:
                att = kf.evaluate(
                    "() => typeof mArg!=='undefined' && mArg.attachments ? "
                    "mArg.attachments.map(a=>({type:a.type,passed:a.isPassed})) : []")
                vids = [a for a in (att or []) if a.get("type") == "video"]
                if vids and any(a.get("passed") for a in vids):
                    video_done = True
                elif not vids:
                    video_done = True  # 无视频附件
            except Exception:
                pass
        # 测验状态
        if cq.has_quiz(page):
            qf = cq.open_quiz(page)
            if qf:
                page.wait_for_timeout(3000)
                st = cq.check_quiz_status(qf)
                quiz_status = st
                if st == "completed":
                    try:
                        t = qf.evaluate("()=>document.body.innerText") or ""
                        import re
                        m = re.search(r"本次成绩\s*(\d+(?:\.\d+)?)", t)
                        if m:
                            quiz_score = m.group(1)
                    except Exception:
                        pass
        return (video_done, quiz_status, quiz_score)
    except Exception as e:
        log.warning(f"检查节点 {node_id} 异常: {e}")
        return None


def main():
    db = Database()
    tasks = [t for t in db.get_tasks(COURSE) if t.get("job_count", 0) > 0]
    db.close()
    if LIMIT > 0:
        tasks = tasks[:LIMIT]
    print(f"=== 复查 {COURSE}: {len(tasks)} 个有任务点章节 ===", flush=True)

    stats = {"video_ok": 0, "quiz_completed": 0, "quiz_pending": 0, "problems": []}
    with Session(headless=True, state_file=STATE) as s:
        if not s.ensure_login():
            print("登录失败"); return
        page = s.page
        for i, t in enumerate(tasks, 1):
            res = check_node(page, s, t["node_id"], COURSE)
            if res is None:
                stats["problems"].append((t.get("number"), t["node_id"], "检查失败"))
                continue
            vdone, qstatus, score = res
            if vdone:
                stats["video_ok"] += 1
            tag = []
            if not vdone:
                tag.append("视频未完成")
            if qstatus == "completed":
                stats["quiz_completed"] += 1
                tag.append(f"测验完成{score}分" if score else "测验完成")
            elif qstatus == "pending":
                stats["quiz_pending"] += 1
                tag.append("测验待完成")
            print(f"  [{i}/{len(tasks)}] {t.get('number')} {t.get('title','')[:20]} "
                  f"视频={'✓' if vdone else '✗'} 测验={qstatus} {score}", flush=True)
            if tag and (not vdone or qstatus == "pending"):
                stats["problems"].append((t.get("number"), t["node_id"], " / ".join(tag)))

    print(f"\n=== 复查总览 ===", flush=True)
    print(f"  视频完成: {stats['video_ok']}/{len(tasks)}", flush=True)
    print(f"  测验完成: {stats['quiz_completed']}  测验待完成: {stats['quiz_pending']}", flush=True)
    if stats["problems"]:
        print(f"  ⚠️ 问题清单 ({len(stats['problems'])}):", flush=True)
        for num, nid, why in stats["problems"]:
            print(f"    {num} ({nid}): {why}", flush=True)
    else:
        print("  ✅ 无未完成任务点", flush=True)


if __name__ == "__main__":
    main()
