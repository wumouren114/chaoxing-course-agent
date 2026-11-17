"""只读：dump 课程目录前几个章节节点的真实 HTML，弄清平台完成标记结构。"""
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "data" / "storage_state.json"
URL = "https://mooc1.chaoxing.com/visit/stucoursemiddle?courseid=268560848&clazzid=158282453&cpi=575101306&ismooc2=1&v=2"

with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=True)
    ctx = browser.new_context(storage_state=str(STATE), viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.goto(URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(5000)
    if page.locator(".coursenoticepop .start-study").count() > 0:
        page.locator(".coursenoticepop .start-study").click()
        page.wait_for_timeout(1500)
    page.wait_for_selector("iframe#frame_content-zj", timeout=20000)
    fr = page.frame(name="frame_content-zj")
    fr.wait_for_selector("div.chapter_item", timeout=20000)

    # 顶部进度区完整 HTML
    top = fr.evaluate("""() => {
        const els = Array.from(document.querySelectorAll('*')).filter(e =>
            e.children.length===0 && /任务点|已完成/.test(e.textContent||''));
        return els.slice(0,6).map(e => ({tag:e.tagName, cls:(e.className||'').toString(), txt:e.textContent.trim().slice(0,60), parentCls:(e.parentElement?.className||'').toString()}));
    }""")
    print("=== 顶部进度元素 ===")
    import json
    print(json.dumps(top, ensure_ascii=False, indent=2))

    # 前 6 个章节节点完整 HTML
    nodes = fr.evaluate("""() => Array.from(document.querySelectorAll('div.chapter_item')).slice(0,6).map(n => ({
        id:n.id, cls:(n.className||'').toString(), outer:n.outerHTML.slice(0, 1200)
    }))""")
    print("\n=== 前6个章节节点 ===")
    for n in nodes:
        print(f"\n--- id={n['id']} cls={n['cls']} ---")
        print(n["outer"])
    browser.close()
