import os
import json
import ast
from pathlib import Path
from typing import Dict, Any
from state_models import ProjectState
import config
from core.persona_learner import persona_learner
from core.knowledge_base import knowledge_base
from core.master_data import master_data

# 디스크 walk 시 제외할 디렉터리(노이즈/대용량 방지)
_EXCLUDE_DIRS = {".git", ".archive", "node_modules", "dist", "build", ".next",
                 "venv", ".venv", "__pycache__", "coverage", ".turbo", "out",
                 # [2026-07-27] CodeBuilder 의 후보 스테이징 영역과 실패 번들.
                 #   컨텍스트/프리뷰/회귀 게이트가 이것들을 '워크스페이스의 실제 파일'로
                 #   착각하면 중복 파일이 잡히고 컨텍스트가 두 배로 부풀어 오른다.
                 ".candidate", ".failures"}


def _clip(text: str, limit: int) -> str:
    """긴 텍스트를 limit자로 절단 (토큰/할당량 절감)."""
    text = text or ""
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n…(이하 {len(text) - limit}자 생략)"

class ContextEngine:
    @staticmethod
    def build_core_context(state: ProjectState, light: bool = False, full_file_exts=None) -> str:
        """
        [전면 개편]
        기존의 무거운 코드 문자열 대신, 물리 디스크의 실제 파일을 읽어오는 컨텍스트 라우터.
        light=True이면 워크스페이스 전체 파일 주입을 생략하고 요약만 포함한다.
        모든 산출물 요약/파일은 토큰 상한으로 절단하여 무료 티어 할당량(TPM) 폭증을 방어한다.

        full_file_exts: 개발자가 '본인이 전체 재출력할 파일'의 확장자 튜플(예: (".tsx",".ts")).
          여기에 해당하는 파일은 **절단 없이 전체** 주입한다(증분 codegen - 멀티태스크에서
          기존 기능이 truncation 으로 누락되던 회귀의 근본 차단). 미지정(None)이면 종전과
          100% 동일하게 동작한다(모든 파일 per_file 절단 + ctx_max 총량 절단).
        """
        sm = getattr(config, "SUMMARY_MAX_LENGTH", 4000)
        # 코드 누적/기존기능 보존을 위해 컨텍스트 예산 상향(Pro 600k 컨텍스트 기준 안전).
        # 기존 파일이 과하게 잘려 재생성 시 기능이 누락되던 회귀 완화. (무료티어 TPM과의 트레이드오프)
        per_file = 4000
        full_file_exts = tuple(full_file_exts or ())
        # 전체파일 주입 모드면 더 큰 총량 상한 적용(소유 파일이 다시 잘리지 않도록)
        ctx_max = (getattr(config, "CONTEXT_MAX_LENGTH_CODE", 200000)
                   if full_file_exts else getattr(config, "CONTEXT_MAX_LENGTH", 20000))

        profile = persona_learner.get_company_profile()
        profile_str = json.dumps(profile, ensure_ascii=False, indent=2) if profile else "학습된 프로필 없음"

        rag_context = knowledge_base.get_relevant_context(state)
        # 프로젝트에 연결된 지식팩(도메인 참고자료) 그라운딩 - 어떤 LLM 제공사로 폴백돼도
        # 동일한 지식이 주입되어 산출물 품질의 기준선을 형성한다
        grounding = knowledge_base.get_grounding_context(state)
        # [M1] 결정론적 기준정보(Master Data) - 벡터 검색이 아닌 확정 조회로 주입되며,
        # 정형 기준(수치·명칭·단위)이므로 비정형 지식팩 그라운딩보다 '앞에' 배치한다(우선순위).
        #
        # ★ [2026-07-29 / D-010] 기준정보에 **컨텍스트 예산의 몫을 명시적으로 배정**한다.
        #   D-010 으로 주입 상한을 없앤 뒤, 도메인·조직범위가 선언되지 않은 프로젝트에서
        #   "전수"가 곧 "DB 전체"가 되어 **블록 하나가 예산 20,000자를 전부 삼켰다**
        #   (실측 70건 = 21,877자). 그 결과 뒤에 붙는 기술 명세가 `_clip` 에 통째로 잘려
        #   **코더가 API 계약·화면 구성을 못 보는 회귀**가 발생했다(test_context_full_files).
        #   기준정보가 중요하다는 것과 기준정보가 나머지 전부를 굶겨도 된다는 것은 다르다.
        #   절반을 상한으로 두고, 잘리면 레코드 경계에서 끊고 그 사실을 블록에 적는다.
        _master_budget = max(8000, int(ctx_max * 0.5))
        master_context = master_data.get_master_context(state, max_chars=_master_budget)

        context_parts = [
            f" [기업 프로필 & 사용자 성향]:\n{profile_str}"
        ]
        if master_context:
            context_parts.append(master_context)
        # ★ [ECM E2 / 감사 ENTERPRISE-01 Action 3] 템플릿별 기준정보 바인딩 규칙.
        #   ⚠️ 감사 지적: 템플릿이 마스터의 어느 섹션을 근거로 써야 하는지 명시하지 않으면
        #     **LLM 이 마스터를 무시하고 환각으로 수치를 지어낸다.** 기준정보를 주입하는 것만으로는
        #     부족하고 "이 값들은 계산 결과이니 지어내지 말라"는 규칙이 함께 있어야 한다.
        #   기준정보 본문(위 master_context) **바로 뒤**에 둔다 — 규칙이 대상보다 앞에 오면
        #     무엇에 대한 규칙인지 모른다.
        try:
            from core.enterprise_context.profile_resolver import render_binding_block
            _binding = render_binding_block(getattr(state, "template_id", "") or "")
            if _binding:
                context_parts.append(_binding)
        except Exception as e:
            # 바인딩 규칙 누락이 파이프라인을 멈추게 하면 안 된다(부가 지시문).
            print(f"⚠️ [ContextEngine] 기준정보 바인딩 규칙 주입 생략: {e}")
        # [M3] 외부 실측값 병기 - 기본 off. 켠 프로젝트만 활성 연계 시스템에서 온디맨드 조회해
        # 기준값(M1) 바로 뒤에 '참고(비신뢰)'로 병기한다. lazy import 로 순환참조 회피.
        if getattr(state, "mcp_live_grounding", False):
            try:
                from core.mcp_broker import mcp_broker
                live_context = mcp_broker.get_live_context(state)
                if live_context:
                    context_parts.append(live_context)
            except Exception as e:
                print(f"⚠️ [ContextEngine] 실측 병기 실패(생략): {e}")
        if grounding:
            context_parts.append(f" [도메인 참고 지식 - 반드시 정합 유지]:\n{grounding}")
        if rag_context:
            context_parts.append(f" [과거 유사 사례 참고]:\n{rag_context}")
            
        context_parts.extend([
            f" [프로젝트 목표]: {state.project_name}",
            f" [초기 기획]: {state.initial_idea}",
            f" [현재 스프린트 태스크]: {state.current_sprint_task_id}"
        ])

        stage = (getattr(state, "current_stage", "") or "").upper()
        is_planning = stage in ("PLANNING", "RFP", "PRD", "ARCHITECTURE", "TECH_SPEC", "UI_DESIGN", "CLARIFICATION")

        if getattr(state, "rfp_summary", "") and is_planning:
            context_parts.append(f" [요구사항 정의서 (RFP) - 반드시 충족해야 할 기준 계약]:\n{_clip(state.rfp_summary, sm)}")
        if getattr(state, "prd_summary", "") and is_planning:
            context_parts.append(f" [기획서 (PRD)]:\n{_clip(state.prd_summary, sm)}")
        if getattr(state, "architecture_summary", ""):
            arch = state.architecture_summary
            if not is_planning:
                # [Context Diet] 실행 단계에선 아키텍처는 절반으로 강제 압축 (핵심만)
                arch = _clip(arch, sm // 2)
            context_parts.append(f"️ [아키텍처]:\n{arch}")
            
        if getattr(state, "tech_spec_summary", ""):
            ts = state.tech_spec_summary
            if not is_planning and state.current_sprint_task_id and state.workspace_root:
                try:
                    from nodes.utils.wbs_manager import WBSManager
                    wbs = WBSManager(workspace_root=state.workspace_root).get_wbs()
                    current_task = next((t for t in wbs.get("tasks", []) if t.get("task_id") == state.current_sprint_task_id), None)
                    if current_task:
                        agents = current_task.get("required_agents", [])
                        # 극단적 다이어트: Frontend/Backend 무관한 부분(문단 단위) 잘라내기 휴리스틱
                        is_fe = any("Front" in a or "UI" in a for a in agents)
                        is_be = any("Back" in a or "DB" in a or "Data" in a for a in agents)

                        # [R1 수정] API/계약/인터페이스 섹션은 FE·BE 양쪽 모두에게 필수
                        #   (프론트가 호출할 엔드포인트·요청/응답 스키마가 여기 있음).
                        #   → FE 전담 태스크에서도 절대 drop 하지 않는다.
                        #   순수 구현 세부(DB 스키마/서버 내부 등)만 무관 담당에서 제거.
                        SHARED_KW = ("api", "계약", "contract", "endpoint", "엔드포인트",
                                     "interface", "인터페이스")
                        FE_KW = ("frontend", "front-end", "프론트", "ui", "client", "클라이언트")
                        BE_KW = ("backend", "back-end", "백엔드", "database", "데이터베이스",
                                 "db", "server", "서버")

                        filtered_ts = []
                        keep = True
                        for line in ts.splitlines():
                            if line.startswith("#"):
                                lower_line = line.lower()
                                # SHARED 를 먼저 판정 → "Backend API" 류 헤더도 계약으로 보존
                                if any(k in lower_line for k in SHARED_KW):
                                    keep = True
                                elif any(k in lower_line for k in FE_KW):
                                    keep = is_fe or not is_be  # FE 담당이거나 BE 전담이 아니면 유지
                                elif any(k in lower_line for k in BE_KW):
                                    keep = is_be or not is_fe  # BE 담당이거나 FE 전담이 아니면 유지
                                else:
                                    keep = True  # 분류 불가(개요 등 공용 섹션)는 항상 유지
                            if keep:
                                filtered_ts.append(line)
                        ts = "\n".join(filtered_ts)
                except Exception:
                    pass
            context_parts.append(f"️ [기술 사양 (Tech Spec)]:\n{_clip(ts, sm)}")

        #  [컨텍스트 라우터] QA, Reviewer, 개발자 교차 참조를 위해 실제 파일 디스크에서 읽어오기.
        #   - 소유 파일(full_file_exts 일치): 전체 주입(절단 금지) - 재출력 시 기존 기능 보존.
        #   - 그 외 파일: per_file 절단(전체파일 모드에선 1줄 색인만) - 토큰 절감.
        #   - file_index 가 비거나 stale 해도, 소유 확장자는 디스크를 직접 walk 해 주입(자가복구).
        if not light and state.workspace_root:
            ws_path = Path(state.workspace_root)
            if ws_path.exists():
                owned_blocks: list[str] = []
                other_blocks: list[str] = []
                injected: set[str] = set()  # 중복 주입 방지(소문자 정규화 비교)

                def _extract_snippet(raw: str, rel_path: str, limit: int) -> str:
                    if rel_path.endswith(".py"):
                        try:
                            tree = ast.parse(raw)
                            lines = raw.splitlines()
                            skeleton = []
                            for node in tree.body:
                                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                                    sig = lines[node.lineno - 1].strip()
                                    doc = ast.get_docstring(node)
                                    if doc:
                                        skeleton.append(f"{sig}\n    \"\"\"{doc.split(chr(10))[0]}...\"\"\"\n    ...")
                                    else:
                                        skeleton.append(f"{sig}\n    ...")
                                elif isinstance(node, (ast.Import, ast.ImportFrom)):
                                    skeleton.append(lines[node.lineno - 1])
                            skeleton_text = "\n".join(skeleton)
                            if skeleton_text and len(skeleton_text) < limit:
                                return f"[AST Skeleton]\n{skeleton_text}"
                        except Exception:
                            pass
                    return _clip(raw, limit)

                def _emit(rel_path: str, meta=None):
                    key = rel_path.lower()
                    if key in injected:
                        return
                    target_file = ws_path / rel_path
                    if not target_file.exists():
                        return
                    is_owned = bool(full_file_exts) and rel_path.endswith(full_file_exts)
                    try:
                        raw = target_file.read_text(encoding="utf-8")
                        if is_owned:
                            owned_blocks.append(
                                f"--- FILE (이번 작업의 수정 대상 - 전체 코드 보존 필수): {rel_path} ---\n```\n{raw}\n```\n")
                        elif full_file_exts:
                            purpose = getattr(meta, "purpose", "") or (meta.get("purpose", "") if isinstance(meta, dict) else "")
                            other_blocks.append(f"--- FILE (참조 - 본 작업 비대상): {rel_path}" + (f" - {purpose}" if purpose else "") + " ---")
                        else:
                            from core.jit_context import extract_signatures
                            _, ext = os.path.splitext(rel_path)
                            if ext in [".ts", ".tsx", ".js", ".jsx", ".py"]:
                                snippet = extract_signatures(raw, ext)
                                other_blocks.append(f"--- FILE: {rel_path} (JIT Signature) ---\n```\n{snippet}\n```\n")
                            else:
                                snippet = _extract_snippet(raw, rel_path, per_file)
                                other_blocks.append(f"--- FILE: {rel_path} ---\n```\n{snippet}\n```\n")
                        injected.add(key)
                    except Exception as e:
                        other_blocks.append(f"--- FILE: {rel_path} (읽기 실패: {e}) ---")

                # 1) file_index 기반 주입(기존 동작)
                for rel_path, meta in (state.file_index or {}).items():
                    _emit(rel_path, meta)

                # 2) [자가복구] 소유 확장자 파일을 디스크에서 직접 발견해 주입 - file_index 에 없어
                #    누락되던 기존 코드까지 보장(멀티태스크 file_index 유실 회귀 차단).
                if full_file_exts:
                    for disk_path in sorted(ws_path.rglob("*")):
                        if len(injected) >= 120:
                            break
                        if not disk_path.is_file():
                            continue
                        rel = str(disk_path.relative_to(ws_path)).replace("\\", "/")
                        if any(seg in _EXCLUDE_DIRS for seg in rel.split("/")):
                            continue
                        if rel.endswith(full_file_exts):
                            _emit(rel)

                if owned_blocks or other_blocks:
                    context_parts.append("\n [현재 워크스페이스 실제 파일 상태 (Context Router)]:")
                    # 소유 파일을 먼저 배치 → 총량 절단 시에도 보존 우선
                    context_parts.extend(owned_blocks)
                    context_parts.extend(other_blocks)

        # 전체 컨텍스트 총량 상한 (TPM 방어)
        return _clip("\n\n".join(context_parts), ctx_max)

    @staticmethod
    def get_strict_json_instruction() -> str:
        """
         [SSOT 규격 통일] 
        모든 에이전트의 프롬프트 끝에 강제로 주입되는 절대 출력 규칙.
        기존 skills 폴더의 모든 XML 지시를 무시하고 오직 이것만 따르도록 덮어씁니다.
        """
        return """
===================================================================
 [절대 준수 시스템 명령: STRICT JSON OUTPUT ONLY] 

당신의 응답은 반드시 아래의 JSON 포맷과 정확히 일치해야 합니다.
마크다운 설명, 인삿말, XML 태그(<file> 등)는 절대 금지됩니다. 
응답 텍스트 전체가 단일하고 유효한 JSON 객체여야 합니다.

[기대 출력 스키마]:
{
  "files": [
    {
      "file_path": "생성/수정할 파일의 상대 경로 (예: src/App.tsx, backend/main.py)",
      "code": "여기에 전체 소스 코드를 작성 (부분 패치 불가, 반드시 전체 코드)"
    }
  ],
  "deleted_files": ["더 이상 필요 없어 삭제할 파일의 상대 경로 (없으면 빈 배열)"],
  "error": "생성이 불가능한 경우에만 사유를 쓰고, 정상 생성 시에는 빈 문자열"
}

[파일 삭제]
· 리팩터링·기술스택 전환으로 기존 파일이 더 이상 필요 없어지면 `deleted_files` 에 그 경로를
  넣으십시오. **이것이 파일을 지우는 유일한 방법입니다.**
· 삭제하려는 파일을 `files` 에 빈 내용으로 넣지 마십시오 — 빈 파일이 남을 뿐입니다.
· 이미 삭제된(또는 존재하지 않는) 경로를 넣어도 무해합니다.

[출력 예산 - 반드시 지킬 것]
· 위 스키마 외의 필드(설명, 메타데이터, 결정기록 등)를 추가하지 마십시오. **전부 무시됩니다.**
· 응답은 마지막 닫는 중괄호까지 완결되어야 합니다. 중간에 끊기면 **응답 전체가 폐기**되어
  한 글자도 반영되지 않습니다. 파일이 많아 한 응답에 다 담기 어렵다고 판단되면,
  이번 태스크 범위에 **꼭 필요한 파일만** 내십시오(불필요한 파일을 함께 내다가 잘리는 것이
  최악입니다).
===================================================================
"""