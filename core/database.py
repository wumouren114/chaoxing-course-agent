"""
数据库模块 —— SQLite 持久化 + 断点恢复
表：courses(课程) / tasks(任务) / events(状态事件) / anomalies(异常) / answers(题目建议) / run_state(运行状态)
"""
import sqlite3
import json
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Dict

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "automation.db"


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class Database:
    def __init__(self, path: Path = DB_PATH):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        c = self.conn.cursor()
        c.executescript("""
        CREATE TABLE IF NOT EXISTS courses (
            key TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            courseid TEXT, clazzid TEXT, cpi TEXT,
            created_at TEXT, updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course TEXT NOT NULL,
            node_id TEXT NOT NULL,
            number TEXT, title TEXT,
            job_count INTEGER DEFAULT 0,
            content_types TEXT,
            state TEXT NOT NULL DEFAULT 'WAITING',
            reason TEXT DEFAULT '',
            retry_count INTEGER DEFAULT 0,
            meta TEXT,
            UNIQUE(course, node_id)
        );
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course TEXT, node_id TEXT,
            from_state TEXT, to_state TEXT,
            reason TEXT, ts TEXT
        );
        CREATE TABLE IF NOT EXISTS anomalies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course TEXT, node_id TEXT,
            kind TEXT, reason TEXT,
            snapshot TEXT, ts TEXT, handled INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS answers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course TEXT, node_id TEXT,
            question TEXT, options TEXT,
            suggestion TEXT, analysis TEXT,
            confirmed INTEGER DEFAULT 0, ts TEXT
        );
        CREATE TABLE IF NOT EXISTS run_state (
            key TEXT PRIMARY KEY, value TEXT
        );
        """)
        self.conn.commit()

    # ---------- 课程 ----------
    def upsert_course(self, key, name, courseid, clazzid, cpi):
        self.conn.execute("""
            INSERT INTO courses(key,name,courseid,clazzid,cpi,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?)
            ON CONFLICT(key) DO UPDATE SET
              name=excluded.name, courseid=excluded.courseid,
              clazzid=excluded.clazzid, cpi=excluded.cpi, updated_at=excluded.updated_at
        """, (key, name, courseid, clazzid, cpi, now(), now()))
        self.conn.commit()

    # ---------- 任务 ----------
    def upsert_task(self, course, node_id, number, title, job_count, meta=None):
        self.conn.execute("""
            INSERT INTO tasks(course,node_id,number,title,job_count,state,meta)
            VALUES(?,?,?,?,?, 'WAITING', ?)
            ON CONFLICT(course,node_id) DO UPDATE SET
              number=excluded.number, title=excluded.title, job_count=excluded.job_count
        """, (course, node_id, number, title, job_count,
              json.dumps(meta or {}, ensure_ascii=False)))
        self.conn.commit()

    def get_task(self, course, node_id) -> Optional[Dict]:
        row = self.conn.execute(
            "SELECT * FROM tasks WHERE course=? AND node_id=?", (course, node_id)
        ).fetchone()
        return dict(row) if row else None

    def get_tasks(self, course: str, states: Optional[List[str]] = None) -> List[Dict]:
        if states:
            marks = ",".join("?" for _ in states)
            rows = self.conn.execute(
                f"SELECT * FROM tasks WHERE course=? AND state IN ({marks}) ORDER BY id",
                [course] + states
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM tasks WHERE course=? ORDER BY id", (course,)
            ).fetchall()
        return [dict(r) for r in rows]

    def update_task_state(self, course, node_id, to_state, reason="", retry_count=None):
        row = self.get_task(course, node_id)
        if not row:
            return
        sets = ["state=?", "reason=?"]
        params = [to_state, reason]
        if retry_count is not None:
            sets.append("retry_count=?"); params.append(retry_count)
        elif to_state == "ERROR":
            sets.append("retry_count=retry_count+1")
        params += [course, node_id]
        self.conn.execute(f"UPDATE tasks SET {','.join(sets)} WHERE course=? AND node_id=?", params)
        self.conn.execute("""
            INSERT INTO events(course,node_id,from_state,to_state,reason,ts)
            VALUES(?,?,?,?,?,?)
        """, (course, node_id, row["state"], to_state, reason, now()))
        self.conn.commit()

    def update_task_meta(self, course, node_id, content_types=None, meta=None):
        sets, params = [], []
        if content_types is not None:
            sets.append("content_types=?"); params.append(json.dumps(content_types, ensure_ascii=False))
        if meta is not None:
            sets.append("meta=?"); params.append(json.dumps(meta, ensure_ascii=False))
        if not sets:
            return
        params += [course, node_id]
        self.conn.execute(f"UPDATE tasks SET {','.join(sets)} WHERE course=? AND node_id=?", params)
        self.conn.commit()

    # ---------- 异常 ----------
    def log_anomaly(self, course, node_id, kind, reason, snapshot=None):
        self.conn.execute("""
            INSERT INTO anomalies(course,node_id,kind,reason,snapshot,ts)
            VALUES(?,?,?,?,?,?)
        """, (course, node_id, kind, reason,
              json.dumps(snapshot or {}, ensure_ascii=False), now()))
        self.conn.commit()

    def get_anomalies(self, course=None, handled=None):
        sql, params = "SELECT * FROM anomalies WHERE 1=1", []
        if course:
            sql += " AND course=?"; params.append(course)
        if handled is not None:
            sql += " AND handled=?"; params.append(handled)
        sql += " ORDER BY id"
        return [dict(r) for r in self.conn.execute(sql, params).fetchall()]

    # ---------- 题目建议 ----------
    def save_answer(self, course, node_id, question, options, suggestion, analysis):
        self.conn.execute("""
            INSERT INTO answers(course,node_id,question,options,suggestion,analysis,confirmed,ts)
            VALUES(?,?,?,?,?,?,0,?)
        """, (course, node_id, question, json.dumps(options, ensure_ascii=False),
              suggestion, analysis, now()))
        self.conn.commit()

    def confirm_answer(self, answer_id):
        self.conn.execute("UPDATE answers SET confirmed=1 WHERE id=?", (answer_id,))
        self.conn.commit()

    # ---------- 运行状态（断点恢复） ----------
    def set_run_state(self, key, value):
        self.conn.execute("""
            INSERT INTO run_state(key,value) VALUES(?,?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
        """, (key, str(value)))
        self.conn.commit()

    def get_run_state(self, key, default=None):
        row = self.conn.execute("SELECT value FROM run_state WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    # ---------- 统计 ----------
    def summary(self, course) -> Dict:
        rows = self.conn.execute(
            "SELECT state, COUNT(*) n FROM tasks WHERE course=? GROUP BY state", (course,)
        ).fetchall()
        counts = {r["state"]: r["n"] for r in rows}
        total = sum(counts.values())
        return {
            "total": total, "counts": counts,
            "completed": counts.get("COMPLETED", 0),
            "skipped": counts.get("SKIPPED", 0),
            "needs_review": counts.get("NEEDS_REVIEW", 0),
            "errors": counts.get("ERROR", 0),
            "progress_pct": round(counts.get("COMPLETED", 0) / total * 100, 1) if total else 0,
        }

    def close(self):
        self.conn.close()


if __name__ == "__main__":
    db = Database()
    # 冒烟测试
    db.upsert_course("test", "测试课程", "1", "2", "3")
    db.upsert_task("test", "n1", "1.1", "测试章节", 2)
    print("初始:", db.get_task("test", "n1")["state"])
    db.update_task_state("test", "n1", "RUNNING", "开始")
    db.update_task_state("test", "n1", "COMPLETED", "平台确认")
    print("完成后:", db.get_task("test", "n1")["state"])
    db.set_run_state("last_node", "n1")
    print("断点:", db.get_run_state("last_node"))
    print("统计:", db.summary("test"))
    print("事件数:", len([1 for _ in db.conn.execute("SELECT * FROM events")]))
    db.close()
    print("✅ 数据库冒烟测试通过")
