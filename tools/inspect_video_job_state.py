"""只读探查：打开脚本声称'已完成'的章节，看平台知识卡片里视频任务点的真实状态。"""
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "data" / "storage_state.json"
URL = "https://mooc1.chaoxing.com/visit/stucoursemiddle?courseid=268560848&clazzid=158282453&cpi=575101306&ismooc2=1&v=2"
NODE = "1221807919"  # 2.1 认识AI写作，脚本数据库标记为 COMPLETED

with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=True)
    ctx = browser.new_context(storage_state=str(STATE), viewport={"width": 1440, "height": 900})
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
    print("[探查] 章节:", node.get_attribute("title"))
    print("[探查] 目录完成标记:", node.evaluate("n => { const t=n.querySelector('.bntHoverTips'); return t?t.textContent.trim():'(无)'; }"))
    node.scroll_into_view_if_needed()
    node.click()
    page.wait_for_timeout(7000)

    # 找知识卡片 iframe
    kc = None
    for f in page.frames:
        if "knowledge/cards" in (f.url or "") or "knowledgeCard" in (f.url or ""):
            kc = f; break
    print("[探查] 知识卡片frame:", kc.url if kc else "(未找到)")

    if kc:
        states = kc.evaluate("""() => {
            const out=[];
            document.querySelectorAll('[aria-label]').forEach(e=>{
                const a=e.getAttribute('aria-label')||'';
                if(/任务点|已完成|未完成/.test(a)) out.push({tag:e.tagName, cls:(e.className||'').toString().slice(0,60), label:a});
            });
            return out;
        }""")
        print("[探查] 任务点状态:")
        for s in states:
            print("   ", s)
        # 也 dump 视频相关容器文本
        txt = kc.evaluate("() => document.body.innerText.slice(0,500)")
        print("[探查] 卡片正文:", txt.replace("\n", " | ")[:300])
    browser.close()
