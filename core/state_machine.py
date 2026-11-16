"""
状态机模块 —— 任务状态管理
状态：WAITING / RUNNING / COMPLETED / NEEDS_REVIEW / ERROR / SKIPPED
核心规则：SKIPPED 绝不等于 COMPLETED；只有平台真实反馈完成才能置为 COMPLETED。
"""
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, List


class TaskState(str, Enum):
    WAITING = "WAITING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    ERROR = "ERROR"
    SKIPPED = "SKIPPED"


# 允许的合法状态转移
ALLOWED_TRANSITIONS: Dict[TaskState, set] = {
    TaskState.WAITING: {TaskState.RUNNING, TaskState.SKIPPED, TaskState.ERROR},
    TaskState.RUNNING: {
        TaskState.COMPLETED, TaskState.NEEDS_REVIEW,
        TaskState.ERROR, TaskState.SKIPPED, TaskState.WAITING,  # 暂停→回到等待
    },
    TaskState.NEEDS_REVIEW: {
        TaskState.COMPLETED, TaskState.WAITING, TaskState.ERROR, TaskState.SKIPPED,
    },
    TaskState.ERROR: {TaskState.WAITING, TaskState.RUNNING, TaskState.SKIPPED, TaskState.ERROR},
    TaskState.SKIPPED: {TaskState.WAITING},   # 可手动恢复
    TaskState.COMPLETED: set(),               # 终态，不再变化
}


class InvalidTransitionError(Exception):
    pass


@dataclass
class StateEvent:
    from_state: TaskState
    to_state: TaskState
    reason: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


@dataclass
class TaskNode:
    """一个章节任务节点"""
    node_id: str
    title: str
    number: str = ""
    course: str = ""
    job_count: int = 0
    state: TaskState = TaskState.WAITING
    reason: str = ""
    retry_count: int = 0
    history: List[StateEvent] = field(default_factory=list)
    # 内容识别结果
    content_types: List[str] = field(default_factory=list)
    meta: dict = field(default_factory=dict)

    def transition(self, to: TaskState, reason: str = "", force: bool = False):
        """执行一次状态转移。force=True 用于断点恢复等强制修正场景。"""
        if to == self.state:
            return
        if not force and to not in ALLOWED_TRANSITIONS.get(self.state, set()):
            raise InvalidTransitionError(
                f"非法状态转移: {self.state.value} -> {to.value} (任务 {self.node_id})"
            )
        self.history.append(StateEvent(self.state, to, reason))
        self.state = to
        self.reason = reason
        if to == TaskState.RUNNING:
            pass

    # 语义化快捷方法
    def mark_running(self, reason=""):
        self.transition(TaskState.RUNNING, reason)

    def mark_completed(self, reason="平台确认完成"):
        self.transition(TaskState.COMPLETED, reason)

    def mark_needs_review(self, reason):
        """需要人工处理：题目无法解析、需人工确认等"""
        self.transition(TaskState.NEEDS_REVIEW, reason)

    def mark_error(self, reason):
        """执行异常：视频无法播放、页面加载失败等"""
        self.retry_count += 1
        self.transition(TaskState.ERROR, reason)

    def mark_skipped(self, reason):
        """跳过：绝不等于完成"""
        self.transition(TaskState.SKIPPED, reason)

    def pause(self):
        """暂停：RUNNING -> WAITING"""
        self.transition(TaskState.WAITING, "用户暂停")

    @property
    def is_terminal(self) -> bool:
        """终态：不需要再自动处理"""
        return self.state in (TaskState.COMPLETED, TaskState.SKIPPED)

    @property
    def is_actionable(self) -> bool:
        """可继续处理的状态"""
        return self.state in (TaskState.WAITING, TaskState.ERROR, TaskState.NEEDS_REVIEW)

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id, "title": self.title, "number": self.number,
            "course": self.course, "job_count": self.job_count,
            "state": self.state.value, "reason": self.reason,
            "retry_count": self.retry_count,
            "content_types": self.content_types, "meta": self.meta,
            "history": [{"from": e.from_state.value, "to": e.to_state.value,
                         "reason": e.reason, "ts": e.timestamp} for e in self.history],
        }


class TaskQueue:
    """按目录顺序管理任务队列"""

    def __init__(self, tasks: Optional[List[TaskNode]] = None):
        self.tasks: List[TaskNode] = tasks or []

    def add(self, task: TaskNode):
        self.tasks.append(task)

    def next_actionable(self) -> Optional[TaskNode]:
        """按顺序返回下一个可处理的任务"""
        for t in self.tasks:
            if t.is_actionable:
                return t
        return None

    def get(self, node_id: str) -> Optional[TaskNode]:
        for t in self.tasks:
            if t.node_id == node_id:
                return t
        return None

    def summary(self) -> dict:
        counts = {s.value: 0 for s in TaskState}
        for t in self.tasks:
            counts[t.state.value] += 1
        total = len(self.tasks)
        return {
            "total": total,
            "counts": counts,
            "progress_pct": round(counts["COMPLETED"] / total * 100, 1) if total else 0,
        }
