"""
认证模块 —— 自动登录与会话管理
- 从 config/credentials.json 读取凭据
- 手机号+密码自动登录学习通；登录态持久化到 profile，后续复用
- Session 持有 playwright/browser/page 的完整生命周期，供上层 Agent 使用
"""
import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
CRED_FILE = ROOT / "config" / "credentials.json"
PROFILE = ROOT / "data" / "browser_profile"
STATE_FILE = ROOT / "data" / "storage_state.json"
LOGIN_URL = "https://passport2.chaoxing.com/"


def load_credentials():
    with open(CRED_FILE, encoding="utf-8") as f:
        return json.load(f)


def _is_logged_in(page) -> bool:
    url = (page.url or "").lower()
    if "passport" in url or "/login" in url:
        return False
    return any(k in url for k in ("chaoxing.com", "mooc1", "mooc2", "i.mooc"))


class Session:
    """持有一个完整的 Playwright 会话生命周期

    profile / state_file 可指定，用于多课程并行时的会话隔离；
    不指定则沿用默认（单课程场景）。
    """

    def __init__(self, headless=True, viewport=None, profile=None, state_file=None):
        self.headless = headless
        self.viewport = viewport or {"width": 1440, "height": 900}
        self.profile = Path(profile) if profile else PROFILE
        self.state_file = Path(state_file) if state_file else STATE_FILE
        self.profile.parent.mkdir(parents=True, exist_ok=True)
        self.pw = None
        self.context = None
        self.page = None

    def __enter__(self):
        self.pw = sync_playwright().start()
        self._browser = None
        # 优先用 storage_state 注入登录态：persistent profile 的 cookie 会过期被踢回
        # 登录页，而 storage_state.json 由每次成功登录后刷新，是更可靠的登录来源。
        if self.state_file and Path(self.state_file).exists():
            self._browser = self.pw.chromium.launch(
                channel="msedge", headless=self.headless)
            self.context = self._browser.new_context(
                storage_state=str(self.state_file), viewport=self.viewport)
        else:
            self.context = self.pw.chromium.launch_persistent_context(
                user_data_dir=str(self.profile), channel="msedge",
                headless=self.headless, viewport=self.viewport,
            )
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if self.context:
                self.context.close()
        finally:
            try:
                if self._browser:
                    self._browser.close()
            finally:
                if self.pw:
                    self.pw.stop()

    def ensure_login(self, timeout=60) -> bool:
        """确保处于登录态：优先复用 profile，否则自动登录。返回是否成功"""
        self.page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
        self.page.wait_for_timeout(2000)
        if _is_logged_in(self.page):
            print("[认证] 复用已有登录态")
            self._save_state()
            return True

        cred = load_credentials()
        self.page.fill("#phone", cred["phone"])
        self.page.fill("#pwd", cred["password"])
        for sel in ["input[type=checkbox]", ".agree-checkbox", "[class*=agree]"]:
            try:
                cb = self.page.locator(sel).first
                if cb.count() > 0 and not cb.is_checked():
                    cb.check()
                    break
            except Exception:
                pass
        self.page.click("#loginBtn")
        print("[认证] 已提交登录，等待跳转...")

        start = time.time()
        while time.time() - start < timeout:
            self.page.wait_for_timeout(1500)
            if _is_logged_in(self.page):
                print(f"[认证] ✅ 登录成功: {self.page.url}")
                self._save_state()
                return True
            try:
                body = self.page.locator("body").inner_text(timeout=3000)
                if "滑动" in body or ("安全验证" in body):
                    print("[认证] ⚠️ 出现验证码/安全验证，需人工处理")
                    return False
            except Exception:
                pass
        print(f"[认证] ⏰ 登录超时，当前 URL: {self.page.url}")
        return False

    def _save_state(self):
        try:
            self.context.storage_state(path=str(self.state_file))
        except Exception as e:
            print(f"[认证] 保存状态失败: {e}")

    @property
    def logged_in(self):
        return _is_logged_in(self.page)


if __name__ == "__main__":
    with Session(headless=True) as s:
        ok = s.ensure_login()
        print("登录状态:", "成功" if ok else "失败")
        print("当前 URL:", s.page.url)
        if ok:
            print("页面标题:", s.page.title())
            print("文本预览:", s.page.locator("body").inner_text(timeout=10000)[:200])
