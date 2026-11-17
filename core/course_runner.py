"""
整门课批量播放器 —— 按目录顺序自动播放所有视频
设计：
- 从数据库取 WAITING 任务，按目录顺序
- 每章节：进入→识别内容→播放所有视频→核对平台完成→落状态
- 单章节异常隔离，记录后继续
- 断点续跑：每节处理完即存库
- 边界：随课弹题走"抓题→助手作答→自动提交"流程；考试/考核拒绝作答
严格正常播放，不拖拽、不伪造、不绕过检测。
"""
import time
import re
from pathlib import Path
from typing import Optional, Dict, List

from core.auth import Session
from core.database import Database
from core.video import find_player_frame, read_state, click_play, monitor_playback
from core.catalog import COURSES
from core.live_state import LiveState
from core.report import COURSE_NAMES
from core.logger import get_logger
from core.control import ControlManager, detect_human_intervention

log = get_logger("runner")
ROOT = Path(__file__).resolve().parent.parent

MIDDLE = {
    "ai_tools": "https://mooc1.chaoxing.com/visit/stucoursemiddle?courseid=268560848&clazzid=158282453&cpi=575101306&ismooc2=1&v=2",
    "ai_principle": "https://mooc1.chaoxing.com/visit/stucoursemiddle?courseid=268560836&clazzid=158282442&cpi=575101306&ismooc2=1&v=2",
}


def open_course(s: Session, course: str):
    """打开课程主页，返回目录 iframe"""
    page = s.page
    page.goto(MIDDLE[course], wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(5000)
    if page.locator(".coursenoticepop .start-study").count() > 0:
        page.locator(".coursenoticepop .start-study").click()
        page.wait_for_timeout(1500)
    page.wait_for_selector("iframe#frame_content-zj", timeout=20000)
    fr = page.frame(name="frame_content-zj")
    fr.wait_for_selector("div.chapter_item", timeout=20000)
    return fr


def enter_chapter(page, fr, node_id):
    """从目录点击进入指定章节"""
    node = fr.locator(f"div.chapter_item#cur{node_id}")
    if node.count() == 0:
        raise ValueError(f"目录中未找到章节节点 {node_id}")
    title = node.get_attribute("title") or node_id
    node.click()
    page.wait_for_timeout(5000)
    return title


def find_all_video_frames(page, timeout=30, poll=2, min_count=1):
    """找出当前页面所有视频播放器 iframe。

    视频 iframe 常为延迟加载：进入章节后立即读取 page.frames 可能为空，
    导致把"有视频的章节"误判为"纯文档/测验章节"（见 4.2 的误判）。
    这里做带超时的轮询等待，直到出现至少 min_count 个视频 frame 或超时。
    """
    import time as _t
    deadline = _t.time() + timeout
    found = [f for f in page.frames if "ananas/modules/video" in (f.url or "")]
    while len(found) < min_count and _t.time() < deadline:
        page.wait_for_timeout(int(poll * 1000))
        found = [f for f in page.frames if "ananas/modules/video" in (f.url or "")]
    return found


def check_chapter_completion(fr, node_id) -> Dict:
    """核对目录中该章节的完成状态。

    关键修复（2026-11-17）：任务的"未完成"标记 catalog_tishi120 并不在
    div.chapter_item 自身 class 上，而在子元素 .catalog_jindu 上。旧实现检查错
    元素，导致永远读出"已完成"、数据库记假账。改用平台原生的 .bntHoverTips
    文本（'已完成' / 'X个待完成任务点'）判定，与网页版一致。
    """
    try:
        node = fr.locator(f"div.chapter_item#cur{node_id}")
        if node.count() == 0:
            return {"confirmed": False, "reason": "节点不存在"}
        text = node.inner_text(timeout=5000)
        # 平台原生完成标记：.bntHoverTips 文本 == '已完成'
        tip = ""
        tips = node.locator(".bntHoverTips")
        for i in range(tips.count()):
            t = (tips.nth(i).text_content() or "").strip()
            if t:
                tip = t
        done = (tip == "已完成")
        # 兜底：若该章节确实没有任务点，也算无需处理
        cls = node.get_attribute("class") or ""
        # 节点文本末尾的数字 = 剩余待完成任务点数
        m = re.search(r"(\d+)\s*$", text.strip())
        remaining = int(m.group(1)) if m else -1
        return {"confirmed": done, "remaining": remaining, "tip": tip,
                "text": text.replace("\n", " ")[:80], "node_class": cls}
    except Exception as e:
        return {"confirmed": False, "reason": str(e)}


def process_chapter(s: Session, task: dict, ls: Optional[LiveState] = None) -> Dict:
    """
    处理单个章节：进入→播放所有视频→核对完成
    返回 result dict
    """
    node_id = task["node_id"]
    page = s.page
    result = {"status": "NEEDS_REVIEW", "reason": "", "videos_played": 0}

    # 无任务点的章节直接跳过，不进播放器
    if task.get("job_count", 0) == 0:
        result["status"] = "SKIPPED"
        result["reason"] = "该章节无任务点，无需播放"
        return result

    try:
        fr = open_course(s, task["course"])
        # 轻量检测人工环节（仅读文本，不截图不干扰播放）
        intervention = detect_human_intervention(page)
        if intervention:
            result["intervention"] = intervention
            result["status"] = "NEEDS_REVIEW"
            result["reason"] = f"需要人工处理: {intervention}"
            return result
        title = enter_chapter(page, fr, node_id)
        log.info(f"进入章节 {node_id} {title}")
        if ls:
            ls.update(task=node_id, task_title=title, stage="处理章节", message=f"进入 {title}")

        # 播放当前页面所有视频（带轮询等待，兼容视频 iframe 延迟加载）
        players = find_all_video_frames(page, timeout=30)
        log.info(f"章节 {node_id} 发现 {len(players)} 个视频（已等待最多30秒）")
        if not players:
            result["status"] = "NEEDS_REVIEW"
            result["reason"] = "等待30秒后仍未发现视频（可能是纯文档/测验章节）"
            return result

        # 暂停回调：检测弹题并走作答流程（把 course/node/title 绑定到闭包）
        from core.quiz_handler import handle_pause_for_quiz
        def _on_pause(pg, pf):
            return handle_pause_for_quiz(pg, pf, task["course"], node_id,
                                         wait_seconds=600, context=title)

        all_ok = True
        for idx, player in enumerate(players):
            player.wait_for_load_state("domcontentloaded", timeout=20000)
            if ls:
                ls.update(stage=f"播放视频 {idx+1}/{len(players)}", message=f"{title}")
            # 必须播到视频真正结尾：monitor_playback 现以 ended / 到片尾为准，
            # 单纯"进度≥90%"不再触发完成，避免续播视频在90%处提前跳下一节。
            played = monitor_playback(page, player, progress_threshold=99.9, poll=5,
                                      on_pause=_on_pause)
            if not played.get("ok"):
                all_ok = False
                log.warning(f"章节 {node_id} 视频{idx+1}播放失败: {played.get('reason')}")
                break
            result["videos_played"] += 1

        # 视频播完后，处理章节内的独立测验（"2测验"tab）
        # 检测 → 抓题 → 入协作队列（等助手作答）→ 点选提交 → 核验
        try:
            import os
            from core import chapter_quiz as cq
            quiz_wait = int(os.environ.get("QUIZ_WAIT_SECONDS", "0"))
            if quiz_wait > 0 and cq.has_quiz(page):
                if ls:
                    ls.update(stage="章节测验作答", message=f"{title} - 等待作答")
                # 重新进入章节，确保测验tab可点
                fr_q = open_course(s, task["course"])
                enter_chapter(page, fr_q, node_id)
                qr = cq.answer_quiz(page, task["course"], node_id, wait_seconds=quiz_wait)
                result["quiz"] = qr
                log.info(f"章节测验结果 {node_id}: {qr.get('status')} - {qr.get('reason')}")
                if ls:
                    ls.event(f"测验 {task.get('number','')}: {qr.get('status')}",
                             "ok" if qr.get("status") == "answered" else "warn")
        except Exception as e:
            log.warning(f"章节测验处理异常 {node_id}: {e}")

        # 核对平台完成（重新加载目录）
        fr2 = open_course(s, task["course"])
        confirm = check_chapter_completion(fr2, node_id)
        result["confirm"] = confirm

        if all_ok and confirm.get("confirmed"):
            result["status"] = "COMPLETED"
            result["reason"] = f"播放{result['videos_played']}个视频，平台确认完成"
        elif all_ok and not confirm.get("confirmed"):
            # 可能还有测验任务点未完成
            remaining = confirm.get("remaining", -1)
            if remaining and remaining > 0:
                result["status"] = "NEEDS_REVIEW"
                result["reason"] = f"视频已完成，但仍有{remaining}个任务点（测验/问卷）需人工处理"
            else:
                result["status"] = "NEEDS_REVIEW"
                result["reason"] = "播放达标但平台未判完成"
        else:
            result["status"] = "ERROR"
            result["reason"] = "视频播放未完成"

    except Exception as e:
        log.exception(f"处理章节 {node_id} 异常: {e}")
        result["status"] = "ERROR"
        result["reason"] = f"异常: {e}"

    return result


def run_course(course: str, db: Database, limit: Optional[int] = None,
               ls: Optional[LiveState] = None, profile=None, state_file=None,
               signal_file=None, resume_file=None) -> Dict:
    """批量运行整门课（或前 limit 个任务），返回统计
    profile / state_file / signal_file / resume_file：多课程并行时的隔离参数
    """
    log.info(f"开始整门课播放: {course}, limit={limit}")
    ctrl = ControlManager(ls, signal_file=signal_file, resume_file=resume_file)
    if ls:
        ls.reset()
        ls.update(running=True, control="RUNNING", course=course,
                  course_name=COURSE_NAMES.get(course, course), stage="启动", message="整门课播放启动")
        ls.event("整门课批量播放启动", "ok")

    processed = 0
    with Session(headless=True, profile=profile, state_file=state_file) as s:
        if not s.ensure_login():
            log.error("登录失败")
            if ls: ls.update(running=False, stage="登录失败", message="登录失败")
            return {"error": "登录失败"}
        if ls: ls.event("登录成功", "ok")

        while True:
            # 检查停止/暂停信号
            if ctrl.stopped:
                log.info("收到停止信号")
                if ls: ls.event("⏹ 收到停止指令", "warn")
                break
            ctrl.wait_if_paused(ls)

            if limit and processed >= limit:
                log.info(f"达到 limit={limit}，停止")
                break
            tasks = db.get_tasks(course, states=["WAITING", "ERROR"])
            if not tasks:
                log.info("没有待处理任务")
                break
            task = tasks[0]
            node_id = task["node_id"]

            # 无任务点直接跳过
            if task.get("job_count", 0) == 0:
                db.update_task_state(course, node_id, "SKIPPED", "该章节无任务点，无需播放")
                processed += 1
                continue

            # 标记 RUNNING
            db.update_task_state(course, node_id, "RUNNING", "批量播放器领取")
            db.set_run_state(f"last_{course}", node_id)

            # 处理
            result = process_chapter(s, task, ls)

            # 若结果提示遇到人工环节，挂起等待用户处理
            if result.get("intervention"):
                log.warning(f"检测到人工环节: {result['intervention']}")
                resumed = ctrl.suspend_for_human(result["intervention"], ls)
                if not resumed:
                    db.update_task_state(course, node_id, "NEEDS_REVIEW",
                                         f"人工环节未处理: {result['intervention']}")
                    processed += 1
                    continue
                # 用户确认后重试该章节
                result = process_chapter(s, task, ls)

            # 落状态
            status = result["status"]
            state_map = {"COMPLETED": "COMPLETED", "NEEDS_REVIEW": "NEEDS_REVIEW",
                         "ERROR": "ERROR", "SKIPPED": "SKIPPED"}
            db.update_task_state(course, node_id, state_map.get(status, "ERROR"), result["reason"])
            if result.get("videos_played"):
                db.update_task_meta(course, node_id, content_types=["video"],
                                    meta={"videos_played": result["videos_played"],
                                          "confirm": result.get("confirm")})
            if status == "ERROR":
                db.log_anomaly(course, node_id, "chapter_error", result["reason"])

            processed += 1
            log.info(f"[{processed}] {node_id} -> {status}: {result['reason']}")
            if ls:
                ls.event(f"[{processed}] {task.get('number','')} {task['title']} → {status}",
                         "ok" if status == "COMPLETED" else "warn")
                summary_tmp = db.summary(course)
                ls.update(stats={"total": summary_tmp["total"], "completed": summary_tmp["completed"],
                                 "skipped": summary_tmp["skipped"], "review": summary_tmp["needs_review"],
                                 "errors": summary_tmp["errors"], "pct": summary_tmp["progress_pct"]})

    summary = db.summary(course)
    if ls:
        ls.update(running=False, control="STOPPED", stage="批量播放结束", message="运行结束")
        ls.event("批量播放结束", "ok")
    log.info(f"批量播放结束: {summary}")
    return summary


if __name__ == "__main__":
    # 测试：只跑 2 个 WAITING 任务
    import sys
    db = Database()
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    ls = LiveState()
    result = run_course("ai_tools", db, limit=limit, ls=ls)
    print("结果:", result)
    db.close()
