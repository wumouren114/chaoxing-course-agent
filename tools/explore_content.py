"""
探索章节内容页 v2 —— 单会话内完成 登录→课程→章节→内容页
避免多进程并发访问 profile 导致 Cookie 冲突
"""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
from core.auth import Session, _is_logged_in, LOGIN_URL

ROOT = Path(__file__).resolve().parent.parent
SNAP = ROOT / "data" / "snapshots"
COURSE_MIDDLE = ("https://mooc1.chaoxing.com/visit/stucoursemiddle"
                 "?courseid=268560848&clazzid=158282453&cpi=575101306&ismooc2=1&v=2")


def main():
    with Session(headless=True) as s:
        page = s.page
        if not s.ensure_login():
            print("[探索] 登录失败，终止")
            return
        print("[探索] 登录态确认，访问课程中间页...")
        new_pages = []
        s.context.on("page", lambda pg: new_pages.append(pg))

        page.goto(COURSE_MIDDLE, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)
        print(f"[探索] 课程页 URL: {page.url}")

        # 关闭"课程须知"弹窗（精确 class 选择器）
        if page.locator(".coursenoticepop .start-study").count() > 0:
            page.locator(".coursenoticepop .start-study").click()
            page.wait_for_timeout(2000)
            print("[探索] 已关闭课程须知弹窗")

        # 等章节 iframe 出现
        page.wait_for_selector("iframe#frame_content-zj", timeout=20000)
        frame = page.frame(name="frame_content-zj")
        frame.wait_for_selector("div.chapter_item", timeout=20000)
        print(f"[探索] 章节节点数: {frame.locator('div.chapter_item').count()}")

        # 点击 2.1
        node = frame.locator("div.chapter_item#cur1221807919")
        print(f"[探索] 2.1 节点: {node.count()}")
        node.click()
        page.wait_for_timeout(6000)
        print(f"[探索] 点击后主 URL: {page.url}, 新窗口数: {len(new_pages)}")

        frames = page.evaluate("""() => Array.from(document.querySelectorAll('iframe')).map(f => ({
            src:(f.getAttribute('src')||'').slice(0,180), id:f.id||'', name:f.name||''
        }))""")
        print("\n[探索] 所有 iframe:")
        print(json.dumps(frames, ensure_ascii=False, indent=2))

        target = new_pages[0] if new_pages else page
        target.wait_for_timeout(3000)
        print(f"\n[探索] 目标页: {target.url} | {target.title()}")
        text = target.locator("body").inner_text(timeout=10000)
        print("\n[探索] 内容页文本（前 3000 字）:")
        print(text[:3000])
        html = target.content()
        (SNAP / "06_content_page.html").write_text(html, encoding="utf-8")
        print(f"\n[快照] 06_content_page.html ({len(html)} 字符)")

        frames2 = target.evaluate("""() => Array.from(document.querySelectorAll('iframe')).map(f => ({
            src:(f.getAttribute('src')||'').slice(0,200), id:f.id||'', name:f.name||''
        }))""")
        print("\n[探索] 内容页 iframe:")
        print(json.dumps(frames2, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
