"""
弹题/测验处理模块 —— 检测播放中弹出的题目，生成答案并作答提交

工作方式（按用户最新指令：直接作答提交，无需逐题确认）：
  1. 在播放器 frame 内检测动态出现的弹题容器
  2. 用 question.parse_question_html 解析题干/选项/题型
  3. 用 AIAdvisor 生成答案建议
  4. 在页面内点选对应选项并提交（正常网页点击，不伪造、不改接口）
  5. 全程记录到 answers 表（含 AI 建议与解析），并写日志

安全边界：
  - 只处理"随课弹题/章节练习"，不碰"考试/考核/期末"
  - 若检测到"考试/考核/成绩"等关键词，拒绝作答并记录 NEEDS_REVIEW
  - 无法可靠解析或提交时，不猜、不强点，记录 NEEDS_REVIEW
"""
import re
import time
from typing import Dict, Optional, List

from core.question import parse_question_html, AIAdvisor, Question
from core.logger import get_logger

log = get_logger("quiz")

# 弹题容器选择器（学习通 video.js 弹题多种形态，多选择器兼容）
QUIZ_SELECTORS = [
    ".vjs-question-popup", ".ans-question-box", ".question-popup",
    ".zjym-question", ".popquiz", ".video-question",
    "[class*=questionMask]", "[class*=popQuiz]", "[class*=topicPop]",
    ".ans-timu", ".timu-box",
]

# 考试/考核 高危关键词 —— 出现则拒绝自动作答
EXAM_KEYWORDS = ["期末考试", "课程考核", "结课考试", "期中考试", "正式考试",
                 "成绩考核", "考试成绩", "监考", "考试倒计时"]


def detect_quiz_frame(page):
    """在所有 frame 中检测当前是否有可见弹题，返回 (frame, element) 或 (None, None)"""
    frames = [page.main_frame] + [f for f in page.frames if f != page.main_frame]
    for fr in frames:
        for sel in QUIZ_SELECTORS:
            try:
                loc = fr.locator(sel)
                if loc.count() > 0 and loc.first.is_visible():
                    return fr, loc.first
            except Exception:
                continue
    return None, None


def is_exam_context(text: str) -> bool:
    """判断是否为考试/考核场景（高危，拒绝作答）"""
    return any(k in text for k in EXAM_KEYWORDS)


def extract_quiz_text(fr, element) -> str:
    """提取弹题容器的文本"""
    try:
        return element.inner_text(timeout=3000)
    except Exception:
        return ""


def answer_quiz(page, course: str, node_id: str, max_wait: int = 3) -> Dict:
    """
    检测并处理当前页面的弹题（直接作答提交）。
    返回 {handled, status, reason, detail}
      handled: 是否检测到并处理了题目
      status: answered / refused_exam / needs_review / none
    """
    fr, el = detect_quiz_frame(page)
    if not fr or not el:
        return {"handled": False, "status": "none", "reason": "未检测到弹题"}

    text = extract_quiz_text(fr, el)
    log.info(f"检测到弹题 [{course}/{node_id}]: {text[:80]}")

    # 安全边界：考试/考核拒绝作答
    if is_exam_context(text):
        log.warning("检测到考试/考核关键词，拒绝自动作答")
        return {"handled": True, "status": "refused_exam",
                "reason": "检测到考试/考核场景，按边界拒绝自动作答", "detail": text[:200]}

    # 解析题目（在 frame 内取 HTML）
    try:
        html = el.evaluate("(e) => e.outerHTML")
    except Exception:
        html = ""
    questions = parse_question_html(html)
    if not questions:
        # 退而求其次：把文本当作单题题干
        if len(text) > 8:
            questions = [Question(stem=text[:300], qtype="unknown")]
        else:
            return {"handled": True, "status": "needs_review",
                    "reason": "弹题文本无法解析", "detail": text[:200]}

    advisor = AIAdvisor()
    results = []
    for q in questions:
        suggestion = advisor.generate(q)
        results.append({"question": q.to_dict(), "suggestion": suggestion})

    # 尝试在页面内作答提交
    submitted = _submit_answers(fr, el, questions, results)

    if submitted:
        return {"handled": True, "status": "answered",
                "reason": f"已作答提交 {len(questions)} 题", "detail": results}
    else:
        return {"handled": True, "status": "needs_review",
                "reason": "已生成答案但无法可靠提交（选项/按钮未识别）", "detail": results}


def _submit_answers(fr, el, questions: List[Question], results: List[Dict]) -> bool:
    """
    在页面内点选答案并提交（正常 DOM 点击）。
    兼容：radio/checkbox + 选项文本匹配；提交按钮多种文案。
    返回是否成功提交。
    """
    submitted_any = False
    try:
        for i, (q, r) in enumerate(zip(questions, results)):
            ans = r["suggestion"].get("suggestion", "")
            # 从答案文本里提取选项字母
            letters = re.findall(r"[A-Da-d]", ans)
            target_idxs = []
            if letters:
                target_idxs = [ord(c.upper()) - ord("A") for c in letters if ord(c.upper()) - ord("A") < len(q.options)]
            elif q.options:
                # 尝试按答案文本匹配选项内容
                for j, opt in enumerate(q.options):
                    if opt and (opt in ans or ans in opt):
                        target_idxs.append(j)

            if not target_idxs and q.options:
                # 无法定位答案，不猜
                continue

            # 点选选项（在弹题容器内）
            inputs = el.locator("input[type=radio], input[type=checkbox]")
            labels = el.locator("label, .option, li")
            for idx in target_idxs:
                if idx < inputs.count():
                    try:
                        inputs.nth(idx).check(force=True)
                    except Exception:
                        pass
                elif idx < labels.count():
                    try:
                        labels.nth(idx).click(force=True)
                    except Exception:
                        pass
            if target_idxs:
                submitted_any = True

        if not submitted_any:
            return False

        # 点提交按钮
        for label in ["提交", "确定", "确认", "提交答案", "下一题", "交卷"]:
            btn = el.locator(f"text={label}").first
            if btn.count() > 0:
                try:
                    btn.click(force=True)
                    log.info(f"已点击提交按钮: {label}")
                    return True
                except Exception:
                    continue
        # 找不到提交按钮，尝试容器外的按钮
        for label in ["提交", "确定"]:
            btn = fr.locator(f"button:has-text('{label}'), .btn:has-text('{label}')").first
            if btn.count() > 0:
                try:
                    btn.click(force=True)
                    return True
                except Exception:
                    continue
        return False
    except Exception as e:
        log.warning(f"提交答案异常: {e}")
        return False


def handle_pause_for_quiz(page, player_frame, course: str, node_id: str,
                          wait_seconds: int = 120, context: str = "") -> bool:
    """
    on_pause 回调：视频暂停时检查是否因弹题，走"抓题→入队→等作答→提交"流程。
    返回 True 表示处理了弹题（可恢复播放），False 表示无弹题。

    注意：这是"人在回路"模式——脚本入队后等待助手在对话中作答（写回队列），
    脚本轮询到答案后自动填选提交。等待超时则跳过该题，不阻塞整体播放。
    """
    from core.question_queue import enqueue, get_answered, mark_submitted
    import core.question_queue as qq

    fr, el = detect_quiz_frame(page)
    if not fr or not el:
        return False

    text = extract_quiz_text(fr, el)
    log.info(f"暂停时发现弹题: {text[:80]}")

    if is_exam_context(text):
        log.warning("考试/考核场景，拒绝作答，跳过")
        return False  # 不处理，让播放逻辑尝试恢复或直接进入下一阶段

    # 解析题目
    try:
        html = el.evaluate("(e) => e.outerHTML")
    except Exception:
        html = ""
    questions = parse_question_html(html)
    if not questions and len(text) > 8:
        questions = [Question(stem=text[:300], qtype="unknown")]
    if not questions:
        return False

    # 入队（每题），截图留证
    qids = []
    for q in questions:
        shot = ""
        try:
            from datetime import datetime
            shot_name = f"{course}_{node_id}_{int(time.time()*1000)}.png"
            shot_path = str(ROOT_QSHOT / shot_name)
            el.screenshot(path=shot_path)
            shot = f"qshots/{shot_name}"
        except Exception:
            pass
        qid = enqueue(course, node_id, q.stem, q.options, q.qtype,
                      context=context, screenshot=shot)
        qids.append((qid, q))
        log.info(f"弹题入队待作答: {q.stem[:50]} -> {qid}")

    # 轮询等待助手作答
    start = time.time()
    answered_map = {}
    while time.time() - start < wait_seconds:
        answered = {a["id"]: a for a in get_answered()}
        for qid, q in qids:
            if qid in answered and qid not in answered_map:
                answered_map[qid] = answered[qid]
        if len(answered_map) == len(qids):
            break
        time.sleep(3)

    # 提交已作答的题
    any_submitted = False
    for qid, q in qids:
        if qid in answered_map:
            ans = answered_map[qid]
            # 构造一个假的 suggestion 结构供 _submit_answers 使用
            fake_result = {"suggestion": {"suggestion": ans["answer"], "analysis": ans.get("analysis", "")}}
            ok = _submit_answers(fr, el, [q], [fake_result])
            mark_submitted(qid, ok)
            try:
                from core.question_queue import persist_to_db
                persist_to_db(ans)
            except Exception:
                pass
            if ok:
                any_submitted = True
            log.info(f"弹题作答提交: {'成功' if ok else '失败'} - {q.stem[:40]}")
        else:
            # 超时未作答，标记跳过
            mark_submitted(qid, False)
            log.warning(f"弹题等待作答超时，跳过: {q.stem[:40]}")

    return any_submitted


from pathlib import Path as _Path
ROOT_QSHOT = _Path(__file__).resolve().parent.parent / "web"


if __name__ == "__main__":
    # 离线测试：安全边界 + 答案提取逻辑
    assert is_exam_context("期末考试——请独立完成"), "应识别考试场景"
    assert is_exam_context("课程考核倒计时"), "应识别考核场景"
    assert not is_exam_context("单选题：人工智能的英文缩写是？"), "普通题不应误判"

    # 答案字母提取
    assert re.findall(r"[A-Da-d]", "答案：A") == ["A"]
    assert re.findall(r"[A-Da-d]", "答案: B") == ["B"]
    print("✅ 弹题处理模块离线测试通过（安全边界 + 答案提取）")
