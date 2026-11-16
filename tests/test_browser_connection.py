"""
浏览器连接测试 —— 第一步环境验证用
目标：确认 Playwright 能启动本机 Edge，并成功打开一个页面、读取标题。
不访问学习通，只做最小连通性验证。
"""
from playwright.sync_api import sync_playwright


def main():
    print("[测试] 开始浏览器连接测试...")
    with sync_playwright() as p:
        print("[测试] 启动 Edge (channel=msedge, headless=True)...")
        browser = p.chromium.launch(channel="msedge", headless=True)
        print("[测试] 浏览器启动成功")
        page = browser.new_page()
        # 用 data URL，完全离线，避免网络干扰
        page.set_content("<html><head><title>连接测试通过</title></head><body><h1 id='ok'>OK</h1></body></html>")
        title = page.title()
        text = page.locator("#ok").inner_text()
        print(f"[测试] 页面标题: {title}")
        print(f"[测试] 元素文本: {text}")
        assert title == "连接测试通过", "标题不符"
        assert text == "OK", "元素文本不符"
        # 打印浏览器版本，确认走的是系统 Edge
        print(f"[测试] 浏览器版本: {browser.version}")
        browser.close()
    print("[测试] ✅ 浏览器连接测试全部通过")


if __name__ == "__main__":
    main()
