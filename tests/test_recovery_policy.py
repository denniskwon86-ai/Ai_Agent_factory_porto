# ==========================================
# 복구 정책 테스트 (2026-07-27, C2)
#
# 고치는 결함:
#   ① 재시도 스웜이 실제로는 항상 1개였다. Backend/Frontend 노드가 _heavy=True 로
#      하드코딩되어 `1 if _heavy else (3 if _is_rework else 1)` 의 재작업 분기가
#      도달하지 않는 죽은 코드였다. 즉 재시도는 다양성 있는 복구가 아니라
#      같은 모델에게 같은 요청을 다시 보낸 것이었다.
#   ② 실패 원인이 파일 하나의 구문 오류인데도 전체 파일 재출력을 요구했다.
#      출력 예산을 다시 태우고(잘릴 확률↑), 앞 회차 수정이 되돌아갔다(결함 #21).
# ==========================================
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nodes.execution import (
    _recovery_swarm_size,
    _targeted_repair_instruction,
    _tech_spec_declares_no_server_api,
)


# ── ① 복구 표본 수 ────────────────────────────────────────────────
def test_first_attempt_uses_single_sample():
    """평시 생성은 1회 호출 — 토큰 낭비와 429 폭주를 막는다."""
    assert _recovery_swarm_size(is_rework=False, retry=0) == 1
    assert _recovery_swarm_size(is_rework=False, retry=3) == 1


def test_rework_first_round_still_single():
    """재작업 1회차는 아직 단일 — 새 표본(캐시 우회)만으로 회복되는 경우가 많다."""
    assert _recovery_swarm_size(is_rework=True, retry=0) == 1


def test_rework_second_round_gets_diversity():
    """2회차부터 표본 2개. 기존엔 항상 1이라 '같은 요청 재전송'이었다.
    3개로 되돌리지 않는 이유: 비용·429·타임아웃 악화."""
    assert _recovery_swarm_size(is_rework=True, retry=1) == 2
    assert _recovery_swarm_size(is_rework=True, retry=5) == 2


# ── ② 정밀 복구 지시 ──────────────────────────────────────────────
def test_targeted_repair_names_only_failing_files():
    log = "[src/App.tsx] 로드/컴파일 실패: 미해결 상대 모듈 import: \"./App.css\""
    out = _targeted_repair_instruction(log)
    assert "src/App.tsx" in out
    assert "이 파일들만" in out
    # 전체 재출력 지시를 이번 회차에 한해 해제한다고 명시해야 한다(가드와 충돌 방지)
    assert "적용하지 않습니다" in out


def test_targeted_repair_deduplicates_and_collects_multiple():
    log = "[main.py] SyntaxError\n[src/a.ts] oops\n[main.py] SyntaxError again"
    out = _targeted_repair_instruction(log)
    assert out.count("main.py") == 1, "같은 파일을 중복 나열하면 안 됩니다"
    assert "src/a.ts" in out


def test_no_targeted_repair_when_no_file_named():
    """파일을 지목하지 않는 일반 오류에는 정밀 복구를 걸지 않는다(전체 재생성이 맞다)."""
    assert _targeted_repair_instruction("백엔드 산출물이 비어 있습니다") == ""
    assert _targeted_repair_instruction("") == ""


# ── ③ 서버 API 없음 선언 (C3) ─────────────────────────────────────
class _Spec:
    def __init__(self, spec):
        self.tech_spec_summary = spec


def test_no_server_api_declaration_detected():
    assert _tech_spec_declares_no_server_api(_Spec("이 기능은 브라우저 내에서 처리한다. 서버 API 없음."))
    assert _tech_spec_declares_no_server_api(_Spec('{"server_api_required": false}'))


def test_ambiguous_spec_keeps_backend_required():
    """보수적 판정 — 선언이 명확하지 않으면 기존 동작(백엔드 필요)을 유지한다."""
    assert not _tech_spec_declares_no_server_api(_Spec("REST API 엔드포인트 3개를 제공한다."))
    assert not _tech_spec_declares_no_server_api(_Spec(""))
