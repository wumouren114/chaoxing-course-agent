"""
章节测验自动答题模块（2026-11-17）

学习通章节结构：一个章节含"1视频 + 2测验"两个任务点。视频播完后，
测验藏在章节学习页的"测验"tab 里，点击后加载题目 iframe：
  ananas/modules/work/index.html → 子 iframe /mooc-ans/work/doHomeWorkNew?...

题目 DOM（已抓包确认）：
  - 题型分组 h3.newTestType："一. 单选题（共1题）"
  - 题目容器 div[id^=question].singleQuesId / .judgeQuesId / .multiQuesId
  - 选项 li[qid][qtype]，span.num_option[data=A/B/C/D 或 true/false]，
    选项文字在 a.after（正常明文）；题干 .fontLabel 被平台字体加密成乱码，
    但答题只需"选项文字 + 题型"即可靠常识作答。
  - qtype: 0=单选, 1=多选, 3=判断, 2=填空
  - 提交 a.btnSubmit(onclick=btnBlueSubmit())，保存 a.btnSave

工作方式（人在回路）：
  1. 抓题 → 写入 pending_questions.json（题干尽量还原 + 明文选项）
  2. 我在对话里读选项给答案 → answer(qid, "B" 或 "A,B") 写回队列
  3. 脚本轮询到答案 → 正常点击选项 → 点提交 → 核验

安全边界：
  - 只处理"章节测验"（doHomeWorkNew / 章节测验），不碰考试/考核/期末
  - 遇到考试关键词拒绝作答
  - 无法可靠解析/提交时不猜，标记 NEEDS_REVIEW
"""
import re
import time
import json
from typing import Dict, List, Optional
from pathlib import Path

from core.logger import get_logger
from core import question_queue as qq

log = get_logger("chapter_quiz")

EXAM_KEYWORDS = ["期末考试", "课程考核", "结课考试", "期中考试", "正式考试",
                 "成绩考核", "考试成绩", "监考", "考试倒计时", "期末测验"]

# qtype -> 中文题型
QTYPE_NAME = {"0": "单选题", "1": "多选题", "2": "填空题", "3": "判断题"}


def find_quiz_tab(page):
    """在章节学习页找"测验"tab（形如"2测验"），返回可点击元素或 None"""
    for f in page.frames:
        try:
            loc = f.locator("li:has-text('测验'), a:has-text('测验'), span:has-text('测验')")
            for j in range(loc.count()):
                el = loc.nth(j)
                if not el.is_visible(timeout=800):
                    continue
                txt = (el.inner_text(timeout=800) or "").strip()
                if txt.endswith("测验"):
                    return el
        except Exception:
            continue
    return None


def has_quiz(page, wait_ms=8000) -> bool:
    """判断当前章节是否有测验 tab"""
    return find_quiz_tab(page) is not None


def open_quiz(page, timeout_ms=12000):
    """点击"测验"tab，返回题目 iframe（url 含 work/doHomeWorkNew 或 api/work）"""
    tab = find_quiz_tab(page)
    if not tab:
        return None
    try:
        tab.click(timeout=5000)
    except Exception as e:
        log.warning(f"点击测验tab失败: {e}")
        return None
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        for f in page.frames:
            u = f.url or ""
            # 答题页 doHomeWorkNew；已完成后的回顾页 selectWorkQuestionYiPiYue
            if any(k in u for k in ("doHomeWorkNew", "/api/work?", "selectWorkQuestion")):
                return f
        page.wait_for_timeout(1000)
    return None


def find_quiz_frame(page):
    """不点击tab，直接在现有 frames 里找题目 iframe（答题页或回顾页）。"""
    for f in page.frames:
        u = f.url or ""
        if any(k in u for k in ("doHomeWorkNew", "/api/work?", "selectWorkQuestion")):
            return f
    return None


def check_quiz_status(qf) -> str:
    """返回测验状态：completed / pending / unknown"""
    try:
        txt = qf.evaluate("() => document.body ? document.body.innerText : ''") or ""
    except Exception:
        return "unknown"
    if "已完成" in txt or "本次成绩" in txt:
        return "completed"
    if "待完成" in txt:
        return "pending"
    return "unknown"


def parse_quiz(qf) -> Dict:
    """
    从题目 iframe 解析所有题目。
    返回 {questions: [{qid,qtype,type_name,stem,options:[{key,text}]}], title, exam:bool}
    """
    info = {"questions": [], "title": "", "exam": False}
    try:
        body = qf.evaluate("() => document.body ? document.body.innerText : ''") or ""
    except Exception:
        body = ""
    if any(k in body for k in EXAM_KEYWORDS):
        info["exam"] = True
        return info
    # 标题（章节测验 / Midjourney服务器创建）
    m = re.search(r"章节测验\s*\n?\s*(?:待完成|已完成)?\s*\n?\s*([^\n]+)", body)
    if m:
        info["title"] = m.group(1).strip()

    # 逐题：按 li[qid] 分组
    try:
        items = qf.evaluate("""() => {
            const out = [];
            const lis = document.querySelectorAll('li[qid][qtype]');
            const seen = {};
            for (const li of lis) {
                const qid = li.getAttribute('qid');
                const qtype = li.getAttribute('qtype');
                if (!seen[qid]) {
                    const qdiv = document.getElementById('question' + qid);
                    let stem = '';
                    if (qdiv) {
                        const t = qdiv.querySelector('.fontLabel, .Zy_TItle');
                        stem = t ? t.innerText.trim() : '';
                    }
                    seen[qid] = {qid, qtype, stem, options: []};
                    out.push(seen[qid]);
                }
                const opt = li.querySelector('span.num_option');
                const txt = li.querySelector('a.after');
                seen[qid].options.push({
                    key: opt ? (opt.getAttribute('data') || '') : '',
                    text: txt ? txt.innerText.trim() : (li.innerText || '').trim()
                });
            }
            return out;
        }""")
    except Exception as e:
        log.warning(f"解析题目JS异常: {e}")
        return info

    for it in items or []:
        if not it["options"]:
            continue
        info["questions"].append({
            "qid": it["qid"],
            "qtype": it["qtype"],
            "type_name": QTYPE_NAME.get(it["qtype"], "未知题型"),
            "stem": it["stem"],
            "options": it["options"],
        })
    return info


def queue_questions(course, node_id, info, wait_seconds=900) -> List[str]:
    """把题目写入协作队列，返回 qid 列表。题干乱码时用选项重建可读题干。"""
    qids = []
    for q in info["questions"]:
        opts = [o["text"] for o in q["options"]]
        # 题干乱码（含 cxsecret 特征字）时，用题型+选项做可读提示
        stem = q["stem"]
        if not stem or re.search(r"[\u4e00-\u9fff]{0,2}[\u0100-\u017f]", stem) and "Midjourney" not in stem:
            stem = f"[{q['type_name']}] 请从选项中选择正确答案"
        qid = qq.enqueue(course, node_id, stem, opts,
                         qtype=q["qtype"], context="章节测验", screenshot="")
        qids.append(qid)
        log.info(f"测验题入队 {qid}: {q['type_name']} 选项={opts}")
    return qids


def wait_and_collect(qids, wait_seconds=900, poll=3) -> Dict[str, str]:
    """轮询队列，等待助手作答。返回 {qid: answer}"""
    start = time.time()
    got = {}
    while time.time() - start < wait_seconds:
        answered = {a["id"]: a for a in qq.get_answered()}
        for qid in qids:
            if qid in answered and qid not in got:
                got[qid] = (answered[qid].get("answer") or "").strip()
                log.info(f"收到作答 {qid} -> {got[qid]}")
        if len(got) == len(qids):
            break
        time.sleep(poll)
    return got


def select_and_submit(page, qf, info, answers: Dict[str, str]) -> bool:
    """
    按答案点选选项并提交。
    实测学习通行为：
      - 点选项 li 或 a.after 会设置 hidden input answer<qid>=<key>（单选key=A/B，判断key=true/false）
      - 点 a.btnSubmit 后在【父页面】弹出"确认提交？"确认框，需再点其中的"提交"
    answers: {qid: 'B' 或 'B,D' 或选项文字}
    """
    try:
        for q in info["questions"]:
            qid = q["qid"]
            ans = answers.get(qid, "")
            if not ans:
                return False
            keys = _normalize_answer(ans, q)
            if not keys:
                log.warning(f"无法定位答案: qid={qid} ans={ans}")
                return False
            for k in keys:
                # 用选项索引定位（选项顺序固定 A/B/C/D，判断 A=对/B=错），
                # 避免选项文字含 / 等符号时破坏 CSS 选择器。
                idx = _answer_index(k, q)
                clicked = False
                if idx >= 0:
                    lis = qf.locator(f"li[qid='{qid}']")
                    try:
                        if idx < lis.count():
                            # 点 li 触发 addChoice（实测可靠）
                            lis.nth(idx).click(timeout=3000)
                            clicked = True
                    except Exception:
                        pass
                if not clicked:
                    # 兜底：仍尝试 data 属性
                    for dk in [k, _to_bool_key(k)]:
                        try:
                            loc = qf.locator(f"li[qid='{qid}'] span.num_option[data='{dk}']")
                            if loc.count() > 0 and loc.first.is_visible(timeout=1000):
                                loc.first.click(timeout=3000)
                                clicked = True
                                break
                        except Exception:
                            continue
                if not clicked:
                    log.warning(f"选项点击失败 qid={qid} key={k}")
            # 核验 hidden input 是否记录成功
            recorded = ""
            try:
                recorded = qf.evaluate(
                    f"() => {{ const e=document.querySelector('input[name=answer{qid}]'); return e?e.value:''; }}")
            except Exception:
                pass
            log.info(f"已选 qid={qid} -> {keys} (记录值={recorded})")

        # 点提交按钮
        submitted = False
        for sel in ["a.btnSubmit", "a.workBtnIndex:has-text('提交')"]:
            try:
                btn = qf.locator(sel).first
                if btn.count() > 0 and btn.is_visible(timeout=1000):
                    btn.click(timeout=5000)
                    submitted = True
                    log.info("已点击提交按钮")
                    break
            except Exception:
                continue
        if not submitted:
            return False
        time.sleep(2)

        # 处理父页面"确认提交？"弹窗
        confirmed = _confirm_submit(page)
        if confirmed:
            log.info("已确认提交弹窗")
        time.sleep(3)
        return True
    except Exception as e:
        log.warning(f"提交异常: {e}")
        return False


def _answer_index(k: str, q: Dict) -> int:
    """答案 key 转选项索引。单选/多选 A->0...；判断 true/A/对->0, false/B/错->1。"""
    opts = q.get("options", [])
    if q.get("qtype") == "3" or len(opts) == 2 and opts[0]["key"] in ("true", "A"):
        return 0 if k.upper() in ("A", "TRUE", "对", "正确") else 1
    if re.fullmatch(r"[A-Da-d]", k):
        return ord(k.upper()) - ord("A")
    # 按 key 反查
    for i, o in enumerate(opts):
        if o["key"] == k:
            return i
    return -1


def _to_bool_key(k: str) -> str:
    """判断题 A->true / B->false"""
    if k == "A":
        return "true"
    if k == "B":
        return "false"
    return k


def _confirm_submit(page) -> bool:
    """在父页面找"确认提交？"弹窗并点"提交"确认。"""
    for f in [page.main_frame] + [fr for fr in page.frames if fr != page.main_frame]:
        try:
            txt = f.evaluate("() => document.body ? document.body.innerText : ''") or ""
            if "确认提交" not in txt:
                continue
            # 在弹窗内点"提交"（排除"暂时保存"）
            for sel in ["a:has-text('提交')", "button:has-text('提交')", "text=提交"]:
                loc = f.locator(sel)
                for j in range(loc.count()):
                    el = loc.nth(j)
                    if el.is_visible(timeout=800):
                        t = (el.inner_text(timeout=800) or "").strip()
                        if t == "提交":
                            el.click(timeout=3000)
                            return True
        except Exception:
            continue
    return False


def _normalize_answer(ans: str, q: Dict) -> List[str]:
    """把助手答案转成选项 key 列表。支持 'B'、'B,D'、'true'、'对'、选项文字。"""
    ans = ans.strip()
    qtype = q["qtype"]
    opts = q["options"]
    # 判断题
    if qtype == "3" or ans in ("对", "错", "正确", "错误", "true", "false", "True", "False"):
        mapping = {"对": "true", "正确": "true", "true": "true", "True": "true", "A": "true",
                   "错": "false", "错误": "false", "false": "false", "False": "false", "B": "false"}
        if ans in mapping:
            return [mapping[ans]]
        # 判断题 data 可能就是 A/B
        for o in opts:
            if o["text"] in ans:
                return [o["key"]]
        return []
    # 选项文字优先（避免 "Discord" 里的 D/c/d 被误当字母答案）
    for o in opts:
        if o["text"] and len(o["text"]) >= 2 and o["text"].lower() in ans.lower():
            return [o["key"]]
    # 再试去掉前导符号的核心词（如 "/imagine" -> "imagine"，兼容路径等被转义的情况）
    for o in opts:
        core = re.sub(r"^[\s/\-#]+", "", o["text"] or "").lower()
        if len(core) >= 3 and core in ans.lower():
            return [o["key"]]
    # 纯字母答案：如 "B" / "B,D" / "答案：B" / "选B"
    # 只从"看起来是选项字母"的片段提取——去掉常见中文前缀和标点，
    # 剩下的若仅由 A-D/逗号/空格组成才认作字母答案。
    cleaned = re.sub(r"[答案选项选择：:是为\.、\s]", "", ans)
    if cleaned and re.fullmatch(r"[A-Da-d,，/]+", cleaned):
        letters = [c.upper() for c in re.findall(r"[A-Da-d]", cleaned)]
        valid = {o["key"].upper() for o in opts if o.get("key")}
        # 多选题的选项 key 为空（字母藏在 aria-label / 索引里），
        # 此时不能用 valid 白名单过滤，否则全被过滤掉导致提交失败。
        # 直接按字母序返回，交给 _answer_index 按索引点选。
        if not valid:
            return letters
        return [c for c in letters if c in valid]
    return []


def answer_quiz(page, course, node_id, wait_seconds=900) -> Dict:
    """
    完整流程：打开测验tab → 解析 → 入队等作答 → 提交 → 返回结果。
    供 course_runner 在视频播完后调用。
    """
    result = {"handled": False, "status": "none", "reason": ""}
    if not has_quiz(page):
        result["reason"] = "该章节无测验tab"
        return result
    qf = open_quiz(page)
    if not qf:
        result["status"] = "needs_review"
        result["reason"] = "找到测验tab但未加载题目iframe"
        return result
    # 等待题目容器异步加载（关键：open_quiz 返回时题目可能还没渲染出来）
    try:
        qf.wait_for_selector("li[qid][qtype]", timeout=15000)
    except Exception:
        log.warning("等待题目容器超时，尝试直接解析")
    page.wait_for_timeout(2000)
    info = parse_quiz(qf)
    if info.get("exam"):
        result.update(handled=True, status="refused_exam", reason="检测到考试/考核，拒绝作答")
        return result
    qs = info["questions"]
    if not qs:
        result.update(handled=True, status="needs_review", reason="未解析到题目")
        return result
    result["handled"] = True
    result["question_count"] = len(qs)
    result["questions"] = qs

    qids = queue_questions(course, node_id, info, wait_seconds=wait_seconds)
    log.info(f"等待作答（最多{wait_seconds}秒），请到面板/队列查看题目")
    answers = wait_and_collect(qids, wait_seconds=wait_seconds)

    if len(answers) < len(qids):
        result.update(status="needs_review",
                      reason=f"{len(qids)}题中仅作答{len(answers)}题（等待超时）")
        return result

    # 关键：wait_and_collect 返回的 answers 以"队列id"为键，
    # 而 select_and_submit 按"题目qid"取值 —— 必须做一次映射转换。
    answers_by_qid = {}
    for q, qid in zip(info["questions"], qids):
        if qid in answers:
            answers_by_qid[q["qid"]] = answers[qid]

    # 等待作答期间 iframe 可能被平台重建（frame detached），重新获取题目 frame
    fresh_qf = find_quiz_frame(page) or qf
    try:
        fresh_qf.wait_for_selector("li[qid][qtype]", timeout=8000)
    except Exception:
        pass
    ok = select_and_submit(page, fresh_qf, info, answers_by_qid)
    # 落库留痕
    try:
        from core.database import Database
        db = Database()
        for q, qid in zip(qs, qids):
            db.save_answer(course, node_id, q["stem"],
                           json.dumps([o["text"] for o in q["options"]], ensure_ascii=False),
                           answers.get(qid, ""), f"题型={q['type_name']} 提交={'成功' if ok else '失败'}")
        db.close()
    except Exception:
        pass
    for qid in qids:
        qq.mark_submitted(qid, ok)

    result.update(status="answered" if ok else "needs_review",
                  reason=f"已提交{len(qs)}题" if ok else "作答已生成但提交失败")
    return result


if __name__ == "__main__":
    # 离线测试答案归一化
    q1 = {"qtype": "0", "options": [{"key":"A","text":"WeChat"},{"key":"B","text":"Discord"},
                                     {"key":"C","text":"Twitter"},{"key":"D","text":"Telegram"}]}
    q2 = {"qtype": "3", "options": [{"key":"true","text":"对"},{"key":"false","text":"错"}]}
    assert _normalize_answer("B", q1) == ["B"]
    assert _normalize_answer("答案：B. Discord", q1) == ["B"]
    assert _normalize_answer("Discord", q1) == ["B"]
    assert _normalize_answer("对", q2) == ["true"]
    assert _normalize_answer("错误", q2) == ["false"]
    print("✅ chapter_quiz 离线测试通过（答案归一化）")
