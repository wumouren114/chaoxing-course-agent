"""抓取章节测验子iframe(#frame_content)里的真实题目DOM。
用法: python tools/probe_questions.py [course] [node_id]
"""
import sys, json
from pathlib import Path
from playwright.sync_api import sync_playwright

COURSE = sys.argv[1] if len(sys.argv) > 1 else "ai_tools"
NODE = sys.argv[2] if len(sys.argv) > 2 else "1221808027"
CFG = {
    "ai_tools": dict(middle="https://mooc1.chaoxing.com/visit/stucoursemiddle?courseid=268560848&clazzid=158282453&cpi=575101306&ismooc2=1&v=2"),
    "ai_principle": dict(middle="https://mooc1.chaoxing.com/visit/stucoursemiddle?courseid=268560836&clazzid=158282442&cpi=575101306&ismooc2=1&v=2"),
}
STATE = str(Path(f"data/storage_state{'_principle' if COURSE=='ai_principle' else ''}.json").resolve())

with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge", headless=True)
    ctx = b.new_context(storage_state=STATE)
    pg = ctx.new_page()
    pg.goto(CFG[COURSE]["middle"], wait_until="domcontentloaded", timeout=60000)
    pg.wait_for_timeout(6000)
    if pg.locator(".coursenoticepop .start-study").count() > 0:
        pg.locator(".coursenoticepop .start-study").click()
        pg.wait_for_timeout(1200)
    fr = pg.frame(name="frame_content-zj")
    fr.wait_for_selector("div.chapter_item", timeout=20000)
    fr.locator(f"div.chapter_item#cur{NODE} .clicktitle").click()
    pg.wait_for_timeout(8000)
    # 点测验
    for f in pg.frames:
        try:
            loc = f.locator("li:has-text('测验'), a:has-text('测验')")
            for j in range(loc.count()):
                el = loc.nth(j)
                if el.is_visible(timeout=1000) and (el.inner_text(timeout=1000) or "").strip().endswith("测验"):
                    el.click(timeout=4000); break
        except Exception: pass
    pg.wait_for_timeout(9000)

    print("=== 所有 frame ===")
    for i, f in enumerate(pg.frames):
        print(f"  [{i}] name={f.name!r} url={(f.url or '')[:100]}")

    # 找题目 iframe：url 含 api/work 或 name=frame_content 且 url 非空
    qf = None
    for f in pg.frames:
        u = f.url or ""
        if "api/work" in u or ("frame_content" in (f.name or "") and "work" in u):
            qf = f; break
    if not qf:
        # 兜底：取 url 含 work 的最深 frame
        for f in pg.frames:
            if "work" in (f.url or "").lower() and "modules/work" not in (f.url or ""):
                qf = f; break
    print("\n题目frame:", qf.url[:140] if qf else None)

    if qf:
        qf.wait_for_load_state("domcontentloaded", timeout=20000)
        pg.wait_for_timeout(3000)
        txt = qf.evaluate("() => document.body ? document.body.innerText : ''") or ""
        print("\n=== 题目frame可见文本(前3000) ===")
        print(txt[:3000])

        print("\n=== 题目元素明细 ===")
        for sel in ["input[type=radio]", "input[type=checkbox]", "textarea",
                    "button", "a", "[class*=timu]", "[class*=question]",
                    "[class*=topic]", "[class*=answer]", "[class*=option]",
                    "[class*=subject]", "[class*=choose]"]:
            try:
                n = qf.locator(sel).count()
            except Exception:
                continue
            if n == 0: continue
            rows=[]
            for j in range(min(n, 25)):
                try:
                    el = qf.locator(sel).nth(j)
                    rows.append({
                        "tag": el.evaluate("e=>e.tagName"),
                        "type": el.get_attribute("type") or "",
                        "name": el.get_attribute("name") or "",
                        "value": el.get_attribute("value") or "",
                        "cls": (el.get_attribute("class") or "")[:40],
                        "text": (el.inner_text(timeout=800) or "").strip().replace("\n"," ")[:60],
                        "html": el.evaluate("e=>e.outerHTML")[:200],
                    })
                except Exception: pass
            print(f"\n  {sel} x{n}:")
            for r in rows[:15]:
                print("    ", json.dumps(r, ensure_ascii=False)[:280])

        try:
            Path(f"data/snapshots/questions_{COURSE}_{NODE}.html").write_text(qf.content(), encoding="utf-8")
            print("\n题目HTML已保存")
        except Exception as e: print("保存失败", e)
    b.close()
