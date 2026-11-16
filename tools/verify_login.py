"""
验证持久化 profile 中的登录态是否有效
用已有 profile 启动浏览器，访问学习通空间页，判断是否已登录。
"""
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
PROFILE_DIR = ROOT / "data" / "browser_profile"


def main():
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            channel="msedge",
            headless=True,
            no_viewport=True,
        )
        page = context.pages[0] if context.pages else context.new_page()
        print("[验证] 访问学习通空间页...")
        try:
            page.goto("https://i.chaoxing.com/", wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(3000)
            url = page.url
            title = page.title()
            print(f"[验证] 当前 URL: {url}")
            print(f"[验证] 页面标题: {title}")
            # 取页面部分文本辅助判断
            body = page.locator("body").inner_text(timeout=5000)[:500]
            print(f"[验证] 页面文本预览: {body!r}")
            logged = "passport" not in url.lower() and "login" not in url.lower()
            # 进一步：查找登录后常见的用户名元素
            if logged:
                print("[验证] ✅ 看起来已登录（URL 未跳转登录页）")
            else:
                print("[验证] ❌ 未登录（仍在登录页）")
        except Exception as e:
            print(f"[验证] 访问出错: {e}")
        context.close()


if __name__ == "__main__":
    main()
