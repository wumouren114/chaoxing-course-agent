"""
第三步：单章节端到端测试
目标章节：ai_tools / 2.1 认识AI写作 (node_id=1221807919)
流程：登录 → 打开章节 → 识别内容 → 正常播放视频至≥90% → 检查平台完成判定 → 落库
严格约束：不拖拽、不伪造、不绕过检测。
"""
import sys
import time
import json
from pathlib import Path

sys.path.insert(0, ".")
from core.auth import Session
from core.video import find_player_frame, read_state, click_play, monitor_playback
from core.database import Database

ROOT = Path(__file__).resolve().parent.parent
SNAP = ROOT / "data" / "snapshots"
COURSE_MIDDLE = ("https://mooc1.chaoxing.com/visit/stucoursemiddle"
                 "?courseid=268560848&clazzid=158282453&cpi=575101306&ismooc2=1&v=2")
NODE_ID = "1221807919"


def check_task_status(kcards_frame, node_id):
    """检查知识卡片页中该视频任务点的完成状态（aria-label）"""
    try:
        return kcards_frame.evaluate("""() => {
            const out = [];
            document.querySelectorAll('.ans-job-video, [class*=ans-job-icon]').forEach(e=>{
                out.push({cls:(e.className||'').toString().slice(0,50),
                          label:e.getAttribute('aria-label')||''});
            });
            return out;
        }""")
    except Exception as e:
        return [{"error": str(e)}]


def main():
    db = Database()
    # 确保课程与任务记录存在
    db.upsert_course("ai_tools", "人人都能上手的AI工具", "268560848", "158282453", "575101306")
    db.upsert_task("ai_tools", NODE_ID, "2.1", "认识AI写作", 2,
                   meta={"type": "single_chapter_test"})
    with Session(headless=True) as s:
        page = s.page
        if not s.ensure_login():
            print("[单章测试] 登录失败"); return
        print("[单章测试] 登录成功，打开课程...")
        page.goto(COURSE_MIDDLE, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)
        if page.locator(".coursenoticepop .start-study").count() > 0:
            page.locator(".coursenoticepop .start-study").click()
            page.wait_for_timeout(1500)
        page.wait_for_selector("iframe#frame_content-zj", timeout=20000)
        fr = page.frame(name="frame_content-zj")
        fr.wait_for_selector("div.chapter_item", timeout=20000)
        print(f"[单章测试] 点击章节 {NODE_ID}...")
        fr.locator(f"div.chapter_item#cur{NODE_ID}").click()
        page.wait_for_timeout(6000)

        # 播放前状态
        kcards = None
        for f in page.frames:
            if "knowledge/cards" in (f.url or ""):
                kcards = f; break
        if kcards:
            print("[单章测试] 播放前任务点状态:", json.dumps(check_task_status(kcards, NODE_ID), ensure_ascii=False))

        # 播放视频
        player = find_player_frame(page)
        if not player:
            print("[单章测试] ❌ 未找到播放器"); return
        player.wait_for_load_state("domcontentloaded", timeout=20000)

        print("[单章测试] 开始监测播放（约需 7 分钟，正常播放）...")
        result = monitor_playback(page, player, progress_threshold=90, poll=5)
        print(f"[单章测试] 播放结果: {result.get('reason')}")
        print(f"[单章测试] 最终状态: {result.get('final')}")

        # 播放后状态
        if kcards:
            try:
                kcards.reload() if hasattr(kcards, 'reload') else None
            except Exception:
                pass
            page.wait_for_timeout(2000)
            print("[单章测试] 播放后任务点状态:", json.dumps(check_task_status(kcards, NODE_ID), ensure_ascii=False))

        # 检查目录页该节点的完成标识（回到目录 iframe）
        try:
            node_status = fr.locator(f"div.chapter_item#cur{NODE_ID}").get_attribute("class")
            print(f"[单章测试] 目录节点 class: {node_status}")
        except Exception as e:
            print(f"[单章测试] 目录状态读取失败: {e}")

        # 落库
        if result.get("ok"):
            db.update_task_state("ai_tools", NODE_ID, "COMPLETED", "正常播放达标≥90%")
            db.update_task_meta("ai_tools", NODE_ID,
                                content_types=["video", "quiz"],
                                meta={"duration": result.get("duration"),
                                      "final": result.get("final")})
        else:
            db.update_task_state("ai_tools", NODE_ID, "ERROR", result.get("reason", "未知"))
        db.set_run_state("last_tested_node", NODE_ID)
        print("[单章测试] 结果已落库。统计:", db.summary("ai_tools"))
        db.close()


if __name__ == "__main__":
    main()
