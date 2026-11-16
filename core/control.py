"""
控制模块 —— 控制面板信号 + 人工环节挂起
读取 web/control_signal.json（面板写入的指令）：start / pause_toggle / stop / resume
人工环节检测：平台弹出验证/确认时，挂起等待 web/resume_signal.txt 出现
"""
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
SIGNAL_FILE = WEB / "control_signal.json"
RESUME_FILE = WEB / "resume_signal.txt"


class ControlManager:
    def __init__(self, live_state=None, signal_file=None, resume_file=None):
        self.ls = live_state
        self.signal_file = Path(signal_file) if signal_file else SIGNAL_FILE
        self.resume_file = Path(resume_file) if resume_file else RESUME_FILE
        self._paused = False
        self._stopped = False
        self._last_ts = 0

    def _read_signal(self):
        if not self.signal_file.exists():
            return None
        try:
            data = json.loads(self.signal_file.read_text(encoding="utf-8"))
            if data.get("ts", 0) != self._last_ts:
                self._last_ts = data.get("ts", 0)
                return data.get("command")
        except Exception:
            pass
        return None

    def poll(self):
        """轮询控制指令，更新内部状态"""
        cmd = self._read_signal()
        if cmd == "pause_toggle":
            self._paused = not self._paused
        elif cmd == "start":
            self._paused = False
            self._stopped = False
        elif cmd == "stop":
            self._stopped = True
        elif cmd == "resume":
            self._paused = False
        return cmd

    @property
    def stopped(self):
        self.poll()
        return self._stopped

    @property
    def paused(self):
        self.poll()
        return self._paused

    def wait_if_paused(self, ls=None):
        """暂停时阻塞等待，同时把状态同步到面板"""
        while self.paused and not self.stopped:
            if ls:
                ls.update(control="PAUSED", message="已暂停（点击面板'暂停/继续'恢复）")
            time.sleep(1)
        if not self.stopped and ls:
            ls.update(control="RUNNING", message="继续执行")

    def suspend_for_human(self, reason: str, ls=None, timeout=1800):
        """
        检测到人工环节：挂起等待用户处理完成。
        用户在面板确认后，web/resume_signal.txt 会出现，或超时自动跳过。
        返回 True=用户已恢复，False=超时/停止
        """
        if self.resume_file.exists():
            self.resume_file.unlink()
        if ls:
            ls.update(control="PAUSED", stage="等待人工处理",
                      message=f"⚠️ 需要人工处理：{reason}。处理后请在面板点击继续。")
            ls.event(f"⏸ 挂起等待人工: {reason}", "warn")
        start = time.time()
        while time.time() - start < timeout:
            if self.stopped:
                return False
            if self.resume_file.exists() or self._manual_resume_requested():
                self.resume_file.unlink(missing_ok=True)
                self._paused = False
                if ls:
                    ls.update(control="RUNNING", stage="继续执行", message="人工已确认，继续")
                    ls.event("▶ 人工已确认，继续执行", "ok")
                return True
            time.sleep(1)
        if ls:
            ls.event("等待人工超时，跳过该环节", "warn")
        return False

    def _manual_resume_requested(self):
        cmd = self._read_signal()
        return cmd in ("resume", "start", "pause_toggle")


def detect_human_intervention(page) -> str:
    """
    检测页面是否出现需要人工处理的环节
    返回原因字符串，或空字符串表示无需人工
    """
    try:
        text = page.locator("body").inner_text(timeout=5000)
    except Exception:
        return ""
    keywords = {
        "滑动验证": ["请滑动", "拖动滑块", "安全验证", "滑动验证"],
        "短信验证": ["短信验证码", "输入验证码"],
        "登录失效": ["请重新登录", "登录已过期", "会话超时"],
    }
    for label, kws in keywords.items():
        for kw in kws:
            if kw in text:
                return f"{label}: 页面出现「{kw}」"
    return ""


if __name__ == "__main__":
    cm = ControlManager()
    print("控制管理器初始化完成")
    print("当前停止状态:", cm.stopped)
    print("当前暂停状态:", cm.paused)
