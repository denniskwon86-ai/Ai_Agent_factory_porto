import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

import asyncio
from core.agent_graph import get_runtime_app
from state_models import ProjectState

async def test_mfg():
    app = await get_runtime_app("mfg_sim")
    
    state = ProjectState(
        project_name="친환경 전기차 배터리 라인 증설",
        initial_idea="신규 모델 수요 급증에 대비해 친환경 전기차 배터리 생산 라인을 2배로 증설할 때의 가치사슬 시뮬레이션을 수행하라.",
        template_id="mfg_sim",
        workspace_root="./workspace"
    )
    
    config = {"configurable": {"thread_id": "test_mfg_2"}}
    print("🚀 제조업 시뮬레이터(mfg_sim) 파이프라인 구동 시작!")
    
    async for output in app.astream(state.model_dump(), config, stream_mode="values"):
        current = ProjectState.model_validate(output)
        print("-------------------------------------------------")
        for agent_id, art in current.artifacts.items():
            # 길이를 요약해서 출력
            print(f"[{agent_id}] 산출물 (길이: {len(art)}자)")
            
    print("\n✅ 전체 시뮬레이션 파이프라인 구동 종료!")
    
    # 마지막 상태 출력
    final_state = await app.aget_state(config)
    final_artifacts = final_state.values.get("artifacts", {})
    print("\n=== 최종 산출물 요약 ===")
    for k, v in final_artifacts.items():
        print(f"✔️ {k}: {len(v)}자")

if __name__ == "__main__":
    asyncio.run(test_mfg())
