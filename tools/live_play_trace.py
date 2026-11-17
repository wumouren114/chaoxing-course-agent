"""
有头实时播放 + 全程抓包诊断（用户可在桌面看到浏览器画面）。

目标：查清"视频播了但平台不认完成"的根因。
- 有头浏览器（headless=False），正常点击播放，不拖拽进度、不伪造数据
- 全程监听上报请求（含 jobid 的心跳/完成上报）
- 实时状态写到 web/live_trace_status.json（可随时查看）
- 暂停时检测弹题，走既有 handle_pause_for_quiz 自动作答
- 播放到阈值后，重新加载目录核对平台完成标记

用法：
  .venv/Scripts/python -u tools/live_play_trace.py ai_tools <node_id>
  .venv/Scripts/python -u tools/live_play_trace.py ai_principle <node_id>
"""
import json
import sys
import time
import re
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from collections import Counter
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
STATUS = ROOT / "web" / "live_trace_status.json"
TRACE = ROOT / "data" / "video_report_trace.jsonl"
STATE = ROOT / "data" / "storage_state.json"

COURSES = {
    "ai_tools": {
        "name": "人人都能上手的AI工具",
        "url": "https://mooc1.chaoxing.com/visit/stucoursemiddle?courseid=268560848&clazzid=158282453&cpi=575101306&ismooc2=1&v=2",
    },
    "ai_principle": {
        "name": "生成式人工智能原理及其影响和应用",
        "url": "https://mooc1.chaoxing.com/visit/stucoursemiddle?courseid=268560836&clazzid=158282442&cpi=575101306&ismooc2=1&v=2",
    },
}

course_key = sys.argv[1] if len(sys.argv) > 1 else "ai_tools"
node_id = sys.argv[2] if len(sys.argv) > 2 else "1221807919"
COURSE = COURSES[course_key]
# 复用已有登录态的 profile（第一门课已跑完，主 profile 空闲）
PROFILE = ROOT / "data" / ("browser_profile" if course_key == "ai_tools" else "browser_profile_principle")

report_events = []


def status(**kw):
    d = {"course": COURSE["name"], "node_id": node_id, "ts": time.strftime("%H:%M:%S")}
    d.update(kw)
    STATUS.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        with open(TRACE, "a", encoding="utf-8") as f:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    except Exception:
        pass


def on_request(req):
    u = req.url
    q = parse_qs(urlparse(u).query)
    # 抓取携带上报特征的请求
    if any(k in q for k in ("jobid", "clazzid", "objectId", "playTime", "duration", "d")) \
       or req.resource_type in ("xhr", "fetch"):
        report_events.append({
            "t": time.strftime("%H:%M:%S"), "dir": "REQ", "method": req.method,
            "url": u[:350], "params": {k: v[0] for k, v in q.items()},
            "post": (req.post_data or "")[:300],
        })


def on_response(resp):
    u = resp.url
    q = parse_qs(urlparse(u).query)
    if any(k in q for k in ("jobid", "clazzid", "objectId")) or "/status" in u or "report" in u.lower():
        try:
            body = resp.text()[:300]
        except Exception:
            body = "(n/a)"
        report_events.append({
            "t": time.strftime("%H:%M:%S"), "dir": "RESP", "status": resp.status,
            "url": u[:350], "body": body,
        })


def read_player(pf):
    return pf.evaluate("""() => {const v=document.querySelector('video.vjs-tech, video');
        if(!v) return null;
        return {cur: Math.round(v.currentTime*10)/10, dur: v.duration,
                paused: v.paused, ended: v.ended, vol: v.volume, muted: v.muted,
                pct: (v.duration>0 && isFinite(v.duration)) ? Math.round(v.currentTime/v.duration*1000)/10 : -1};}""")


def main():
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    status(stage="启动有头浏览器", message="正在打开浏览器（请在桌面查看窗口）")
    with sync_playwright() as p:
        # 用 storage_state 注入新鲜 cookie（persistent profile 登录态已失效）
        browser = p.chromium.launch(channel="msedge", headless=False)
        ctx = browser.new_context(storage_state=str(STATE),
                                  viewport={"width": 1366, "height": 768})
        ctx.on("request", on_request)
        ctx.on("response", on_response)
        page = ctx.new_page()

        status(stage="打开课程", message=COURSE["name"])
        page.goto(COURSE["url"], wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(8000)
        # 诊断：打印实际停留页面
        print(f"[诊断] 当前URL: {page.url}")
        print(f"[诊断] 标题: {page.title()}")
        try:
            print(f"[诊断] 正文前300: {page.locator('body').inner_text(timeout=5000)[:300]}")
        except Exception as e:
            print(f"[诊断] 读正文失败: {e}")
        print(f"[诊断] frames: {[f.url[:80] for f in page.frames]}")

        if page.locator(".coursenoticepop .start-study").count() > 0:
            print("[诊断] 点击'开始学习'")
            page.locator(".coursenoticepop .start-study").click()
            page.wait_for_timeout(2000)
        page.wait_for_timeout(3000)
        try:
            page.wait_for_selector("iframe#frame_content-zj", timeout=20000)
        except Exception:
            print(f"[诊断] ❌ 仍无目录iframe。URL={page.url}")
            print(f"[诊断] frames={[f.url[:100] for f in page.frames]}")
            raise
        fr = page.frame(name="frame_content-zj")
        fr.wait_for_selector("div.chapter_item", timeout=20000)
        node = fr.locator(f"div.chapter_item#cur{node_id}")
        title = node.get_attribute("title") or node_id
        print(f"[直播] 章节: {title}")
        status(stage="进入章节", task_title=title,
               message="目录完成标记: " + node.evaluate("n=>{const t=n.querySelector('.bntHoverTips');return t?t.textContent.trim():'(无)'}"))
        node.scroll_into_view_if_needed()
        node.click()
        page.wait_for_timeout(8000)

        player = None
        for f in page.frames:
            if "ananas/modules/video" in (f.url or ""):
                player = f; break
        if not player:
            status(stage="错误", message="未找到播放器frame"); print("[直播] 未找到播放器"); ctx.close(); return

        before = read_player(player)
        print(f"[直播] 播放前: {before}")
        status(stage="点击播放", message=f"播放前 currentTime={before.get('cur')}s duration={before.get('dur')}",
               video=before)

        # 正常点击播放
        from core.video import click_play
        click_play(player)
        page.wait_for_timeout(3000)

        # 答题回调
        from core.quiz_handler import handle_pause_for_quiz
        def on_pause(pg, pf):
            status(stage="检测暂停/弹题", message="视频暂停，检查是否有弹题")
            return handle_pause_for_quiz(pg, pf, course_key, node_id, wait_seconds=120, context=title)

        start = time.time()
        last_pct = -999
        stalled = 0
        while time.time() - start < 60 * 40:  # 最多40分钟
            try:
                if player.is_detached():
                    for f in page.frames:
                        if "ananas/modules/video" in (f.url or ""):
                            player = f; break
            except Exception:
                pass
            try:
                st = read_player(player)
            except Exception as e:
                status(stage="读取状态异常", message=str(e)[:100])
                page.wait_for_timeout(5000); continue
            if st is None:
                page.wait_for_timeout(5000); continue
            pct = st["pct"]
            if pct != last_pct:
                print(f"[直播] {pct}% cur={st['cur']}/{st['dur']} paused={st['paused']} vol={st['vol']} muted={st['muted']}")
                status(stage="播放中", video=st, message=f"进度 {pct}% 音量={st['vol']} 静音={st['muted']}")
                last_pct = pct
            # 关键修复：必须播到视频真正结束，而非90%——90%对续播视频会提前退出，
            # 导致播放器的完成上报（playingTime≈duration）没机会发出，平台不认完成。
            if st.get("ended") or (isinstance(pct, (int, float)) and pct >= 99.5):
                status(stage="播放结束", message=f"进度{pct}%，ended={st.get('ended')}，等待完成上报", video=st)
                print("[直播] 视频播到结尾，额外等待12秒让完成上报发出...")
                page.wait_for_timeout(12000)
                break
            if st.get("paused") and not st.get("ended"):
                stalled += 1
                if stalled == 1:
                    try:
                        on_pause(page, player)
                    except Exception as e:
                        print(f"[直播] on_pause异常: {e}")
                if stalled >= 3:
                    print("[直播] 暂停过久，点击恢复")
                    click_play(player); stalled = 0
            else:
                stalled = 0
            page.wait_for_timeout(5000)

        # 核对平台完成标记：模拟用户"手点一下"——重新加载后主动再进一次该章节触发缓存刷新
        print("[直播] 重新加载并重新进入该章节，触发目录计数刷新...")
        page.goto(COURSE["url"], wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(6000)
        if page.locator(".coursenoticepop .start-study").count() > 0:
            page.locator(".coursenoticepop .start-study").click()
            page.wait_for_timeout(1200)
        page.wait_for_selector("iframe#frame_content-zj", timeout=20000)
        fr2 = page.frame(name="frame_content-zj")
        fr2.wait_for_selector("div.chapter_item", timeout=20000)
        node2 = fr2.locator(f"div.chapter_item#cur{node_id}")
        mark_before = node2.evaluate("n=>{const t=n.querySelector('.bntHoverTips');return t?t.textContent.trim():'(无)'}")
        top_before = re.findall(r"已完成任务点[：:\s]*(\d+)\s*/\s*(\d+)", fr2.locator("body").inner_text(timeout=8000))
        print(f"[直播] 刷新前: 章标记='{mark_before}' 顶部={top_before}")
        # 主动再点一次章节（等价用户手点），触发服务端同步
        node2.scroll_into_view_if_needed(); node2.click()
        page.wait_for_timeout(9000)
        # 再回到课程主页读最终计数
        page.goto(COURSE["url"], wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(6000)
        if page.locator(".coursenoticepop .start-study").count() > 0:
            page.locator(".coursenoticepop .start-study").click()
            page.wait_for_timeout(1200)
        page.wait_for_selector("iframe#frame_content-zj", timeout=20000)
        fr3 = page.frame(name="frame_content-zj")
        fr3.wait_for_selector("div.chapter_item", timeout=20000)
        node3 = fr3.locator(f"div.chapter_item#cur{node_id}")
        mark = node3.evaluate("n=>{const t=n.querySelector('.bntHoverTips');return t?t.textContent.trim():'(无)'}")
        top = re.findall(r"已完成任务点[：:\s]*(\d+)\s*/\s*(\d+)", fr3.locator("body").inner_text(timeout=8000))
        print(f"[直播] 刷新后: 章标记='{mark}' 顶部={top}")
        status(stage="核对完成", message=f"刷新前[章={mark_before},顶={top_before}] 刷新后[章={mark},顶={top}]")

        # 汇总上报请求
        job_reqs = [e for e in report_events if e["dir"] == "REQ" and "jobid" in e["params"]]
        job_resp = [e for e in report_events if e["dir"] == "RESP"]
        print(f"\n===== 上报请求汇总：携带jobid {len(job_reqs)} 条，响应 {len(job_resp)} 条 =====")
        print("--- playingTime 上报序列（应随时间增长到≈duration才算有效观看）---")
        for e in job_reqs:
            print(f"  {e['t']}  playingTime={e['params'].get('playingTime')}  dur={e['params'].get('duration')}  isdrag={e['params'].get('isdrag')}")
        if job_reqs:
            for e in job_reqs[:8]:
                print(f"  [{e['method']}] {e['url'][:150]}")
                print(f"     {json.dumps(e['params'], ensure_ascii=False)[:250]}")
        else:
            print("  ⚠️ 全程没有携带 jobid 的上报请求！")
        # 保存完整 trace
        (ROOT / "data" / "video_report_trace.json").write_text(
            json.dumps(report_events, ensure_ascii=False, indent=2), encoding="utf-8")
        status(stage="诊断完成", message=f"章标记='{mark}' 平台顶部={top} jobid上报{len(job_reqs)}条")
        print(f"\n[直播] 浏览器保持打开30秒供观察，然后关闭...")
        page.wait_for_timeout(30000)
        ctx.close()


if __name__ == "__main__":
    main()
