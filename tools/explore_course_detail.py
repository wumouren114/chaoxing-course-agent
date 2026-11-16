"""
探索课程详情页 —— 识别章节目录结构
先做"人人都能上手的AI工具"这一门（courseid=268560848）
"""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
PROFILE = ROOT / "data" / "browser_profile"
SNAP = ROOT / "data" / "snapshots"
SNAP.mkdir(parents=True, exist_ok=True)

COURSE_URL = ("https://mooc1.chaoxing.com/visit/stucoursemiddle"
              "?courseid=268560848&clazzid=158282453&cpi=575101306&ismooc2=1&v=2")


def dump(page, name):
    html = page.content()
    (SNAP / f"{name}.html").write_text(html, encoding="utf-8")
    try:
        page.screenshot(path=str(SNAP / f"{name}.png"), full_page=True)
    except Exception as e:
        print(f"[快照] 截图失败: {e}")
    print(f"[快照] {name}.html ({len(html)} 字符) | {page.url}")


def main():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE), channel="msedge", headless=True, no_viewport=True
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        print(f"[探索] 访问课程中间页...")
        page.goto(COURSE_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)
        print(f"[探索] 跳转后 URL: {page.url}")
        dump(page, "04_course_middle")

        # 检测所有 iframe（章节目录常在 iframe 里）
        frames = page.evaluate("""() => Array.from(document.querySelectorAll('iframe')).map(f => ({
            src: f.getAttribute('src') || '', id: f.id || '', name: f.name || '', cls: f.className || ''
        }))""")
        print("\n[探索] iframe 列表:")
        print(json.dumps(frames, ensure_ascii=False, indent=2))

        text = page.locator("body").inner_text(timeout=10000)
        print("\n[探索] 页面文本（前 2000 字）:")
        print(text[:2000])
        ctx.close()


if __name__ == "__main__":
    main()
