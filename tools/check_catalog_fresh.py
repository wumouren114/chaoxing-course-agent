"""决定性核验：多次刷新目录，检查若干章节的完成标记类名 + 顶部计数，排除缓存。"""
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "data" / "storage_state.json"
URL = "https://mooc1.chaoxing.com/visit/stucoursemiddle?courseid=268560848&clazzid=158282453&cpi=575101306&ismooc2=1&v=2"
NODES = ["1221807919", "1221807924", "1221808048", "1221808098"]  # 2.1 2.4 5.x 8.5(脚本称完成)

with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=True)
    ctx = browser.new_context(storage_state=str(STATE), viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    for round in range(1, 4):
        page.goto(URL + f"&r={round}", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(6000)
        if page.locator(".coursenoticepop .start-study").count() > 0:
            page.locator(".coursenoticepop .start-study").click()
            page.wait_for_timeout(1200)
        page.wait_for_selector("iframe#frame_content-zj", timeout=20000)
        fr = page.frame(name="frame_content-zj")
        fr.wait_for_selector("div.chapter_item", timeout=20000)

        import re
        body = fr.locator("body").inner_text(timeout=8000)
        top = re.findall(r"已完成任务点[：:\s]*(\d+)\s*/\s*(\d+)", body)
        print(f"\n===== 第{round}次刷新 | 顶部: {top} =====")
        for nid in NODES:
            info = fr.evaluate("""(nid) => {
                const n = document.querySelector('div.chapter_item#cur'+nid);
                if(!n) return null;
                const st = n.querySelector('.catalog_state');
                const jd = n.querySelector('.catalog_jindu');
                const tips = Array.from(n.querySelectorAll('.bntHoverTips')).map(t=>t.textContent.trim()).filter(Boolean);
                const el = st||jd;
                return {title:n.getAttribute('title'),
                        elClass: el?(el.className||'').toString():'(none)',
                        tips: tips};
            }""", nid)
            print(f"  {nid}: {info}")
    browser.close()
