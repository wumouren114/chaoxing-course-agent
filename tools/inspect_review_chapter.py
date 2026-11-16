"""
只读探查 NEEDS_REVIEW 章节的真实内容类型（不播放、不提交、不改进度）。

隔离策略：
- 用非持久化 browser + new_context(storage_state=...) 注入 cookie 快照，
  绝不打开主 profile（data/browser_profile），避免干扰正在播放的会话。
- 只做导航与 DOM 读取，结束后立即关闭。

用法：
  .venv/Scripts/python -u tools/inspect_review_chapter.py [node_id]
默认 node_id = 1221808002（4.2 如何用AI快速生成PPT）
"""
import json
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "data" / "storage_state.json"
SNAP = ROOT / "data" / "snapshots"
COURSE_MIDDLE = ("https://mooc1.chaoxing.com/visit/stucoursemiddle"
                 "?courseid=268560848&clazzid=158282453&cpi=575101306&ismooc2=1&v=2")
NODE = sys.argv[1] if len(sys.argv) > 1 else "1221808002"


def dump_frames(page, tag):
    frames = page.evaluate("""() => Array.from(document.querySelectorAll('iframe')).map(f => ({
        src:(f.getAttribute('src')||'').slice(0,260), id:f.id||'', name:f.name||'',
        cls:(f.className||'').slice(0,120)
    }))""")
    print(f"\n[{tag}] iframe 数: {len(frames)}")
    print(json.dumps(frames, ensure_ascii=False, indent=2))
    return frames


def main():
    SNAP.mkdir(parents=True, exist_ok=True)
    if not STATE.exists():
        print("[探查] 缺少 storage_state.json，无法注入登录态"); return
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        ctx = browser.new_context(storage_state=str(STATE),
                                  viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        new_pages = []
        ctx.on("page", lambda pg: new_pages.append(pg))

        page.goto(COURSE_MIDDLE, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(4000)
        print(f"[探查] 中间页 URL: {page.url}")
        if "passport" in page.url or "login" in page.url:
            print("[探查] ❌ 登录态失效，被踢回登录页。需先刷新 storage_state。")
            browser.close(); return

        if page.locator(".coursenoticepop .start-study").count() > 0:
            page.locator(".coursenoticepop .start-study").click()
            page.wait_for_timeout(1500)

        page.wait_for_selector("iframe#frame_content-zj", timeout=20000)
        fr = page.frame(name="frame_content-zj")
        fr.wait_for_selector("div.chapter_item", timeout=20000)

        node = fr.locator(f"div.chapter_item#cur{NODE}")
        print(f"[探查] 目标节点 {NODE} count={node.count()}")
        if node.count() == 0:
            print("[探查] ❌ 目录中找不到该节点"); browser.close(); return
        title = node.get_attribute("title") or ""
        print(f"[探查] 标题: {title}")
        node.scroll_into_view_if_needed()
        node.click()
        page.wait_for_timeout(6000)
        print(f"[探查] 点击后主 URL: {page.url}")

        dump_frames(page, "主页面")

        # 定位内容承载页：优先新开窗口，否则当前页
        target = new_pages[0] if new_pages else page
        target.wait_for_timeout(4000)
        print(f"\n[探查] 内容页: {target.url} | {target.title()}")
        text = ""
        try:
            text = target.locator("body").inner_text(timeout=10000)
            print("\n[探查] 内容页文本（前 2500 字）:")
            print(text[:2500])
        except Exception as e:
            print("[探查] 读取 body 文本失败:", e)

        html = target.content()
        (SNAP / f"review_{NODE}.html").write_text(html, encoding="utf-8")
        print(f"\n[快照] review_{NODE}.html ({len(html)} 字符)")
        dump_frames(target, "内容页")

        # 遍历所有子 frame，找视频/测验/文档的蛛丝马迹
        print("\n[探查] === 逐 frame 摘要 ===")
        for i, f in enumerate(target.frames):
            url = f.url or ""
            if url == "about:blank":
                continue
            try:
                body = f.evaluate("() => (document.body ? document.body.innerText : '')", timeout=8000)
            except Exception:
                body = ""
            src = url[:150]
            has_video = any(k in (url + body).lower() for k in
                            ("ananas/modules/video", "video_html5_api", ".mp4", "vjs-tech"))
            has_quiz = any(k in body for k in ("单选题", "多选题", "判断题", "提交", "选项", "题目"))
            print(f"  [{i}] {src}  len(body)={len(body)}  video={has_video} quiz={has_quiz}")
            if body:
                print("      text:", body[:180].replace("\n", " "))

        # 导出 knowledge cards 子 frame 的 HTML（视频/测验/任务点状态都在这里）
        for f in target.frames:
            if "knowledge/cards" in (f.url or ""):
                try:
                    kh = f.evaluate("() => document.body ? document.body.innerHTML : ''")
                    (SNAP / f"review_{NODE}_cards.html").write_text(kh, encoding="utf-8")
                    print(f"\n[快照] review_{NODE}_cards.html ({len(kh)} 字符)")
                    from core.content import parse_knowledge_html
                    parsed = parse_knowledge_html(kh)
                    print("[探查] 知识卡片内容识别:")
                    print(json.dumps(parsed, ensure_ascii=False, indent=2)[:3000])
                except Exception as e:
                    print("[探查] 读取 knowledge cards 失败:", e)

        browser.close()
        print("\n[探查] 完成（只读，未播放/未提交）")


if __name__ == "__main__":
    main()
