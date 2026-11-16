"""
调度器核心 —— Agent 的大脑
把 状态机 + 数据库 + 视频监测 串起来，支持 开始/暂停/继续/停止。
原则：
- 按目录顺序处理任务
- 单任务异常隔离，记录后继续下一个允许执行的任务
- SKIPPED 绝不等于 COMPLETED
- 暂停时记录进度，可断点恢复
"""
import time
import threading
from enum import Enum
from typing import Optional, Callable

from core.database import Database
from core.logger import get_logger
from core.state_machine import TaskState

log = get_logger("scheduler")


class ControlState(str, Enum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"


class Controller:
    """线程安全的控制状态（供控制面板与调度循环通信）"""
    def __init__(self):
        self._state = ControlState.IDLE
        self._lock = threading.Lock()

    @property
    def state(self):
        with self._lock:
            return self._state

    def set(self, state: ControlState):
        with self._lock:
            self._state = state
        log.info(f"控制状态: {state.value}")

    def start(self):  self.set(ControlState.RUNNING)
    def pause(self):  self.set(ControlState.PAUSED)
    def resume(self): self.set(ControlState.RUNNING)
    def stop(self):   self.set(ControlState.STOPPING)

    def should_stop(self):
        return self.state in (ControlState.STOPPING, ControlState.STOPPED)

    def should_pause(self):
        return self.state == ControlState.PAUSED

    def wait_if_paused(self, check_interval=1.0):
        """暂停时阻塞等待，直到恢复或停止"""
        while self.state == ControlState.PAUSED:
            time.sleep(check_interval)


class Scheduler:
    def __init__(self, db: Database, controller: Controller,
                 task_handler: Optional[Callable] = None):
        self.db = db
        self.controller = controller
        self.task_handler = task_handler  # 处理单个任务的回调
        self.log = log

    def build_task_list(self, course: str, catalog_items: list):
        """从目录解析结果建立完整任务列表（跳过分组标题）"""
        count = 0
        for item in catalog_items:
            if not item.get("node_id"):
                continue  # 分组标题，不建任务
            self.db.upsert_task(
                course, item["node_id"], item.get("number", ""),
                item.get("title", ""), item.get("job_count", 0),
                meta={"courseid": item.get("courseid"), "clazzid": item.get("clazzid")},
            )
            count += 1
        self.log.info(f"建立任务列表: {course} 共 {count} 个任务")
        return count

    def run(self, course: str):
        """主调度循环"""
        self.controller.start()
        self.log.info(f"调度开始: {course}")
        while not self.controller.should_stop():
            self.controller.wait_if_paused()

            # 取下一个可执行任务（WAITING/ERROR/NEEDS_REVIEW，按顺序）
            tasks = self.db.get_tasks(course, states=["WAITING", "ERROR", "NEEDS_REVIEW"])
            if not tasks:
                self.log.info("没有待处理任务，调度结束")
                break
            task = tasks[0]

            # 标记为 RUNNING
            self.db.update_task_state(course, task["node_id"], "RUNNING", "调度器领取")
            self.db.set_run_state(f"current_{course}", task["node_id"])

            # 处理任务（异常隔离）
            try:
                result = self._process_one(course, task)
            except Exception as e:
                self.log.exception(f"任务异常: {task['node_id']} - {e}")
                self.db.update_task_state(course, task["node_id"], "ERROR", f"异常: {e}")
                self.db.log_anomaly(course, task["node_id"], "exception", str(e))
                continue

            # 根据结果落状态
            self._apply_result(course, task, result)

        self.controller.set(ControlState.STOPPED)
        self.log.info("调度循环结束")

    def _process_one(self, course, task):
        """处理单个任务，返回 result dict"""
        if self.task_handler is None:
            # 默认：无处理器则标记需人工
            return {"status": "NEEDS_REVIEW", "reason": "未配置任务处理器"}
        return self.task_handler(course, task, self.controller)

    def _apply_result(self, course, task, result):
        node_id = task["node_id"]
        status = result.get("status", "ERROR")
        reason = result.get("reason", "")
        state_map = {
            "COMPLETED": TaskState.COMPLETED,
            "NEEDS_REVIEW": TaskState.NEEDS_REVIEW,
            "ERROR": TaskState.ERROR,
            "SKIPPED": TaskState.SKIPPED,
            "WAITING": TaskState.WAITING,
        }
        target = state_map.get(status, TaskState.ERROR)
        # 核心规则：SKIPPED 绝不能因成功路径变成 COMPLETED
        if target == TaskState.COMPLETED and not result.get("platform_confirmed", False):
            self.log.warning(f"任务 {node_id} 声称完成但无平台确认，降级为 NEEDS_REVIEW")
            target = TaskState.NEEDS_REVIEW
            reason = "完成未获平台确认: " + reason
        self.db.update_task_state(course, node_id, target.value, reason)
        self.log.info(f"任务 {node_id} -> {target.value} ({reason})")


if __name__ == "__main__":
    # 单元测试：用假数据验证调度循环与状态落库
    import tempfile
    from pathlib import Path
    db = Database(Path(tempfile.gettempdir()) / "sched_test.db")
    ctrl = Controller()
    sched = Scheduler(db, ctrl)

    items = [
        {"node_id": "n1", "number": "1.1", "title": "章节1", "job_count": 1, "courseid": "c", "clazzid": "k"},
        {"node_id": "", "number": "", "title": "分组标题", "job_count": 0},  # 应被跳过
        {"node_id": "n2", "number": "1.2", "title": "章节2", "job_count": 2, "courseid": "c", "clazzid": "k"},
    ]
    n = sched.build_task_list("test", items)
    assert n == 2, f"应建立2个任务，实际{n}"
    print("✅ 任务列表建立正确（分组标题被跳过）")

    # 测试控制状态
    ctrl.pause()
    assert ctrl.should_pause()
    ctrl.resume()
    assert not ctrl.should_pause()
    ctrl.stop()
    assert ctrl.should_stop()
    print("✅ 控制状态 开始/暂停/恢复/停止 正确")

    # 测试完成降级规则（无平台确认不能标完成）
    db.update_task_state("test", "n1", "RUNNING", "test")
    sched._apply_result("test", {"node_id": "n1"}, {"status": "COMPLETED", "reason": "声称完成"})
    assert db.get_task("test", "n1")["state"] == "NEEDS_REVIEW"
    print("✅ 无平台确认的完成被降级为 NEEDS_REVIEW")

    db.update_task_state("test", "n1", "RUNNING", "test")
    sched._apply_result("test", {"node_id": "n1"},
                        {"status": "COMPLETED", "reason": "平台确认", "platform_confirmed": True})
    assert db.get_task("test", "n1")["state"] == "COMPLETED"
    print("✅ 有平台确认的完成正确标为 COMPLETED")
    print("\n🎉 调度器单元测试通过")
