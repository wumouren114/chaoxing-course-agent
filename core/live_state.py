"""
实时状态模块 —— 供监控面板读取
把脚本运行状态、视频进度、截图写入文件，Web 面板定时读取展示。
"""
import json
import time
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
STATUS_FILE = ROOT / "web" / "live_status.json"
SHOT_FILE = ROOT / "web" / "live_screenshot.png"
LOG_FILE = ROOT / "web" / "live_events.json"

DEFAULT = {
    "running": False,
    "control": "IDLE",
    "course": "",
    "course_name": "",
    "task": "",
    "task_title": "",
    "stage": "空闲",
    "video": {"current": 0, "duration": 0, "pct": 0, "paused": True, "display": "0:00/0:00"},
    "stats": {"total": 0, "completed": 0, "skipped": 0, "review": 0, "errors": 0, "pct": 0},
    "message": "等待启动",
    "updated_at": "",
    "shot_version": 0,
}


class LiveState:
    def __init__(self, status_file=None, log_file=None):
        # 支持自定义文件路径：多课程并行时各写各的，避免互相覆盖
        self.status_file = Path(status_file) if status_file else STATUS_FILE
        self.log_file = Path(log_file) if log_file else LOG_FILE
        self.status_file.parent.mkdir(parents=True, exist_ok=True)
        self._shot_version = 0
        self._events = []

    def update(self, **kwargs):
        data = dict(DEFAULT)
        if self.status_file.exists():
            try:
                data.update(json.loads(self.status_file.read_text(encoding="utf-8")))
            except Exception:
                pass
        data.update(kwargs)
        data["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.status_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return data

    def event(self, text, level="info"):
        self._events.append({
            "ts": datetime.now().strftime("%H:%M:%S"),
            "text": text, "level": level,
        })
        self._events = self._events[-80:]
        self.log_file.write_text(json.dumps(self._events, ensure_ascii=False, indent=2), encoding="utf-8")

    def screenshot(self, page):
        """抓取自动化浏览器当前画面"""
        try:
            page.screenshot(path=str(SHOT_FILE), full_page=False)
            self._shot_version += 1
            self.update(shot_version=self._shot_version)
            return True
        except Exception as e:
            self.event(f"截图失败: {e}", "error")
            return False

    def reset(self):
        self._events = []
        self.log_file.write_text("[]", encoding="utf-8")
        return self.update(**DEFAULT)


if __name__ == "__main__":
    ls = LiveState()
    ls.reset()
    ls.update(running=True, control="RUNNING", course="ai_tools",
              course_name="人人都能上手的AI工具", task="1221807919",
              task_title="2.1 认识AI写作", stage="视频播放监测", message="测试中")
    ls.event("系统启动", "ok")
    ls.event("开始监测视频播放")
    print("✅ 实时状态写入测试通过")
    print(STATUS_FILE.read_text(encoding="utf-8")[:400])
