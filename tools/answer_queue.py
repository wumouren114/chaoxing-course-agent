"""
助手作答工具：把答案写回协作队列。
用法: python tools/answer_queue.py list
      python tools/answer_queue.py answer <qid> <答案> ["解析"]
示例: python tools/answer_queue.py answer ai_tools_1221808027_xxx B "Discord是Midjourney平台"
      python tools/answer_queue.py answer ai_tools_1221808027_yyy 对
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import question_queue as qq

def main():
    if len(sys.argv) < 2:
        print(__doc__); return
    cmd = sys.argv[1]
    if cmd == "list":
        items = qq.all_items()
        pending = [q for q in items if q["status"] == "PENDING"]
        print(f"=== 待答 {len(pending)} 题 ===")
        for q in pending:
            print(f"\nqid: {q['id']}")
            print(f"  题型: {q['qtype']}  题干: {q['stem'][:80]}")
            print(f"  选项: {' | '.join(q['options'])}")
    elif cmd == "answer":
        if len(sys.argv) < 4:
            print(__doc__); return
        qid, ans = sys.argv[2], sys.argv[3]
        analysis = sys.argv[4] if len(sys.argv) > 4 else ""
        ok = qq.answer(qid, ans, analysis)
        print("已写入答案" if ok else "未找到该qid")
    elif cmd == "clear":
        items = qq.all_items()
        qq._save([])
        print(f"已清空 {len(items)} 条记录")

if __name__ == "__main__":
    main()
