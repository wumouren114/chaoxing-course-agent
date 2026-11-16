"""
可视化运行器 v2 —— 无头安静播放 + 低频状态更新
关键修复：播放期间不截图、不高频轮询 DOM，避免触发平台"失焦即暂停"机制。
监控面板靠低频文字状态更新；播放结束后才截图。
严格正常播放，不拖拽、不伪造、不绕过检测。

用法：python tools/run_visual.py [course] [node_id]
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, ".")
from core.auth import Session
from core.video import find_player_frame, read_state, click_play, monitor_playback
from core.database import Database
from core.live_state import LiveState
from core.report import generate_report, COURSE_NAMES
from core.catalog import parse_catalog_html, fetch_chapter_html

ROOT = Path(__file__).resolve().parent.parent
MIDDLE = {
    "ai_tools": "https://mooc1.chaoxing.com/visit/stucoursemiddle?courseid=268560848&clazzid=158282453&cpi=575101306&ismooc2=1&v=2",
    "ai_principle": "https://mooc1.chaoxing.com/visit/stucoursemiddle?courseid=268560836&clazzid=158282442&cpi=575101306&ismooc2=1&v=2",
}


def verify_platform_completion(page, course, node_id):
    """播放后回目录页核对平台真实完成状态（关键：不靠播放器进度臆断）"""
    try:
        # 播放后页面可能停留在播放器，必须重新导航到课程主页再核对
        page.goto(MIDDLE[course], wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)
        if page.locator(".coursenoticepop .start-study").count() > 0:
            page.locator(".coursenoticepop .start-study").click()
            page.wait_for_timeout(1500)
        page.wait_for_selector("iframe#frame_content-zj", timeout=20000)
        fr = page.frame(name="frame_content-zj")
        fr.wait_for_selector("div.chapter_item", timeout=20000)
        body = fr.locator("body").inner_text(timeout=5000)
        top = body.split("\n")[0] if body else ""
        node = fr.locator(f"div.chapter_item#cur{node_id}")
        cls = node.get_attribute("class") if node.count() > 0 else ""
        # 判断：样式类里没有 catalog_tishi120（未完成标记）即认为平台判完成
        import re
        done = "catalog_tishi120" not in (cls or "")
        # 更可靠：看顶部进度是否增长
        m = re.search(r"(\d+)/(\d+)", top)
        top_done = int(m.group(1)) if m else -1
        return {"confirmed": done, "top_progress": top.strip(),
                "top_done": top_done, "node_class": cls,
                "reason": "平台样式判定"}
    except Exception as e:
        return {"confirmed": False, "reason": f"核对出错: {e}"}


def main():
    course = sys.argv[1] if len(sys.argv) > 1 else "ai_tools"
    node_id = sys.argv[2] if len(sys.argv) > 2 else "1221807919"

    ls = LiveState()
    ls.reset()
    ls.event("运行器启动（无头安静模式）", "ok")
    db = Database()
    db.upsert_course(course, COURSE_NAMES.get(course, course),
                     "268560848" if course == "ai_tools" else "268560836",
                     "158282453" if course == "ai_tools" else "158282442",
                     "575101306")
    db.upsert_task(course, node_id, "2.1", "认识AI写作", 2)

    with Session(headless=True) as s:  # 无头：无窗口焦点争夺
        page = s.page
        ls.update(running=True, control="RUNNING", course=course,
                  course_name=COURSE_NAMES.get(course, course),
                  stage="登录", message="正在登录…")
        if not s.ensure_login():
            ls.update(stage="登录失败", running=False, message="登录失败")
            ls.event("登录失败", "error")
            return
        ls.event("登录成功", "ok")

        ls.update(stage="打开课程", message="进入课程页面…")
        page.goto(MIDDLE[course], wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)
        if page.locator(".coursenoticepop .start-study").count() > 0:
            page.locator(".coursenoticepop .start-study").click()
            page.wait_for_timeout(1500)
        page.wait_for_selector("iframe#frame_content-zj", timeout=20000)
        fr = page.frame(name="frame_content-zj")
        fr.wait_for_selector("div.chapter_item", timeout=20000)
        node = fr.locator(f"div.chapter_item#cur{node_id}")
        title = node.get_attribute("title") or node_id
        ls.update(task=node_id, task_title=title, stage="打开章节", message=f"进入 {title}")
        ls.event(f"打开章节 {title}", "ok")
        node.click()
        page.wait_for_timeout(6000)

        player = find_player_frame(page)
        if not player:
            ls.update(stage="异常", message="未找到播放器", running=False)
            ls.event("未找到播放器", "error")
            return
        player.wait_for_load_state("domcontentloaded", timeout=20000)

        # 低频状态更新：每轮只读一次状态写文件，不截图、不做多余DOM操作
        tick = [0]

        def on_tick(st):
            tick[0] += 1
            ls.update(
                stage="视频播放监测（后台安静播放）",
                video={"current": st.get("current_time", 0),
                       "duration": st.get("duration", 0),
                       "pct": st.get("progress_pct", 0),
                       "paused": st.get("paused", True),
                       "display": f"{st.get('time_display','0:00')} / {st.get('duration_display','0:00')}"},
                message="后台正常播放中（无窗口干扰）",
            )
            if tick[0] % 10 == 0:
                ls.event(f"播放进度 {st.get('progress_pct',0)}%")

        ls.event("开始后台播放（不截图不干扰）", "ok")
        result = monitor_playback(page, player, progress_threshold=90, poll=5, on_tick=on_tick)
        ls.event(f"播放结束: {result.get('reason')}",
                 "ok" if result.get("ok") else "error")

        # 播放结束后才截图（此时不影响播放）
        ls.screenshot(page)

        # 关键：核对平台真实完成状态
        ls.update(stage="核对平台完成状态", message="正在核对平台是否判定完成…")
        time.sleep(2)
        confirm = verify_platform_completion(page, course, node_id)
        ls.event(f"平台核对: {confirm.get('top_progress')} / {confirm.get('reason')}",
                 "ok" if confirm.get("confirmed") else "warn")

        if result.get("ok") and confirm.get("confirmed"):
            db.update_task_state(course, node_id, "COMPLETED", "播放达标且平台确认完成")
            ls.update(stage="完成", message="平台确认完成")
            ls.event("✅ 平台确认任务完成", "ok")
        elif result.get("ok") and not confirm.get("confirmed"):
            db.update_task_state(course, node_id, "NEEDS_REVIEW",
                                 f"播放达标但平台未完成: {confirm.get('top_progress')}")
            ls.update(stage="未获平台确认", message="播放达标但平台仍判未完成")
            ls.event("⚠️ 播放达标但平台未判完成", "warn")
        else:
            db.update_task_state(course, node_id, "ERROR", result.get("reason", "未知"))
            ls.update(stage="异常", message=result.get("reason", "播放异常"))

        summary = db.summary(course)
        ls.update(running=False, control="STOPPED", stage="本次验证结束",
                  stats={"total": summary["total"], "completed": summary["completed"],
                         "skipped": summary["skipped"], "review": summary["needs_review"],
                         "errors": summary["errors"], "pct": summary["progress_pct"]},
                  message="验证结束，详见报告")
        report = generate_report(db, course)
        ls.event(f"报告: {report.name}")
        print(f"[运行器] 播放: {result.get('reason')}")
        print(f"[运行器] 平台核对: {confirm}")
        print(f"[运行器] 报告: {report}")


if __name__ == "__main__":
    main()
