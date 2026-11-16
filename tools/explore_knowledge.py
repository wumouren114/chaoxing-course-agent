"""
深入探索知识卡片 iframe —— 识别视频/测验/资料/课件元素
复用：登录 → 课程 → 点击 2.1 → 进入 iframe#iframe → 分析卡片
"""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
from core.auth import Session

ROOT = Path(__file__).resolve().parent.parent
SNAP = ROOT / "data" / "snapshots"
COURSE_MIDDLE = ("https://mooc1.chaoxing.com/visit/stucoursemiddle"
                 "?courseid=268560848&clazzid=158282453&cpi=575101306&ismooc2=1&v=2")


def main():
    with Session(headless=True) as s:
        page = s.page
        s.ensure_login()
        page.goto(COURSE_MIDDLE, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)
        if page.locator(".coursenoticepop .start-study").count() > 0:
            page.locator(".coursenoticepop .start-study").click()
            page.wait_for_timeout(1500)
        page.wait_for_selector("iframe#frame_content-zj", timeout=20000)
        frame = page.frame(name="frame_content-zj")
        frame.wait_for_selector("div.chapter_item", timeout=20000)
        frame.locator("div.chapter_item#cur1221807919").click()
        page.wait_for_timeout(6000)

        # 进入知识卡片 iframe
        kf = page.frame_locator("iframe#iframe")
        body = kf.locator("body")
        text = body.inner_text(timeout=15000)
        print("[知识卡片] 文本（前 2000 字）:")
        print(text[:2000])

        html = body.inner_html(timeout=15000)
        (SNAP / "07_knowledge_cards.html").write_text(html, encoding="utf-8")
        print(f"\n[快照] 07_knowledge_cards.html ({len(html)} 字符)")

        # 分析卡片结构
        cards = kf.locator(".knowledge-card, [class*=card], .task, li").count()
        print(f"\n[知识卡片] 疑似卡片元素数: {cards}")

        # 拿到实际 frame 对象用于 evaluate
        real_frame = None
        for f in page.frames:
            if "knowledge/cards" in (f.url or ""):
                real_frame = f
                break
        if not real_frame:
            print("[知识卡片] 未找到知识卡片 frame")
            return

        # 抓视频/音频/文档/测验相关元素
        info = real_frame.evaluate("""() => {
            const out = {videos:[], audios:[], docs:[], quizzes:[], tasks:[], allClasses:[]};
            // 视频
            document.querySelectorAll('video, .video, [class*=video], iframe[src*=video], .vjs-big-play-button').forEach(e=>{
                out.videos.push({tag:e.tagName, cls:(e.className||'').toString().slice(0,60), src:(e.getAttribute('src')||'').slice(0,100)});
            });
            // 音频
            document.querySelectorAll('audio, [class*=audio]').forEach(e=>{
                out.audios.push({tag:e.tagName, cls:(e.className||'').toString().slice(0,60)});
            });
            // 文档/PPT/资料
            document.querySelectorAll('[class*=ppt],[class*=doc],[class*=PDF],[class*=pdf],[class*=office]').forEach(e=>{
                out.docs.push({tag:e.tagName, cls:(e.className||'').toString().slice(0,60), text:(e.innerText||'').trim().slice(0,40)});
            });
            // 测验
            document.querySelectorAll('[class*=quiz],[class*=test],[class*=exam],[class*=question]').forEach(e=>{
                out.quizzes.push({tag:e.tagName, cls:(e.className||'').toString().slice(0,60), text:(e.innerText||'').trim().slice(0,40)});
            });
            // 任务点标记
            document.querySelectorAll('[class*=task],[class*=job],[class*=point]').forEach(e=>{
                const t=(e.innerText||'').trim();
                if(t) out.tasks.push({tag:e.tagName, cls:(e.className||'').toString().slice(0,50), text:t.slice(0,50)});
            });
            return out;
        }""")
        print("\n[知识卡片] 元素分析:")
        print(json.dumps(info, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
