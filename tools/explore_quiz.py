"""
探索真实测验题 DOM 结构（独立只读会话）
- 用 storage_state.json 创建独立 context，不碰正在播放的 persistent profile
- 只抓 DOM，不播放视频、不改任何状态
"""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "data" / "storage_state.json"
SNAP = ROOT / "data" / "snapshots"
COURSE_MIDDLE = "https://mooc1.chaoxing.com/visit/stucoursemiddle?courseid=268560848&clazzid=158282453&cpi=575101306&ismooc2=1&v=2"
NODE_ID = "1221807919"  # 2.1 认识AI写作


def main():
    SNAP.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        # 纯内存只读会话：不落盘 profile，仅注入登录态，抓完即关
        browser = p.chromium.launch(channel="msedge", headless=True)
        ctx = browser.new_context(storage_state=str(STATE),
                                  viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.goto(COURSE_MIDDLE, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)
        print("[探测] URL:", page.url)

        # 关闭课程须知弹窗
        if page.locator(".coursenoticepop .start-study").count() > 0:
            page.locator(".coursenoticepop .start-study").click()
            page.wait_for_timeout(2000)
            print("[探测] 已关闭须知弹窗")

        # 章节目录 iframe
        fr = page.frame(name="frame_content-zj")
        if not fr:
            print("[探测] 未找到目录 iframe")
            ctx.close(); browser.close(); return
        fr.wait_for_selector("div.chapter_item", timeout=20000)
        node = fr.locator(f"div.chapter_item#cur{NODE_ID}")
        print("[探测] 目标节点数:", node.count())
        node.click()
        page.wait_for_timeout(6000)

        # 知识卡片 iframe
        kf = page.frame(name="iframe") or page.frame(url=lambda u: u and "knowledge/cards" in u)
        if not kf:
            # 遍历找
            for f in page.frames:
                if "knowledge/cards" in (f.url or ""):
                    kf = f; break
        if not kf:
            print("[探测] 未找到知识卡片 iframe，保存主页面供分析")
            (SNAP / "09_quiz_main.html").write_text(page.content(), encoding="utf-8")
            ctx.close(); browser.close(); return

        html = kf.evaluate("() => document.body.innerHTML")
        (SNAP / "09_knowledge_cards_full.html").write_text(html, encoding="utf-8")
        print("[探测] 知识卡片 HTML 已保存，长度:", len(html))

        # 列出所有可能的任务/测验元素
        info = kf.evaluate("""() => {
            const sels = ['.ans-job-video','.ans-job-audio','.ans-job-doc',
              '[class*=job]','[class*=task]','[class*=quiz]','[class*=exam]',
              '[class*=question]','[class*=homework]','[class*=zuoye]',
              'iframe','a[onclick]','.trans-question-box'];
            const out = {};
            for (const s of sels) {
              const els = document.querySelectorAll(s);
              if (els.length) out[s] = Array.from(els).slice(0,10).map(e => ({
                tag: e.tagName,
                cls: (e.className||'').toString().slice(0,80),
                id: e.id,
                text: (e.innerText||'').trim().slice(0,60),
                title: e.getAttribute('title')||'',
                src: (e.getAttribute('src')||'').slice(0,120),
                data: (e.getAttribute('data')||'').slice(0,200),
                onclick: (e.getAttribute('onclick')||'').slice(0,100),
                aria: e.getAttribute('aria-label')||''
              }));
            }
            return out;
        }""")
        (SNAP / "09_quiz_elements.json").write_text(
            json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
        print("[探测] 元素清单:")
        print(json.dumps(info, ensure_ascii=False, indent=2)[:4000])
        ctx.close()
        browser.close()


if __name__ == "__main__":
    main()
