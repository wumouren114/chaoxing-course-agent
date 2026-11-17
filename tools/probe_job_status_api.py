"""只读：进入章节页，抓取 studentstudy 返回的各任务点 isPassed 权威状态。"""
import re, json
from pathlib import Path
from playwright.sync_api import sync_playwright

URL = "https://mooc1.chaoxing.com/visit/stucoursemiddle?courseid=268560848&clazzid=158282453&cpi=575101306&ismooc2=1&v=2"
STATE = str(Path("data/storage_state.json").resolve())
NODE = "1221807919"

captured = []

with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge", headless=True)
    ctx = b.new_context(storage_state=STATE)

    def on_resp(resp):
        u = resp.url
        if any(k in u for k in ("studentstudyAjax", "initdatawithviewer", "knowledge/cards")):
            try:
                txt = resp.text()
            except Exception:
                return
            captured.append({"url": u[:200], "body": txt})

    ctx.on("response", on_resp)
    pg = ctx.new_page()
    pg.goto(URL, wait_until="domcontentloaded", timeout=60000)
    pg.wait_for_timeout(7000)
    if pg.locator(".coursenoticepop .start-study").count() > 0:
        pg.locator(".coursenoticepop .start-study").click()
        pg.wait_for_timeout(1500)
    fr = pg.frame(name="frame_content-zj")
    fr.wait_for_selector("div.chapter_item", timeout=20000)
    node = fr.locator(f"div.chapter_item#cur{NODE}")
    node.locator(".clicktitle").click()
    pg.wait_for_timeout(9000)

    print(f"=== 捕获 {len(captured)} 个相关响应 ===")
    for c in captured:
        print("\nURL:", c["url"])
        body = c["body"]
        # 找 isPassed / jobid 相关片段
        for m in re.finditer(r'.{80}isPassed.{120}', body):
            print("   ", m.group(0).replace("\n", " ")[:220])
        # knowledge/cards 页里的 mArg.isPassed
        m = re.search(r'"isPassed"\s*:\s*(true|false)', body)
        if m:
            print("    mArg isPassed =", m.group(1))
    b.close()
