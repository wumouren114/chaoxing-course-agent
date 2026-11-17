"""
抓包诊断：监听视频播放过程中的上报请求，定位"平台为什么不判完成"。

- 隔离会话（独立 browser + storage_state），不碰正在播放的 profile。
- 正常点击播放，不拖拽进度、不伪造数据 —— 只观察上报请求。
- 采集 90 秒内的 XHR/fetch，重点看含 jobid/clazzid/duration/report 的上报。

用法：
  .venv/Scripts/python -u tools/trace_video_report.py [node_id] [seconds]
默认 node=1221807919 (2.1 认识AI写作), seconds=90
"""
import json
import sys
import time
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "data" / "storage_state.json"
URL = "https://mooc1.chaoxing.com/visit/stucoursemiddle?courseid=268560848&clazzid=158282453&cpi=575101306&ismooc2=1&v=2"
NODE = sys.argv[1] if len(sys.argv) > 1 else "1221807919"
SECONDS = int(sys.argv[2]) if len(sys.argv) > 2 else 90

KEYWORDS = ("jobid", "clazzid", "duration", "report", "ananas", "video", "progress",
            "studytime", "playTime", "multimedia", "mooc-ans", "status", "track", "log")

records = []


def on_request(req):
    u = req.url
    low = u.lower()
    if req.resource_type in ("xhr", "fetch") or any(k.lower() in low for k in KEYWORDS):
        q = parse_qs(urlparse(u).query)
        # 只保留携带上报特征的请求，避免刷屏
        interesting = any(k in q for k in ("jobid", "clazzid", "duration", "d", "playTime", "ut", "objectId"))
        if not interesting and req.resource_type not in ("xhr", "fetch"):
            return
        records.append({
            "dir": "REQ", "method": req.method, "url": u[:400],
            "post": (req.post_data or "")[:500],
            "params": {k: v[0] for k, v in q.items()},
        })


def on_response(resp):
    u = resp.url
    low = u.lower()
    q = parse_qs(urlparse(u).query)
    if any(k in q for k in ("jobid", "clazzid", "duration", "playTime", "objectId")) or any(k.lower() in low for k in ("report", "status", "progress")):
        try:
            body = resp.text()[:400]
        except Exception:
            body = "(无法读取)"
        records.append({
            "dir": "RESP", "status": resp.status, "url": u[:400],
            "body": body,
            "params": {k: v[0] for k, v in q.items()},
        })


def main():
    if not STATE.exists():
        print("[抓包] 缺少 storage_state.json"); return
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        ctx = browser.new_context(storage_state=str(STATE), viewport={"width": 1440, "height": 900})
        ctx.on("request", on_request)
        ctx.on("response", on_response)
        page = ctx.new_page()

        page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(6000)
        if page.locator(".coursenoticepop .start-study").count() > 0:
            page.locator(".coursenoticepop .start-study").click()
            page.wait_for_timeout(1500)
        page.wait_for_selector("iframe#frame_content-zj", timeout=20000)
        fr = page.frame(name="frame_content-zj")
        fr.wait_for_selector("div.chapter_item", timeout=20000)
        node = fr.locator(f"div.chapter_item#cur{NODE}")
        print(f"[抓包] 章节: {node.get_attribute('title')}")
        node.scroll_into_view_if_needed()
        node.click()
        print(f"[抓包] 已点击章节，等待视频 frame 加载...")
        page.wait_for_timeout(8000)

        player = None
        for f in page.frames:
            if "ananas/modules/video" in (f.url or ""):
                player = f; break
        if not player:
            print("[抓包] ❌ 未找到播放器 frame"); browser.close(); return
        print("[抓包] 播放器 frame:", player.url[:160])

        st = player.evaluate("""() => {const v=document.querySelector('video');return v?{dur:v.duration,cur:v.currentTime,paused:v.paused}:null}""")
        print("[抓包] 播放前状态:", st)

        # 正常点击播放（不拖拽）
        try:
            big = player.locator("button.vjs-big-play-button")
            if big.count() > 0 and big.is_visible():
                big.click(timeout=3000)
            else:
                player.evaluate("() => {const v=document.querySelector('video'); if(v) v.play();}")
        except Exception as e:
            player.evaluate("() => {const v=document.querySelector('video'); if(v) v.play();}")
        print(f"[抓包] 已点击播放，采集 {SECONDS} 秒上报请求...")

        baseline = len(records)
        for i in range(SECONDS // 15):
            page.wait_for_timeout(15000)
            # frame 可能在完成时被卸载，动态重新定位
            try:
                cur_player = player
                if cur_player.is_detached():
                    cur_player = None
                    for f in page.frames:
                        if "ananas/modules/video" in (f.url or ""):
                            cur_player = f; break
                if cur_player:
                    s = cur_player.evaluate("""() => {const v=document.querySelector('video');return v?{cur:Math.round(v.currentTime),paused:v.paused,dur:v.duration}:null}""")
                    print(f"  +{(i+1)*15}s  进度={s}")
                else:
                    print(f"  +{(i+1)*15}s  播放器frame已卸载（可能发生跳转/重载）")
            except Exception as e:
                print(f"  +{(i+1)*15}s  读取异常: {str(e)[:60]}")

        browser.close()

    print("\n" + "=" * 70)
    print(f"播放期间网络请求（共 {len(records)} 条，新增 {len(records)-baseline}）")
    print("=" * 70)
    # 聚合同一 URL 的请求次数
    from collections import Counter
    req_urls = Counter()
    for r in records:
        if r["dir"] == "REQ":
            # 去掉时间戳类参数做聚合
            key = r["url"].split("?")[0]
            req_urls[key] += 1
    print("\n--- 上报接口聚合（URL 路径 : 次数） ---")
    for url, cnt in req_urls.most_common(30):
        print(f"  {cnt:>3}x  {url}")

    print("\n--- 携带 jobid 的请求详情（前 12 条） ---")
    shown = 0
    for r in records:
        if r["dir"] == "REQ" and "jobid" in r["params"]:
            print(f"  [{r['method']}] {r['url'][:200]}")
            print(f"        params: {json.dumps(r['params'], ensure_ascii=False)[:350]}")
            if r["post"]:
                print(f"        POST: {r['post'][:250]}")
            shown += 1
            if shown >= 12: break
    if shown == 0:
        print("  ⚠️ 没有捕获到任何携带 jobid 的上报请求！")

    print("\n--- 上报响应（前 10 条） ---")
    shown = 0
    for r in records:
        if r["dir"] == "RESP":
            print(f"  [{r['status']}] {r['url'][:180]}")
            print(f"        body: {r['body'][:200]}")
            shown += 1
            if shown >= 10: break
    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
