"""
视频监测模块 —— 正常播放 + 状态监测
原则：只做正常网页操作（点击播放、等待自然播放完成），不拖拽进度、不伪造记录、不绕过检测。
平台规则：观看时长需≥总时长90%，未完成前不可拖拽/离开/最小化。
"""
import time
from typing import Optional, Dict


def find_player_frame(page):
    """在页面的所有 frame 中定位视频播放器 frame"""
    for f in page.frames:
        url = f.url or ""
        if "ananas/modules/video/index.html" in url or "ananas/modules/video" in url:
            return f
    return None


def read_state(player_frame) -> Dict:
    """读取视频当前播放状态"""
    return player_frame.evaluate("""() => {
        const v = document.querySelector('video.vjs-tech, video');
        if (!v) return {found: false};
        const R = (x, n=2) => Math.round(x * Math.pow(10,n)) / Math.pow(10,n);
        const dur = (v.duration && isFinite(v.duration)) ? v.duration : 0;
        const cur = v.currentTime || 0;
        const curDisp = document.querySelector('.vjs-current-time-display');
        const durDisp = document.querySelector('.vjs-duration-display');
        return {
            found: true,
            current_time: R(cur, 2),
            duration: R(dur, 2),
            paused: v.paused,
            ended: v.ended,
            muted: v.muted,
            volume: v.volume,
            ready_state: v.readyState,
            progress_pct: dur > 0 ? R(cur / dur * 100, 1) : 0,
            time_display: curDisp ? curDisp.innerText.trim() : '',
            duration_display: durDisp ? durDisp.innerText.trim() : '',
            src: (v.src || '').slice(0, 150),
        };
    }""")


def click_play(player_frame) -> bool:
    """正常点击播放按钮（等价用户点击大播放按钮）"""
    try:
        # 优先点大播放按钮
        big = player_frame.locator("button.vjs-big-play-button")
        if big.count() > 0 and big.first.is_visible():
            big.first.click()
            return True
        # 否则点控制栏播放按钮
        ctrl = player_frame.locator("button.vjs-play-control")
        if ctrl.count() > 0:
            ctrl.first.click()
            return True
        # 最后兜底：直接调用 video.play()（仍是正常播放，不伪造进度）
        player_frame.evaluate("() => { const v=document.querySelector('video'); if(v) v.play(); }")
        return True
    except Exception as e:
        print(f"[视频] 点击播放失败: {e}")
        return False


def wait_for_metadata(player_frame, timeout=20) -> bool:
    """等待视频元数据加载完成（拿到 duration）"""
    start = time.time()
    while time.time() - start < timeout:
        st = read_state(player_frame)
        if st.get("duration", 0) > 0:
            return True
        time.sleep(1)
    return False


def monitor_playback(page, player_frame, max_seconds=None,
                     progress_threshold=90, poll=3, on_tick=None,
                     on_pause=None) -> Dict:
    """
    监测视频自然播放，直到进度达标或超时。
    不做任何拖拽/跳帧；只读取状态并等待。
    on_pause(page, player_frame) -> 可选回调：检测到暂停时调用，用于处理弹题；
      返回 True 表示已处理（随后恢复播放），False/None 表示无弹题。
    返回监测结果字典。
    """
    # 平台视频的时长需点击播放后才加载，所以先正常点击播放，再等元数据
    st0 = read_state(player_frame)
    if st0.get("paused", True):
        print("[视频] 点击播放...")
        click_play(player_frame)
        time.sleep(3)

    if not wait_for_metadata(player_frame):
        return {"ok": False, "reason": "视频元数据加载失败（拿不到时长）"}

    st = read_state(player_frame)
    duration = st["duration"]
    print(f"[视频] 总时长: {duration}s ({st.get('duration_display','')})")

    # 若播放后意外暂停，再点一次
    if st.get("paused", True) and not st.get("ended"):
        click_play(player_frame)
        time.sleep(2)

    if max_seconds is None:
        max_seconds = duration * 1.5 + 60  # 给足自然播放时间

    start = time.time()
    last_pct = -1
    stalled_count = 0
    while time.time() - start < max_seconds:
        st = read_state(player_frame)
        pct = st.get("progress_pct", 0)
        if on_tick:
            on_tick(st)
        if pct != last_pct:
            print(f"[视频] 进度: {pct}% ({st.get('time_display','')}/{st.get('duration_display','')}) "
                  f"paused={st.get('paused')}")
            last_pct = pct
        if st.get("ended") or pct >= progress_threshold:
            return {
                "ok": True, "reason": "播放进度达标",
                "final": st, "duration": duration,
            }
        # 检测卡住（进度长时间不动且处于暂停）
        if st.get("paused") and pct > 0:
            stalled_count += 1
            # 首次检测到暂停就检查弹题（弹题会导致视频暂停等待作答）
            if stalled_count == 1 and on_pause:
                try:
                    handled = on_pause(page, player_frame)
                    if handled:
                        print("[视频] 已处理暂停原因（弹题），恢复播放")
                        time.sleep(1)
                        click_play(player_frame)
                        stalled_count = 0
                except Exception as e:
                    print(f"[视频] on_pause 回调异常: {e}")
            if stalled_count >= 5:
                # 尝试再次点击播放（可能是网络抖动导致的暂停）
                print("[视频] 检测到暂停，尝试恢复播放")
                click_play(player_frame)
                stalled_count = 0
        else:
            stalled_count = 0
        time.sleep(poll)

    return {"ok": False, "reason": "播放监测超时", "final": read_state(player_frame),
            "duration": duration}


if __name__ == "__main__":
    # 单独测试：只读取状态，不实际长时间播放
    from core.auth import Session
    COURSE_MIDDLE = ("https://mooc1.chaoxing.com/visit/stucoursemiddle"
                     "?courseid=268560848&clazzid=158282453&cpi=575101306&ismooc2=1&v=2")
    with Session(headless=True) as s:
        s.ensure_login()
        s.page.goto(COURSE_MIDDLE, wait_until="domcontentloaded", timeout=60000)
        s.page.wait_for_timeout(5000)
        if s.page.locator(".coursenoticepop .start-study").count() > 0:
            s.page.locator(".coursenoticepop .start-study").click()
            s.page.wait_for_timeout(1500)
        s.page.wait_for_selector("iframe#frame_content-zj", timeout=20000)
        fr = s.page.frame(name="frame_content-zj")
        fr.wait_for_selector("div.chapter_item", timeout=20000)
        fr.locator("div.chapter_item#cur1221807919").click()
        s.page.wait_for_timeout(6000)
        player = find_player_frame(s.page)
        print("播放器 frame:", player.url if player else None)
        if player:
            player.wait_for_load_state("domcontentloaded", timeout=20000)
            print("等待元数据...")
            ok = wait_for_metadata(player, timeout=30)
            print("元数据加载:", ok)
            print("当前状态:", read_state(player))
