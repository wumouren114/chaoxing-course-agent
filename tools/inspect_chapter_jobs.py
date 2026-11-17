"""只读：列出章节知识卡片里的所有任务点及其类型/完成状态。"""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "data" / "storage_state.json"
COURSES = {
    "ai_tools": ("https://mooc1.chaoxing.com/visit/stucoursemiddle?courseid=268560848&clazzid=158282453&cpi=575101306&ismooc2=1&v=2", "1221807919"),
    "ai_principle": ("https://mooc1.chaoxing.com/visit/stucoursemiddle?courseid=268560836&clazzid=158282442&cpi=575101306&ismooc2=1&v=2", "1113731098"),
}
key = sys.argv[1] if len(sys.argv) > 1 else "ai_tools"
URL, NODE = COURSES[key]

with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge", headless=True)
    ctx = b.new_context(storage_state=str(STATE), viewport={"width": 1440, "height": 900})
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
    print("章节:", node.get_attribute("title"))
    node.scroll_into_view_if_needed(); node.click()
    page.wait_for_timeout(8000)

    kc = None
    for f in page.frames:
        if "knowledge/cards" in (f.url or ""):
            kc = f; break
    if not kc:
        print("无知识卡片frame"); b.close(); sys.exit()
    print("卡片URL:", kc.url[:150])

    # 列出所有任务点图标（含 class 和 aria-label + 外层容器信息）
    jobs = kc.evaluate("""() => {
        const out=[];
        document.querySelectorAll('[class*=ans-job]').forEach(e=>{
            const cls=(e.className||'').toString();
            const label=e.getAttribute('aria-label')||'';
            const p=e.parentElement;
            const pp=p?p.parentElement:null;
            out.push({tag:e.tagName, cls, label,
                      parentCls:p?(p.className||'').toString().slice(0,80):'',
                      grandText:pp?(pp.innerText||'').trim().slice(0,60):''});
        });
        return out;
    }""")
    print("\n=== 任务点元素 ===")
    import json
    for j in jobs:
        print(json.dumps(j, ensure_ascii=False))

    # 视频 iframe 及其 data 属性
    vids = kc.evaluate("""() => Array.from(document.querySelectorAll('iframe')).map(f=>({
        src:(f.getAttribute('src')||'').slice(0,200),
        data: JSON.stringify(Object.fromEntries(Object.entries(f.dataset)))
    }))""")
    print("\n=== iframe ===")
    for v in vids:
        print(json.dumps(v, ensure_ascii=False))
    b.close()
