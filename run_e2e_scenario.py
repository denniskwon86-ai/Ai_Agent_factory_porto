# -*- coding: utf-8 -*-
"""E2E 시나리오 완주 드라이버 — 테스트 캠페인용.

기획(PLANNING) 가동 → HOTL 게이트 자동 승인(무피드백 resume, 마스터플랜 §2-5 규칙)
→ WBS 확정 → 실행 태스크 순차 가동 → 전 태스크 DONE 까지 무인 완주.

사용:  venv\\Scripts\\python.exe run_e2e_scenario.py [project_id] [아이디어]
기본:  A-1 (test_a1_unitconv, 단위 변환기)
종료코드: 0=완주, 1=실패(원인 stdout), 2=타임아웃/스톨
"""
import sys
import time
import json
import requests

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE = "http://localhost:8080/api/v1/factory"
POLL_SEC = 10
STALL_LIMIT_SEC = 15 * 60      # 활동 없음 15분 → 스톨 판정
PLANNING_TIMEOUT = 60 * 60
TASK_TIMEOUT = 45 * 60

PROJECT_ID = sys.argv[1] if len(sys.argv) > 1 else "test_a1_unitconv"
IDEA = sys.argv[2] if len(sys.argv) > 2 else (
    "길이(cm/inch), 무게(kg/lb), 온도(섭씨/화씨)를 서로 변환해주는 심플한 단위 변환기 웹앱. "
    "로그인 불필요, 단일 화면, 변환 이력 5개까지 화면에 표시."
)


def log(msg: str):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def get(path: str, timeout=45):
    # 서버 재시작 직후 첫 호출은 그래프 컴파일/체크포인터 초기화로 수십 초 걸릴 수 있다
    # → 일시 타임아웃/연결오류로 완주 드라이버가 죽지 않게 재시도 내성
    for attempt in range(3):
        try:
            r = requests.get(f"{BASE}{path}", timeout=timeout)
            return r.json() if r.ok else None
        except requests.exceptions.RequestException as e:
            log(f"   (get {path} 시도 {attempt + 1}/3 실패: {type(e).__name__} — 15초 후 재시도)")
            time.sleep(15)
    return None


def post(path: str, body: dict, timeout=60):
    last = None
    for attempt in range(3):
        try:
            return requests.post(f"{BASE}{path}", json=body, timeout=timeout)
        except requests.exceptions.RequestException as e:
            last = e
            log(f"   (post {path} 시도 {attempt + 1}/3 실패: {type(e).__name__} — 15초 후 재시도)")
            time.sleep(15)
    raise last


def latest_state() -> dict:
    d = get(f"/{PROJECT_ID}/state/latest")
    return (d or {}).get("data") or {}


def feed_tail(n=1):
    d = get(f"/{PROJECT_ID}/feed")
    items = (d or {}).get("data") or []
    return items[-n:]


def wbs():
    d = get(f"/{PROJECT_ID}/wbs")
    return (d or {}).get("data") if (d or {}).get("status") == "success" else None


def check_hotl():
    d = get(f"/{PROJECT_ID}/hotl/check")
    return (d or {}).get("hotl_task_id")


def auto_approve(task_id: str):
    st = latest_state()
    stage = st.get("current_stage", "?")
    feedback = ""

    # 요구확인 인터뷰 게이트: UI 기본값과 동일하게 '추천안'으로 답변(그라운딩 품질 유지)
    if stage == "CLARIFICATION" and (st.get("clarification_questions") or []) and not (st.get("clarification_summary") or "").strip():
        lines = ["[요구 확인 인터뷰 답변]"]
        for i, q in enumerate(st["clarification_questions"]):
            opts = q.get("options") or []
            rec = next((o for o in opts if o.get("recommended")), opts[0] if opts else None)
            if rec:
                lines.append(f"{i + 1}. {q.get('question', '')}")
                lines.append(f"→ 선택: {rec.get('label', '')} ({rec.get('description', '')})")
        feedback = "\n".join(lines)

    # WBS 게이트인데 태스크가 비어 있으면 승인 대신 '재분할' 지시(빈 WBS 로 기획이 끝나는 것 방지)
    if stage == "PMO":
        w = wbs()
        if not (w and (w.get("tasks") or [])):
            feedback = "이전 분할 결과가 비어 있습니다. PRD와 아키텍처를 기준으로 WBS 를 다시 분할하십시오(최소 4개 태스크)."

    mode = "자동 승인(무피드백)" if not feedback else ("추천안 답변" if stage == "CLARIFICATION" else "재분할 지시")
    log(f"⏸️ HOTL 게이트 감지 (task={task_id}, stage={stage}) → {mode} resume")
    r = post(f"/{PROJECT_ID}/hotl/resume", {"task_id": task_id, "feedback": feedback})
    log(f"   resume 응답: {r.status_code} {r.text[:120]}")


def activity_marker() -> str:
    """활동 감지용 지문 — 피드 마지막 항목 ts + 상태의 current_stage/점수."""
    tail = feed_tail(1)
    st = latest_state()
    return json.dumps([tail, st.get("current_stage"), st.get("stage_scores"),
                       st.get("build_status"), st.get("developer_retry_count")], ensure_ascii=False, default=str)


def wait_phase(done_check, phase_name: str, timeout_sec: int) -> str:
    """done_check() -> 'done'|'failed:<msg>'|None. HOTL 자동승인/스톨감지 포함 폴링."""
    started = time.time()
    last_marker = activity_marker()
    last_change = time.time()
    while True:
        time.sleep(POLL_SEC)
        if time.time() - started > timeout_sec:
            return f"failed:{phase_name} 전체 타임아웃({timeout_sec}s)"

        hotl = check_hotl()
        if hotl:
            auto_approve(hotl)
            last_change = time.time()
            continue

        res = done_check()
        if res:
            return res

        m = activity_marker()
        st = latest_state()

        if st.get("factory_mode") == "SUSPENDED_QUOTA":
            time.sleep(POLL_SEC)
            st2 = latest_state()
            if st2.get("factory_mode") == "SUSPENDED_QUOTA":
                return f"failed:{phase_name} 쿼터 완전 소진으로 인해 중단됨 (SUSPENDED_QUOTA)"

        if m != last_marker:
            last_marker = m
            last_change = time.time()
            tail = feed_tail(1)
            if tail:
                e = tail[0]
                log(f"   … {e.get('stage_label', e.get('stage', ''))}/{e.get('phase', '')} : {str(e.get('detail', ''))[:80]}")
        elif time.time() - last_change > STALL_LIMIT_SEC:
            return f"failed:{phase_name} 스톨(활동 없음 {STALL_LIMIT_SEC // 60}분) — 서버 로그 확인 필요"


def main():
    resume = "--resume" in sys.argv
    log(f"=== E2E 완주 {'재개' if resume else '시작'}: {PROJECT_ID} ===")

    if resume:
        # 재개 모드: 진행 중인 기획/실행을 이어받는다(새 PLANNING 가동·아카이빙 없음)
        st = latest_state()
        log(f"재개 지점: task={st.get('current_sprint_task_id')} / stage={st.get('current_stage')}")
    else:
        log(f"아이디어: {IDEA[:80]}")
        # 0) 프로젝트 보장
        r = post("/projects", {"project_id": PROJECT_ID, "template_id": "default"})
        log(f"프로젝트 생성: {r.status_code} ({'기존 재사용' if r.status_code in (400, 409) else '신규'})")

        # 1) 기획(PLANNING) — UI 와 동일 페이로드
        planning_id = f"PLANNING_{int(time.time() * 1000)}"
        r = post(f"/{PROJECT_ID}/sprint/start", {
            "task_id": planning_id,
            "project_state_payload": {
                "schema_version": "5.1.0",
                "project_name": PROJECT_ID,
                "initial_idea": IDEA,
                "master_data": "",
                "factory_mode": "PLANNING",
            },
        })
        log(f"기획 가동({planning_id}): {r.status_code} {r.text[:120]}")
        if not r.ok:
            return 1

    def planning_done():
        w = wbs()
        if w and (w.get("tasks") or []):
            st = latest_state()
            # WBS 게이트까지 승인 완료 후 스트림 종료 시점: hotl 없음 + WBS 존재
            if not check_hotl():
                return "done"
        return None

    res = wait_phase(planning_done, "PLANNING", PLANNING_TIMEOUT)
    if res != "done":
        log(f"❌ 기획 실패: {res}")
        return 1
    w = wbs()
    tasks = w.get("tasks") or []
    log(f"✅ 기획 완주 — WBS {len(tasks)}개 태스크: {[t.get('task_id') for t in tasks]}")

    # 2) 실행 태스크 순차 가동
    #    한 태스크가 실패해도 중단하지 않고 끝까지 시도한 뒤 마지막에 집계한다.
    task_results = []   # [(task_id, "done" | "failed:...")]
    for t in tasks:
        tid = t.get("task_id")
        cur = (wbs() or {}).get("tasks") or []
        status = next((x.get("status") for x in cur if x.get("task_id") == tid), "?")
        if status == "DONE":
            log(f"⏭️ {tid} 이미 DONE — 건너뜀")
            continue

        st = latest_state()
        if resume and st.get("factory_mode") == "SUSPENDED_QUOTA" and str(st.get("current_sprint_task_id")) == str(tid):
            r = post(f"/{PROJECT_ID}/sprint/resume-quota", {"task_id": tid})
            log(f"🚀 쿼터 재개 {tid} ({t.get('title', '')[:40]}): {r.status_code}")
            if r.status_code == 409:
                log(f"⚠️ 이미 실행 중이거나 재개 대상 아님 (무시하고 폴링 진입)")
            elif not r.ok:
                log(f"❌ 가동 실패: {r.text[:200]}")
                return 1
        else:
            st.update({
                "current_sprint_task_id": tid,
                "factory_mode": "REVISION" if str(tid).startswith("TASK_REV_") else "EXECUTION",
            })
            r = post(f"/{PROJECT_ID}/sprint/start", {"task_id": tid, "project_state_payload": st})
            log(f"🚀 태스크 가동 {tid} ({t.get('title', '')[:40]}): {r.status_code}")
            if not r.ok:
                log(f"❌ 가동 실패: {r.text[:200]}")
                task_results.append((tid, f"START_FAILED: {r.text[:120]}"))
                continue

        def task_done(tid=tid):
            cur = (wbs() or {}).get("tasks") or []
            stt = next((x.get("status") for x in cur if x.get("task_id") == tid), None)
            if stt == "DONE":
                return "done"
            if stt == "FAILED":
                s = latest_state()
                return f"failed:태스크 {tid} FAILED — build_error_log: {str(s.get('build_error_log', ''))[:300]}"
            return None

        res = wait_phase(task_done, f"TASK {tid}", TASK_TIMEOUT)
        if res != "done":
            # ★ [2026-07-27] 한 태스크가 실패해도 **완주를 포기하지 않는다**.
            #   ⚠️ 실측(test_a1_v9): E2E-04 가 FAILED 되자 드라이버가 즉시 종료해
            #     E2E-05 는 시도조차 못 했고 E2E-03 은 IN_PROGRESS 로 방치됐다.
            #     완주 테스트의 목적은 '5개 중 몇 개가 되는가'를 아는 것인데,
            #     첫 실패에서 멈추면 전체 그림을 영영 볼 수 없다.
            #   파이프라인은 정상이었다(FAILED_REVIEW 로 정직하게 종결 + 롤백 + 실패 번들).
            #   포기한 것은 **테스트 하네스**였다.
            log(f"❌ {res}")
            log(f"➡️ {tid} 실패 — 나머지 태스크를 계속 진행합니다(최종 집계는 마지막에).")
            task_results.append((tid, res))
            continue
        log(f"✅ {tid} DONE")
        task_results.append((tid, "done"))

    # ── 최종 집계 ────────────────────────────────────────────────────────────
    _ok = [t for t, r in task_results if r == "done"]
    _ng = [(t, r) for t, r in task_results if r != "done"]
    log("=== 📊 태스크 집계 ===")
    for _t, _r in task_results:
        log(f"   {'✅' if _r == 'done' else '❌'} {_t}: {_r if _r != 'done' else 'DONE'}")
    log(f"   → 성공 {len(_ok)} / 전체 {len(task_results)}")
    if _ng:
        log(f"=== ⛔ 미완주: 실패 태스크 {len(_ng)}건 — 게시(Release)를 진행하지 않습니다 ===")
        log("   (A-1 완주 판정은 '전 태스크 DONE + QA + 수용검수 + 게시'를 모두 충족해야 합니다)")
        return 1

    log("=== 🏁 전 태스크 완주 성공 ===")
    st = latest_state()
    log(f"최종 요약: stage_scores={json.dumps(st.get('stage_scores'), ensure_ascii=False)}")
    log(f"qa_verdict={st.get('qa_verdict')} / supervisor_verdict={st.get('supervisor_verdict')}")

    # 3) 최종 결과물 라이브러리 자동 게시 (Release)
    log("📦 최종 결과물 라이브러리 게시(Release) 진행 중...")
    try:
        r = post(f"/{PROJECT_ID}/release", {})
        if r.ok:
            rel_data = r.json()
            rel_id = rel_data.get("release_id", "unknown") if isinstance(rel_data, dict) else "ok"
            log(f"✅ 결과물 라이브러리 게시 완료! (release_id: {rel_id})")
            log("👉 사용자 UI (http://localhost:5173) [결과물 라이브러리] 탭에서 확인 가능합니다.")
        else:
            log(f"⚠️ 결과물 라이브러리 게시 실패: {r.status_code} {r.text[:200]}")
    except Exception as e:
        log(f"⚠️ 결과물 라이브러리 게시 중 예외 발생: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
