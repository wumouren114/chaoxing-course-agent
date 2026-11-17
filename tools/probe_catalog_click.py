"""只读探查：模拟用户点开章节/点任务点标记，观察目录完成计数是否刷新。"""
from pathlib import Path
from playwright.sync_api import sync_playwright

URL = "https://mooc1.chaoxing.com/visit/stucoursemiddle?courseid=268560848&clazzid=158282453&cpi=575101306&ismooc2=1&v=2"
STATE = str(Path("data/storage_state.json").resolve())
NODE = "1221807919"

STATE_JS = """n => {
    const j = n.querySelector('.catalog_jindu');
    const t = n.querySelector('.bntHoverTips');
    const k = n.querySelector('.knowledgeJobCount');
    return {jindu: j ? j.className : '', tip: t ? t.textContent.trim() : '', count: k ? k.value : ''};
}"""

with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge", headless=True)
    ctx = b.new_context(storage_state=STATE)
    pg = ctx.new_page()
    pg.goto(URL, wait_until="domcontentloaded", timeout=60000)
    pg.wait_for_timeout(7000)
    if pg.locator(".coursenoticepop .start-study").count() > 0:
        pg.locator(".coursenoticepop .start-study").click()
        pg.wait_for_timeout(1500)
    fr = pg.frame(name="frame_content-zj")
    fr.wait_for_selector("div.chapter_item", timeout=20000)

    def state():
        n = fr.locator(f"div.chapter_item#cur{NODE}")
        return n.evaluate(STATE_JS)

    def top():
        txt = fr.locator("body").inner_text(timeout=8000)
        import re
        return re.findall(r"已完成任务点[：:\s]*(\d+)\s*/\s*(\d+)", txt)

    print("初始:", state(), "顶部", top())

    node = fr.locator(f"div.chapter_item#cur{NODE}")
    node.locator(".clicktitle").click()
    pg.wait_for_timeout(10000)
    print("进入章节后:", state(), "顶部", top())

    # 回到课程主页重读
    pg.goto(URL, wait_until="domcontentloaded", timeout=60000)
    pg.wait_for_timeout(7000)
    fr = pg.frame(name="frame_content-zj")
    fr.wait_for_selector("div.chapter_item", timeout=20000)
    print("回主页后:", state(), "顶部", top())

    b.close()
