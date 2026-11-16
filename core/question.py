"""
题目辅助模块 —— 识别题干/选项 + AI 生成答案建议 + 人工确认后作答

重要边界（必须遵守）：
  1. 只生成"建议"，不自动提交任何考核/考试
  2. 必须由用户在面板确认后，才允许代为填写
  3. 无法解析或无法生成建议的题目，一律标记 NEEDS_REVIEW

设计：
  - parse_question_html(html)  纯解析，离线可测
  - AIAdvisor                  可插拔 AI 接口（OpenAI 兼容），无配置时降级为规则建议
  - 建议落库到 answers 表，confirmed=0，等人工确认
"""
import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Dict, Optional

ROOT = Path(__file__).resolve().parent.parent
AI_CONFIG = ROOT / "config" / "ai_config.json"


@dataclass
class Question:
    stem: str = ""                      # 题干
    options: List[str] = field(default_factory=list)  # 选项文本
    qtype: str = "unknown"              # single / multiple / judge / blank / unknown
    related_material: str = ""          # 关联课程资料文本
    raw_html: str = ""                  # 原始 HTML（备查）

    def to_dict(self):
        return asdict(self)


def _detect_qtype(text: str, html: str = "") -> str:
    """根据文本和 HTML 判断题型"""
    t = (text + " " + html).lower()
    if any(k in t for k in ("多选题", "多项选择", "multiple")):
        return "multiple"
    if any(k in t for k in ("判断题", "对错", "正确错误", "true or false", "judge")):
        return "judge"
    if any(k in t for k in ("填空题", "填空", "blank")):
        return "blank"
    if any(k in t for k in ("单选题", "单项选择", "single")):
        return "single"
    return "unknown"


def parse_question_html(html: str) -> List[Question]:
    """
    从题库/测验页 HTML 解析题目列表（纯解析，便于离线测试）。
    兼容常见结构：.question / .q-item / li 里的题干 + 选项 label。
    """
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    questions: List[Question] = []

    # 常见题目容器
    containers = soup.select(
        ".question, .q-item, .question-item, .topic-item, "
        ".singleQuestion, .multiQuestion, .judgeQuestion, .fillQuestion, "
        "[class*=questionItem], [class*=topic-item]"
    )
    if not containers:
        # 退而求其次：找包含题干文本和多个选项的 li/div
        containers = [c for c in soup.select("li, div")
                      if c.select_one("input[type=radio], input[type=checkbox]")]

    for c in containers:
        # 题型
        qtype = _detect_qtype(c.get("class") and " ".join(c.get("class")) or "", str(c))

        # 题干：优先专门的 class
        stem_el = (c.select_one(".q-text, .stem, .question-text, .topic-text, .title")
                   or c.select_one("p, div"))
        stem = stem_el.get_text(" ", strip=True) if stem_el else ""
        # 去掉题干里混入的题型前缀
        stem = re.sub(r"^\s*[（(]?\s*(单选题|多选题|判断题|填空题)\s*[)）]?\s*", "", stem).strip()

        # 选项
        options = []
        opt_els = c.select("label, .option, .q-option, .answer-option, li")
        for o in opt_els:
            txt = o.get_text(" ", strip=True)
            txt = re.sub(r"^[A-Za-z][\.、：:]\s*", "", txt).strip()
            if txt and txt not in options and len(txt) < 200:
                options.append(txt)
        # 判断题默认选项
        if qtype == "judge" and not options:
            options = ["正确", "错误"]

        if not stem:
            continue
        questions.append(Question(
            stem=stem, options=options, qtype=qtype,
            related_material="", raw_html=str(c)[:500]
        ))

    return questions


class AIAdvisor:
    """可插拔 AI 建议器：优先用配置的 OpenAI 兼容接口，失败则降级为规则建议"""

    def __init__(self, config_path: Path = AI_CONFIG):
        self.cfg = {}
        if config_path.exists():
            try:
                self.cfg = json.loads(config_path.read_text(encoding="utf-8"))
            except Exception:
                self.cfg = {}
        self.enabled = bool(self.cfg.get("api_key") and self.cfg.get("base_url"))

    def generate(self, q: Question) -> Dict:
        """生成答案建议与解析。返回 {suggestion, analysis, source}"""
        if self.enabled:
            try:
                return self._call_api(q)
            except Exception as e:
                # API 失败降级，不抛异常中断流程
                fallback = self._rule_based(q)
                fallback["analysis"] += f"\n（AI接口调用失败，已降级为规则建议: {e}）"
                return fallback
        return self._rule_based(q)

    def _call_api(self, q: Question) -> Dict:
        """调用 OpenAI 兼容的 chat/completions 接口"""
        import urllib.request
        base = self.cfg["base_url"].rstrip("/")
        model = self.cfg.get("model", "gpt-3.5-turbo")
        prompt = self._build_prompt(q)
        body = json.dumps({
            "model": model,
            "messages": [
                {"role": "system", "content": "你是课程答题助手。只给出答案建议和简短解析，不承诺替用户提交。"},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{base}/chat/completions", data=body,
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.cfg['api_key']}"},
        )
        with urllib.request.urlopen(req, timeout=self.cfg.get("timeout", 30)) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        content = data["choices"][0]["message"]["content"]
        return self._parse_api_reply(content)

    def _build_prompt(self, q: Question) -> str:
        lines = [f"题型：{q.qtype}", f"题干：{q.stem}"]
        if q.options:
            lines.append("选项：" + " | ".join(f"{chr(65+i)}. {o}" for i, o in enumerate(q.options)))
        if q.related_material:
            lines.append("关联课程资料：\n" + q.related_material[:1500])
        lines.append("\n请输出：\n答案：<选项字母或内容>\n解析：<简短解释>")
        return "\n".join(lines)

    def _parse_api_reply(self, content: str) -> Dict:
        m = re.search(r"答案[：:]\s*(.+)", content)
        a = re.search(r"解析[：:]\s*([\s\S]+)", content)
        return {
            "suggestion": m.group(1).strip() if m else content.strip()[:120],
            "analysis": a.group(1).strip() if a else "",
            "source": f"ai:{self.cfg.get('model', 'unknown')}",
        }

    def _rule_based(self, q: Question) -> Dict:
        """无 AI 接口时的保守建议：不猜答案，提示人工判断"""
        hint = ""
        if q.qtype == "judge":
            hint = "判断题仅两个选项，请结合课程内容判断。"
        elif q.qtype in ("single", "multiple"):
            hint = f"共 {len(q.options)} 个选项，请逐项对照课程资料判断。"
        return {
            "suggestion": "（未配置AI接口，未生成自动建议）",
            "analysis": f"题型：{q.qtype}。{hint} 需人工确认后再作答。",
            "source": "rule",
        }


if __name__ == "__main__":
    # 离线测试：模拟学习通测验题 HTML
    sample = """
    <div class="question singleQuestion">
      <div class="q-text">（单选题）人工智能的英文缩写是？</div>
      <label>A. AI</label>
      <label>B. ML</label>
      <label>C. DL</label>
      <label>D. NLP</label>
    </div>
    <div class="question judgeQuestion">
      <div class="q-text">（判断题）生成式AI可以创作文本和图像。</div>
    </div>
    """
    qs = parse_question_html(sample)
    print(f"解析出 {len(qs)} 道题：")
    for i, q in enumerate(qs, 1):
        print(f"  {i}. [{q.qtype}] {q.stem} | 选项={q.options}")
    assert len(qs) == 2, "应解析出 2 道题"
    assert qs[0].qtype == "single" and "AI" in qs[0].options[0]
    assert qs[1].qtype == "judge" and qs[1].options == ["正确", "错误"]

    advisor = AIAdvisor()
    for q in qs:
        r = advisor.generate(q)
        print(f"  建议[{r['source']}]: {r['suggestion']}")
        assert r["suggestion"], "必须有建议字段"

    print("✅ 题目辅助模块离线测试通过")
