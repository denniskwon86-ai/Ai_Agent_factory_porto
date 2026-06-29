import os
import json
from pathlib import Path
from typing import Dict, Any
from state_models import ProjectState
import config

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
          여기에 해당하는 파일은 **절단 없이 전체** 주입한다(증분 codegen — 멀티태스크에서
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

        context_parts = [
            f"🎯 [프로젝트 목표]: {state.project_name}",
            f"💡 [초기 기획]: {state.initial_idea}",
            f"📍 [현재 스프린트 태스크]: {state.current_sprint_task_id}"
        ]

        if getattr(state, "rfp_summary", ""):
            context_parts.append(f"📋 [요구사항 정의서 (RFP) — 반드시 충족해야 할 기준 계약]:\n{_clip(state.rfp_summary, sm)}")
        if state.prd_summary:
            context_parts.append(f"📄 [기획서 (PRD)]:\n{_clip(state.prd_summary, sm)}")
        if state.architecture_summary:
            context_parts.append(f"🏗️ [아키텍처]:\n{_clip(state.architecture_summary, sm)}")
        if state.tech_spec_summary:
            context_parts.append(f"🛠️ [기술 사양 (Tech Spec)]:\n{_clip(state.tech_spec_summary, sm)}")

        # 🚨 [컨텍스트 라우터] QA, Reviewer, 개발자 교차 참조를 위해 실제 파일 디스크에서 읽어오기.
        #   - 소유 파일(full_file_exts 일치): 전체 주입(절단 금지) — 재출력 시 기존 기능 보존.
        #   - 그 외 파일: per_file 절단(전체파일 모드에선 1줄 색인만) — 토큰 절감.
        if not light and state.workspace_root and state.file_index:
            ws_path = Path(state.workspace_root)
            if ws_path.exists():
                context_parts.append("\n📁 [현재 워크스페이스 실제 파일 상태 (Context Router)]:")
                owned_blocks: list[str] = []
                other_blocks: list[str] = []
                for rel_path, meta in state.file_index.items():
                    target_file = ws_path / rel_path
                    if not target_file.exists():
                        continue
                    is_owned = bool(full_file_exts) and rel_path.endswith(full_file_exts)
                    try:
                        raw = target_file.read_text(encoding="utf-8")
                        if is_owned:
                            owned_blocks.append(
                                f"--- FILE (이번 작업의 수정 대상 — 전체 코드 보존 필수): {rel_path} ---\n```\n{raw}\n```\n")
                        elif full_file_exts:
                            # 전체파일 모드의 비소유 파일은 본문 없이 1줄 색인(토큰 절감)
                            purpose = getattr(meta, "purpose", "") or (meta.get("purpose", "") if isinstance(meta, dict) else "")
                            other_blocks.append(f"--- FILE (참조 — 본 작업 비대상): {rel_path}" + (f" — {purpose}" if purpose else "") + " ---")
                        else:
                            other_blocks.append(f"--- FILE: {rel_path} ---\n```\n{_clip(raw, per_file)}\n```\n")
                    except Exception as e:
                        other_blocks.append(f"--- FILE: {rel_path} (읽기 실패: {e}) ---")
                # 소유 파일을 먼저 배치 → 총량 절단 시에도 보존 우선
                context_parts.extend(owned_blocks)
                context_parts.extend(other_blocks)

        # 전체 컨텍스트 총량 상한 (TPM 방어)
        return _clip("\n\n".join(context_parts), ctx_max)

    @staticmethod
    def get_strict_json_instruction() -> str:
        """
        🚨 [SSOT 규격 통일] 
        모든 에이전트의 프롬프트 끝에 강제로 주입되는 절대 출력 규칙.
        기존 skills 폴더의 모든 XML 지시를 무시하고 오직 이것만 따르도록 덮어씁니다.
        """
        return """
===================================================================
🛑 [절대 준수 시스템 명령: STRICT JSON OUTPUT ONLY] 🛑

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
  "state_updates": {
    "architecture_decisions": [{"id": "ADR-00X", "decision": "...", "reason": "..."}],
    "technical_debt": [{"id": "DEBT-00X", "description": "...", "priority": 1}],
    "file_index_updates": {
        "src/App.tsx": {"change_summary": "...", "purpose": "..."}
    }
  }
}
===================================================================
"""