"""
探索章节目录 v2 —— 从课程中间页进入（带正确 enc 参数），再进 iframe
"""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
PROFILE = ROOT / "data" / "browser_profile"
SNAP = ROOT / "data" / "snapshots"
SNAP.mkdir(parents=True, exist_ok=True)

MIDDLE_URL = ("https://mooc1.chaoxing.com/visit/stucoursemiddle"
              "?courseid=268560848&clazzid=158282453&cpi=575101306&ismooc2=1&v=2")


def main():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE), channel="msedge", headless=True, no_viewport=True
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        print("[探索] 访问课程中间页...")
        page.goto(MIDDLE_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)
        print(f"[探索] 跳转后 URL: {page.url}")
        print(f"[探索] 标题: {page.title()}")

        # 点掉"我已阅读, 开始学习"（若存在）
        for sel in ["text=我已阅读, 开始学习", "text=我已阅读", "text=开始学习"]:
            try:
                btn = page.locator(sel).first
                if btn.count() > 0:
                    btn.click()
                    page.wait_for_timeout(3000)
                    print(f"[探索] 已点击: {sel}")
                    break
            except Exception:
                pass

        # 列出所有 iframe
        frames = page.evaluate("""() => Array.from(document.querySelectorAll('iframe')).map(f => ({
            src: (f.getAttribute('src')||'').slice(0,150), id: f.id||'', name: f.name||''
        }))""")
        print("\n[探索] iframe 列表:")
        print(json.dumps(frames, ensure_ascii=False, indent=2))

        # 进入章节 iframe（按 name 或 id）
        frame = None
        for ident in ["frame_content-zj"]:
            frame = page.frame(name=ident) or page.frame_locator(f"iframe#{ident}")
            if frame:
                break
        # 用 frame_locator 更稳
        floc = page.frame_locator("iframe").first
        try:
            body_text = floc.locator("body").inner_text(timeout=10000)
            print("\n[探索] 章节 iframe 文本（前 3000 字）:")
            print(body_text[:3000])
            html = floc.locator("body").inner_html(timeout=10000)
            (SNAP / "05_chapter_frame.html").write_text(html, encoding="utf-8")
            print(f"\n[快照] 05_chapter_frame.html ({len(html)} 字符)")
        except Exception as e:
            print(f"[探索] 读取章节 iframe 失败: {e}")
            # 尝试读主页面文本
            print("主页面文本:", page.locator("body").inner_text(timeout=10000)[:2000])
        ctx.close()


if __name__ == "__main__":
    main()
