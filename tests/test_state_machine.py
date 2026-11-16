"""状态机单元测试"""
import sys
sys.path.insert(0, ".")
from core.state_machine import TaskNode, TaskQueue, TaskState, InvalidTransitionError


def test_transitions():
    t = TaskNode("n1", "测试章节")
    assert t.state == TaskState.WAITING
    t.mark_running()
    assert t.state == TaskState.RUNNING
    t.mark_completed()
    assert t.state == TaskState.COMPLETED
    print("✅ 正常流程 WAITING→RUNNING→COMPLETED")


def test_skipped_not_completed():
    """核心规则：跳过绝不等于完成"""
    t = TaskNode("n2", "跳过的章节")
    t.mark_running()
    t.mark_skipped("视频无法播放")
    assert t.state == TaskState.SKIPPED
    assert t.state != TaskState.COMPLETED
    assert not t.is_actionable
    # 跳过后不能再直接置为完成（需先恢复 WAITING）
    try:
        t.mark_completed()
        raise AssertionError("SKIPPED→COMPLETED 应被禁止")
    except InvalidTransitionError:
        pass
    print("✅ SKIPPED 不等于 COMPLETED，且不能直接转 COMPLETED")


def test_error_and_retry():
    t = TaskNode("n3", "异常章节")
    t.mark_running()
    t.mark_error("页面加载失败")
    assert t.state == TaskState.ERROR
    assert t.retry_count == 1
    assert t.is_actionable  # 异常任务可重试
    t.mark_running()
    t.mark_completed()
    assert t.state == TaskState.COMPLETED
    print("✅ ERROR→重试→COMPLETED，retry_count 正确")


def test_needs_review():
    t = TaskNode("n4", "需人工确认")
    t.mark_running()
    t.mark_needs_review("题目无法解析")
    assert t.state == TaskState.NEEDS_REVIEW
    assert t.is_actionable
    print("✅ NEEDS_REVIEW 状态正确，可继续处理")


def test_pause():
    t = TaskNode("n5", "暂停测试")
    t.mark_running()
    t.pause()
    assert t.state == TaskState.WAITING
    print("✅ RUNNING→WAITING 暂停正确")


def test_terminal():
    c = TaskNode("c1", "完成"); c.mark_running(); c.mark_completed()
    s = TaskNode("s1", "跳过"); s.mark_running(); s.mark_skipped("测试跳过")
    assert c.is_terminal and s.is_terminal
    print("✅ 终态判定正确")


def test_queue():
    q = TaskQueue()
    for i in range(3):
        q.add(TaskNode(f"q{i}", f"章节{i}"))
    q.tasks[0].mark_running(); q.tasks[0].mark_completed()
    nxt = q.next_actionable()
    assert nxt.node_id == "q1"
    summary = q.summary()
    assert summary["total"] == 3
    assert summary["counts"]["COMPLETED"] == 1
    assert summary["progress_pct"] == round(1/3*100, 1)
    print(f"✅ 队列顺序与统计正确: {summary}")


def test_history():
    t = TaskNode("h1", "历史测试")
    t.mark_running(); t.mark_error("err1"); t.mark_running(); t.mark_completed()
    assert len(t.history) == 4
    d = t.to_dict()
    assert len(d["history"]) == 4
    print("✅ 状态历史记录正确")


if __name__ == "__main__":
    test_transitions()
    test_skipped_not_completed()
    test_error_and_retry()
    test_needs_review()
    test_pause()
    test_terminal()
    test_queue()
    test_history()
    print("\n🎉 状态机全部测试通过")
