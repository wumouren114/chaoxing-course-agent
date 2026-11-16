"""
目录解析模块 —— 从课程页面提取完整章节任务列表
- 复用 Session 登录态访问课程
- 解析 iframe 内的 chapter_item 节点
- 输出结构化章节列表（含 ID、编号、标题、任务点数、原始状态标识）
"""
import json
import re
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
PROFILE = ROOT / "data" / "browser_profile"
SNAP = ROOT / "data" / "snapshots"

# 课程中间页入口
COURSE_MIDDLE = ("https://mooc1.chaoxing.com/visit/stucoursemiddle"
                 "?courseid={courseid}&clazzid={clazzid}&cpi={cpi}&ismooc2=1&v=2")

# 两门目标课程
COURSES = {
    "ai_tools": {
        "name": "人人都能上手的AI工具",
        "courseid": "268560848", "clazzid": "158282453", "cpi": "575101306",
    },
    "ai_principle": {
        "name": "生成式人工智能原理及其影响和应用",
        "courseid": "268560836", "clazzid": "158282442", "cpi": "575101306",
    },
}


def parse_catalog_html(html: str, course_key: str) -> list:
    """从章节 iframe 的 HTML 中解析章节列表（纯字符串解析，便于离线测试）"""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for div in soup.select("div.chapter_item"):
        node_id = (div.get("id") or "").replace("cur", "")
        onclick = div.get("onclick") or ""
        title = div.get("title") or ""
        sbar_el = div.select_one(".catalog_sbar")
        sbar = sbar_el.get_text(strip=True) if sbar_el else ""
        name_el = div.select_one(".catalog_name")
        name = name_el.get_text(" ", strip=True) if name_el else title
        # 任务点数量
        count_el = div.select_one(".knowledgeJobCount")
        job_count = int(count_el.get("value", 0)) if count_el else 0
        # 完成状态文本（部分节点无进度元素）
        jindu = div.select_one(".catalog_jindu")
        status_text = " ".join(jindu.get("class", [])) if jindu else ""
        points = div.select_one(".catalog_points_yi")
        points_text = points.get_text(strip=True) if points else ""
        tip = div.select_one(".bntHoverTips")
        tip_text = tip.get_text(strip=True) if tip else ""
        # 从 onclick 提取课程/班级 ID
        m = re.search(r"toOld\('(\d+)',\s*'(\d+)',\s*'(\d+)'", onclick)
        cid, kid, clazz = (m.group(1), m.group(2), m.group(3)) if m else ("", node_id, "")
        items.append({
            "course": course_key,
            "node_id": node_id,
            "courseid": cid,
            "clazzid": clazz,
            "number": sbar,
            "title": title or name,
            "job_count": job_count,
            "points_text": points_text,
            "status_class": status_text,
            "tip": tip_text,
        })
    return items


def fetch_chapter_html(course_key: str, headless=True) -> str:
    """用登录态访问课程，返回章节 iframe 的 HTML"""
    cfg = COURSES[course_key]
    url = COURSE_MIDDLE.format(**cfg)
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE), channel="msedge", headless=headless, no_viewport=True
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)
        # 点掉开始学习弹窗
        for sel in ["text=我已阅读, 开始学习", "text=我已阅读", "text=开始学习"]:
            try:
                btn = page.locator(sel).first
                if btn.count() > 0:
                    btn.click()
                    page.wait_for_timeout(2500)
                    break
            except Exception:
                pass
        floc = page.frame_locator("iframe").first
        body = floc.locator("body")
        html = body.inner_html(timeout=15000)
        ctx.close()
        return html


def main():
    print("[目录] 解析课程目录（基于已保存的真实页面快照）...")
    snap = SNAP / "05_chapter_frame.html"
    if not snap.exists():
        print("[目录] 无快照，先从线上抓取...")
        html = fetch_chapter_html("ai_tools")
        (SNAP / "05_chapter_frame.html").write_text(html, encoding="utf-8")
    else:
        html = snap.read_text(encoding="utf-8")
    items = parse_catalog_html(html, "ai_tools")
    print(f"[目录] 共解析 {len(items)} 个章节节点")
    print(json.dumps(items[:8], ensure_ascii=False, indent=2))
    # 统计
    total_jobs = sum(i["job_count"] for i in items)
    print(f"[目录] 任务点总数: {total_jobs}")
    # 保存结构化结果
    (ROOT / "data" / "catalog_ai_tools.json").write_text(
        json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
