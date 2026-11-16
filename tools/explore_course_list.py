"""
探索课程列表页（mooc2-ans visit/interaction）
抓取所有课程卡片：课程名、链接、iframe 结构
"""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
PROFILE = ROOT / "data" / "browser_profile"
SNAP = ROOT / "data" / "snapshots"
SNAP.mkdir(parents=True, exist_ok=True)

COURSE_URL = "https://mooc2-ans.chaoxing.com/visit/interaction"


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
        print(f"[探索] 访问课程列表: {COURSE_URL}")
        page.goto(COURSE_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)
        dump(page, "03_course_list")

        # 列出所有 iframe
        frames = page.evaluate("""() => Array.from(document.querySelectorAll('iframe')).map(f => ({
            src: f.getAttribute('src') || '', id: f.id || '', name: f.name || '', cls: f.className || ''
        }))""")
        print("\n[探索] iframe 列表:")
        print(json.dumps(frames, ensure_ascii=False, indent=2))

        # 抓取页面文本（截取）
        text = page.locator("body").inner_text(timeout=10000)
        print("\n[探索] 页面文本（前 1500 字）:")
        print(text[:1500])
        ctx.close()


if __name__ == "__main__":
    main()
