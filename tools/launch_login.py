"""
登录辅助脚本 v2 —— 信号确认机制
启动有头 Edge，用户手动登录。登录成功后由外部写入信号文件 data/login_signal.txt，
脚本检测到信号即保存会话状态（storage_state + 持久化 profile）。
不再依赖 URL 猜测，避免误判。
"""
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
PROFILE_DIR = ROOT / "data" / "browser_profile"
STATE_FILE = ROOT / "data" / "storage_state.json"
SIGNAL_FILE = ROOT / "data" / "login_signal.txt"
INFO_FILE = ROOT / "data" / "login_info.json"
LOGIN_URL = "https://passport2.chaoxing.com/"
POLL = 2
MAX_WAIT = 600  # 给足 10 分钟


def main():
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    if SIGNAL_FILE.exists():
        SIGNAL_FILE.unlink()
    print("[登录] 启动有头 Edge 窗口...", flush=True)
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            channel="msedge",
            headless=False,
            no_viewport=True,
            args=["--start-maximized"],
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
        print("[登录] >>> 请在弹出的 Edge 窗口中手动登录 <<<", flush=True)
        print("[登录] 登录成功后，回到对话里告诉我，我会写入确认信号。", flush=True)

        start = time.time()
        while time.time() - start < MAX_WAIT:
            time.sleep(POLL)
            if SIGNAL_FILE.exists():
                print("[登录] 收到确认信号，保存会话状态...", flush=True)
                context.storage_state(path=str(STATE_FILE))
                import json
                info = {"url": page.url, "title": page.title(),
                        "saved_at": time.strftime("%Y-%m-%d %H:%M:%S")}
                INFO_FILE.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"[登录] 当前页面: {page.url}", flush=True)
                print(f"[登录] ✅ 登录态已保存到 {STATE_FILE.name}", flush=True)
                print("[登录] 保持窗口打开 15 秒供确认，随后关闭。", flush=True)
                time.sleep(15)
                context.close()
                return
        print("[登录] ⏰ 等待超时，未收到确认信号。", flush=True)
        context.close()


if __name__ == "__main__":
    main()
