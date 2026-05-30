import streamlit as st
import json
import os
import pandas as pd
import time
from filelock import FileLock, Timeout

# ---------------------------------------------------------
# 1. 페이지 기본 설정
# ---------------------------------------------------------
st.set_page_config(
    page_title="Factory PMO Dashboard", 
    page_icon="🏭", 
    layout="wide"
)

WBS_FILE = "00_wbs_master_plan.json"
LOCK_FILE = f"{WBS_FILE}.lock"

# ---------------------------------------------------------
# 2. 데이터 로드 로직 (FileLock 기반 동시성 방어)
# ---------------------------------------------------------
def load_wbs_data():
    if not os.path.exists(WBS_FILE):
        return None
    
    # 팩토리(code_builder)가 엑셀/JSON을 갱신 중일 때 읽기 시도 방지
    lock = FileLock(LOCK_FILE, timeout=2)
    try:
        with lock:
            with open(WBS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Timeout:
        st.warning("⏳ 현재 파이프라인이 WBS 파일을 갱신 중입니다. 잠시 후 다시 시도합니다...")
        return None
    except Exception as e:
        st.error(f"❌ 데이터 로딩 중 오류 발생: {e}")
        return None

# ---------------------------------------------------------
# 3. UI 화면 렌더링
# ---------------------------------------------------------
st.title("🏭 범용 자율형 소프트웨어 팩토리 - PMO 대시보드")
st.markdown("다중 에이전트 파이프라인의 **스프린트 진척도 및 자원 현황**을 실시간으로 모니터링합니다.")

# 상단 컨트롤 패널 (자동 새로고침)
col1, col2 = st.columns([8, 2])
with col1:
    auto_refresh = st.checkbox("🔄 3초 자동 새로고침 켜기", value=True)
with col2:
    if st.button("즉시 새로고침"):
        st.rerun()

data = load_wbs_data()

if data:
    project_name = data.get("project_name", "이름 없는 프로젝트")
    created_at = data.get("created_at", "-")
    tasks = data.get("tasks", [])
    
    st.subheader(f"📋 마스터플랜: {project_name} (수립일: {created_at})")
    
    # 진척률 계산
    total_tasks = len(tasks)
    completed_tasks = sum(1 for t in tasks if t.get("status") == "DONE")
    progress_rate = int((completed_tasks / total_tasks) * 100) if total_tasks > 0 else 0
    
    # 상단 요약 메트릭
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("전체 WBS 태스크", f"{total_tasks} 개")
    m2.metric("완료된 태스크", f"{completed_tasks} 개")
    m3.metric("현재 진척률", f"{progress_rate} %")
    m4.metric("팩토리 가동 상태", "완공 (Completed) 🏁" if progress_rate == 100 else "가동 중 (Running) 🟢")
    
    # 대형 프로그레스 바 렌더링
    st.progress(progress_rate / 100.0)
    st.markdown("---")
    
    # ---------------------------------------------------------
    # 4. WBS 상세 테이블 뷰
    # ---------------------------------------------------------
    st.subheader("📊 세부 WBS (Work Breakdown Structure) 현황")
    if tasks:
        df = pd.DataFrame(tasks)
        # 화면 표시용 컬럼 정리
        display_df = df[['task_id', 'sprint_day', 'title', 'status', 'estimated_token_budget', 'completed_at']].copy()
        display_df.columns = ['Task ID', 'Day', '모듈명', '상태(Status)', '토큰 예산', '완료 일시']
        
        # 상태(DONE/TODO)에 따른 색상 하이라이트 함수
        def color_status(val):
            if val == 'DONE':
                return 'background-color: #e6ffed; color: #1e7e34; font-weight: bold'
            return 'background-color: #fff5eb; color: #fd7e14; font-weight: bold'
        
        # 스타일 적용하여 데이터프레임 출력
        st.dataframe(display_df.style.map(color_status, subset=['상태(Status)']), use_container_width=True)
        
        # ---------------------------------------------------------
        # 5. 아코디언 뷰: 태스크 상세 스코프 (Scope 락 통제 확인용)
        # ---------------------------------------------------------
        st.subheader("🔍 태스크 상세 설계 범위 통제 (Scope & Out-of-Scope)")
        for t in tasks:
            with st.expander(f"[{t.get('status', 'TODO')}] {t.get('task_id')} : {t.get('title')}"):
                st.markdown(f"**🎯 달성 목표:** {t.get('goal', '')}")
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown("✅ **In-Scope (구현 대상)**")
                    for s in t.get('scope', []):
                        st.markdown(f"- {s}")
                with c2:
                    st.markdown("🚫 **Out-of-Scope (절대 구현 금지 - 환각 차단)**")
                    for o in t.get('out_of_scope', []):
                        st.markdown(f"- {o}")
    else:
        st.info("아직 생성된 태스크가 없습니다.")

else:
    st.info("📂 WBS 데이터를 기다리는 중입니다... 메인 콘솔에서 `[0. WBS 마스터플랜 수립]`을 먼저 실행해 주세요.")

# ---------------------------------------------------------
# 자동 새로고침 루프 (파일 최하단)
# ---------------------------------------------------------
if auto_refresh:
    time.sleep(3)
    st.rerun()