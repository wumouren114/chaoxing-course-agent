"""
探索视频播放器内部结构 —— 进入嵌套 iframe，找 video 元素/播放状态/进度
这是"播放状态监测"的关键
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

        print("[播放器] 所有 frame:")
        for f in page.frames:
            print(f"  - {f.name!r:20} {f.url[:110]}")

        # 找到 video/index.html 播放器 frame
        player = None
        for f in page.frames:
            if "video/index.html" in (f.url or "") or "ananas/modules/video" in (f.url or ""):
                player = f
                break
        if not player:
            print("[播放器] ❌ 未找到播放器 frame")
            return
        print(f"\n[播放器] 找到: {player.url}")
        player.wait_for_load_state("domcontentloaded", timeout=20000)
        page.wait_for_timeout(3000)

        html = player.content()
        (SNAP / "08_player.html").write_text(html, encoding="utf-8")
        print(f"[快照] 08_player.html ({len(html)} 字符)")

        # 分析 video 元素和播放控件
        info = player.evaluate("""() => {
            const out = {videos:[], controls:[], state:{}};
            document.querySelectorAll('video').forEach(v=>{
                out.videos.push({
                    id:v.id, cls:(v.className||'').toString().slice(0,80),
                    currentTime:v.currentTime, duration:v.duration,
                    paused:v.paused, ended:v.ended, muted:v.muted,
                    src:(v.src||'').slice(0,120),
                    readyState:v.readyState
                });
            });
            // 常见播放器控件 class
            const kw = /play|pause|time|progress|duration|current|volume|speed|fullscreen|vjs|control/i;
            document.querySelectorAll('div,span,button,a').forEach(e=>{
                const c=(e.className||'').toString();
                if(c && kw.test(c) && e.children.length<4){
                    const t=(e.innerText||'').trim().slice(0,20);
                    out.controls.push({tag:e.tagName, cls:c.slice(0,60), text:t});
                }
            });
            out.controls = out.controls.slice(0,50);
            return out;
        }""")
        print("\n[播放器] 元素分析:")
        print(json.dumps(info, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
