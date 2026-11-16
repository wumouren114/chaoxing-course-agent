"""
页面结构探索 —— 第二步
1. 访问个人空间，点击/进入课程列表
2. 抓取课程列表的 DOM 结构、链接、文本
3. 保存 HTML 快照，供后续分析真实选择器
只读探索，不做任何点击完成动作。
"""
import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
PROFILE = ROOT / "data" / "browser_profile"
SNAP = ROOT / "data" / "snapshots"
SNAP.mkdir(parents=True, exist_ok=True)


def dump(page, name):
    """保存页面 HTML 快照 + 基本信息"""
    html = page.content()
    (SNAP / f"{name}.html").write_text(html, encoding="utf-8")
    try:
        page.screenshot(path=str(SNAP / f"{name}.png"), full_page=False)
    except Exception as e:
        print(f"[快照] 截图失败: {e}")
    print(f"[快照] 已保存 {name}.html ({len(html)} 字符) | URL={page.url}")


def main():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE), channel="msedge", headless=True, no_viewport=True
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        print("[探索] 访问个人空间...")
        page.goto("https://i.chaoxing.com/", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)
        dump(page, "01_space_home")

        # 找出所有指向课程的链接 / 含"课程"字样的元素
        print("\n[探索] 分析首页导航结构...")
        nav_info = page.evaluate("""() => {
            const out = [];
            document.querySelectorAll('a').forEach(a => {
                const t = (a.innerText || '').trim();
                const href = a.getAttribute('href') || '';
                if (t && (t.includes('课程') || href.includes('course'))) {
                    out.push({text: t.slice(0,40), href: href.slice(0,120)});
                }
            });
            return out;
        }""")
        print(json.dumps(nav_info, ensure_ascii=False, indent=2))

        # 尝试点击"课程"导航
        print("\n[探索] 尝试进入课程列表页...")
        try:
            course_link = page.locator("a:has-text('课程')").first
            if course_link.count() > 0:
                course_link.click()
                page.wait_for_timeout(4000)
                print(f"[探索] 点击后 URL: {page.url}")
                dump(page, "02_course_list")
            else:
                print("[探索] 未找到'课程'链接")
        except Exception as e:
            print(f"[探索] 点击课程失败: {e}")

        ctx.close()


if __name__ == "__main__":
    main()
