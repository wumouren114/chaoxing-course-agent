"""
探索学习通登录页表单结构（只读，不填密码）
用临时 context，避免污染已登录的 profile
"""
import json
from playwright.sync_api import sync_playwright

LOGIN_URL = "https://passport2.chaoxing.com/"


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page()
        print("[探索] 访问登录页...")
        page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)
        print(f"[探索] URL: {page.url}")

        # 抓所有 input
        inputs = page.evaluate("""() => Array.from(document.querySelectorAll('input')).map(i => ({
            id: i.id||'', name: i.name||'', type: i.type||'',
            placeholder: i.placeholder||'', cls: (i.className||'').slice(0,50)
        }))""")
        print("\n[探索] 输入框:")
        print(json.dumps(inputs, ensure_ascii=False, indent=2))

        # 抓所有按钮
        btns = page.evaluate("""() => Array.from(document.querySelectorAll('button,a,input[type=submit],div'))
            .filter(e => /登录|登陆|login|提交/.test((e.innerText||'')+(e.value||'')))
            .slice(0,15).map(e => ({tag:e.tagName, text:(e.innerText||e.value||'').trim().slice(0,30),
            id:e.id||'', cls:(e.className||'').slice(0,50)}))""")
        print("\n[探索] 登录相关按钮:")
        print(json.dumps(btns, ensure_ascii=False, indent=2))

        # 登录方式 tab（二维码/手机号/账号）
        tabs = page.evaluate("""() => Array.from(document.querySelectorAll('*'))
            .filter(e => e.children.length===0 && /二维码|手机号|账号密码|短信/.test(e.innerText||''))
            .slice(0,15).map(e => ({tag:e.tagName, text:e.innerText.trim().slice(0,20), cls:(e.className||'').slice(0,40)}))""")
        print("\n[探索] 登录方式切换:")
        print(json.dumps(tabs, ensure_ascii=False, indent=2))

        text = page.locator("body").inner_text(timeout=10000)
        print("\n[探索] 页面文本（前 800 字）:")
        print(text[:800])
        browser.close()


if __name__ == "__main__":
    main()
