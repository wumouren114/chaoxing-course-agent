"""
验证平台是否真的判定任务完成 —— 完成判定的关键一步
回到课程目录 + 知识卡片，检查 2.1 节点的完成标识
"""
import json
from playwright.sync_api import sync_playwright
from core.auth import Session

ROOT = __import__("pathlib").Path(__file__).resolve().parent.parent
MIDDLE = "https://mooc1.chaoxing.com/visit/stucoursemiddle?courseid=268560848&clazzid=158282453&cpi=575101306&ismooc2=1&v=2"
NODE = "1221807919"


def main():
    with Session(headless=True) as s:
        page = s.page
        s.ensure_login()
        page.goto(MIDDLE, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)
        if page.locator(".coursenoticepop .start-study").count() > 0:
            page.locator(".coursenoticepop .start-study").click()
            page.wait_for_timeout(1500)
        page.wait_for_selector("iframe#frame_content-zj", timeout=20000)
        fr = page.frame(name="frame_content-zj")
        fr.wait_for_selector("div.chapter_item", timeout=20000)

        node = fr.locator(f"div.chapter_item#cur{NODE}")
        print("[验证] 目录节点 class:", node.get_attribute("class"))
        # 任务点数量与进度文本
        print("[验证] 节点文本:", node.inner_text(timeout=5000).replace("\n", " ")[:200])
        jindu = node.locator(".catalog_jindu")
        if jindu.count() > 0:
            print("[验证] 进度元素 class:", jindu.first.get_attribute("class"))
            print("[验证] 进度文本:", jindu.first.inner_text(timeout=5000))
            tip = node.locator(".bntHoverTips")
            if tip.count() > 0:
                print("[验证] 提示:", tip.first.inner_text(timeout=5000))

        # 顶部总进度
        body = fr.locator("body").inner_text(timeout=5000)
        print("[验证] 顶部进度行:", body.split("\n")[0:3])

        # 打开章节看知识卡片的 aria-label
        node.click()
        page.wait_for_timeout(6000)
        kcards = None
        for f in page.frames:
            if "knowledge/cards" in (f.url or ""):
                kcards = f; break
        if kcards:
            states = kcards.evaluate("""() => Array.from(document.querySelectorAll('.ans-job-video,[class*=ans-job-icon]'))
                .map(e=>({cls:(e.className||'').toString().slice(0,50), label:e.getAttribute('aria-label')||''}))""")
            print("[验证] 知识卡片任务点状态:", json.dumps(states, ensure_ascii=False))


if __name__ == "__main__":
    main()
