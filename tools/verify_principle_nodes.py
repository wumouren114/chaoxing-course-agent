"""只读核验：ai_principle 指定章节的服务端权威完成状态。

对每个 node：
  1. 进入章节页，抓 knowledge/cards 与 studentstudyAjax 响应
  2. 解析 mArg.attachments[].isPassed / knowledgeJobCount / jobid 明细
  3. 输出服务端真实完成状态（不依赖目录缓存标记）
用法: python tools/verify_principle_nodes.py [node_id ...]
"""
import re
import json
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

URL = ("https://mooc1.chaoxing.com/visit/stucoursemiddle"
       "?courseid=268560836&clazzid=158282442&cpi=575101306&ismooc2=1&v=2")
STATE = str(Path("data/storage_state_principle.json").resolve())

DEFAULT_NODES = ["1113731109", "1113731112", "1113731114"]
nodes = sys.argv[1:] if len(sys.argv) > 1 else DEFAULT_NODES


def analyze(node, captured, pg):
    print(f"\n{'='*70}\n节点 {node}")
    found_passed = []
    for c in captured:
        body = c["body"]
        url = c["url"]
        # mArg.isPassed（knowledge/cards 页服务端权威标记）
        for m in re.finditer(r'"isPassed"\s*:\s*(true|false)', body):
            found_passed.append(m.group(1))
        # attachments 中所有 isPassed + 类型
        for m in re.finditer(
            r'"(?:isPassed|jobId|jobid|type|name)"\s*:\s*("(?:[^"\\]|\\.)*"|true|false|\d+)',
            body,
        ):
            pass  # 明细太多，按需展开
    # 统计
    t = found_passed.count("true")
    f = found_passed.count("false")
    print(f"  捕获 isPassed: true×{t} / false×{f}")
    # 目录节点文本（平台显示的完成任务点）；进入章节后 iframe 可能重建，重新获取
    try:
        fr2 = pg.frame(name="frame_content-zj") or pg.frames[0]
        nd = fr2.locator(f"div.chapter_item#cur{node}")
        if nd.count():
            print("  目录文本:", nd.inner_text(timeout=3000).replace("\n", " ")[:90])
            tips = nd.locator(".bntHoverTips")
            for i in range(tips.count()):
                print("  bntHoverTips:", (tips.nth(i).text_content() or "").strip())
    except Exception as e:
        print("  目录读取失败(不影响权威判定):", str(e)[:60])
    verdict = "✅ 服务端已完成(isPassed=true)" if t and not f else (
        "⚠️ 混合/需人工" if t and f else "❌ 未见 isPassed=true"
    )
    print(f"  判定: {verdict}")


with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge", headless=True)
    ctx = b.new_context(storage_state=STATE)
    captured = []

    def on_resp(resp):
        u = resp.url
        if any(k in u for k in ("studentstudyAjax", "initdatawithviewer", "knowledge/cards")):
            try:
                captured.append({"url": u[:200], "body": resp.text()})
            except Exception:
                pass

    ctx.on("response", on_resp)
    pg = ctx.new_page()
    pg.goto(URL, wait_until="domcontentloaded", timeout=60000)
    pg.wait_for_timeout(7000)
    if pg.locator(".coursenoticepop .start-study").count() > 0:
        pg.locator(".coursenoticepop .start-study").click()
        pg.wait_for_timeout(1500)
    fr = pg.frame(name="frame_content-zj")
    fr.wait_for_selector("div.chapter_item", timeout=20000)

    for node in nodes:
        captured.clear()
        # 每个节点重新加载课程主页，确保目录 iframe 干净可用
        try:
            pg.goto(URL, wait_until="domcontentloaded", timeout=60000)
            pg.wait_for_timeout(5000)
            if pg.locator(".coursenoticepop .start-study").count() > 0:
                pg.locator(".coursenoticepop .start-study").click()
                pg.wait_for_timeout(1200)
            fr = pg.frame(name="frame_content-zj")
            fr.wait_for_selector("div.chapter_item", timeout=20000)
            nd = fr.locator(f"div.chapter_item#cur{node}")
            if nd.count() == 0:
                print(f"\n节点 {node}: 目录中不存在")
                continue
            nd.locator(".clicktitle").click()
            pg.wait_for_timeout(7000)
        except Exception as e:
            print(f"\n节点 {node}: 点击失败 {str(e)[:80]}")
            continue
        analyze(node, captured, pg)

    b.close()
