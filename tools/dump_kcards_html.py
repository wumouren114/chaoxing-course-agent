"""只读：dump 指定章节知识卡片的完整 HTML，用于分析测验/任务点结构。"""
import sys, json
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "data" / "storage_state.json"
COURSES = {
    "ai_tools": ("https://mooc1.chaoxing.com/visit/stucoursemiddle?courseid=268560848&clazzid=158282453&cpi=575101306&ismooc2=1&v=2", "1221807919"),
    "ai_principle": ("https://mooc1.chaoxing.com/visit/stucoursemiddle?courseid=268560836&clazzid=158282442&cpi=575101306&ismooc2=1&v=2", "1113731098"),
}
key = sys.argv[1] if len(sys.argv) > 1 else "ai_tools"
node = sys.argv[2] if len(sys.argv) > 2 else COURSES[key][1]
URL = COURSES[key][0]

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
    target = fr.locator(f"div.chapter_item#cur{node}")
    print("章节:", target.get_attribute("title"))
    target.scroll_into_view_if_needed(); target.click()
    page.wait_for_timeout(9000)

    # 列出所有 frame
    print("\n=== 所有 frame ===")
    for f in page.frames:
        print(" -", (f.url or "")[:180])

    # 找知识卡片 frame
    kc = None
    for f in page.frames:
        if "knowledge/cards" in (f.url or ""):
            kc = f; break
    if not kc:
        print("!! 无知识卡片frame"); b.close(); sys.exit()

    html = kc.evaluate("() => document.body.innerHTML")
    out = ROOT / "data" / "snapshots" / f"kcards_{node}.html"
    out.parent.mkdir(exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"\n知识卡片HTML已保存: {out} ({len(html)} 字符)")

    # 统计所有任务点类型
    summary = kc.evaluate("""() => {
        const r={jobs:[], links:[], iframes:[]};
        document.querySelectorAll('[class*=ans-job], [class*=ans-attach], [class*=homework], [class*=zuoye], [class*=exam], [class*=task]').forEach(e=>{
            r.jobs.push({tag:e.tagName, cls:(e.className||'').toString().slice(0,120),
                label:e.getAttribute('aria-label')||'', jobid:e.getAttribute('jobid')||'',
                text:(e.innerText||'').trim().slice(0,80)});
        });
        document.querySelectorAll('a[href]').forEach(a=>{
            const h=a.getAttribute('href')||'';
            if(/exam|homework|zuoye|quiz|test|question|task/i.test(h))
                r.links.push({text:(a.innerText||'').trim().slice(0,60), href:h.slice(0,180)});
        });
        document.querySelectorAll('iframe').forEach(f=>r.iframes.push({
            src:(f.getAttribute('src')||'').slice(0,200),
            cls:(f.className||'').toString().slice(0,80)}));
        return r;
    }""")
    print("\n=== 任务点/测验相关元素 ===")
    for j in summary["jobs"]:
        print(json.dumps(j, ensure_ascii=False))
    print("\n=== 测验类链接 ===")
    for l in summary["links"]:
        print(json.dumps(l, ensure_ascii=False))
    print("\n=== iframe ===")
    for v in summary["iframes"]:
        print(json.dumps(v, ensure_ascii=False))
    b.close()
