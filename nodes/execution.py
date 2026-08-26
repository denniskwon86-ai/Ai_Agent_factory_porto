import os
import json
import re
import asyncio
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List
import config
from state_models import ProjectState
from core.llm_gateway import gateway, QuotaExhaustedException, GenerationFailure
from core.agent_registry import agent_skill
from nodes.utils.git_manager import GitManager
from nodes.utils.wbs_manager import WBSManager
from nodes.utils.syntax_checker import LocalSyntaxChecker
from nodes.code_builder import CodeBuilder
from nodes.utils.traceability_manager import TraceabilityManager

def _load_skill(role_name: str) -> str:
    path = f"skills/{role_name}.md"
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return ""

def _safe_str(output: Any) -> str:
    """ [무적 방어막] List 형태나 객체 데이터가 넘어와도 절대 '.strip()' 에러가 나지 않도록 정규화"""
    if output is None: return ""
    
    if hasattr(output, "content"):
        content = output.content
        if isinstance(content, list):
            return "\n".join([str(c.get("text", c)) if isinstance(c, dict) else str(c) for c in content])
        return str(content)
        
    if isinstance(output, (list, dict)): 
        return json.dumps(output, ensure_ascii=False, indent=2)
    return str(output)

def _extract_files_from_json(json_str: Any) -> List[Dict[str, str]]:
    if not json_str: return []
    try:
        if isinstance(json_str, list):
            json_str = json.dumps(json_str, ensure_ascii=False)
        clean_str = str(json_str).strip()

        data = None
        # 1) 이미 정제된 JSON이면 통째로 파싱 (게이트웨이가 _repair_and_parse_json으로 정돈한 경우)
        try:
            data = json.loads(clean_str)
        except Exception:
            data = None
        # 2) 실패 시 마크다운 펜스 또는 '그리디' 괄호 매칭으로 추출 (중첩 JSON 보존 - 비탐욕 금지)
        if data is None:
            md_match = re.search(r'\x60{3}(?:json)?\s*(\{[\s\S]*\})\s*\x60{3}', clean_str)
            if md_match:
                clean_str = md_match.group(1)
            else:
                alt_match = re.search(r'(\{[\s\S]*\})', clean_str)
                if alt_match:
                    clean_str = alt_match.group(1)
            data = json.loads(clean_str)

        files = data.get("files", []) if isinstance(data, dict) else []
        return files if isinstance(files, list) else []
    except Exception:
        return []


def _extract_deleted_from_json(json_str: Any) -> List[str]:
    """LLM 출력에서 `deleted_files`(삭제 요청 경로)를 뽑는다.

    ⚠️ [2026-07-27] 이 경로가 없으면 파이프라인은 **파일을 지울 수 없다.**
      실측(test_a1_v9 E2E-04): Tech Lead 가 스택 전환으로 React 파일 삭제를 지시했는데
      개발자에게 삭제 수단이 없어 두 아키텍처가 공존했고, 같은 지적이 8회 반복되며
      재작업 예산이 소진됐다."""
    if not json_str:
        return []
    try:
        s = str(json_str).strip()
        try:
            data = json.loads(s)
        except Exception:
            m = re.search(r'(\{[\s\S]*\})', s)
            data = json.loads(m.group(1)) if m else None
        if not isinstance(data, dict):
            return []
        out = data.get("deleted_files") or []
        return [str(p) for p in out if isinstance(p, str) and p.strip()] if isinstance(out, list) else []
    except Exception:
        return []

def _collect_disk_files(workspace_root: str, exts: tuple, cap: int = 120) -> List[Dict[str, str]]:
    """워크스페이스 디스크에서 지정 확장자 파일을 수집해 [{file_path, code}] 로 반환.
    프리뷰/회귀 게이트가 '마지막 LLM 출력'이 아니라 '디스크의 현재 전체 파일 집합'을 보도록 한다.
    노이즈 디렉터리(node_modules/.git/.archive 등)는 제외."""
    out: List[Dict[str, str]] = []
    if not workspace_root:
        return out
    root = Path(workspace_root)
    if not root.exists():
        return out
    from core.context_engine import _EXCLUDE_DIRS
    for p in sorted(root.rglob("*")):
        if len(out) >= cap:
            break
        if not p.is_file():
            continue
        rel = str(p.relative_to(root)).replace("\\", "/")
        if any(seg in _EXCLUDE_DIRS for seg in rel.split("/")):
            continue
        if rel.endswith(exts):
            try:
                out.append({"file_path": rel, "code": p.read_text(encoding="utf-8")})
            except Exception:
                continue
    return out


async def run_architect(state: Any) -> Dict[str, Any]:
    state_obj = ProjectState.model_validate(state)
    print(" [Agent] Architect 토론·합의 기반 설계 진행 중...")

    # 기획 단계에서 사용자가 승인한 UI 목업이 있으면 화면 구조/컴포넌트 경계를 아키텍처에 반영
    extra = ""
    ui_mockup = (getattr(state_obj, "ui_mockup_summary", "") or "").strip()
    if ui_mockup:
        extra = f"\n\n[참조: 사용자가 승인한 UI 목업 - 화면 구성과 컴포넌트 경계를 아키텍처 설계에 반영하십시오]\n{ui_mockup}"

    # ★★★ [2026-08-26 실측] **이 플랫폼이 무엇을 만들 수 있는지 알려 준다.**
    #
    # ⚠️⚠️ 없을 때 Architect 는 「백엔드 API 서버(예: Spring Boot)」를 설계했고, 공장은
    #   `InboundApplication.java` 를 만들었다. 그런데 `server.custom_logic`·`api.direct_call`
    #   은 계약상 **금지**다 — 프론트 렌더 검증이 8회 반려하고 FAILED_REVIEW 로 끝났다.
    #   스킬은 오히려 「High FR 은 반드시 REST 엔드포인트로 설계하라」고 적고 있었다.
    # ★ 계약을 안 타는 레거시 프로젝트에는 빈 문자열이라 종전과 같이 동작한다.
    from core.app_runtime_brief import render as _runtime_brief
    extra += _runtime_brief(state_obj)

    from nodes.utils.debate import run_supervised_stage
    updates, result = await run_supervised_stage(state_obj, agent_skill("Architect", "architect_skill", template_id=state_obj.template_id), "ARCHITECTURE", extra_instruction=extra)
    print(f"[OK] [Agent] Architect 설계 완료 - 점수 {result.get('score')} / 판정 {result.get('verdict')}")
    updates.setdefault("factory_mode", "EXECUTION")
    updates.setdefault("needs_revision", False)
    return updates

def _approved_contract_brief(state_obj: Any) -> str:
    """이 프로젝트에 **이미 있는 계약**을 Tech Lead 에게 그대로 보여 준다.

    ## ⚠️ 왜 필요한가 (2026-08-26 실측)

    계약은 프로젝트 하나인데 태스크마다 Tech Lead 가 데이터셋을 처음부터 다시 정의했다.
    두 선언이 달라지자 합산기가 「사람이 정해야 합니다」로 멈췄고 — 그런데 **사람이
    정할 화면도 API 도 없다.** 막다른 길이었다.

    ★ 합산기를 고치지 않는다. 자동 병합은 조용한 권한 확대이므로 그 거절이 옳다.
      고칠 것은 **Tech Lead 가 이미 있는 것을 모른 채 새로 짓는 것**이다.

    ⚠️ 계약이 없으면 빈 문자열이다 — 첫 태스크에는 붙을 것이 없다.
    """
    from nodes.contract import contract_path

    ws = getattr(state_obj, "workspace_root", "") or ""
    if not ws:
        return ""
    try:
        with open(contract_path(ws), encoding="utf-8") as f:
            contract = json.load(f)
    except Exception:
        return ""
    datasets = (contract or {}).get("datasets") or []
    if not datasets:
        return ""

    #: ★★★ **요약하지 않는다 — 원문을 그대로 싣는다.**
    #:
    #: ⚠️⚠️ [2026-08-26 실측] 처음에는 이름·라벨·출처·행동·칸만 골라 보여 주고 「글자 그대로
    #:   옮기라」고 했다. 그랬더니 Tech Lead 가 **내가 안 보여 준 `enterprise_contract_key`
    #:   를 빠뜨린** 데이터셋을 냈고, 컴파일러가 그 자리에서 막았다:
    #:     「출처가 ENTERPRISE_READ 인데 어느 업무 데이터에서 오는지가 없습니다」
    #:   요약본을 정본처럼 내밀면 **받는 쪽은 그 요약이 전부인 줄 안다.** 내가 만든 결함이다.
    #: ★ 그대로 옮기라고 시킬 것이면 **그대로 보여 줘야** 한다.
    lines = ["", "", "[🚨 이 프로젝트에는 **이미 승인된 계약**이 있습니다]", "",
             "아래는 계약 정본의 `datasets` **원문 그대로**입니다(요약이 아닙니다).", "",
             "```json",
             json.dumps(datasets, ensure_ascii=False, indent=2),
             "```"]
    lines += [
        "",
        "★ 이 데이터셋을 다시 쓴다면 **위 선언을 글자 그대로** 옮겨 적으십시오.",
        "  이름·칸·타입·행동·출처 중 하나라도 다르면 합산기가 «두 태스크가 다르게",
        "  선언했다» 로 **파이프라인을 멈춥니다**(자동 병합하지 않습니다).",
        "⚠️ 정말로 바꿔야 한다면 바꾸십시오 — 다만 그것은 **재승인 대상**입니다.",
        "  「같은 것을 조금 다르게 적는 것」과 「바꾸는 것」을 구분하십시오.",
        "★ 이 태스크가 새 데이터를 다루면 **위 목록에 더해서** 선언하십시오. 빼면 그 데이터셋이",
        "  계약에서 사라지고, 이미 만들어진 화면이 읽을 것을 잃습니다.",
    ]
    return "\n".join(lines)


async def run_tech_lead(state: Any) -> Dict[str, Any]:
    state_obj = ProjectState.model_validate(state)

    extra = ""
    if getattr(state_obj, "reviewer_decision", "") == "REWORK_DEV" or getattr(state_obj, "needs_revision", False):
        print("️ [Agent] Tech Lead: 결함/기획변경에 따른 토론 기반 재설계(Rework) 진행 중...")
        extra = f"\n\n[ 재작업(Rework) 지시사항]:\n리뷰어 또는 PM의 피드백을 반영하여 설계를 수정하십시오:\n{state_obj.reviewer_feedback}"
    else:
        print("️ [Agent] Tech Lead 토론·합의 기반 기술명세 진행 중...")

    # 기술명세 재작업에서 LLM이 오래된 예시 파일(index.tsx/App.css 등)을 사실처럼 다시 제안하면,
    # 이미 정상인 워크스페이스를 스스로 깨뜨리고 심사-재작업 왕복만 반복한다. 스킬의 일반 규칙에만
    # 맡기지 않고, 호출 시점의 실제 파일/태스크 사실을 프롬프트 마지막에 불변 조건으로 주입한다.
    # 초기 태스크처럼 파일이 아직 없을 때는 새 파일 생성을 허용하되, 기존 파일이 하나라도 있으면
    # 목록 밖 경로·상대 import·근거 없는 서버 API를 제안할 수 없다.
    existing_paths = set((state_obj.file_index or {}).keys())
    if state_obj.workspace_root:
        root = Path(state_obj.workspace_root)
        if root.exists():
            for disk in root.rglob("*"):
                if disk.is_file() and ".git" not in disk.parts and ".archive" not in disk.parts:
                    try:
                        existing_paths.add(str(disk.relative_to(root)).replace("\\", "/"))
                    except ValueError:
                        continue

    task_goal = ""
    try:
        wbs = WBSManager(workspace_root=state_obj.workspace_root).get_wbs() or {}
        task = next((t for t in (wbs.get("tasks") or [])
                     if str(t.get("task_id")) == str(state_obj.current_sprint_task_id)), {})
        task_goal = f"goal={task.get('goal', '')}; scope={', '.join(task.get('scope') or [])}"
    except Exception:
        task_goal = ""

    if existing_paths:
        inventory = "\n".join(f"- {p}" for p in sorted(existing_paths)[:80])
        extra += (
            "\n\n[시스템 강제 사실 — 위반 금지]\n"
            f"현재 태스크: {state_obj.current_sprint_task_id}. {task_goal}\n"
            "다음은 실제 워크스페이스에 존재하는 파일의 완전한 기준 목록이다. "
            "기술명세·CODE INSTRUCTIONS·STATE_UPDATES에서 이 목록 밖의 기존 파일을 언급하거나 "
            "상대 import 대상으로 삼지 마라. 새 파일이 꼭 필요하면 먼저 필요성을 설명하고 "
            "같은 명세 안에 실제 전체 경로와 책임을 정의하라.\n"
            f"{inventory}\n"
            "이번 명세에는 (1) 각 실제 파일의 책임과 FR-ID, (2) 함수/컴포넌트 입력·출력·오류 처리, "
            "(3) 서버 API가 필요 없으면 '서버 API 없음'을 반드시 포함하라. "
            "이전 초안의 index.tsx, App.css, 근거 없는 백엔드 API는 현재 사실이 아니므로 재사용 금지."
        )

    # ★★★ [2026-08-26 실측] **이미 승인된 계약을 보여 준다.**
    #
    # ⚠️⚠️ 이것이 없어서 E2E-02 가 막혔다. 계약은 **프로젝트 하나**인데 태스크마다 Tech Lead
    #   가 데이터셋을 **처음부터 다시** 정의했고, 두 선언이 달라지자 합산기가 멈췄다:
    #     「데이터셋 «raw_material_inbound_status» 를 «E2E-01» 와 «E2E-02» 가 다르게
    #      선언했습니다 — … 사람이 정해야 합니다(자동 병합하지 않습니다).」
    #   합산기가 옳다 — 자동 병합은 조용한 권한 확대다. 문제는 **Tech Lead 가 이미 있는
    #   것을 못 봤다**는 점이다(전수 확인: 계약 파일을 읽는 코드가 0곳이었다).
    # ★ 지문이 그대로면 재승인도 필요 없다 — 사람의 승인 횟수까지 함께 줄어든다.
    extra += _approved_contract_brief(state_obj)

    from nodes.utils.debate import run_supervised_stage
    updates, result = await run_supervised_stage(state_obj, agent_skill("Tech_Lead", "tech_lead_skill", template_id=state_obj.template_id), "TECH_SPEC", extra_instruction=extra)
    output_str = updates.get("tech_spec_summary", getattr(state_obj, "tech_spec_summary", "") or "")

    # 기존 STATE_UPDATES(ADR/기술부채/파일인덱스) 파싱 로직 유지
    arch_decisions = state_obj.architecture_decisions
    tech_debt = state_obj.technical_debt
    file_idx = state_obj.file_index

    state_update_match = re.search(r'5\.\s*STATE_UPDATES[\s\S]*?\x60{3}(?:json)?\s*(\{[\s\S]*?\})\s*\x60{3}', output_str)
    if state_update_match:
        try:
            su = json.loads(state_update_match.group(1))
            #  견고화: LLM이 ADR/부채를 객체가 아닌 문자열(ID)로 줄 때 정상 스키마로 변환 (재개 시 검증 크래시 방지)
            #  ⚠️ [2026-07-26] 과거 dict 는 **검증 없이 그대로** 상태에 넣었다. LLM 이 동의어 키
            #     ({id,title,description})를 내면 이후 ProjectState 검증이 8개 오류로 실패해
            #     스프린트 루프가 통째로 죽었다. → 여기서 모델로 즉시 검증해 불량 항목만 버린다.
            #     (ADR/DebtItem 이 동의어 흡수·기본값을 갖고 있으므로 정상 편차는 살아남는다)
            from state_models import ADR as _ADR, DebtItem as _Debt
            for item in (su.get("architecture_decisions") or []):
                if isinstance(item, str) and item.strip():
                    item = {"id": item.strip()[:64], "decision": item.strip(), "reason": ""}
                if isinstance(item, dict):
                    try:
                        arch_decisions.append(_ADR.model_validate(item).model_dump())
                    except Exception as e:
                        print(f"⚠️ ADR 항목 1건 스키마 불일치로 건너뜀: {e}")
            for item in (su.get("technical_debt") or []):
                if isinstance(item, str) and item.strip():
                    item = {"id": item.strip()[:64], "description": item.strip(), "priority": 3}
                if isinstance(item, dict):
                    try:
                        tech_debt.append(_Debt.model_validate(item).model_dump())
                    except Exception as e:
                        print(f"⚠️ 기술부채 항목 1건 스키마 불일치로 건너뜀: {e}")
            if "file_index_updates" in su:
                for path, info in su["file_index_updates"].items():
                    if path in file_idx:
                        file_idx[path].purpose = info.get("purpose", file_idx[path].purpose)
                        file_idx[path].change_summary = info.get("change_summary", file_idx[path].change_summary)
        except Exception as e:
            print(f"⚠️ Tech Lead STATE_UPDATES 파싱 실패: {e}")

    updates["architecture_decisions"] = arch_decisions
    updates["technical_debt"] = tech_debt
    updates["file_index"] = file_idx

    #: ★★★ [2026-08-25 실측] **계약 초안을 남긴다.**
    #:
    #: ⚠️⚠️ 이 저장이 **없어서** SW 생성기가 Tech Lead 다음 칸에서 늘 끝났다.
    #:   `nodes/contract.load_drafts()` 는 처음부터 있었는데 쓰는 곳이 저장소 어디에도
    #:   없었다(전수 확인). 그래서 계약 컴파일러가 언제나
    #:     「계약 대상 태스크인데 계약 초안이 없습니다 … Tech Lead 가 초안을 만들어야 합니다.」
    #:   를 내고 지문이 비어 `TerminalHandler` 로 빠졌다 — 사용자가 본 「계약이 생성되지
    #:   않아 전달 실패」가 이것이다.
    #: ★ 초안은 **이 태스크의 것**이다. 합산은 컴파일러가 WBS 전체로 다시 한다.
    _save_contract_draft(state_obj, output_str)

    print(f"[OK] [Agent] Tech Lead 기술명세 완료 - 점수 {result.get('score')} / 판정 {result.get('verdict')}")
    return updates


#: 계약 초안 블록. ★ 스킬(`skills/tech_lead_skill.md` §1-B)이 내는 모양이다.
#: ⚠️ 언어 태그를 느슨하게 받는다 — 모델이 ```json / ```json contract-draft / ```
#:   중 무엇을 쓸지 강제할 수 없다. **못 찾는 것보다 넓게 찾는 편이 낫다.**
_DRAFT_BLOCK = re.compile(
    r"```(?:json)?[^\r\n]*contract-draft[^\r\n]*([\s\S]*?)```", re.IGNORECASE)


def _save_contract_draft(state_obj: Any, output_str: str) -> None:
    """Tech Lead 출력에서 계약 초안을 뽑아 저장한다. **실패해도 명세를 되돌리지 않는다.**

    ⚠️ 다만 **조용히 넘기지 않는다.** 초안이 없으면 다음 칸(계약 컴파일러)이 막히고,
      그때 사람은 「왜 막혔나」를 여기까지 거슬러 올라와야 한다. 여기서 말해 준다."""
    from nodes.contract import save_draft

    ws = getattr(state_obj, "workspace_root", "") or ""
    tid = str(getattr(state_obj, "current_sprint_task_id", "") or "").strip()
    if not ws or not tid:
        return

    m = _DRAFT_BLOCK.search(output_str or "")
    if not m:
        #: ⚠️ 「1-B 를 안 냈다」와 「데이터를 안 쓴다」는 다른 사실이다. 여기서 빈 계약을
        #:   지어내면 뒤 칸이 **아무 데이터도 안 쓰는 앱**을 정상으로 컴파일한다.
        print("⚠️ [Tech Lead] 계약 초안 블록(1-B CONTRACT DRAFT)이 없습니다 — "
              "다음 단계(계약 컴파일)가 이 태스크에서 막힙니다.")
        return
    try:
        draft = json.loads(m.group(1))
    except Exception as e:
        print(f"⚠️ [Tech Lead] 계약 초안을 읽지 못했습니다(JSON 오류): {e}")
        return
    if not isinstance(draft, dict):
        print("⚠️ [Tech Lead] 계약 초안이 객체가 아닙니다 — 저장하지 않습니다.")
        return
    try:
        path = save_draft(ws, tid, draft)
        print(f"[OK] [Tech Lead] 계약 초안 저장 — {os.path.relpath(path, ws)} "
              f"(데이터셋 {len(draft.get('datasets') or [])}개)")
    except Exception as e:
        print(f"⚠️ [Tech Lead] 계약 초안을 저장하지 못했습니다: {e}")

# 증분 개발 지시 - 멀티태스크에서 이전 태스크가 만든 기능을 덮어써 잃어버리는 회귀 방지.
# 소유 파일은 컨텍스트에 '전체 코드'로(절단 없이) 주입되므로, 모델은 기존 기능을 빠짐없이 볼 수 있다.
_INCREMENTAL_GUARD = (
    "\n\n[ 증분 개발 - 절대 준수]: 당신은 빈 화면이 아니라 **기존 코드베이스를 확장**한다. "
    "컨텍스트의 '현재 워크스페이스 실제 파일 상태'에는 당신이 수정할 파일들의 **전체 코드가 절단 없이** 들어 있다. "
    "거기 이미 구현된 모든 기능(데이터 입력/CRUD/목록/상태/이벤트 핸들러 등)을 **절대 삭제하거나 누락하지 말 것.** "
    "이번 태스크의 기능은 **추가/수정만** 하라. 파일을 다시 출력할 때는 반드시 "
    "'기존 코드 전부 + 이번 신규 기능'을 합친 완전한 코드를 내라. 기존 기능을 하나라도 빠뜨리면 즉시 재작업 처리된다."
    # [2026-07-26 실측] 전체 재출력을 강제하기 때문에, 이전 회차에서 고친 결함(예: 없는 App.css import)이
    #   다음 회차 재출력에서 되살아나 '고쳤다 되돌리기'가 반복됐다. 전체 재출력의 부작용을 여기서 막는다.
    "\n\n[ import 규칙 - 위반 시 렌더 검증 자동 실패]: 상대경로로 import 하는 파일은 "
    "**반드시 이번 응답의 files 배열에 실제 내용과 함께 포함**하거나, 그 **import 문을 삭제**하라. "
    "존재하지 않는 파일을 import 하면 빌드가 깨진다(특히 CSS: `import './App.css'` 처럼 "
    "파일을 만들지 않을 것이면 import 자체를 쓰지 말 것). "
    "react 와 상대경로 파일 외의 외부 라이브러리(axios 등)는 import 할 수 없다."
    "\n\n[ 회귀 금지]: 이전 회차의 검토 의견으로 이미 수정한 사항은, 파일을 전체 재출력할 때도 "
    "**그 수정 상태를 유지**하라. 한 번 제거한 import·한 번 고친 버그를 되살리면 즉시 재작업 처리된다."
    # [2026-07-27 실측] test_a1_v9 의 E2E-04 가 React(`src/App.tsx`) 위에 바닐라 JS
    #   (`index.html` + 루트 `script.js`)를 새로 얹었다. 두 아키텍처가 한 워크스페이스에
    #   공존하면서 렌더 검증이 App 루트를 확정하지 못했고, 재작업 8회를 소진해 FAILED 됐다.
    #   '기존 코드를 확장하라'는 지시만으로는 **패러다임 전환**을 막지 못한다.
    "\n\n[🏛️ 아키텍처 일관성 - 위반 시 즉시 재작업]: 워크스페이스에 이미 존재하는 "
    "**기술 스택과 구조를 그대로 따르라.** 새로운 패러다임을 도입하지 말 것.\n"
    "· 기존에 React 컴포넌트(`.tsx`)로 되어 있으면 계속 React 컴포넌트로 만든다. "
    "`index.html` + 전역 `script.js` 같은 바닐라 JS 구현을 **새로 추가하지 마라.**\n"
    "· 반대로 기존이 바닐라 JS 면 React 를 새로 도입하지 마라.\n"
    "· 진입점(App 루트, index.html 등)은 **하나만** 존재해야 한다. 같은 기능을 다른 방식으로 "
    "구현한 파일을 나란히 두면 어느 것이 진짜인지 알 수 없어 빌드가 깨진다.\n"
    "· 기존 구조가 이번 요구에 맞지 않는다고 판단되면, 새 구조를 덧붙이지 말고 "
    "**기존 파일을 수정**하라."
)

# 개발자별 '소유 파일' 확장자 - 컨텍스트에 전체(무절단) 주입할 대상(증분 codegen).
_FE_OWNED_EXTS = (".tsx", ".ts", ".jsx", ".js", ".css", ".html")
_BE_OWNED_EXTS = (".py",)

_NO_SERVER_API_MARKERS = (
    "서버 API 없음", "서버 api 없음", "server api 없음",
    "no server api", "server_api_required: false", '"server_api_required": false',
    "서버 API가 없", "백엔드 API 없음", "서버 없음",
)


def _tech_spec_declares_no_server_api(state_obj: ProjectState) -> bool:
    """기술명세가 '서버 API 없음'을 명시적으로 선언했는가.

    ⚠️ [2026-07-27] `skills/tech_lead_skill.md` 는 서버 API 가 없을 때 "서버 API 없음"을
      **명시하도록** 요구한다(그 파일 :36, :53). 그런데 그 선언을 실제로 읽어서 역할 배정에
      반영하는 곳이 없었다. 그 결과 backend_skill 의 'FastAPI·DB·main.py 를 만들어라'가
      항상 이겨서, 서버가 필요 없는 앱에도 백엔드가 생성됐다(test_a1_v4 실측).

    보수적으로 판정한다 — 선언이 **명확할 때만** True. 애매하면 기존 동작(백엔드 필요)을 유지한다."""
    spec = (_safe_str(getattr(state_obj, "tech_spec_summary", "")) or "")
    if not spec:
        return False
    low = spec.lower()
    return any(m.lower() in low for m in _NO_SERVER_API_MARKERS)


def _is_syntax_clean(raw_out: Any) -> bool:
    """이 표본의 파일들이 정적 문법 검사를 통과하는가(파일이 1개 이상일 것)."""
    files = _extract_files_from_json(_safe_str(raw_out))
    if not files:
        return False
    for f in files:
        path = f.get("file_path", "")
        code = f.get("code", "")
        if path.endswith((".ts", ".tsx", ".js", ".jsx")):
            valid, _ = LocalSyntaxChecker.check_javascript_syntax(code)
            if not valid:
                return False
        elif path.endswith(".py"):
            valid, _ = LocalSyntaxChecker.check_python_syntax(code)
            if not valid:
                return False
    return True


_FILE_ERR_RE = re.compile(r'^\s*\[([^\]]+\.(?:tsx?|jsx?|py|css|html))\]', re.MULTILINE)


def _targeted_repair_instruction(build_error_log: str) -> str:
    """빌드 오류가 특정 파일을 지목하면 **그 파일만** 정밀 복구하도록 지시한다.

    ⚠️ [2026-07-27 C2] `_INCREMENTAL_GUARD` 는 항상 '기존 파일 전부 + 신규'를 재출력하라고
      요구한다. 그런데 실패 원인이 파일 하나의 구문 오류일 때 전체를 다시 쓰게 하면
      ① 출력 예산을 통째로 다시 태우고(잘릴 확률↑) ② 이미 정상인 파일까지 새로 쓰면서
      앞 회차 수정이 되돌아간다(결함 #21 의 회귀 메커니즘). 지목된 파일만 고치게 한다."""
    if not build_error_log:
        return ""
    targets = list(dict.fromkeys(_FILE_ERR_RE.findall(build_error_log)))
    if not targets:
        return ""
    return (
        "\n\n[🎯 정밀 복구 지시 - 이번 회차에 한함]\n"
        f"직전 실패는 다음 파일에서만 발생했습니다: {', '.join(targets)}\n"
        "· **이 파일들만** 수정해서 내십시오. 나머지 정상 파일은 이번 응답에 포함하지 마십시오.\n"
        "· 이유: 정상 파일까지 다시 쓰면 출력이 잘릴 위험이 커지고, 앞 회차에서 이미 고친 "
        "내용이 되돌아갑니다.\n"
        "· 위의 '증분 개발' 지시 중 '기존 파일 전부 재출력' 부분은 **이번 회차에는 적용하지 않습니다.**"
    )


def _recovery_swarm_size(is_rework: bool, retry: int) -> int:
    """복구 시도의 표본 수.

    ⚠️ [2026-07-27 실측 결함] 기존 식 `1 if _heavy else (3 if _is_rework else 1)` 은
      Backend/Frontend 노드가 `_heavy=True` 로 **하드코딩**되어 있어 **항상 1** 이었다.
      주석은 "재작업 시 3중 스웜"이라고 적혀 있었지만 그 분기는 도달하지 않는 죽은 코드였다.
      즉 v4 의 재시도는 다양성 있는 복구가 아니라 **같은 모델에게 같은 요청을 다시 보낸 것**이다.

    그렇다고 3개 병렬로 되돌리지 않는다 — 비용·429·타임아웃을 악화시킨다.
    정책: 1차는 단일 생성, 2회차부터만 표본 2개(첫 유효 결과를 채택).
    """
    if not is_rework:
        return 1
    return 2 if retry >= 1 else 1


def _generation_failure_update(gf: GenerationFailure, node: str,
                               _gf_state: Any = None) -> Dict[str, Any]:
    """공급자/출력계약 실패를 '빌드 실패'가 아닌 종료 상태로 승격한다.

    ⚠️ 핵심: `developer_retry_count` 를 **증가시키지 않는다.** 이 실패는 생성된 코드의
      결함이 아니므로, 개발자가 코드를 고칠 기회를 여기서 소모하면 안 된다.
      실측(test_a1_v4): 228.6s·420.0s·77.0s 공급자 타임아웃 3건이 그 예산을 먹었다."""
    print(f"⛔ [{node}] 생성 실패({gf.kind}) — 코드 결함이 아니므로 재작업 예산을 소모하지 않고 종결합니다.")
    # [§10.3/§8.3] 이 실패의 원인은 이미 게이트웨이가 kind 로 판정해 뒀다 — 그대로 옮긴다.
    #   (여기서 다시 추론하면 같은 사실에 두 개의 답이 생긴다.)
    try:
        from core import quality_telemetry as _qt
        _qt.record_failure(_gf_state, gate_name=node, artifact_type="CODE",
                           kind=gf.kind, detail=str(gf)[:400])
    except Exception:
        pass
    return {
        "terminal_status": gf.terminal_status,
        "terminal_reason": f"[{node}] {gf.kind}: {str(gf)[:400]}",
        "build_status": "failed",
        "failed_node": node,
        "factory_mode": "HOTL_PAUSED",
    }


async def _swarm_execution(state_obj: ProjectState, base_prompt: str, is_heavy: bool, full_file_exts: tuple,
                           num_swarm: int = 3, cacheable: bool = True) -> Any:
    """Micro-Swarm 실행기: N개의 에이전트를 병렬로 띄우고 문법/샌드박스 통과 코드를 선별

    cacheable=False: 재작업/재시도 호출에서 Exact Hash Cache 를 우회한다.
      ⚠️ [2026-07-26 실측 결함] 재시도 시 캐시를 타면 재작업 루프가 통째로 무력화된다.
        빌드 실패 → build_error_log 를 프롬프트에 주입해 재시도하지만, **에러가 매번 같으므로
        프롬프트 해시도 같다** → 캐시 히트 → 똑같은 코드 반환 → 똑같은 실패. 이 사이클이
        재작업 상한(8)까지 0.0초에 반복되고(실측 9초에 캐시히트 38건) 결국
        'best-effort 수용'으로 미해결 결함을 안고 통과해 버린다.
        `nodes/utils/debate.py:179,202` 가 같은 함정 때문에 이미 cacheable=False 를 쓰고 있는데
        개발자 노드에는 그 조치가 빠져 있었다. 재시도는 '새 표본을 뽑는 것'이 목적이므로
        캐시를 타면 안 된다."""

    async def _run_single(variant_id: int):
        # Variant에 따라 시스템 프롬프트를 미세하게 변경하여 다양성(Swarm Diversity) 유도
        variant_prompt = base_prompt + f"\n\n[System Note: You are Swarm Agent #{variant_id}. Focus on writing clean, bug-free code.]"
        try:
            return await gateway.aexecute(state_obj, variant_prompt, is_heavy=is_heavy,
                                          full_file_exts=full_file_exts, cacheable=cacheable)
        except QuotaExhaustedException:
            raise
        except GenerationFailure:
            # ⚠️ [2026-07-27] 여기서 삼켜 None 을 돌려주면 호출부가 '산출물이 비었다' =
            #   빌드 실패로 오해해 개발자 재작업 예산을 소모한다. 반드시 전파한다.
            raise
        except Exception:
            return None

    print(f" [Micro-Swarm] {num_swarm}개의 병렬 에이전트 생성 중...")
    # ★ [2026-07-27 C2] 첫 유효 결과가 나오면 나머지를 **취소**한다.
    #   기존 `asyncio.gather` 는 모든 표본이 끝날 때까지 기다렸다. 표본 하나가 이미
    #   문법 검증을 통과했는데도 다른 표본의 420초 타임아웃을 끝까지 대기하는 낭비가 있었다.
    _tasks = [asyncio.create_task(_run_single(i)) for i in range(1, num_swarm + 1)]
    results: List[Any] = []
    try:
        _pending = set(_tasks)
        while _pending:
            _done, _pending = await asyncio.wait(_pending, return_when=asyncio.FIRST_COMPLETED)
            for t in _done:
                try:
                    r = t.result()
                except QuotaExhaustedException:
                    raise
                except Exception as ex:
                    r = ex
                results.append(r)
                # 이 표본이 문법 검증까지 통과했으면 즉시 채택하고 나머지는 취소한다.
                if not isinstance(r, Exception) and _is_syntax_clean(r):
                    if _pending:
                        print(f" [Micro-Swarm] 유효 결과 확보 — 나머지 표본 {len(_pending)}개 취소")
                        for p in _pending:
                            p.cancel()
                    return r
    finally:
        for t in _tasks:
            if not t.done():
                t.cancel()

    for r in results:
        if isinstance(r, QuotaExhaustedException):
            raise r

    valid_outputs = []
    for idx, raw_out in enumerate(results):
        if isinstance(raw_out, Exception):
            continue
        out_str = _safe_str(raw_out)
        if not out_str: continue
        
        # 파일 추출 및 샌드박스(정적 문법) 검증
        files = _extract_files_from_json(out_str)
        is_valid = True
        for f in files:
            path = f.get("file_path", "")
            code = f.get("code", "")
            if path.endswith((".ts", ".tsx", ".js", ".jsx")):
                valid, _ = LocalSyntaxChecker.check_javascript_syntax(code)
                if not valid: is_valid = False; break
            elif path.endswith(".py"):
                valid, _ = LocalSyntaxChecker.check_python_syntax(code)
                if not valid: is_valid = False; break
                
        if is_valid and files:
            print(f" [Micro-Swarm] 에이전트 #{idx+1}의 코드가 컴파일 검증을 통과했습니다!")
            return raw_out # 첫 번째 성공작 즉시 반환
        else:
            if files: valid_outputs.append(raw_out)
            
    if valid_outputs:
        print("⚠️ [Micro-Swarm] 샌드박스를 완벽히 통과한 코드를 찾지 못했습니다. 베스트-에포트 결과를 반환합니다.")
        return valid_outputs[0]

    # ★ [2026-07-27] 파일이 하나도 안 나온 경우: 원인을 구분해서 올려보낸다.
    #   기존 코드는 `results[0]` 를 그대로 돌려줬는데, 그것이 예외 객체이거나 None 이면
    #   호출부에서 '빈 산출물' = 빌드 실패가 되어 **공급자 장애가 코드 결함으로 둔갑**했다.
    _gen_fail = next((r for r in results if isinstance(r, GenerationFailure)), None)
    if _gen_fail is not None:
        raise _gen_fail
    _other_exc = next((r for r in results if isinstance(r, Exception)), None)
    if _other_exc is not None:
        print(f"⚠️ [Micro-Swarm] 전 표본 실패(예외): {type(_other_exc).__name__}: {str(_other_exc)[:200]}")
        return None
    print("⚠️ [Micro-Swarm] 전 표본이 파일을 생성하지 못했습니다.")
    return results[0] if results else None


async def run_developer_fe(state: Any) -> Dict[str, Any]:
    state_obj = ProjectState.model_validate(state)
    print(" [Agent] Frontend Worker 비동기 코딩 중...")
    prompt = _load_skill(agent_skill("Frontend", "frontend_skill", template_id=state_obj.template_id)) + _INCREMENTAL_GUARD
    
    prompt += f"\n\n[참조: UI 기획/목업 설계 - 화면 개발 시 반드시 아래 UI 디자이너의 의도를 그대로 화면에 구현하십시오]\n{getattr(state_obj, 'ui_mockup_summary', '')}"
    prompt += f"\n\n[참조: 아키텍처 설계]\n{getattr(state_obj, 'architecture_summary', '')}"
    prompt += f"\n\n[참조: 기술 명세]\n{getattr(state_obj, 'tech_spec_summary', '')}"

    # 디자인 토큰 가이드 주입 - 일관된 스타일로 첫 판 품질↑(재작업↓). 안정 텍스트라 캐시 친화적.
    _ds = _load_skill("design_system")
    if _ds:
        prompt += "\n\n[디자인 시스템 가이드 - 아래 Tailwind 토큰/레시피를 그대로 사용]\n" + _ds

    _retry = getattr(state_obj, "developer_retry_count", 0)
    _is_rework = getattr(state_obj, "reviewer_decision", "") == "REWORK_DEV" or _retry > 0
    if getattr(state_obj, "reviewer_decision", "") == "REWORK_DEV":
        prompt += f"\n\n[ 재작업(Rework) 지시사항]:\n{state_obj.reviewer_feedback}"

    # [자가복구 P1] 빌드 실패 재시도라면 직전 실패 '원인'을 반드시 주입 - 미주입 시 재시도는
    # 같은 프롬프트의 재추첨일 뿐이라 같은 오류를 반복한다
    _berr = (getattr(state_obj, "build_error_log", "") or "").strip()
    if _berr:
        prompt += f"\n\n[ 직전 빌드 실패 원인 - 아래 오류를 반드시 해결한 코드를 생성하십시오]:\n{_berr}"
        prompt += _targeted_repair_instruction(_berr)
        print(f" [Frontend] 직전 빌드 오류 반영 재시도({_retry}회차): {_berr[:80]}")

    # 강제로 Pro 티어(유료) 사용
    _heavy = True
    try:
        output = await _swarm_execution(state_obj, prompt, is_heavy=_heavy, full_file_exts=_FE_OWNED_EXTS,
                                        num_swarm=_recovery_swarm_size(_is_rework, _retry),
                                        cacheable=not _is_rework)
    except GenerationFailure as gf:
        return _generation_failure_update(gf, "Frontend", state_obj)
    return {"frontend_code_summary": _safe_str(output), "build_error_log": "", "failed_node": ""}

async def run_developer_be(state: Any) -> Dict[str, Any]:
    state_obj = ProjectState.model_validate(state)
    print("⚙️ [Agent] Backend Worker 비동기 코딩 중...")
    prompt = _load_skill(agent_skill("Backend", "backend_skill", template_id=state_obj.template_id)) + _INCREMENTAL_GUARD

    prompt += f"\n\n[참조: 아키텍처 설계]\n{getattr(state_obj, 'architecture_summary', '')}"
    prompt += f"\n\n[참조: 기술 명세]\n{getattr(state_obj, 'tech_spec_summary', '')}"

    _retry = getattr(state_obj, "developer_retry_count", 0)
    _is_rework = getattr(state_obj, "reviewer_decision", "") == "REWORK_DEV" or _retry > 0
    if getattr(state_obj, "reviewer_decision", "") == "REWORK_DEV":
        prompt += f"\n\n[ 재작업(Rework) 지시사항]:\n{state_obj.reviewer_feedback}"

    # [자가복구 P1] 빌드 실패 재시도라면 직전 실패 '원인'을 반드시 주입
    _berr = (getattr(state_obj, "build_error_log", "") or "").strip()
    if _berr:
        prompt += f"\n\n[ 직전 빌드 실패 원인 - 아래 오류를 반드시 해결한 코드를 생성하십시오]:\n{_berr}"
        prompt += _targeted_repair_instruction(_berr)
        print(f" [Backend] 직전 빌드 오류 반영 재시도({_retry}회차): {_berr[:80]}")

    # 강제로 Pro 티어(유료) 사용
    _heavy = True
    try:
        output = await _swarm_execution(state_obj, prompt, is_heavy=_heavy, full_file_exts=_BE_OWNED_EXTS,
                                        num_swarm=_recovery_swarm_size(_is_rework, _retry),
                                        cacheable=not _is_rework)
    except GenerationFailure as gf:
        return _generation_failure_update(gf, "Backend", state_obj)
    return {"backend_code_summary": _safe_str(output), "build_error_log": "", "failed_node": ""}

async def run_terminal_handler(state: Any) -> Dict[str, Any]:
    """★ [2026-07-27 신설] 업무 종결 노드 — 실패를 '조용한 END' 로 흘리지 않는다.

    ⚠️ 왜 이 노드가 필요한가 (실측 결함):
      `run_code_builder` 의 롤백 분기는 `current_retry >= 3` 일 때만 도는데,
      CodeBuilder 는 retry 0/1/2 로만 진입한다 — retry=2 에서 실패하면 3 을 반환하고
      `map_builder_router` 가 `3 < 3` 거짓으로 **즉시 END** 로 보내기 때문이다.
      따라서 **롤백은 정상 실패 흐름에서 한 번도 실행된 적이 없다**(죽은 코드).
      게다가 END 로 나가면 오케스트레이터가 그것을 DONE 으로 마킹했다.

    이 노드는 다음을 한 곳에서 원자적으로 처리한다:
      1) 실패 번들 저장(재현 근거)  2) 마지막 안전 지점으로 롤백  3) 종료 상태 확정
    """
    state_obj = ProjectState.model_validate(state)
    terminal = (getattr(state_obj, "terminal_status", "") or "").strip()
    retry = getattr(state_obj, "developer_retry_count", 0)

    # 종료 상태가 없이 도달했다면(= 빌드 자가복구 소진 경로) 여기서 확정한다.
    if not terminal:
        terminal = "FAILED_BUILD"
    reason = (getattr(state_obj, "terminal_reason", "") or "").strip() \
        or f"빌드 자가복구 {retry}회 소진 — 유효한 코드로 회복하지 못했습니다."

    print(f"🏁 [종결 처리] terminal_status={terminal} / retry={retry}")
    print(f"   사유: {reason[:300]}")

    bundle_path = ""
    workspace_root = getattr(state_obj, "workspace_root", "") or ""
    # ── 1) 실패 번들: 무엇이 왜 실패했는지 사람이 재현할 수 있는 근거를 남긴다 ──
    try:
        if workspace_root:
            # ⚠️ [2026-07-27 결함] 실패 번들을 워크스페이스 안(`.failures/`)에 쓰면
            #   바로 아래의 롤백이 `git clean -fd` 로 **추적되지 않은 파일을 전부 지운다**
            #   (nodes/utils/git_manager.py:89). 즉 증거를 저장한 직후 스스로 삭제했다.
            #   실측: test_a1_v8 의 번들이 "저장 완료" 로그를 남기고도 디스크에 없었다.
            #   → 워크스페이스 **밖**(data/failures/<project>/)에 남긴다. 실패 번들은
            #     프로젝트 산출물이 아니라 진단 자료이므로 롤백 대상이 되면 안 된다.
            _pid = Path(workspace_root).name or "unknown_project"
            bundle_dir = Path("data") / "failures" / _pid
            bundle_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            task_id = getattr(state_obj, "current_sprint_task_id", "") or "unknown"
            bundle = {
                "timestamp": ts,
                "task_id": task_id,
                "terminal_status": terminal,
                "terminal_reason": reason,
                "developer_retry_count": retry,
                "supervisor_hops": getattr(state_obj, "supervisor_hops", 0),
                "failed_node": getattr(state_obj, "failed_node", ""),
                "build_error_log": (getattr(state_obj, "build_error_log", "") or "")[:8000],
                "reviewer_feedback": (getattr(state_obj, "reviewer_feedback", "") or "")[:4000],
                "frontend_files": [f.get("file_path") for f in _extract_files_from_json(state_obj.frontend_code_summary)],
                "backend_files": [f.get("file_path") for f in _extract_files_from_json(state_obj.backend_code_summary)],
                # 생성 응답 원문 — 결함 재현의 핵심 근거(모델 출력이 영속 저장되지 않아
                # 과거 구문 오류의 출처를 특정할 수 없었던 문제를 여기서 해소한다).
                "frontend_code_summary": (_safe_str(state_obj.frontend_code_summary) or "")[:60000],
                "backend_code_summary": (_safe_str(state_obj.backend_code_summary) or "")[:60000],
            }
            bundle_file = bundle_dir / f"{task_id}_{ts}.json"
            bundle_file.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
            bundle_path = str(bundle_file)
            print(f"   📦 실패 번들 저장: {bundle_path}")
    except Exception as e:
        print(f"   ⚠️ 실패 번들 저장 실패(무시하고 진행): {e}")

    # ── 2) 롤백: 실패 코드가 실물에 남지 않게 마지막 안전 지점으로 되돌린다 ──
    #    SUSPENDED_*(공급자/쿼터)는 코드가 잘못된 게 아니므로 롤백하지 않는다.
    if workspace_root and not terminal.startswith("SUSPENDED_"):
        try:
            git_mgr = GitManager(workspace_root)
            last_commit = getattr(state_obj.git_info, "last_commit_hash", None) if state_obj.git_info else None
            git_mgr.rollback_to_safe_state(last_commit)
            print(f"   ↩️ 마지막 안전 지점으로 롤백 완료 (commit={last_commit or 'HEAD'})")
        except Exception as e:
            print(f"   ⚠️ 롤백 실패(수동 확인 필요): {e}")

    return {
        "terminal_status": terminal,
        "terminal_reason": reason,
        "failure_bundle_path": bundle_path,
        "build_status": "failed",
        "factory_mode": "HOTL_PAUSED",
    }


def _build_failed(state_obj: ProjectState, node: str, error_log: str,
                  current_retry: int) -> Dict[str, Any]:
    """빌드 실패 상태 업데이트 + §10.3 계측을 **한 곳에서** 만든다.

    ⚠️ 이 함수를 만든 이유: 빌드 실패 반환지점이 6곳으로 흩어져 있어, 계측을 각각 붙이면
      한 곳을 빠뜨렸을 때 그 실패 유형만 통계에서 조용히 사라진다(이 프로젝트에서 반복된
      '배선 누락' 결함 유형). 상태 갱신과 계측을 같은 함수에 묶어 빠질 수 없게 한다."""
    try:
        from core import quality_telemetry as _qt
        _qt.record_failure(state_obj, gate_name="BUILD", artifact_type="CODE",
                           error_log=error_log or "", detail=error_log or "")
    except Exception:
        pass
    out: Dict[str, Any] = {"build_status": "failed", "failed_node": node,
                           "developer_retry_count": current_retry + 1}
    if error_log:
        out["build_error_log"] = error_log
    return out


async def run_code_builder(state: Any) -> Dict[str, Any]:
    print("️ [Headless 빌더] 파일 병합 및 원자적 디스크 저장 가동...")
    state_obj = ProjectState.model_validate(state)
    
    if not state_obj.workspace_root: raise ValueError("workspace_root 없음")

    current_retry = getattr(state_obj, "developer_retry_count", 0)
    req_agents = getattr(state_obj, "current_required_agents", [])

    # ⚠️ [2026-07-27] 여기 있던 `if current_retry >= 3: 롤백` 분기를 제거했다.
    #   그 분기는 **도달 불가능한 죽은 코드**였다: CodeBuilder 는 retry 0/1/2 로만 진입하고
    #   (retry=2 에서 실패하면 3 을 반환), `map_builder_router` 가 `3 < 3` 거짓으로
    #   곧장 빠져나가므로 retry>=3 상태로 이 노드에 들어올 일이 없었다.
    #   즉 "3회 실패 시 롤백"은 설계 의도만 있었고 한 번도 실행되지 않았다.
    #   → 롤백·실패 번들·종료 상태는 이제 `run_terminal_handler` 가 단독으로 책임진다
    #     (라우터가 상한 초과 시 TerminalHandler 로 보낸다).

    arch_files = _extract_files_from_json(state_obj.architecture_summary)
    tech_files = _extract_files_from_json(state_obj.tech_spec_summary)
    fe_files = _extract_files_from_json(state_obj.frontend_code_summary)
    be_files = _extract_files_from_json(state_obj.backend_code_summary)
    
    all_files_to_write = arch_files + tech_files + fe_files + be_files
    
    has_fe = any("frontend" in a.lower() or "프론트" in a for a in req_agents)
    has_be = any("backend" in a.lower() or "백엔드" in a for a in req_agents)

    # ★ [2026-07-27 C3] 서버 API 가 필요 없는 태스크에서 백엔드 산출물 0개를 결함으로 보지 않는다.
    #   ⚠️ 실측 결함: `skills/backend_skill.md` 는 모든 백엔드 작업에 FastAPI·DB·main.py 를
    #     강하게 요구하는데, Tech Lead 는 브라우저 내 단위 변환처럼 "서버 API 없음"으로
    #     명세할 수 있다. 이 충돌 때문에 test_a1_v4 는 **서버가 필요 없는 단위 변환기에**
    #     main.py 를 만들었고, 그 불필요한 파일이 구문 오류·스모크 실패의 표면이 됐다.
    #   → 기술명세가 '서버 API 없음'을 선언했으면 백엔드 빈 산출물은 정상이다.
    if has_be and not be_files and _tech_spec_declares_no_server_api(state_obj):
        print("ℹ️ [무결성] 기술명세가 '서버 API 없음'을 선언했으므로 백엔드 산출물 0개를 정상으로 처리합니다.")
        has_be = False

    has_coding_agent = has_fe or has_be

    #  [무결성 가드] 코딩 에이전트가 요구됐는데 '그 에이전트'의 추출 파일이 0개면(출력 절단/
    #    JSON 전량 폐기/모델 누락 의심) 다른 에이전트 산출물이 있어도 success 로 위장되지 않게
    #    명시적 실패 처리. 이를 빼면 FE 유실 + BE 성공 → success 커밋 → 다음 태스크에 FE 영구 손실.
    if has_fe and not fe_files:
        print(" [무결성] Frontend 요구됐으나 추출 파일 0개 → 빌드 실패(재작업).")
        return _build_failed(state_obj, "Frontend",
                             "프론트엔드 산출물이 비어 있습니다(출력 절단/파싱 실패 의심). 기존 코드 전부 + 신규 기능을 합쳐 전체를 다시 생성하십시오.",
                             current_retry)
    if has_be and not be_files:
        print(" [무결성] Backend 요구됐으나 추출 파일 0개 → 빌드 실패(재작업).")
        return _build_failed(state_obj, "Backend",
                             "백엔드 산출물이 비어 있습니다(출력 절단/파싱 실패 의심). 기존 코드 전부 + 신규 기능을 합쳐 전체를 다시 생성하십시오.",
                             current_retry)

    if not all_files_to_write:
        if not has_coding_agent: return {"build_status": "success", "failed_node": "", "developer_retry_count": 0}
        else:
            return _build_failed(state_obj, ("Frontend" if has_fe else "Backend"),
                                 "코딩 에이전트가 요구됐으나 기록할 파일이 하나도 추출되지 않았습니다(출력 절단/파싱 실패 의심).",
                                 current_retry)

    # 파일별 개별 검사 - 전체를 이어붙여 검사하면 뒤 파일의 `from __future__ import` 가
    # "파일 선두여야 한다" SyntaxError 를 내는 등 위양성 빌드 실패가 난다(_swarm_execution 과 동일 패턴)
    for f in be_files:
        fp = f.get("file_path", "")
        if fp.endswith(".py") and f.get("code", ""):
            is_be_valid, be_msg = LocalSyntaxChecker.check_python_syntax(f.get("code", ""))
            if not is_be_valid:
                return _build_failed(state_obj, "Backend", f"[{fp}] {be_msg}", current_retry)

    for f in fe_files:
        fp = f.get("file_path", "")
        if fp.endswith((".tsx", ".ts", ".js", ".jsx")) and f.get("code", ""):
            is_fe_valid, fe_msg = LocalSyntaxChecker.check_javascript_syntax(f.get("code", ""))
            if not is_fe_valid:
                return _build_failed(state_obj, "Frontend", f"[{fp}] {fe_msg}", current_retry)

    builder = CodeBuilder(workspace_root=state_obj.workspace_root)
    state_dict = state_obj.model_dump()

    # ★ [2026-07-27] 삭제 요청 처리 — 리팩터링/스택 전환의 필수 수단.
    #   쓰기 **전에** 지운다. 같은 회차에서 지우고 다시 만드는 경우(경로 이동)에도
    #   최종 상태가 올바르도록.
    _to_delete = (_extract_deleted_from_json(state_obj.frontend_code_summary)
                  + _extract_deleted_from_json(state_obj.backend_code_summary))
    if _to_delete:
        _keep = {str(f.get("file_path", "")).replace("\\", "/").lstrip("/") for f in all_files_to_write}
        _actually = [p for p in _to_delete
                     if str(p).replace("\\", "/").lstrip("/") not in _keep]
        if _actually:
            builder.delete_files(_actually)

    updated_state_dict, results = builder.run(state_dict, all_files_to_write)
    
    if updated_state_dict.get("build_status") == "failed":
        if not has_coding_agent: return {"build_status": "success", "developer_retry_count": 0}
        else:
            # 빌더가 남긴 오류를 그대로 계측에 넘긴다(없으면 빈 문자열 → 미분류. 지어내지 않는다).
            return _build_failed(state_obj, ("Frontend" if has_fe else "Backend"),
                                 str(updated_state_dict.get("build_error_log", "") or ""),
                                 current_retry)

    # 🔗 [추적성 엔진] WBS 목표/스코프에서 FR-ID 추출 후 산출물 파일들과 맵핑 저장
    # 추출은 공용 추출기(traceability_manager.extract_ids)로 단일화 — 표기 정규화(FR-1→FR-001)
    # 포함이라 QA 커버리지 게이트(fr_coverage)와 동일 규약으로 대조된다(정규식 SSOT).
    from nodes.utils.traceability_manager import extract_ids as _extract_trace_ids
    goal = getattr(state_obj, "goal", "") or ""
    scope = " ".join(getattr(state_obj, "scope", []) or [])
    fr_ids = _extract_trace_ids(goal + " " + scope, "FR")
    if fr_ids and all_files_to_write:
        written_files = [f.get("file_path", "") for f in all_files_to_write if f.get("file_path")]
        try:
            tm = TraceabilityManager(workspace_root=state_obj.workspace_root)
            tm.update_mapping(state_obj.current_sprint_task_id, fr_ids, written_files)
        except Exception as e:
            print(f"⚠️ [Traceability] 매핑 저장 실패: {e}")
    elif all_files_to_write and not fr_ids and _extract_trace_ids(getattr(state_obj, "prd_summary", "") or "", "FR"):
        # PRD 는 FR 체계를 쓰는데 이 태스크가 FR 을 인용하지 않음 → 매핑이 조용히 비어
        # QA fr_coverage 게이트에서 '미구현'으로 집계된다. 침묵하지 않고 원인을 표면화(경고).
        print(f"⚠️ [Traceability] 태스크 {state_obj.current_sprint_task_id} 가 FR-ID 를 인용하지 않아 "
              f"추적성 매핑이 비었습니다 — WBS goal/scope 에 FR-ID 명시 필요(QA 커버리지 감점 요인).")

    # ️ [프리뷰/회귀 정합성] frontend/backend_code_summary 를 'LLM 마지막 출력'이 아니라
    #    '디스크의 현재 전체 파일 집합'으로 재구성. 이번 태스크가 일부 파일만 재출력해도(또는 한
    #    파일을 통째로 누락해도) 과거 파일이 디스크에 남아 프리뷰에서 사라지지 않고, 회귀 게이트가
    #    전체 그림을 본다. 미수정 파일은 baseline 과 동일하므로 회귀로 오인되지 않는다.
    out: Dict[str, Any] = {"build_status": "success", "developer_retry_count": 0,
                           "file_index": updated_state_dict.get("file_index", state_obj.file_index)}
    fe_full = _collect_disk_files(state_obj.workspace_root, _FE_OWNED_EXTS)
    be_full = _collect_disk_files(state_obj.workspace_root, _BE_OWNED_EXTS)
    if fe_full:
        out["frontend_code_summary"] = json.dumps({"files": fe_full}, ensure_ascii=False)
    if be_full:
        out["backend_code_summary"] = json.dumps({"files": be_full}, ensure_ascii=False)
    return out

async def run_reviewer(state: Any) -> Dict[str, Any]:
    """Reviewer(개발 엔지니어, 단위 관점) - 코드 정확성·버그·해당 단위 기능 동작 검증 게이트.
    코드리뷰 단계의 PASS/REWORK_DEV/ESCALATE_PM 3분기 및 Git 커밋/WBS 완료 로직 보존, 단계 기준 채점 기록.
    (역할 분리: '전체 통합 정합'은 QA, '고객 RFP 수용'은 Supervisor 가 담당.)"""
    state_obj = ProjectState.model_validate(state)
    # 리뷰 왕복 카운터 - 매 리뷰 실행마다 +1 (route_from_reviewer 가 상한 초과 시 루프 차단)
    hops = getattr(state_obj, "supervisor_hops", 0) + 1

    if getattr(state_obj, "pm_override_reason", ""):
        print(f"⚖️ [Agent] Reviewer: PM의 기각/강행 지시 수용 (사유: {state_obj.pm_override_reason})")
        reviewer_decision = "PASS"
        review_text = "PM 최종 승인 지시: " + state_obj.pm_override_reason
    elif hops >= getattr(config, "GLOBAL_MAX_SUPERVISOR_HOPS", 8):
        # ══════════════════════════════════════════════════════════════════════
        # ★ [2026-07-27] best-effort PASS 제거 — 이것이 '가짜 통과'의 진원지였다
        # ══════════════════════════════════════════════════════════════════════
        # ⚠️ 기존 동작: 재작업 예산이 소진되면 `PASS` 를 강제 설정해 태스크를 DONE 으로 만들고
        #   "미해결 이슈는 상위 게이트로 이관"한다고 적어놨다. 그러나 상위 게이트(QA/Supervisor)는
        #   이 태스크가 미해결 상태로 왔다는 사실을 알 방법이 없었고, 오케스트레이터는 END 를
        #   DONE 으로 마킹했다. 결과: **미해결 결함을 안고 '완료'로 보이는 산출물.**
        #   실측(E2E-01): `재작업 상한(8) 도달 - best-effort 수용` 직후 WBS DONE.
        #   A-1 수용 기준에서 이런 통과는 증거로 쓸 수 없다.
        # → PASS 로 위장하지 않고 FAILED_REVIEW 로 종결한다. 기존 주석이 걱정한
        #   "IN_PROGRESS 방치로 QA 가 영영 안 돌아감" 문제는 종료 상태를 부여함으로써
        #   해결된다(오케스트레이터가 종결로 인식하므로 태스크가 매달리지 않는다).
        print(f"⛔ [Reviewer] 리뷰 재작업 상한({hops}) 도달 — 미해결 결함이 남아 있으므로 "
              f"FAILED_REVIEW 로 종결합니다(가짜 통과 금지).")
        _last_fb = (getattr(state_obj, "reviewer_feedback", "") or "").strip()
        return {
            "reviewer_decision": "REWORK_DEV",       # 라우터가 상한을 보고 END 로 보낸다
            "terminal_status": "FAILED_REVIEW",
            "terminal_reason": (f"리뷰 재작업 왕복 상한({hops}) 도달 — 미해결 결함이 남은 채 예산이 소진되었습니다. "
                                f"마지막 리뷰 의견: {_last_fb[:600] or '(없음)'}"),
            "supervisor_hops": hops,
            "factory_mode": "HOTL_PAUSED",
        }
    else:
        has_fe_code = bool(_extract_files_from_json(state_obj.frontend_code_summary))
        has_be_code = bool(_extract_files_from_json(state_obj.backend_code_summary))

        #  [심볼 회귀 게이트] 직전 커밋(baseline) 대비 사라진 export/핸들러/입력요소/엔드포인트를
        #    결정적으로 탐지(LLM 0콜). 모든 다른 게이트는 신규 파일만 stateless 로 보므로 '기능 삭제'를
        #    못 잡는다(삭제는 오히려 통과). 이 게이트가 멀티태스크 기능 소실의 최종 안전망.
        from nodes.utils.regression_checker import check_symbol_regression, is_deletion_intended
        _new_files = _extract_files_from_json(state_obj.frontend_code_summary) + _extract_files_from_json(state_obj.backend_code_summary)
        if _new_files:
            _hf = " ".join(getattr(fi, "feedback", "") if not isinstance(fi, dict) else fi.get("feedback", "")
                           for fi in (getattr(state_obj, "human_feedback_queue", []) or []))
            _allow_del = is_deletion_intended(" ".join([getattr(state_obj, "reviewer_feedback", "") or "",
                                                        getattr(state_obj, "pm_override_reason", "") or "", _hf]))
            _baseline_commit = getattr(getattr(state_obj, "git_info", None), "last_commit_hash", "") or ""
            _git = GitManager(state_obj.workspace_root)
            # 파일마다 git subprocess 를 도는 동기 작업 - 이벤트 루프(SSE/API) 동결 방지 위해 스레드로
            reg = await asyncio.to_thread(
                check_symbol_regression,
                _new_files,
                lambda rel: _git.read_file_at_commit(_baseline_commit, rel),
                allow_deletion=_allow_del,
            )
            if not reg.get("ok"):
                errs = reg.get("errors", [])
                print(f"❌ [Supervisor] 심볼 회귀 감지: {len(reg.get('regressions', []))}개 파일에서 기능 소실")
                review_text = (
                    " 회귀 감지 - 직전 버전에 있던 기능/심볼이 이번 출력에서 사라졌습니다:\n- "
                    + "\n- ".join(errs[:6])
                    + "\n\n[수정 지침] 컨텍스트의 '현재 워크스페이스 실제 파일'에 주어진 기존 코드 전부를 보존하고, "
                      "이번 태스크 기능만 추가/수정해 '기존 전부 + 신규'를 합친 완전한 코드를 다시 출력하십시오. "
                      "기존 기능을 의도적으로 제거해야 한다면 그 사유를 명시하십시오."
                )
                cr_scores = dict(getattr(state_obj, "stage_scores", {}) or {})
                cr_scores["CODE_REVIEW"] = 0.0
                cr_log = list(getattr(state_obj, "criteria_log", []) or [])
                cr_log.append({"stage": "CODE_REVIEW", "score": 0.0, "verdict": "REWORK_DEV", "blocking_fails": ["symbol_regression"]})
                return {
                    "reviewer_decision": "REWORK_DEV",
                    "reviewer_feedback": review_text,
                    "pm_override_reason": "",
                    "needs_revision": False,
                    "current_stage": "CODE_REVIEW",
                    "stage_scores": cr_scores,
                    "criteria_log": cr_log,
                    "supervisor_feedback": review_text,
                    "supervisor_hops": hops,
                }

        # 🧮 [FinOps 리스크 분석기] 변경분 정적 위험도 산출(LLM 0콜) — baseline(직전 커밋) 대비.
        #    LOW 는 아래에서 '자유 판단 LLM 리뷰' 1콜을 생략(자동 승인)하고, HIGH 는 정밀 검토
        #    지시를 주입한다. 회귀/렌더/입력/품질/스모크 등 결정론 게이트는 그대로 전부 수행.
        risk = None
        if _new_files:
            from core.risk_analyzer import assess_changes
            _risk_git = GitManager(state_obj.workspace_root)
            _risk_base = getattr(getattr(state_obj, "git_info", None), "last_commit_hash", "") or ""
            risk = assess_changes(_new_files, read_old=lambda rel: _risk_git.read_file_at_commit(_risk_base, rel))
            print(f"🧮 [Risk Analyzer] 변경 위험도: {risk['level']} — {risk['summary']} (변경 {risk['changed']}개 파일)")

        # ️ 프론트 렌더 검증 테스트러너: 실제 renderToString 으로 동작 확인 (실패 시 LLM 리뷰 없이 즉시 재작업)
        render_note = ""
        quality_advisory = ""  # 정적 품질 백스톱 권고(하드 차단 아님) - LLM 리뷰어 프롬프트에 주입
        if has_fe_code:
            from nodes.utils.render_checker import check_frontend_render
            # ★ [2026-07-27] 마지막 LLM 출력이 아니라 **디스크의 현재 전체 파일 집합**을 검증한다.
            #   ① 정밀 복구(C2)로 일부 파일만 재출력되면, LLM 출력만 보는 검증은 나머지 모듈을
            #      찾지 못해 '미해결 상대 모듈' 거짓 실패를 낸다.
            #   ② 실제로 배포되는 것은 디스크의 파일 집합이지 마지막 응답이 아니다.
            fe_files = _collect_disk_files(state_obj.workspace_root, _FE_OWNED_EXTS) \
                or _extract_files_from_json(state_obj.frontend_code_summary)
            # 최대 60초 동기 subprocess - 이벤트 루프 동결 방지 위해 스레드로
            render = await asyncio.to_thread(check_frontend_render, fe_files)
            if not render.get("ok") and not render.get("skipped"):
                errs = render.get("errors", [])
                print(f"❌ [TestRunner] 프론트 렌더 검증 실패: {errs}")
                # [2026-07-26] 지시 구체화 — 과거엔 "외부 import / null 안전성" 일반 문구뿐이어서
                #   가장 흔한 실패인 '미해결 상대 모듈'에 맞는 해결책을 알려주지 못했다. 그 결과
                #   재작업마다 같은 import 를 다시 넣어 고쳤다 되돌리기를 반복했다(실측).
                #   → 누락 파일명을 뽑아 **두 가지 선택지를 명시**한다.
                _missing = re.findall(r'미해결 상대 모듈 import:\s*"([^"]+)"', " ".join(errs))
                _fix_hint = ""
                if _missing:
                    _uniq = list(dict.fromkeys(_missing))
                    _fix_hint = (
                        "\n\n[🚨 미해결 import 해결법 — 반드시 둘 중 하나를 택하라]\n"
                        f"존재하지 않는 파일을 import 하고 있다: {', '.join(_uniq)}\n"
                        "  (1) 해당 파일을 **이번 응답의 files 배열에 함께 생성**한다(내용을 실제로 작성).\n"
                        "  (2) 그 import 문을 **삭제**한다(예: CSS 는 없어도 동작하므로 삭제가 더 간단).\n"
                        "⚠️ 이전 회차에서 이미 이 오류를 고쳤다면, 전체 파일을 다시 출력할 때 "
                        "**그 수정을 되돌리지 말 것.** 같은 import 를 다시 넣으면 즉시 재작업 처리된다."
                    )
                review_text = (
                    "️ 프론트엔드 렌더 검증 실패 - 생성 코드가 실제로 렌더되지 않습니다:\n- "
                    + "\n- ".join(errs[:5])
                    + "\n\n위 오류(특히 허용되지 않은 외부 import / null 안전성)를 수정해 다시 작성하십시오."
                    + _fix_hint
                )
                reviewer_decision = "REWORK_DEV"
                # 렌더 실패는 결정적 결함 → LLM 리뷰 생략하고 재작업 루프로 직행
                workspace_root = state_obj.workspace_root
                cr_scores = dict(getattr(state_obj, "stage_scores", {}) or {})
                cr_scores["CODE_REVIEW"] = 0.0
                cr_log = list(getattr(state_obj, "criteria_log", []) or [])
                cr_log.append({"stage": "CODE_REVIEW", "score": 0.0, "verdict": "REWORK_DEV", "blocking_fails": ["frontend_render"]})
                return {
                    "reviewer_decision": "REWORK_DEV",
                    "reviewer_feedback": review_text,
                    "pm_override_reason": "",
                    "needs_revision": False,
                    "current_stage": "CODE_REVIEW",
                    "stage_scores": cr_scores,
                    "criteria_log": cr_log,
                    "supervisor_feedback": review_text,
                    "supervisor_hops": hops,
                }
            elif render.get("ok") and not render.get("skipped"):
                render_note += f"\n([OK] 프론트 렌더 검증 통과 - renderToString {render.get('rendered', 0)}자)"

            # ⌨️ 입력 동작(인터랙티비티) 정적 검증: value 제어 input 에 onChange 누락 = 입력 불가(동결)
            #    renderToString 은 '렌더됨'만 보장하고 '입력됨'은 못 잡으므로 별도 정적 분석으로 차단.
            from nodes.utils.interactivity_checker import check_frontend_interactivity
            interact = check_frontend_interactivity(fe_files)
            if not interact.get("ok"):
                errs = interact.get("errors", [])
                n_frozen = len(interact.get("frozen", []))
                print(f"❌ [TestRunner] 프론트 입력 동작 검증 실패: 동결 입력 {n_frozen}건")
                review_text = (
                    "⌨️ 프론트엔드 입력 동작 검증 실패 - 사용자가 값을 입력할 수 없는 '동결된 입력 필드'가 있습니다:\n- "
                    + "\n- ".join(errs[:5])
                    + "\n\n[수정 지침] 제어 컴포넌트(value={...})에는 반드시 onChange 핸들러와 useState 를 연결하십시오. "
                      "표시 전용 필드라면 readOnly 를 명시하고, 비제어 입력이면 value 대신 defaultValue 를 사용하십시오."
                )
                cr_scores = dict(getattr(state_obj, "stage_scores", {}) or {})
                cr_scores["CODE_REVIEW"] = 0.0
                cr_log = list(getattr(state_obj, "criteria_log", []) or [])
                cr_log.append({"stage": "CODE_REVIEW", "score": 0.0, "verdict": "REWORK_DEV", "blocking_fails": ["frontend_interactivity"]})
                return {
                    "reviewer_decision": "REWORK_DEV",
                    "reviewer_feedback": review_text,
                    "pm_override_reason": "",
                    "needs_revision": False,
                    "current_stage": "CODE_REVIEW",
                    "stage_scores": cr_scores,
                    "criteria_log": cr_log,
                    "supervisor_feedback": review_text,
                    "supervisor_hops": hops,
                }
            else:
                render_note += "\n([OK] 입력 동작 검증 통과 - 제어 입력에 onChange 연결 확인)"

            #  정적 품질 백스톱(Phase 2): 컴포넌트 분리/빈상태/디자인토큰 - 하드 차단이 아니라
            #    권고로 LLM 리뷰어 판단에 주입(오탐 재작업 폭증 방지). frontend_skill/design_system 가
            #    1차 규율, 이 검사기는 그 규율이 무너진 경우를 잡는 백스톱.
            from nodes.utils.quality_checker import check_code_quality
            quality = check_code_quality(fe_files)
            if not quality.get("ok") and not quality.get("skipped"):
                _qw = quality.get("warnings", [])
                quality_advisory = "\n".join(f"- {w}" for w in _qw[:6])
                print(f"⚠️ [QualityCheck] 정적 품질 권고 {len(_qw)}건 (리뷰 판단에 반영)")
                render_note += f"\n(⚠️ 정적 품질 권고 {len(_qw)}건 - 컴포넌트 분리/빈상태/디자인토큰)"
            else:
                render_note += "\n([OK] 정적 품질 점검 통과 - 컴포넌트 분리/빈상태/디자인토큰)"

        # ⚙️ 백엔드 스모크 테스트러너: 격리 부팅 + 엔드포인트 검증 (실패 시 즉시 재작업)
        if has_be_code:
            from nodes.utils.backend_smoke import check_backend_smoke
            # ★ [2026-07-27] 위 렌더 검증과 같은 이유로 디스크의 현재 전체 파일 집합을 검증한다.
            be_files = _collect_disk_files(state_obj.workspace_root, _BE_OWNED_EXTS) \
                or _extract_files_from_json(state_obj.backend_code_summary)
            # 최대 45초 동기 subprocess(격리 부팅) - 이벤트 루프 동결 방지 위해 스레드로
            smoke = await asyncio.to_thread(check_backend_smoke, be_files)
            if not smoke.get("ok") and not smoke.get("skipped"):
                errs = smoke.get("errors", [])
                print(f"❌ [TestRunner] 백엔드 스모크 실패: {errs}")
                review_text = (
                    "⚙️ 백엔드 스모크 실패 - 생성 코드가 정상 부팅/응답하지 않습니다:\n- "
                    + "\n- ".join(errs[:5])
                    + "\n\n위 오류(부팅 크래시 / 내부 모듈 import 누락 / 엔드포인트 5xx 등)를 수정해 다시 작성하십시오."
                )
                cr_scores = dict(getattr(state_obj, "stage_scores", {}) or {})
                cr_scores["CODE_REVIEW"] = 0.0
                cr_log = list(getattr(state_obj, "criteria_log", []) or [])
                cr_log.append({"stage": "CODE_REVIEW", "score": 0.0, "verdict": "REWORK_DEV", "blocking_fails": ["backend_smoke"]})
                return {
                    "reviewer_decision": "REWORK_DEV",
                    "reviewer_feedback": review_text,
                    "pm_override_reason": "",
                    "needs_revision": False,
                    "current_stage": "CODE_REVIEW",
                    "stage_scores": cr_scores,
                    "criteria_log": cr_log,
                    "supervisor_feedback": review_text,
                    "supervisor_hops": hops,
                }
            elif smoke.get("ok") and not smoke.get("skipped"):
                _w = smoke.get("warnings", [])
                render_note += f"\n([OK] 백엔드 스모크 통과 - 라우트 {smoke.get('routes', 0)}개" + (f", 경고 {len(_w)}건" if _w else "") + ")"

        if not has_fe_code and not has_be_code:
            print("⏩ [Smart Bypass] 코드 작성 내역이 없으므로 리뷰를 통과(PASS)합니다.")
            reviewer_decision = "PASS"
            review_text = "코드 작성 없음 - 설계/문서 업데이트 정상 완료."
        elif risk and risk["level"] == "LOW" and getattr(state_obj, "reviewer_decision", "") != "REWORK_DEV":
            # 🧮 [FinOps 자동 승인] 저위험 변경(스타일/문서/변경 없음)은 LLM 리뷰 생략 —
            # 결정론 게이트(회귀/렌더/입력/품질/스모크)는 위에서 이미 전부 통과한 상태라 안전하다.
            # 단 재작업 회차(직전 판정 REWORK_DEV)는 '수정이 됐는지'의 검증이 목적이므로 생략하지 않는다.
            from core.risk_analyzer import format_risk_report
            print("⏩ [Risk Analyzer] 저위험 변경 - LLM 리뷰 생략, 정적 분석 자동 승인(쿼터 절감).")
            reviewer_decision = "PASS"
            review_text = "🧮 정적 리스크 분석 자동 승인 - 저위험(스타일/문서 수준) 변경.\n" + format_risk_report(risk)
        else:
            print(f" [Agent] Reviewer 비동기 코드 리뷰 및 의사결정 분류 중...{render_note}")
            prompt = (
                "당신은 **사용자를 대리해 수용 테스트**를 수행합니다. 요구사항 정의서 기준으로 "
                "**기능이 있는가/없는가, 되는가/안되는가**만 판정하십시오.\n"
                "⚠️ 코드 품질(가독성·구조·네이밍·타입·성능·테스트 부재)로는 반려하지 마십시오 — "
                "그것은 다음 단계 QA 의 몫입니다. **동작하는데 마음에 안 드는 것은 통과**시키고 "
                "개선 의견만 feedback 에 남기십시오.\n\n"
                "다음 3가지 중 하나의 의사결정(decision)을 선택하십시오.\n"
                "1. `PASS`: 문제가 없거나 사소한 오타 수준일 때. 릴리즈 노트 작성.\n"
                "2. `REWORK_DEV`: 구현 누락, 버그, 설계 위반 등 실무진(Tech Lead, 개발자) 선에서 재작업이 필요할 때. 피드백 작성.\n"
                "3. `ESCALATE_PM`: 기획서 자체의 논리적 모순이나 비즈니스 요구사항 위배로 PM의 최종 의사결정이 필요할 때. 피드백 작성.\n\n"
                "응답은 반드시 아래 JSON 포맷을 준수하십시오:\n"
                "\x60\x60\x60json\n"
                "{\n"
                "  \"decision\": \"PASS\",\n"
                "  \"feedback\": \"리뷰 내용 또는 결함/기획 모순 내역\"\n"
                "}\n"
                "\x60\x60\x60"
            )

            # ══════════════════════════════════════════════════════════════════
            # ★ [2026-07-27] 리뷰어에게 **실제 코드**를 준다
            # ══════════════════════════════════════════════════════════════════
            # ⚠️ 실측 결함: 프롬프트는 "현재 작성된 모든 코드를 리뷰하라"고 지시하면서
            #   **코드를 한 줄도 주지 않았다.** 리뷰어는 컨텍스트에 들어온 기술명세·아키텍처를
            #   보고 판단했고, 그래서 **명세에만 존재하고 실제로는 생성되지 않은 파일**을 근거로
            #   반려했다.
            #   실측(test_a1_v8): 워크스페이스에 `src/App.tsx` 하나뿐인데 리뷰어는
            #     "제공된 index.html 에 src/js/main.js 스크립트 태그가 없다" 며 8회 연속 반려.
            #     index.html·main.js 는 **존재한 적이 없는 파일**이다. 개발자는 있지도 않은
            #     파일을 고칠 수 없으니 재작업이 영원히 수렴하지 않는다.
            #   → 디스크의 실제 파일 집합을 명시적으로 주입한다. 리뷰 대상은 '명세'가 아니라
            #     '실제 산출물'이며, 명세와의 괴리 자체가 리뷰어가 판단할 사항이다.
            # ══════════════════════════════════════════════════════════════════
            # ★ [2026-07-27] 리뷰어에게 **자기 이전 판정 이력**을 돌려준다
            # ══════════════════════════════════════════════════════════════════
            # ⚠️ 실측 결함: 리뷰어 노드가 `supervisor_hops` 를 세기만 하고 프롬프트에는 넣지
            #   않아, 매 회차가 **무상태**였다. 같은 결함을 보고 같은 REWORK_DEV 를 반복했고
            #   "내가 이미 N번 같은 말을 했다"는 정보가 없으니 판단이 바뀔 이유가 없었다.
            #   그 결과 상한(8)까지 소진하고 FAILED_REVIEW 로 죽었다.
            #   설계상 `ESCALATE_PM` 경로가 존재하는데(라우터 → Master_PM) **발동 조건이
            #   없어서** 한 번도 쓰이지 않았다. QA·Supervisor 는 리뷰어가 PASS 해야만 실행되므로
            #   리뷰어에서 막히면 그 위의 에스컬레이션 사다리에 **도달 자체가 불가능**하다.
            _hist = list(getattr(state_obj, "rework_history", []) or [])
            if _hist:
                _recent = _hist[-4:]
                prompt += (
                    f"\n\n[⏳ 당신의 이전 판정 이력 — 이번이 {hops}번째 검토입니다 "
                    f"(상한 {getattr(config, 'GLOBAL_MAX_SUPERVISOR_HOPS', 8)})]\n"
                    + "\n".join(f"  {i}회차: {t[:300]}" for i, t in
                                enumerate(_recent, start=max(1, len(_hist) - len(_recent) + 1)))
                    + "\n\n⚠️ **같은 지적을 반복하지 마십시오.** 위와 동일한 문제가 여전히 남아 있다면, "
                      "그것은 개발자가 게을러서가 아니라 **그 지시를 수행할 수 없기 때문**일 가능성이 큽니다"
                      "(예: 시스템이 제공하지 않는 동작 요구, 기획/설계 자체의 모순, 상충하는 요구사항).\n"
                      "그런 경우 `REWORK_DEV` 를 반복하지 말고 **`ESCALATE_PM`** 을 선택해 "
                      "PM 이 기획·설계 수준에서 조정하도록 상신하십시오. 무엇이 왜 수행 불가능해 보이는지 "
                      "feedback 에 구체적으로 쓰십시오."
                )

            # ★ [2026-07-27] 판정 기준(요구사항 정의서)을 명시적으로 준다.
            #   기준 없이 "빠짐없이 구현됐는가"를 물으면 리뷰어가 자기 취향으로 판단하게 된다.
            #   이 단계는 사용자 수용 테스트 대리이므로, **PRD 의 기능 요구와 이번 태스크의
            #   범위**가 판정의 유일한 잣대다.
            _prd = _safe_str(getattr(state_obj, "prd_summary", "") or "")
            _task_scope = ""
            try:
                _wbs_tasks = (WBSManager(workspace_root=state_obj.workspace_root).get_wbs() or {}).get("tasks") or []
                _cur = next((t for t in _wbs_tasks
                             if t.get("task_id") == getattr(state_obj, "current_sprint_task_id", "")), None)
                if _cur:
                    _task_scope = (f"태스크 {_cur.get('task_id')}: {_cur.get('title', '')}\n"
                                   f"목표: {_cur.get('goal', '')}\n범위: {_cur.get('scope', '')}")
            except Exception:
                pass
            if _prd or _task_scope:
                prompt += "\n\n[📋 판정 기준 — 이 요구사항만이 통과/반려의 잣대입니다]\n"
                if _task_scope:
                    prompt += f"\n▶ 이번 태스크가 담당한 범위(이 범위만 판정하십시오):\n{_task_scope}\n"
                if _prd:
                    prompt += f"\n▶ 요구사항 정의서(PRD):\n{_prd[:12000]}\n"
                prompt += ("\n각 기능 요구(FR)에 대해 **있다/없다**, 있다면 **된다/안된다**를 확인하고, "
                           "미충족 항목만 feedback 에 나열하십시오. "
                           "이번 태스크 범위 밖의 요구는 판정 대상이 아닙니다.\n")

            _rv_fe = _collect_disk_files(state_obj.workspace_root, _FE_OWNED_EXTS)
            _rv_be = _collect_disk_files(state_obj.workspace_root, _BE_OWNED_EXTS)
            _rv_files = _rv_fe + _rv_be
            if _rv_files:
                _budget = getattr(config, "REVIEWER_CODE_BUDGET_CHARS", 60000)
                _parts, _used = [], 0
                for _f in _rv_files:
                    _fp, _code = _f.get("file_path", "?"), (_f.get("code") or "")
                    if _used + len(_code) > _budget:
                        _parts.append(f"\n----- {_fp} (이하 생략: 리뷰 예산 초과) -----\n{_code[:1500]}")
                        _used = _budget
                        continue
                    _parts.append(f"\n----- {_fp} -----\n{_code}")
                    _used += len(_code)
                prompt += (
                    "\n\n[🔍 리뷰 대상 — 워크스페이스의 실제 파일 전체]\n"
                    f"아래 {len(_rv_files)}개 파일이 **현재 디스크에 실제로 존재하는 산출물의 전부**입니다.\n"
                    "⚠️ 여기에 없는 파일은 **존재하지 않습니다.** 기술명세에 언급됐더라도 아래 목록에 없으면 "
                    "생성되지 않은 것이며, 그 파일의 내용을 가정하거나 그 파일을 근거로 반려하지 마십시오.\n"
                    "누락이 문제라고 판단되면 '어떤 파일이 없다'가 아니라 **'어떤 기능이 구현되지 않았다'**로 "
                    "지적하고, 개발자가 실제로 손댈 수 있는 파일을 지목하십시오.\n"
                    f"파일 목록: {[f.get('file_path') for f in _rv_files]}\n"
                    + "".join(_parts)
                )
            else:
                prompt += ("\n\n[🔍 리뷰 대상] 워크스페이스에 산출물 파일이 없습니다. "
                           "이 경우 구현 누락으로 판단하십시오.")
            # 정적 품질 백스톱 권고를 리뷰 판단에 주입 - 단, 기능 동작에 지장 없는 사소한 권고만으로는
            # REWORK_DEV 를 남발하지 말 것(재작업 비용 통제). 명백한 분리 결여/디자인 난맥만 반영.
            if quality_advisory:
                prompt += (
                    "\n\n[정적 품질 점검 권고 - 아래를 리뷰에 참고하라. 기능 동작은 정상이나 품질 개선 여지가 있는 항목이다.\n"
                    " 심각한 분리 결여/디자인 난맥이면 REWORK_DEV 사유로 포함하되, 사소한 권고만이라면 PASS 해도 된다]\n"
                    + quality_advisory
                )
            # 🚨 [FinOps 고위험 주입] 스키마/API/의존성/인증 변경은 파급이 크므로 정밀 검토를 지시
            if risk and risk["level"] == "HIGH":
                from core.risk_analyzer import format_risk_report
                prompt += (
                    "\n\n[🚨 정적 리스크 분석 - 고위험 변경 감지. 아래 파일들을 특히 정밀 검토하라.\n"
                    " 스키마/API/의존성/인증 변경이 기획서·설계서와 부합하는지 확인하고, 의심스러우면\n"
                    " PASS 대신 REWORK_DEV 로 구체적 수정 지시를 내릴 것]\n"
                    + format_risk_report(risk)
                )
            #  FIX: 리뷰어 역시 빠르고 비용 효율적인 Flash 모델로 롤백 (자유 스키마 JSON 모드)
            # ⚠️ [2026-07-26 결함 #19] cacheable=False 필수 — 결함 #13 과 같은 계열의 재발.
            #   재작업으로 코드를 개선해도 리뷰어 프롬프트가 이전 회차와 동일해지는 순간
            #   **캐시된 옛 판정(REWORK_DEV)이 재생**되어 개선이 반영되지 않는다.
            #   그 결과 supervisor_hops 가 상한(8)까지 오르고 CODE_REVIEW 점수는 0.0 에 고정된 채
            #   'best-effort 수용' 으로 미해결 결함을 안고 통과한다(실측: hops 1→2→3, 점수 0.0 고정,
            #   같은 해시 3d744629 반복 히트).
            #   심사(judge)·검수 성격의 호출은 **매번 새로 판단해야** 하므로 캐시 대상이 아니다.
            output = await gateway.aexecute(state_obj, prompt, is_heavy=True, output_mode="json",
                                            cacheable=False)
            output_str = _safe_str(output)
            
            reviewer_decision = "PASS"
            review_text = output_str
            try:
                clean_str = output_str.strip()
                # 1차: 게이트웨이가 이미 복구한 JSON 일 가능성이 높으므로 전체 파싱을 먼저 시도
                try:
                    data = json.loads(clean_str)
                except Exception:
                    # 2차: 코드펜스/서술 혼입 시 추출 - 반드시 greedy(*). non-greedy(*?)는 feedback 안의
                    # 첫 '}' 에서 잘려 파싱이 깨지고, except 폴백이 REWORK 를 PASS 로 둔갑시킨다
                    md_match = re.search(r'\x60{3}(?:json)?\s*(\{[\s\S]*\})\s*\x60{3}', clean_str)
                    if md_match: clean_str = md_match.group(1)
                    else:
                        alt_match = re.search(r'(\{[\s\S]*\})', clean_str)
                        if alt_match: clean_str = alt_match.group(1)
                    data = json.loads(clean_str)
                reviewer_decision = data.get("decision", "PASS")
                review_text = data.get("feedback", "")
            except Exception as e:
                print(f"⚠️ Reviewer JSON 파싱 실패 (기본 통과 처리): {e}")

    # ══════════════════════════════════════════════════════════════════════════
    # ★ [2026-07-27] 반복 지적 자동 승격 — LLM 의 자각에만 맡기지 않는다
    # ══════════════════════════════════════════════════════════════════════════
    # ⚠️ 위에서 프롬프트로 "반복하지 말고 상신하라"고 안내했지만, 그것만으로는 보장되지 않는다.
    #   같은 지적이 반복된다는 것은 **개발자가 그 지시를 수행할 수 없다**는 신호다
    #   (실측: 시스템에 파일 삭제 기능이 없는데 "삭제하라"를 8회 반복했다).
    #   그 경우 재작업을 더 돌리는 것은 예산 낭비이므로, 기획·설계 권한을 가진 PM 으로
    #   **결정론적으로** 승격한다. 이것이 없으면 상한까지 소진하고 그냥 죽는다.
    _rework_hist = list(getattr(state_obj, "rework_history", []) or [])
    if reviewer_decision == "REWORK_DEV" and review_text:
        _norm = re.sub(r'\s+', ' ', str(review_text)).strip().lower()[:200]
        _repeats = sum(1 for h in _rework_hist
                       if re.sub(r'\s+', ' ', str(h)).strip().lower()[:200] == _norm)
        _limit = getattr(config, "REPEAT_FEEDBACK_ESCALATE_AFTER", 2)
        if _repeats >= _limit:
            print(f"⬆️ [Reviewer] 동일 지적 {_repeats + 1}회 반복 감지 — 개발자가 수행할 수 없는 "
                  f"지시일 가능성이 큽니다. PM 으로 자동 상신(ESCALATE_PM)합니다.")
            reviewer_decision = "ESCALATE_PM"
            review_text = (
                f"[자동 상신] 아래 지적이 {_repeats + 1}회 반복되었으나 해소되지 않았습니다. "
                f"실무 재작업으로는 수렴하지 않으므로 기획·설계 수준의 조정이 필요합니다.\n"
                f"반복된 지적: {review_text}\n"
                f"검토 요청: (1) 이 요구가 현재 시스템에서 **수행 가능한지** "
                f"(2) 기술명세·아키텍처에 상충이 없는지 (3) 요구를 조정하거나 태스크를 분할할지."
            )
        _rework_hist.append(str(review_text)[:1000])
        _rework_hist = _rework_hist[-8:]

    workspace_root = state_obj.workspace_root
    task_id = state_obj.current_sprint_task_id
    state_dict = state_obj.model_dump()
    git_info_dict = getattr(state_obj, "git_info", None)
    if hasattr(git_info_dict, "model_dump"): git_info_dict = git_info_dict.model_dump()
    elif not git_info_dict: git_info_dict = {}

    # Supervisor: 코드리뷰 단계 기준 채점 기록 (빌드 성공 여부 = deterministic)
    cr_score = 1.0 if (getattr(state_obj, "build_status", "pending") == "success" and reviewer_decision == "PASS") else 0.0
    cr_scores = dict(getattr(state_obj, "stage_scores", {}) or {})
    cr_scores["CODE_REVIEW"] = cr_score
    cr_log = list(getattr(state_obj, "criteria_log", []) or [])
    cr_log.append({
        "stage": "CODE_REVIEW",
        "score": cr_score,
        "verdict": reviewer_decision,
        "blocking_fails": [] if reviewer_decision == "PASS" else ["code_review"],
    })

    if reviewer_decision != "PASS":
        print(f"❌ [Supervisor] 결함 감지! 분류: {reviewer_decision}")
        return {
            "reviewer_decision": reviewer_decision,
            "reviewer_feedback": review_text,
            # 다음 회차 리뷰어가 '내가 이미 무슨 말을 했는지' 알 수 있도록 이력을 남긴다.
            "rework_history": _rework_hist,
            "pm_override_reason": "",
            "needs_revision": False,
            "current_stage": "CODE_REVIEW",
            "stage_scores": cr_scores,
            "criteria_log": cr_log,
            "supervisor_feedback": review_text,
            "supervisor_hops": hops,
        }

    if getattr(state_obj, "build_status", "pending") == "success":
        git_mgr = GitManager(workspace_root)
        commit_hash = git_mgr.commit_sprint_changes(task_id, state_dict)
        if commit_hash:
            git_info_dict["last_commit_hash"] = commit_hash
            git_info_dict["last_commit_task"] = task_id

        wbs_path = os.path.join(workspace_root, "00_wbs_master_plan.json")
        if os.path.exists(wbs_path):
            pass # (수정) 성급한 DONE 마킹 제거 - 파이프라인(END) 도달 시 Orchestrator가 처리하도록 위임
    
    return {
        "code_review_report_summary": review_text,
        "reviewer_decision": "PASS",
        "reviewer_feedback": "",
        "pm_override_reason": "",
        "needs_revision": False,
        "git_info": git_info_dict,
        "current_stage": "CODE_REVIEW",
        "stage_scores": cr_scores,
        "criteria_log": cr_log,
        "supervisor_feedback": "",
        "supervisor_hops": hops,
    }


# 하위 호환 별칭: 기존 import(run_supervisor)를 깨지 않도록 - 이제 run_supervisor 는 '고객사 수용검수' 노드(아래 정의).
# (구 run_reviewer 별칭 사용처는 run_reviewer 로 통일됨.)


def _format_gate_report(title: str, result: Dict[str, Any]) -> str:
    """score_stage 결과를 사람이 읽는 검수 리포트(마크다운)로 정리."""
    lines = [f"## {title}", f"- 판정: {result.get('verdict')} · 점수 {result.get('score')}"]
    per = result.get("per_check", {}) or {}
    if per:
        # ★ [2026-07-27] 관문 항목과 '보고 전용(참고)' 항목을 구분해 표기한다.
        #   구분이 없으면 다음 단계(Supervisor·고객)가 참고 항목의 낮은 점수를 결함으로 오인해
        #   다시 반려하게 된다 — QA 에서 뺀 병목이 뒤에서 부활하는 경로다.
        from criteria import STAGE_RUBRICS as _RUB
        _key = next((k for k in _RUB if k.lower() in title.lower() or title.startswith(k)), None)
        _adv = set()
        if _key:
            _adv = {c["id"] for c in _RUB[_key].get("checks", []) if c.get("advisory")}
        _gate = {k: v for k, v in per.items() if k not in _adv}
        _info = {k: v for k, v in per.items() if k in _adv}
        if _gate:
            lines.append("- 기준별 점수(관문 — 통과/반려 판정에 반영):")
            for k, v in _gate.items():
                lines.append(f"  - {'[OK]' if v >= 0.5 else '❌'} {k}: {v}")
        if _info:
            lines.append("- 개선 권고(참고 — **반려 사유가 아님**. 판단 재료로만 제공):")
            for k, v in _info.items():
                lines.append(f"  - {'[양호]' if v >= 0.5 else '[개선여지]'} {k}: {v}")
    if result.get("blocking_fails"):
        lines.append(f"-  치명 미달: {', '.join(result['blocking_fails'])}")
    if result.get("rationale"):
        lines.append(f"- 총평: {result['rationale']}")
    return "\n".join(lines)


async def run_qa(state: Any) -> Dict[str, Any]:
    """QA(수행사 인도 전 통합 검수) - 기획서·설계서 대비 통합 구현 정합/인도 적합성 평가.
    PASS → Supervisor(고객 수용검수), FAIL → Tech_Lead 재작업. (RFP 비즈니스 수용은 Supervisor 담당.)"""
    state_obj = ProjectState.model_validate(state)
    print(" [Agent] QA 통합 검수(설계서 대비) 진행 중...")
    if state_obj.build_status == "failed":
        report = f"## QA 통합 검수\n- 판정: FAIL (빌드 실패)\n- 에러:\n{state_obj.build_error_log}"
        print(" [QA] 판정: FAIL (빌드 실패)")
        return {"qa_report_summary": report, "qa_verdict": "FAIL", "current_stage": "QA",
                "reviewer_decision": "REWORK_DEV", "reviewer_feedback": report}

    from nodes.utils.scoring import score_stage
    from nodes.utils.test_runner import run_background_tests_and_scans, format_test_results_for_qa
    
    #  [Phase 2] 백그라운드 자동화 테스트 및 스캔 실행
    print("⏳ [QA] 백그라운드 자동화 테스트 및 보안 스캔 실행 중...")
    # pytest/bandit/npm build 등 최대 ~2분 동기 subprocess - 이벤트 루프 동결 방지 위해 스레드로
    test_results = await asyncio.to_thread(run_background_tests_and_scans, state_obj.workspace_root)
    test_report_md = format_test_results_for_qa(test_results)
    if test_report_md:
        print(" [QA] 결정론적 테스트 지표 확보 완료.")

    result = await score_stage(state_obj, "QA", extra_context=test_report_md)
    verdict = "PASS" if result.get("verdict") == "PASS" else "FAIL"
    report = _format_gate_report("QA 통합 검수(기획서·설계서 대비)", result)
    if test_report_md:
        report += f"\n\n{test_report_md}"
        
    print(f" [QA] 판정: {verdict} (점수 {result.get('score')})")
    updates = {"qa_report_summary": report, "qa_verdict": verdict, "current_stage": "QA"}
    if verdict == "FAIL":
        # 설계대로 미구현/통합 결함 → 실무진 재작업(REWORK_DEV→Tech_Lead). 미흡 내역을 피드백으로 전달.
        updates["reviewer_decision"] = "REWORK_DEV"
        updates["reviewer_feedback"] = " [QA 통합 검수 미달 - 설계/통합 결함]\n" + report
    return updates


async def run_supervisor(state: Any) -> Dict[str, Any]:
    """Supervisor(발주 고객사 대리인) - RFP 계약 대비 비즈니스 수용·완료 검수(엄격).
    PASS → ManualWriter, REJECT → PM(ESCALATE_PM, 요구·기능 재조정). route_from_supervisor 가 분기.
    보수적 상한: 수용 시도 2회 초과 시 무한 루프 대신 종료(인간 검토)."""
    state_obj = ProjectState.model_validate(state)
    print("‍⚖️ [Agent] Supervisor 최종 수용검수(RFP 대비) 진행 중...")
    attempts = dict(getattr(state_obj, "stage_attempt_counts", {}) or {})
    attempts["SUPERVISOR"] = attempts.get("SUPERVISOR", 0) + 1

    if state_obj.build_status == "failed":
        report = "## 고객사 수용검수\n- 판정: REJECT (빌드 실패로 인도 불가)"
        return {"supervisor_report_summary": report, "supervisor_verdict": "REJECT",
                "current_stage": "SUPERVISOR", "stage_attempt_counts": attempts}

    from nodes.utils.scoring import score_stage
    from nodes.utils.traceability_manager import read_mappings, build_coverage_report
    # 🔗 [G1 수용검수 근거] 요구 추적성 현황(REQ↔FR↔태스크↔파일, 결정론 집계)을 심판 컨텍스트에
    # 주입 — Supervisor 가 '감'이 아니라 표를 근거로 rfp_business_coverage 를 판정하게 한다.
    trace_md = build_coverage_report(
        getattr(state_obj, "rfp_summary", "") or "",
        getattr(state_obj, "prd_summary", "") or "",
        read_mappings(state_obj.workspace_root),
    )
    result = await score_stage(state_obj, "SUPERVISOR", extra_context=trace_md)
    verdict = "PASS" if result.get("verdict") == "PASS" else "REJECT"
    report = _format_gate_report("고객사 최종 수용검수(RFP 대비)", result)
    if trace_md:
        report += f"\n\n{trace_md}"  # 사람이 보는 수용검수 리포트에도 근거 표 동봉
    print(f"‍⚖️ [Supervisor] 수용 판정: {verdict} (점수 {result.get('score')} / 시도 {attempts['SUPERVISOR']})")
    updates = {"supervisor_report_summary": report, "supervisor_verdict": verdict,
               "current_stage": "SUPERVISOR", "stage_attempt_counts": attempts}
    if verdict == "REJECT":
        # 요구·비즈니스 미충족 → PM 상신(요구·기능 재조정). 미흡 내역 전달.
        updates["reviewer_decision"] = "ESCALATE_PM"
        updates["reviewer_feedback"] = "‍⚖️ [고객사 수용검수 반려 - 요구·완성도 미달]\n" + report
    return updates

async def run_manual_writer(state: Any) -> Dict[str, Any]:
    state_obj = ProjectState.model_validate(state)

    # 빌드 실패 또는 프론트엔드 코드가 없으면 매뉴얼 생략
    if state_obj.build_status == "failed" or not state_obj.frontend_code_summary:
        print("⏩ [Smart Bypass] 빌드 실패 또는 코드 없음 - 사용자 매뉴얼 생성을 건너뜁니다.")
        return {}

    print(" [Agent] Technical Writer 사용자 매뉴얼 작성 중...")
    skill = _load_skill(agent_skill("ManualWriter", "manual_skill", template_id=state_obj.template_id))
    prompt = (
        f"{skill}\n\n"
        f"[참조: 기획서(PRD)]\n{state_obj.prd_summary}\n\n"
        f"[참조: 프론트엔드 코드 요약]\n{state_obj.frontend_code_summary}\n\n"
        f"[참조: QA 최종 검증 리포트]\n{state_obj.qa_report_summary}"
    )
    # B2: 매뉴얼은 요약/코드가 이미 프롬프트에 임베드돼 있어 워크스페이스 재주입 불필요(light=True),
    #     사용자 매뉴얼은 고난도 추론이 아니므로 Flash(is_heavy=False)로 충분 - 비용 절감.
    # output_mode 미지정 시 기본 'code'(CodeOutput 구조화 출력 강제)라 매뉴얼이 files JSON 블롭으로 산출됨
    output = await gateway.aexecute(state_obj, prompt, is_heavy=True, light=True, output_mode="document")
    print("[OK] [Agent] 사용자 매뉴얼 작성 완료.")
    return {"user_manual_summary": _safe_str(output)}
