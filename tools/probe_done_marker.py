"""只读：统计所有章节的目录完成标记分布，找出'已完成'章节长什么样。"""
import re
from collections import Counter
from pathlib import Path
from playwright.sync_api import sync_playwright

URL = "https://mooc1.chaoxing.com/visit/stucoursemiddle?courseid=268560848&clazzid=158282453&cpi=575101306&ismooc2=1&v=2"
STATE = str(Path("data/storage_state.json").resolve())

JS = """() => Array.from(document.querySelectorAll('div.chapter_item'))
  .filter(n => n.id.startsWith('cur'))
  .map(n => {
    const j = n.querySelector('.catalog_jindu');
    const t = n.querySelector('.bntHoverTips');
    const k = n.querySelector('.knowledgeJobCount');
    const s = n.querySelector('.catalog_sbar');
    return {id: n.id, num: s ? s.textContent.trim() : '',
            title: n.getAttribute('title')||'',
            jindu: j ? j.className : '(无)',
            tip: t ? t.textContent.trim() : '(无)',
            count: k ? k.value : '0'};
  })"""

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
    # 滚动触发懒加载
    fr.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
    pg.wait_for_timeout(2500)
    fr.evaluate("() => window.scrollTo(0, 0)")
    pg.wait_for_timeout(1500)

    chapters = fr.evaluate(JS)
    print("=== bntHoverTips 文案分布 ===")
    for tip, n in Counter(c["tip"] for c in chapters).most_common():
        print(f"  {n:>3}章  '{tip}'")
    print("\n=== catalog_jindu class 分布 ===")
    for cls, n in Counter(c["jindu"] for c in chapters).most_common():
        print(f"  {n:>3}章  '{cls}'")

    # 找出不带 catalog_tishi120 的（平台认为完成/无需完成）
    clean = [c for c in chapters if "catalog_tishi120" not in c["jindu"]]
    print(f"\n=== 不带 catalog_tishi120 的章节（共{len(clean)}）===")
    for c in clean[:40]:
        print(f"  {c['num']:>5} {c['title'][:24]:<26} tip='{c['tip']}' count={c['count']} cls='{c['jindu']}'")
    b.close()
