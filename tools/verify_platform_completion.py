"""
权威核验：直接读取学习通平台侧的真实任务点完成状态（只读，不播放不提交）。

稳健策略：充分等待 + 滚动加载全部章节 + 直接取原生文本，避免脆弱选择器。
- 顶部进度："已完成任务点 x/y"（平台最权威）
- 每章完成标记：.bntHoverTips 的 textContent == "已完成"

隔离：独立 browser + new_context(storage_state) 注入 cookie，不碰正在播放的 profile。
"""
import re
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "data" / "storage_state.json"

COURSES = [
    {"key": "ai_tools", "name": "人人都能上手的AI工具",
     "url": "https://mooc1.chaoxing.com/visit/stucoursemiddle?courseid=268560848&clazzid=158282453&cpi=575101306&ismooc2=1&v=2"},
    {"key": "ai_principle", "name": "生成式人工智能原理及其影响和应用",
     "url": "https://mooc1.chaoxing.com/visit/stucoursemiddle?courseid=268560836&clazzid=158282442&cpi=575101306&ismooc2=1&v=2"},
]


def verify_one(ctx, course):
    page = ctx.new_page()
    try:
        page.goto(course["url"], wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(8000)
        if "passport" in page.url or "login" in page.url:
            return {"error": "登录态失效，被踢回登录页: " + page.url}

        if page.locator(".coursenoticepop .start-study").count() > 0:
            page.locator(".coursenoticepop .start-study").click()
            page.wait_for_timeout(2000)

        page.wait_for_selector("iframe#frame_content-zj", timeout=25000)
        fr = page.frame(name="frame_content-zj")
        fr.wait_for_selector("div.chapter_item", timeout=25000)
        page.wait_for_timeout(3000)

        # 滚动目录，触发懒加载
        fr.evaluate("""() => { window.scrollTo(0, document.body.scrollHeight); }""")
        page.wait_for_timeout(2000)
        fr.evaluate("""() => { window.scrollTo(0, 0); }""")
        page.wait_for_timeout(1500)

        # 主页面 + iframe 全文里搜 "已完成任务点"
        full_text = ""
        try:
            full_text = fr.locator("body").inner_text(timeout=8000)
        except Exception:
            pass
        top_hits = re.findall(r"已完成任务点[：:\s]*(\d+)\s*/\s*(\d+)", full_text)
        # 也检查主页面
        try:
            ptxt = page.locator("body").inner_text(timeout=5000)
            top_hits += re.findall(r"已完成任务点[：:\s]*(\d+)\s*/\s*(\d+)", ptxt)
        except Exception:
            pass

        # 逐章：用 text_content 读 .bntHoverTips
        chapters = fr.evaluate("""() => Array.from(document.querySelectorAll('div.chapter_item'))
            .filter(n=>n.id.startsWith('cur')).map(n => {
                const tips = n.querySelectorAll('.bntHoverTips');
                let tip = '';
                tips.forEach(t => { const x=(t.textContent||'').trim(); if(x) tip=x; });
                const jobInput = n.querySelector('.knowledgeJobCount');
                const sbar = n.querySelector('.catalog_sbar');
                return {
                    id:n.id,
                    num: sbar ? sbar.textContent.trim() : '',
                    title: n.getAttribute('title')||'',
                    jobs: jobInput ? jobInput.value : '0',
                    tip: tip,
                    done: tip === '已完成'
                };
            })""")

        with_jobs = [c for c in chapters if c["jobs"] not in ("0", "", None)]
        done = [c for c in with_jobs if c["done"]]
        undone = [c for c in with_jobs if not c["done"]]
        # 无任务点章节单独统计
        no_job = [c for c in chapters if c["jobs"] in ("0", "", None)]

        return {
            "course": course["name"],
            "top": top_hits[:3],
            "chapters_total": len(chapters),
            "with_jobs": len(with_jobs),
            "no_job": len(no_job),
            "done": len(done),
            "undone": len(undone),
            "undone_list": [
                {"num": c["num"], "title": c["title"], "tip": c["tip"], "jobs": c["jobs"]}
                for c in undone
            ],
            "sample_text": full_text[:300].replace("\n", " | "),
        }
    finally:
        page.close()


def main():
    if not STATE.exists():
        print("[核验] 缺少 storage_state.json"); return
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        ctx = browser.new_context(storage_state=str(STATE),
                                  viewport={"width": 1440, "height": 900})
        result = {}
        for c in COURSES:
            try:
                result[c["key"]] = verify_one(ctx, c)
            except Exception as e:
                result[c["key"]] = {"error": str(e)}
        browser.close()

        print("=" * 66)
        print("学习通平台侧 · 真实完成状态核验（只读，与网页版一致）")
        print("=" * 66)
        for c in COURSES:
            r = result.get(c["key"], {})
            print(f"\n【{c['name']}】")
            if "error" in r:
                print("  ❌", r["error"]); continue
            print("  平台顶部已完成任务点:", r["top"] or "(未抓到)")
            print(f"  章节: 共 {r['chapters_total']} | 有任务点 {r['with_jobs']} | 无任务点 {r['no_job']}")
            print(f"  其中平台标记'已完成': {r['done']} 章 | 未完成: {r['undone']} 章")
            if r["undone_list"]:
                print("  未完成章节:")
                for x in r["undone_list"]:
                    print(f"    - {x['num']:>5} {x['title'][:26]:<28} 标记='{x['tip']}' 任务点={x['jobs']}")
            print("  原始文本片段:", r["sample_text"][:160])
        print("\n" + "=" * 66)


if __name__ == "__main__":
    main()
