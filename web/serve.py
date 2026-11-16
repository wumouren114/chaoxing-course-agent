"""监控面板本地服务器（控制指令 + 题目协作 API）"""
import http.server
import socketserver
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(HERE), **kwargs)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        path = self.path.split("?")[0]

        if path == "/api/answer":
            # 面板/助手作答：{id, answer, analysis}
            from core.question_queue import answer, persist_to_db, all_items, mark_submitted
            try:
                data = json.loads(body)
                ok = answer(data["id"], data.get("answer", ""), data.get("analysis", ""))
                if ok:
                    items = {q["id"]: q for q in all_items()}
                    persist_to_db(items[data["id"]])
                self._json({"ok": ok})
            except Exception as e:
                self._json({"ok": False, "error": str(e)})
            return

        # 默认：控制指令
        (HERE / "control_signal.json").write_text(body, encoding="utf-8")
        self._json({"ok": True})

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/api/questions":
            from core.question_queue import all_items
            # 返回待作答 + 已作答（供面板显示）
            items = [q for q in all_items() if q["status"] in ("PENDING", "ANSWERED")]
            self._json(items)
            return
        return super().do_GET()

    def _json(self, obj):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(data)

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    with socketserver.TCPServer(("127.0.0.1", 8765), Handler) as httpd:
        print("server on http://127.0.0.1:8765", flush=True)
        httpd.serve_forever()
