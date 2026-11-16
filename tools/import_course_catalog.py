"""
导入指定课程的章节目录到数据库（独立只读会话，不干扰正在播放的进程）
用法：python tools/import_course_catalog.py ai_principle
"""
import sys
sys.path.insert(0, ".")
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
from core.catalog import COURSES, COURSE_MIDDLE, parse_catalog_html
from core.database import Database

ROOT = Path(".").resolve()


def fetch(course_key: str, state_file: Path) -> str:
    cfg = COURSES[course_key]
    url = COURSE_MIDDLE.format(**cfg)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        ctx = browser.new_context(storage_state=str(state_file),
                                  viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)
        if page.locator(".coursenoticepop .start-study").count() > 0:
            page.locator(".coursenoticepop .start-study").click()
            page.wait_for_timeout(2000)
        page.wait_for_selector("iframe#frame_content-zj", timeout=20000)
        fr = page.frame(name="frame_content-zj")
        fr.wait_for_selector("div.chapter_item", timeout=20000)
        html = fr.evaluate("() => document.body.innerHTML")
        ctx.close(); browser.close()
        return html


def main():
    course = sys.argv[1] if len(sys.argv) > 1 else "ai_principle"
    cfg = COURSES[course]
    state = ROOT / "data" / "storage_state.json"  # 用主登录态

    html = fetch(course, state)
    snap = ROOT / "data" / "snapshots" / f"catalog_{course}.html"
    snap.write_text(html, encoding="utf-8")
    print(f"[导入] 已抓取 {course} 目录 HTML，长度 {len(html)}")

    items = parse_catalog_html(html, course)
    real = [i for i in items if i["node_id"]]
    print(f"[导入] 章节节点 {len(items)}，真实任务 {len(real)}，任务点总数 {sum(i['job_count'] for i in real)}")

    db = Database()
    db.upsert_course(course, cfg["name"], cfg["courseid"], cfg["clazzid"], cfg["cpi"])
    for it in real:
        db.upsert_task(course, it["node_id"], it["number"], it["title"], it["job_count"],
                       meta={"courseid": it["courseid"], "clazzid": it["clazzid"]})
    print(f"[导入] 数据库统计: {db.summary(course)}")
    db.close()
    print(f"[导入] ✅ {course} 目录导入完成")


if __name__ == "__main__":
    main()
