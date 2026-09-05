# ==========================================
# 범용 노드 실행기 (T3 - 범용 멀티에이전트 플랫폼)
# SW 전용 노드 함수(run_architect 등) 없이, 레지스트리 메타(역할·스킬·모델티어)만으로
# 임의의 에이전트 타입(마케팅/리서치/문서 등)을 실행하는 일반화된 LLM 노드.
#
# 동작: 자기 역할/스킬 + 프로젝트 목표(initial_idea) + 상류 단계 산출물(artifacts)을 묶어
#       LLM 을 호출하고, 결과를 state.artifacts[<agent_id>] 에 누적한다.
# - SW 파이프라인(NODE_IMPL 에 구현이 있는 노드)에는 쓰지 않는다(그쪽은 기존 함수 보존).
# - 커스텀 에이전트로 구성된 '범용 템플릿'의 모든 노드가 이 실행기로 동작한다.
# ==========================================
import os
from typing import Any, Dict

from state_models import ProjectState
from core.agent_registry import agent_meta, agent_skill


def _load_skill(skill_name: str) -> str:
    if not skill_name:
        return ""
    path = f"skills/{skill_name}.md"
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return ""


def _master_block_text(state_obj: Any) -> str:
    """이 에이전트에게 줄 **기준정보 본문**.

    ## ⚠️⚠️ [2026-08-29 실측] 같은 필요를 두 경로가 각자 해결했고 한쪽만 연결돼 있었다

    범용 노드는 `state.master_data` 라는 **원시 문자열 칸**만 읽었다. 그 칸을 채우는 곳은
    `POST /projects/{id}/mega/plan` 하나뿐인데(LLM 이 «추천 지표» 를 지어내 저장한다),
    실제로는 **프로젝트 63개 전부 비어 있었다.**

    한편 SW 파이프라인은 같은 자리에서 `get_master_context()` 를 부른다 —
    조직 범위로 거르고 도메인을 유추해 **사내 확정 기준**을 뽑는 확정 조회다.
    `mfg_sim` 상태로 불러 보면 **8,947자**가 나온다(LME 니켈가 16,500·환율 1,350·
    직접노무비 35·OEE 임계 0.85·지연 위약률 0.02 …).

    ★★★ 그래서 시뮬레이터 스킬이 「**상상 금지 — 주입된 데이터로 예측하라**」고 명령하는데
      정작 아무 데이터도 도착하지 않았다. 수행 불가능한 지시였고, 결과는 지어낸 숫자였다
      (`scenario-01` 의 원가 보고서가 「ERP 에서 수집했습니다」로 시작한다 — 아무것도
      읽지 않았다).

    ⚠️ 예산은 **SW 파이프라인과 같은 식**을 쓴다(`context_engine.py:74`). 여기서 다시
      정하면 두 경로가 갈리고, 갈린 쪽이 굶는다. 기준정보 하나가 예산을 다 삼켜 기술
      명세가 통째로 잘린 사고가 이미 있었다(실측 21,877자 > 20,000자).
    ⚠️ 확정 조회가 실패해도 **막지 않는다** — 종전의 문자열 칸으로 떨어진다. MEGA 흐름이
      그 칸을 쓰므로 끊으면 그쪽이 죽는다.
    """
    raw = (getattr(state_obj, "master_data", "") or "").strip()
    try:
        import config
        from core.master_data import master_data as _md, _infer_domains
        #: ⚠️⚠️ **도메인이 정해지지 않으면 주입하지 않는다.**
        #:
        #:   `get_master_context` 는 도메인이 비면 «도메인 무관» 으로 전수를 준다. 그러면
        #:   `content-marketing`·`data-analytics` 같은 템플릿에 **비철금속 제련 기준정보
        #:   10KB**(LME 니켈가·자용로·BOM·CBAM)가 통째로 들어간다 — 마케팅 콘텐츠를 쓰는
        #:   에이전트에게 구리 제련 파라미터를 주는 셈이다(실측 10,141자).
        #:   같은 형태의 사고가 이미 있었다: 도메인·조직범위 미선언 프로젝트에서 «전수» 가
        #:   곧 «DB 전체» 가 되어 블록 하나가 예산을 삼켰다(`context_engine.py:66` 주석).
        #: ★ 관련 없는 기준정보는 «없는 것» 보다 나쁘다 — 산출물이 그쪽으로 끌려간다.
        domains = list(getattr(state_obj, "master_domains", None) or [])
        if not domains:
            domains = _infer_domains(getattr(state_obj, "template_id", "") or "")
        if not domains:
            return raw
        ctx_max = getattr(config, "CONTEXT_MAX_LENGTH", 20000)
        budget = max(8000, int(ctx_max * 0.5))
        text = (_md.get_master_context(state_obj, max_chars=budget) or "").strip()
    except Exception as e:
        print(f"WARN [Universal] 기준정보 확정 조회 실패 - 상태의 값으로 진행합니다: {e}")
        return raw
    if not text:
        return raw
    #: 둘 다 있으면 **확정 조회를 앞에** 둔다 — 사내 기준이 추천값보다 세다.
    return (text + (chr(10) * 2) + raw) if raw else text


def _format_upstream(artifacts: Dict[str, str], summaries: Dict[str, str], self_id: str) -> str:
    """이전 단계 산출물을 사람이 읽는 블록으로 - 범용 노드가 맥락을 이어 작업하도록.
    직전 노드(가장 마지막 항목)는 원본(artifacts)을 쓰고, 그 이전은 요약본(summaries)을 쓴다."""
    keys = [k for k in artifacts.keys() if k != self_id and (artifacts.get(k) or "").strip()]
    if not keys:
        return "(아직 이전 단계 산출물이 없습니다 - 이번이 첫 단계입니다.)"
    
    # 마지막 키(직전 노드)는 원본, 나머지는 요약본
    last_key = keys[-1]
    
    blocks = []
    for k in keys:
        if k == last_key:
            content = artifacts.get(k, "").strip()
            blocks.append(f"### [{k}] (원본 상세)\n{content}")
        else:
            # 요약본이 없으면 원본이라도 쓴다 (하위호환)
            content = summaries.get(k) or artifacts.get(k, "")
            content = content.strip()
            blocks.append(f"### [{k}] (핵심 요약)\n{content}")
            
    return "\n\n".join(blocks)


def _get_format_injection(format_id: str) -> str:
    from api.routes.format_control import load_formats
    formats = load_formats()
    for f in formats:
        if f["id"] == format_id:
            return f["prompt_injection"]
    # 기본 폴백
    return "당신의 최종 결과물은 반드시 <artifact> ... </artifact> 태그 안에 작성하시오. 그 전에 <summary> ... </summary> 태그 안에 핵심 요약을 3줄 이내로 작성하시오."


def _business_data_block(state_obj: Any, meta: Dict[str, Any]) -> str:
    """에이전트가 선언한 데이터 계약만 인증판에서 읽는다."""
    contracts = list(meta.get("data_contracts") or [])
    if not contracts:
        return ""
    binding = dict(getattr(state_obj, "business_data_binding", {}) or {})
    if not binding:
        raise RuntimeError("이 에이전트에 필요한 업무 데이터 적용본이 연결되지 않았습니다.")
    from core.data_preparation.store import data_preparation_store
    from core.project_data_context import render_agent_context
    return render_agent_context(data_preparation_store, binding, contracts)


def make_universal_node(agent_id: str):
    """레지스트리 메타로 구동되는 범용 노드 함수를 생성(클로저로 agent_id 고정)."""

    async def _node(state: Any) -> Dict[str, Any]:
        from core.llm_gateway import gateway  # 지연 임포트(순환 방지)
        from core.parser import extract_summary, extract_artifact
        state_obj = ProjectState.model_validate(state)
        tid = getattr(state_obj, "template_id", "default") or "default"
        fmt_id_from_state = getattr(state_obj, "output_format_id", "default") or "default"
        meta = agent_meta(agent_id, tid)
        fmt_id = meta.get("output_format") or fmt_id_from_state

        role = meta.get("role", "") or agent_id
        name_ko = meta.get("name_ko", "") or agent_id
        stage = str(meta.get("stage", "") or agent_id).strip()
        is_heavy = (meta.get("model_tier", "flash") == "pro")
        skill = _load_skill(agent_skill(agent_id, "", template_id=tid))

        print(f" [Universal] {name_ko}({agent_id}) 실행 중... (tier={'pro' if is_heavy else 'flash'}, format={fmt_id})")

        artifacts = dict(getattr(state_obj, "artifacts", {}) or {})
        summaries = dict(getattr(state_obj, "artifact_summaries", {}) or {})
        upstream = _format_upstream(artifacts, summaries, agent_id)
        
        goal = (getattr(state_obj, "initial_idea", "") or "").strip()
        master_data = _master_block_text(state_obj)
        business_data = _business_data_block(state_obj, meta)

        master_block = f"[전사 마스터 데이터 및 제약사항]\n{master_data}\n\n" if master_data else ""
        business_block = f"[업무키트 인증 데이터]\n{business_data}\n\n" if business_data else ""
        format_injection = _get_format_injection(fmt_id) if fmt_id else ""

        prompt = (
            f"[당신의 역할]\n{role}\n\n"
            + (f"{skill}\n\n" if skill else "")
            + master_block
            + business_block
            + f"[프로젝트 목표]\n{goal}\n\n"
            f"[이전 단계 산출물]\n{upstream}\n\n"
            "[지시]\n위 역할에 충실하게, 프로젝트 목표와 이전 단계 산출물을 바탕으로 "
            "이번 단계의 산출물을 구체적이고 완결성 있게 작성하라. (마스터 데이터가 주어진 경우 최우선으로 준수할 것.)\n\n"
            f"[출력 양식 제약 (중요)]\n{format_injection}"
        )

        output = await gateway.aexecute(state_obj, prompt, is_heavy=is_heavy, output_mode="document", light=True)
        
        # 파싱 (Level 2 하네스)
        out_summary = extract_summary(output)
        out_artifact = extract_artifact(output)
        
        artifacts[agent_id] = str(out_artifact or "")
        summaries[agent_id] = str(out_summary or "")
        
        print(f"[OK] [Universal] {name_ko} 산출물 생성 (요약 {len(summaries[agent_id])}자, 상세 {len(artifacts[agent_id])}자)")
        return {
            "artifacts": artifacts,
            "artifact_summaries": summaries,
            "current_stage": stage,
        }

    _node.__name__ = f"universal_{agent_id}"
    return _node
