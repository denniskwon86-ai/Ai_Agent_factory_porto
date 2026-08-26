"""Decision Ledger — 결정·가정·승인·근거의 **불변 이력** (마스터 명세서 §5.2 / M0 백로그 5).

## 왜 필요한가

제품의 차별점 첫 항목이 "**기업 의도와 결정의 보존** — 왜 이 앱·규칙·수치가 만들어졌는지 추적
가능해야 한다"(§1.3)다. 산출물만 남으면 6개월 뒤 "이 계획 수치가 왜 이렇게 됐나"에 답할 수 없다.
Ledger 는 그 답을 담는 곳이다.

## 설계 원칙 (§5.2)

1. **수정하지 않는다. 정정 이벤트로 보완한다.** 그래서 이 모듈에는 `update`/`delete` 가 **없다**.
   잘못 기록했으면 `parent_event_id` 로 정정 이벤트를 잇는다 — 틀린 기록도 "그때 그렇게
   판단했다"는 사실이므로 지우면 이력이 거짓이 된다.
2. **AI 의 추천과 사용자의 확정 결정을 구분한다.** `actor_type` 이 그 축이다.
3. **근거 없는 경영 수치는 '검증되지 않은 추정'으로 표시한다.** `evidence_refs` 가 비어 있으면
   `is_substantiated=False` 로 읽힌다 — 조회부가 근거 유무를 판단할 수 있어야 한다.

## 변조 탐지 (명세서에 없으나 추가)

"불변 이력"을 주장하려면 사후 변조를 알아챌 수단이 있어야 한다. 각 이벤트에
`prev_hash + 정규화된 payload` 의 SHA-256 을 `event_hash` 로 남겨 체인을 만든다.
⚠️ **한계를 정직하게 밝힌다**: 이것은 DB 파일을 직접 고치는 것을 *막지* 못한다. 체인을
재계산해 **불일치를 탐지**할 수 있을 뿐이다(중간 이벤트를 고치면 이후 전부 깨진다).
진짜 위조 방지는 외부 append-only 저장소나 서명이 필요하며 그건 이 단계의 범위가 아니다.

## 저장 위치

`data/decision_ledger.db` — `advisor.db` 에 두지 않는다. Ledger 는 Blueprint·프로젝트·릴리스·
시나리오·조직 문맥을 모두 참조하는 **전사 자산**인데 상담 DB 안에 있으면 상담 전용처럼 보인다
(ECM §6.2 는 조직 문맥 변경·프로필 변경·복제·권한부여·외부 연결·시나리오 실행도 대상으로 지정).
인프라 규약은 `master_data.py`·`advisor_store.py` 와 동일하다(멱등 DDL + WAL + 스레드 락).
"""
import contextlib
import hashlib
import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence
from core.paths import data_path

_DB_PATH = data_path("decision_ledger.db")

# ── §5.2 필수 이벤트 유형 ─────────────────────────────────────────────────
#   명세서가 열거한 10종 + ECM §6.2 가 요구하는 문맥·복제·권한 이벤트.
#   ⚠️ 미등록 유형은 거부한다 — 오타로 만든 유형이 조용히 쌓이면 집계가 조각난다.
EVENT_TYPES = (
    # 명세서 §5.2
    "REQUIREMENT_CONFIRMED",
    "BLUEPRINT_APPROVED",
    "BLUEPRINT_REJECTED",          # 승인만 남기면 반려 사유가 사라진다(§5.2 정신상 필요)
    "DATA_REQUIREMENT_ACCEPTED",
    "MASTER_VALUE_CHANGED",
    "DATA_CONTRACT_PUBLISHED",
    "WBS_APPROVED",
    "RELEASE_ACCEPTED",
    "SCENARIO_EXECUTED",
    "SHADOW_MODE_PASSED",
    "PRODUCTION_WRITE_APPROVED",
    # ECM §6.2 — 조직 문맥 변경·프로필 변경·복제·권한부여·외부 연결
    "ENTERPRISE_CONTEXT_CHANGED",
    "ENTERPRISE_PROFILE_CHANGED",
    "ENTITY_CLONED",
    "PERMISSION_GRANTED",
    "EXTERNAL_CONNECTION_APPROVED",
    # 파이프라인 연결
    "PROJECT_BOOTSTRAPPED",
    # [CL-1~CL-3 · 2026-08-03] 앱 전달–의사결정–발간 폐쇄루프.
    #   ⚠️ 운영 상태(`data/collaboration.db`)와 별도로 여기에 남기는 이유: 운영 표는 상태를
    #     **덮어쓴다**(PENDING → ACCEPTED). 누가 언제 무엇을 수락했는지는 덮어쓸 수 없는 곳에
    #     있어야 하고, 그것이 이 원장이다. 상태만 있으면 "왜 이 사람이 이 앱을 쓰고 있나"에
    #     답할 수 없다.
    "APP_DELIVERY_CREATED",
    "APP_DELIVERY_ACCEPTED",
    "APP_DELIVERY_REJECTED",
    "APP_DELIVERY_REVOKED",
    "DECISION_CASE_CREATED",
    "DECISION_REVIEW_REQUESTED",
    "DECISION_MEETING_REQUESTED",
    "DECISION_RECORDED",
    "DECISION_ACTION_CREATED",
    "DECISION_EFFECT_MEASURED",
    "PUBLICATION_CREATED",
    "PUBLICATION_RENDERED",
    "PUBLICATION_REVIEW_REQUESTED",
    "PUBLICATION_APPROVED",
    "PUBLICATION_REJECTED",
    "PUBLICATION_PUBLISHED",
    # ★ 게시 **실패**도 원장에 남긴다. 실패를 남기지 않으면 "왜 이 보고서가 안 나갔나"에
    #   답할 수 없고, 다음 사람은 이미 나갔다고 믿는다(작업서 §5.1 "게시 실패를 성공으로
    #   저장 금지"의 원장 쪽 절반이다).
    "PUBLICATION_PUBLISH_FAILED",
    "PUBLICATION_CORRECTED",
    "PUBLICATION_WITHDRAWN",
    # [트랙 I · 2026-08-08] 생성 앱 데이터 평면.
    #   ⚠️ **레코드 1건마다 원장 1건을 쓰지 않는다.** 업무 앱은 레코드를 대량으로 만든다 —
    #     하루 수천 건이 들어오면 «왜 이 결정을 했는가» 의 이력이 데이터 로그에 파묻힌다.
    #     → 데이터셋의 **구조 변경**(생성·스키마·폐지)만 여기에 남기고, 레코드 단위 변경은
    #       `app_records` 자신의 `created_by`/`updated_by`/`deleted_by` 로 귀속을 남긴다.
    #     이 구분은 `tests/test_app_data_plane.py` 가 고정한다.
    "APP_DATASET_CREATED",
    "APP_DATASET_SCHEMA_CHANGED",
    "APP_DATASET_RETIRED",
    # [I-4 4단계 · 설계 §3·§13] App Runtime Contract 검토 게이트.
    #   ⚠️ **자동 통과는 여기에 남기지 않는다.** 지문이 바뀌지 않아 사람을 부르지 않은
    #     일까지 «승인» 으로 쌓으면, 원장에서 승인 건수를 세는 순간 실제보다 많아지고
    #     그 숫자가 「우리는 계약을 N번 검토했다」로 읽힌다.
    #   `subject_id` 는 **계약 지문**이다 — 프로젝트가 아니라 «어느 계약을 승인했는가»
    #     가 남아야 하고, 지문이 바뀌면 그것은 다른 계약이다.
    "APP_CONTRACT_REVIEW_REQUESTED",
    "APP_CONTRACT_APPROVED",
    "APP_CONTRACT_REJECTED",
    # ★★★ [MVP-P0 ①-B / 2026-08-20] **온톨로지 전용 승인 이벤트.**
    #
    #   ⚠️⚠️ 종전에는 범용 이벤트(`DECISION_RECORDED` 등)를 온톨로지 승인으로 재사용하려
    #     했다. 그러면 **같은 행위자의 아무 결정 하나로 다른 관계 승인을 통과**시킬 수
    #     있고, `PUBLICATION_WITHDRAWN` 이 관계 폐지를 승인하는 도메인 착오도 생긴다.
    #   ★ 승인은 «무엇을» 승인했는지가 절반이다. 그래서 목적별 전용 유형을 두고,
    #     `subject_type`·`subject_id` 로 **대상**을 못박는다.
    #       · ONTOLOGY_MODEL_APPROVED    → subject_id = 계약 지문(contract_fingerprint)
    #       · ONTOLOGY_RELATION_APPROVED → subject_id = relation_id
    #       · ONTOLOGY_RELATION_RETIRED  → subject_id = relation_id
    "ONTOLOGY_MODEL_APPROVED",
    "ONTOLOGY_RELATION_APPROVED",
    "ONTOLOGY_RELATION_RETIRED",
    #: ⚠️ 승인 철회. `parent_event_id` 로 원 승인을 가리킨다 — 그러면 그 승인은 죽는다.
    "ONTOLOGY_APPROVAL_REVOKED",
    # ★★★ [G2 · Dataset Ownership Binding / 2026-08-21] **데이터셋 소유 결속 전용 승인.**
    #
    #   ⚠️⚠️ 첫 판은 결속 표의 `approved_by` 문자열 하나로 「승인됨」을 주장했다. 그것은
    #     승인이 아니라 **자기진술**이다 — 같은 호출자가 넣은 값을 같은 호출자가 읽는다.
    #     감사자가 "누가 언제 무슨 근거로 이 부서를 소유자로 정했나" 를 물으면 답이 없다.
    #   ★ 그래서 승인은 **원장 사건**이어야 한다. 결속 표는 그 사건의 id 를 가리키고,
    #     조회할 때마다 그 사건이 살아 있는지 다시 확인한다(사건이 없으면 결속도 없다).
    #       · subject_type = "dataset_ownership_binding"
    #       · subject_id   = 결속 지문(tenant·mode·계약키·범위·부서·시작일의 지문)
    #                        ⚠️ 부서까지 지문에 넣는다 — 그러지 않으면 A부서 승인 사건으로
    #                          B부서 결속을 세울 수 있다.
    "DATASET_OWNERSHIP_APPROVED",
    #: 철회는 `parent_event_id` 로 원 승인을 가리키는 **자식 사건**이다. 원 사건을 지우지
    #: 않는다 — 무엇이 있었고 누가 왜 내렸는지는 남아야 한다.
    "DATASET_OWNERSHIP_REVOKED",
    # ★★★ [G2 M0-3.2 / 2026-08-21] **계산 능력 실행 승인.**
    #
    #   ⚠️⚠️ 계산은 숫자를 만들고, 그 숫자는 회의에 올라간다. 그래서 「산식을 구현했다」와
    #     「이 산식으로 계산해도 된다」는 **다른 결정**이고, 뒤엣것은 사람이 한다.
    #   ★ 대상은 **계산 참조 + 산식 판의 지문**이다(`Capability.fingerprint()`).
    #     ⚠️ 참조 이름만 대상으로 삼으면 산식을 고쳐도 옛 승인이 유효해 보인다 —
    #       그것이 「같은 이름 다른 계산」이다.
    "CALC_CAPABILITY_APPROVED",
    #: 실행 승인 철회. `parent_event_id` 로 원 승인을 가리킨다.
    "CALC_CAPABILITY_REVOKED",
    # ★★★ [G2 M0-3.2b] **계산 기준선 봉인.**
    #
    #   생산-판매 배분·인식 기간·기준 인식일 셋을 **한 봉인**으로 묶는다. 따로 두면
    #   「배분은 새 것, 인식 규칙은 옛 것」 같은 조합이 생기고, 그 조합은 아무도 승인한
    #   적이 없다 — 매출 이연은 셋의 곱이다.
    #   ⚠️ 대상은 **내용의 지문**이다(build_id 가 아니다). 내용을 고치면 지문이 바뀌고
    #     승인이 자동으로 죽는다 — 「같은 기준선 다른 값」이 승인을 물려받지 못한다.
    "CALC_BASELINE_SEALED",
    "CALC_BASELINE_REVOKED",
    # ★★★ [G2 M0-5] **시연 초기화.** 지우는 일도 기록으로 남는다.
    #
    #   ⚠️⚠️ 초기화는 원장 사건을 **하나도 지우지 않는다.** 원장은 추가 전용이고,
    #     초기화 자체가 여기 세 사건으로 남는다.
    #   ★ 셋을 가른다: 요청했다 / 끝났다 / 실패했다. 실패를 안 남기면 「요청만 있고
    #     결과 없음」이 되고, 다음 사람은 초기화가 됐는지 안 됐는지 모른다.
    "DEMO_RESET_REQUESTED",
    "DEMO_RESET_COMPLETED",
    "DEMO_RESET_FAILED",
    "CORRECTION",                  # 정정 전용 — 반드시 parent_event_id 를 가진다
)

ACTOR_TYPES = ("user", "agent", "system")
SUBJECT_TYPES = ("blueprint", "consultation", "project", "release", "scenario",
                 "master_record", "data_contract", "enterprise_entity", "permission",
                 "external_connection", "wbs_task",
                 # [CL-1~CL-3] 폐쇄루프 주체 — 전달·결정·발간은 릴리스나 프로젝트가 아니다.
                 #   같은 subject_type 으로 뭉개면 "이 릴리스에 무슨 일이 있었나"와 "이 전달이
                 #   어떻게 됐나"를 구분할 수 없다.
                 "app_delivery", "decision_case", "publication",
                 # [G2 M0-5] 시연 초기화의 대상은 **키트 인스턴스**다.
                 "demo_reset",
                 # [트랙 I] 생성 앱이 쌓는 업무 데이터의 그릇. 릴리스와 구분한다 —
                 #   «이 릴리스가 어떻게 됐나» 와 «이 앱의 데이터에 무슨 일이 있었나» 는
                 #   다른 질문이고, 뭉개면 둘 다 답할 수 없다.
                 "app_dataset",
                 # [I-4 4단계] 계약은 릴리스도 데이터셋도 아니다 — «이 릴리스가 어떻게
                 #   됐나» 와 «이 계약이 언제 어떤 지문으로 승인됐나» 는 다른 질문이다.
                 "app_contract",
                 # [MVP-P0 ①-B] 온톤로지 주체 — 계약과 관계는 **다른 질문**이다.
                 #   «이 온톤로지 계약이 언제 어떤 지문으로 승인됐나» 와
                 #   «이 관계를 누가 승인·폐지했나» 를 뜼개면 둘 다 답할 수 없다.
                 "ontology_model_contract", "ontology_relation",
                 # [G2] 「어느 부서가 이 데이터셋을 소유하는가」. 계약(app_contract)과 다르다 —
                 #   «이 계약이 승인됐나» 와 «이 데이터의 소유 부서가 누구인가» 는 다른 질문이고,
                 #   후자는 권한 판정에 직접 쓰인다.
                 "dataset_ownership_binding",
                 # [G2 M0-3.2] 계산 능력. 「이 산식으로 계산해도 되는가」는 데이터 소유나
                 #   온톨로지 관계와 **다른 질문**이다 — 뭉개면 셋 다 답할 수 없다.
                 "calc_capability",
                 # [G2 M0-3.2b] 계산 기준선. 「무엇과 비교해 이연을 재는가」는 산식
                 #   승인과 다른 질문이다.
                 "calc_baseline")


#: ★★★ [4.1c-B P0-4] **철회 유형 → 허용되는 부모 유형** 표. 한 곳에만 둔다.
#:
#: ⚠️ 앞 판은 온톨로지 철회 검증이 `_insert` 안에 하드코딩돼 있었고, 소유권 철회를 추가할
#:   때 그 검증을 지나지 않았다. 새 유형이 언제나 느슨한 쪽으로 태어나는 구조였다 —
#:   유형을 늘리는 사람이 검증을 함께 늘리도록, 표를 여기 하나만 둔다.
_REVOCATION_PARENTS = {
    "ONTOLOGY_APPROVAL_REVOKED": ("ONTOLOGY_MODEL_APPROVED", "ONTOLOGY_RELATION_APPROVED",
                                  "ONTOLOGY_RELATION_RETIRED"),
    "DATASET_OWNERSHIP_REVOKED": ("DATASET_OWNERSHIP_APPROVED",),
    "CALC_CAPABILITY_REVOKED": ("CALC_CAPABILITY_APPROVED",),
    "CALC_BASELINE_REVOKED": ("CALC_BASELINE_SEALED",),
}
_REVOCATION_EVENTS = tuple(_REVOCATION_PARENTS)


class DecisionLedgerError(ValueError):
    """검증 실패 — 라우트가 4xx 로 바꾼다."""


_DDL = """
CREATE TABLE IF NOT EXISTS decision_ledger_events (
    event_id        TEXT PRIMARY KEY,
    seq             INTEGER NOT NULL,           -- 체인 순서(자기 증가)
    tenant_id       TEXT NOT NULL DEFAULT 'tenant_default',
    enterprise_scope_id TEXT DEFAULT '',
    entity_mode     TEXT NOT NULL DEFAULT 'REAL',
    project_id      TEXT DEFAULT '',
    blueprint_id    TEXT DEFAULT '',
    event_type      TEXT NOT NULL,
    subject_type    TEXT NOT NULL,
    subject_id      TEXT NOT NULL,
    actor_type      TEXT NOT NULL,              -- user | agent | system
    actor_id        TEXT DEFAULT '',
    decision        TEXT DEFAULT '',            -- 무엇을 결정했는가
    rationale       TEXT DEFAULT '',            -- 왜
    evidence_refs_json       TEXT DEFAULT '[]', -- 근거(데이터셋·버전·테스트 결과)
    input_version_refs_json  TEXT DEFAULT '[]',
    output_version_refs_json TEXT DEFAULT '[]',
    parent_event_id TEXT DEFAULT '',            -- 정정 대상
    prev_hash       TEXT DEFAULT '',
    event_hash      TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    UNIQUE (seq)
);
CREATE INDEX IF NOT EXISTS idx_ledger_subject ON decision_ledger_events(subject_type, subject_id);
CREATE INDEX IF NOT EXISTS idx_ledger_type ON decision_ledger_events(event_type, created_at);
CREATE INDEX IF NOT EXISTS idx_ledger_ctx ON decision_ledger_events(tenant_id, entity_mode);
CREATE INDEX IF NOT EXISTS idx_ledger_project ON decision_ledger_events(project_id);
CREATE INDEX IF NOT EXISTS idx_ledger_blueprint ON decision_ledger_events(blueprint_id);
"""

# 해시에 넣는 필드와 순서. ⚠️ 이 목록을 바꾸면 **기존 체인이 전부 깨진다**(재계산 값이 달라짐).
#   바꿔야 하면 버전을 올려 새 체인을 시작하고 기존 체인은 그대로 보존할 것.
_HASH_FIELDS = ("seq", "tenant_id", "enterprise_scope_id", "entity_mode", "project_id",
                "blueprint_id", "event_type", "subject_type", "subject_id", "actor_type",
                "actor_id", "decision", "rationale", "evidence_refs_json",
                "input_version_refs_json", "output_version_refs_json", "parent_event_id",
                "created_at")
_HASH_VERSION = "v1"


def _compute_hash(row: Dict[str, Any], prev_hash: str) -> str:
    """정규화된 payload + 이전 해시 → SHA-256. 필드 순서를 고정해 재현 가능하게 만든다."""
    payload = _HASH_VERSION + "|" + prev_hash + "|" + "|".join(
        str(row.get(k, "")) for k in _HASH_FIELDS)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class DecisionLedger:
    def __init__(self, db_path: Optional[str] = None):
        """⚠️⚠️ 기본 경로를 **호출 시점에** 해석하고, **파일은 아직 열지 않는다.**

        세 가지가 함께 있어야 격리가 성립한다(2026-08-17 실측 사고):

        ① 예전 시그니처는 `db_path: str = _DB_PATH` 였다. 파이썬은 기본 인자를
           **모듈을 읽을 때 한 번** 평가하므로, 나중에 `_DB_PATH` 를 임시 경로로
           바꿔도 굳어 버린 옛 값이 쓰인다.
        ② `db_path or _DB_PATH` 도 안 된다. **빈 문자열이 운영 원장으로 떨어진다** —
           경로 계산이 빈 값을 낸 바로 그때 운영 파일이 열린다. `None` 만 「지정하지
           않음」으로 인정한다. 빈 문자열은 **잘못된 값**이고, 잘못된 값의 올바른
           결말은 폴백이 아니라 실패다.
        ③ 예전에는 여기서 `_init_db()` 를 불렀다. 모듈 끝의 전역 싱글턴이 **import
           되는 순간** 운영 파일을 만들고 열었다 — autouse fixture 는 그보다 **늦다.**
           수집 단계에서 이미 늦은 것이다. 그래서 실제 사용 직전까지 미룬다."""
        self.db_path = _DB_PATH if db_path is None else db_path
        self._lock = threading.Lock()
        #: 어떤 경로로 스키마를 준비했는지. `db_path` 가 나중에 바뀌면(격리) 다시 준비한다.
        self._prepared_for: Optional[str] = None

    def _ready(self) -> None:
        """첫 사용 직전에 스키마를 준비한다. **`__init__` 에서 부르지 않는다.**

        ⚠️ import 시점에 파일을 만들면 「테스트가 시작되기 전에 이미 운영 파일을
          건드린 상태」가 된다. 그 뒤에 무엇을 격리해도 늦다."""
        if self._prepared_for != self.db_path:
            self._init_db()
            self._prepared_for = self.db_path

    # ── 인프라 (master_data.py 와 동일 규약) ──────────────────────────────
    def _connect(self) -> sqlite3.Connection:
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA busy_timeout = 5000")
        except Exception:
            pass
        return conn

    def _init_db(self):
        conn = self._connect()
        try:
            conn.executescript(_DDL)
            conn.commit()
        finally:
            conn.close()

    def _ensure_tables(self) -> bool:
        try:
            self._init_db()
            return True
        except Exception:
            return False

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    # ── 기록 (append only — update/delete 는 의도적으로 없다) ──────────────
    def append(self, event_type: str, subject_type: str, subject_id: str,
               actor_type: str = "system", actor_id: str = "",
               decision: str = "", rationale: str = "",
               evidence_refs: Optional[List[Any]] = None,
               input_version_refs: Optional[List[Any]] = None,
               output_version_refs: Optional[List[Any]] = None,
               parent_event_id: str = "",
               tenant_id: str = "tenant_default", enterprise_scope_id: str = "",
               entity_mode: str = "REAL",
               project_id: str = "", blueprint_id: str = "") -> Dict[str, Any]:
        """이벤트 1건을 이력 끝에 붙인다.

        ⚠️ **기록 실패는 삼키지 않는다.** 텔레메트리는 부가 기능이라 실패를 삼켰지만, Ledger 는
          "왜 이 결정을 했는가"의 유일한 근거다. 조용히 누락되면 승인 이력이 없는 승인이 생긴다.
          호출부가 감사 실패를 인지하고 판단할 수 있도록 예외를 올린다."""
        self._ready()
        row = self._build_row(
            event_type=event_type, subject_type=subject_type, subject_id=subject_id,
            actor_type=actor_type, actor_id=actor_id, decision=decision,
            rationale=rationale, evidence_refs=evidence_refs,
            input_version_refs=input_version_refs, output_version_refs=output_version_refs,
            parent_event_id=parent_event_id, tenant_id=tenant_id,
            enterprise_scope_id=enterprise_scope_id, entity_mode=entity_mode,
            project_id=project_id, blueprint_id=blueprint_id)
        # ⚠️ `db_path` 가 상대 경로라 **작업 디렉터리가 바뀌면 다른 파일을 가리킨다**(테스트가 tmp
        #   로 chdir 하는 경우, 서비스가 다른 cwd 로 기동되는 경우). 그 파일에는 테이블이 없어
        #   `no such table` 이 난다 — `org_directory._ensure_tables` 에서 실측된 것과 같은 문제다.
        #   한 번 스키마를 만들고 재시도한다. 그래도 실패하면 **예외를 올린다**(삼키지 않는다) —
        #   감사 기록 누락은 호출부가 알아야 한다.
        for attempt in (0, 1):
            try:
                with self._lock, self._connect() as conn:
                    self._insert(conn, row)
                return self._to_public(row)
            except sqlite3.OperationalError:
                if attempt == 0 and self._ensure_tables():
                    continue
                raise
        raise DecisionLedgerError("감사 기록에 실패했습니다.")   # 도달 불가(방어)

    def _build_row(self, event_type: str, subject_type: str, subject_id: str,
                   actor_type: str = "system", actor_id: str = "",
                   decision: str = "", rationale: str = "",
                   evidence_refs: Optional[List[Any]] = None,
                   input_version_refs: Optional[List[Any]] = None,
                   output_version_refs: Optional[List[Any]] = None,
                   parent_event_id: str = "",
                   tenant_id: str = "tenant_default", enterprise_scope_id: str = "",
                   entity_mode: str = "REAL",
                   project_id: str = "", blueprint_id: str = "") -> Dict[str, Any]:
        """검증 + 행 구성. **`append` 와 `transaction()` 이 같은 이 함수를 쓴다** —
        두 벌이면 트랜잭션 경로만 검증이 느슨해지는 날이 온다."""
        if event_type not in EVENT_TYPES:
            raise DecisionLedgerError(f"등록되지 않은 event_type 입니다: {event_type}")
        #: ★★★ [MVP-P0 ①-B / P1] **온톨로지 이벤트는 주체 조합까지 검증한다.**
        #:
        #: ⚠️ 유형만 맞고 주체가 아무거나면, 「관계 승인」 이벤트에 프로젝트 id 를 넣어
        #:   두고 나중에 그 이벤트로 관계를 통과시킬 수 있다.
        _ONTOLOGY_SUBJECT = {
            "ONTOLOGY_MODEL_APPROVED": "ontology_model_contract",
            "ONTOLOGY_RELATION_APPROVED": "ontology_relation",
            "ONTOLOGY_RELATION_RETIRED": "ontology_relation",
            "DATASET_OWNERSHIP_APPROVED": "dataset_ownership_binding",
            "DATASET_OWNERSHIP_REVOKED": "dataset_ownership_binding",
            "CALC_CAPABILITY_APPROVED": "calc_capability",
            "CALC_CAPABILITY_REVOKED": "calc_capability",
            "CALC_BASELINE_SEALED": "calc_baseline",
            "CALC_BASELINE_REVOKED": "calc_baseline",
            #: ★★★ [2026-08-23] 앱 계약 승인·반려도 **대상 종류를 못박는다.**
            #:
            #: ⚠️ 이름만 허용목록에 있고 주체는 열려 있었다. 그러면
            #:   `APP_CONTRACT_APPROVED` 를 `project` 주체로 남겨 두고 나중에 그 사건을
            #:   계약 승인 근거로 읽을 수 있다 — 온톨로지·소유권에서 이미 막은 구멍이다.
            #: ★ 위 머리말이 「subject_id 는 계약 지문이다」라고 이미 적어 두었는데,
            #:   코드가 그것을 강제하지 않았다(주석이 코드를 대신 주장하던 자리).
            "APP_CONTRACT_REVIEW_REQUESTED": "app_contract",
            "APP_CONTRACT_APPROVED": "app_contract",
            "APP_CONTRACT_REJECTED": "app_contract",
            # ★★★ [4.1c-B P0-4] 소유권 승인·철회도 **대상 종류를 못박는다.**
            #   ⚠️ 앞 판은 이름만 허용목록에 넣고 주체 검증을 하지 않았다. 그러면
            #     `DATASET_OWNERSHIP_APPROVED` 를 `app_dataset` 이나 `project` 주체로
            #     남겨 두고, 나중에 그 사건으로 결속을 통과시킬 수 있다 —
            #     온톨로지에서 이미 같은 구멍을 막았는데 새 유형에 다시 낸 것이다.

        }
        #: ★★★ [2026-08-20 Supervisor 지적] 철회는 **관계와 계약 둘 다** 대상이 될 수
        #:   있다. `ontology_relation` 으로 고정하면 **모델 계약 승인을 철회할 방법이
        #:   없다** — 잘못 설치된 계약을 되돌릴 수 없다는 뜻이다.
        _REVOKE_SUBJECTS = ("ontology_relation", "ontology_model_contract")
        if event_type == "ONTOLOGY_APPROVAL_REVOKED":
            if subject_type not in _REVOKE_SUBJECTS:
                raise DecisionLedgerError(
                    f"'ONTOLOGY_APPROVAL_REVOKED' 의 subject_type 은 "
                    f"{list(_REVOKE_SUBJECTS)} 중 하나여야 "
                    f"합니다(받은 값: '{subject_type}').")
        want_subject = _ONTOLOGY_SUBJECT.get(event_type)
        if want_subject and subject_type != want_subject:
            raise DecisionLedgerError(
                f"'{event_type}' 의 subject_type 은 '{want_subject}' "
                f"여야 합니다(받은 값: '{subject_type}').")
        #: ⚠️ 철회는 **무엇을 철회하는지** 가리켜야 한다. 부모 없는 철회는 아무것도
        #:   무효로 만들지 못하면서 «철회했다» 는 기록만 남긴다.
        #: ⚠️ 철회는 **무엇을 철회하는지** 가리켜야 한다. 부모 없는 철회는 아무것도
        #:   무효로 만들지 못하면서 «철회했다» 는 기록만 남긴다. 유형을 늘릴 때 이
        #:   목록에 넣지 않으면 그 유형만 조용히 느슨해진다.
        if event_type in _REVOCATION_EVENTS and not (parent_event_id or "").strip():
            raise DecisionLedgerError(
                f"'{event_type}' 는 parent_event_id 로 원 승인을 가리켜야 합니다.")
        if subject_type not in SUBJECT_TYPES:
            raise DecisionLedgerError(f"등록되지 않은 subject_type 입니다: {subject_type}")
        if actor_type not in ACTOR_TYPES:
            raise DecisionLedgerError(f"actor_type 은 {ACTOR_TYPES} 중 하나여야 합니다.")
        if not subject_id:
            raise DecisionLedgerError("subject_id 는 필수입니다.")
        if event_type == "CORRECTION" and not parent_event_id:
            # 정정인데 대상이 없으면 무엇을 정정하는지 알 수 없다 — 이력이 거짓이 된다.
            raise DecisionLedgerError("CORRECTION 이벤트는 parent_event_id 가 필수입니다.")

        row = {
            "event_id": f"dle_{uuid.uuid4().hex[:14]}",
            "tenant_id": tenant_id or "tenant_default",
            "enterprise_scope_id": enterprise_scope_id or "",
            "entity_mode": entity_mode or "REAL",
            "project_id": project_id or "",
            "blueprint_id": blueprint_id or "",
            "event_type": event_type,
            "subject_type": subject_type,
            "subject_id": subject_id,
            "actor_type": actor_type,
            "actor_id": actor_id or "",
            "decision": decision or "",
            "rationale": rationale or "",
            "evidence_refs_json": json.dumps(evidence_refs or [], ensure_ascii=False,
                                             sort_keys=True),
            "input_version_refs_json": json.dumps(input_version_refs or [], ensure_ascii=False,
                                                  sort_keys=True),
            "output_version_refs_json": json.dumps(output_version_refs or [], ensure_ascii=False,
                                                   sort_keys=True),
            "parent_event_id": parent_event_id or "",
            "created_at": self._now(),
        }
        return row

    def _insert(self, conn: sqlite3.Connection, row: Dict[str, Any]) -> Dict[str, Any]:
        """체인 계산 + INSERT. **락을 이미 쥔 상태**에서 호출한다.

        ⚠️ `append` 와 `transaction()` 이 **같은 이 함수**를 쓴다. 두 벌로 만들면
          한쪽만 고쳐지는 날 체인 해시가 갈리고, 그때 `verify_chain` 은 「누군가
          장부를 고쳤다」고 말한다 — 실제로는 우리가 두 번 구현했을 뿐인데."""
        parent_event_id = row.get("parent_event_id") or ""
        parent = None
        if parent_event_id:
            parent = conn.execute(
                "SELECT event_type, subject_type, subject_id "
                "  FROM decision_ledger_events WHERE event_id=?",
                (parent_event_id,)).fetchone()
            if not parent:
                raise DecisionLedgerError(
                    f"존재하지 않는 parent_event_id 입니다: {parent_event_id}")

        #: ★★★ [MVP-P0 ①-B / 2026-08-20] **철회는 «그 승인의 그 대상» 이어야 한다.**
        #:
        #: ⚠️⚠️ 부모 연결만 보면, **다른 관계 id 를 적은 철회**로도 원 승인을 무효화할 수
        #:   있다. 그러면 「무엇이 철회됐는가」가 이력에서 어긋나고, 감사에서 두 기록이
        #:   서로 다른 대상을 가리킨다.
        #: ★ 그래서 부모가 온톨로지 승인인지, 대상 종류·식별자가 같은지까지 본다.
        #: ★★★ [4.1c-B P0-4] 소유권 철회에 **같은 검증**을 적용한다. 온톨로지에만 두면
        #:   유형이 늘 때마다 검증이 갈라지고, 새 유형은 언제나 느슨한 쪽으로 태어난다.
        if row.get("event_type") in _REVOCATION_EVENTS:
            _APPROVALS = _REVOCATION_PARENTS[str(row.get("event_type"))]
            ptype = str(parent["event_type"]) if parent else ""
            if ptype not in _APPROVALS:
                raise DecisionLedgerError(
                    f"'{row.get('event_type')}' 의 parent_event_id 는 {list(_APPROVALS)} "
                    f"중 하나여야 합니다(부모 유형: '{ptype or '(없음)'}').")
            if str(parent["subject_type"]) != str(row.get("subject_type") or ""):
                raise DecisionLedgerError(
                    f"철회 대상 종류가 원 승인과 다릅니다: "
                    f"'{row.get('subject_type')}' ≠ '{parent['subject_type']}'.")
            if str(parent["subject_id"]) != str(row.get("subject_id") or ""):
                raise DecisionLedgerError(
                    f"철회 대상이 원 승인과 다릅니다: "
                    f"'{row.get('subject_id')}' ≠ '{parent['subject_id']}'.")
        last = conn.execute("SELECT seq, event_hash FROM decision_ledger_events "
                            "ORDER BY seq DESC LIMIT 1").fetchone()
        row["seq"] = (int(last["seq"]) + 1) if last else 1
        row["prev_hash"] = last["event_hash"] if last else ""
        row["event_hash"] = _compute_hash(row, row["prev_hash"])
        cols = ", ".join(row.keys())
        marks = ", ".join("?" for _ in row)
        conn.execute(f"INSERT INTO decision_ledger_events ({cols}) VALUES ({marks})",
                     tuple(row.values()))
        return row

    # ── 조회와 기록을 한 트랜잭션으로 ────────────────────────────────────
    @contextlib.contextmanager
    def transaction(self):
        """**조회 → 판단 → 기록**을 하나의 락·트랜잭션 안에서 한다.

        ★★★ 「열린 요청이 있으면 새로 만들지 않는다」 같은 규칙은 조회와 기록 사이에
          틈이 있으면 지켜지지 않는다. 재시작이 겹치거나 두 요청이 동시에 오면 그
          틈에서 **같은 요청이 두 건** 생기고, 그러면 승인이 어느 쪽에 붙었는지
          아무도 답할 수 없다.
        ⚠️ 블록 안에서는 `append` 를 부르지 않는다(같은 락을 다시 잡아 교착한다) —
          `txn.append(...)` 를 쓴다."""
        self._ready()
        with self._lock, self._connect() as conn:
            yield _LedgerTransaction(self, conn)

    # ── 조회 ──────────────────────────────────────────────────────────────
    @staticmethod
    def _to_public(r: Dict[str, Any]) -> Dict[str, Any]:
        d = dict(r)
        for k in ("evidence_refs", "input_version_refs", "output_version_refs"):
            try:
                d[k] = json.loads(d.pop(f"{k}_json") or "[]")
            except Exception:
                d[k] = []
        # §5.2 — 근거가 없는 결정은 '검증되지 않은 추정'으로 읽혀야 한다. 조회부가 판단할 수
        #   있도록 파생 플래그를 준다(저장하지 않는다 — 규칙이므로 언제든 재계산 가능).
        d["is_substantiated"] = bool(d.get("evidence_refs"))
        return d

    def get_event(self, event_id: str) -> Optional[Dict[str, Any]]:
        self._ready()
        for attempt in (0, 1):
            try:
                with self._connect() as conn:
                    r = conn.execute("SELECT * FROM decision_ledger_events WHERE event_id=?",
                                     (event_id,)).fetchone()
                return self._to_public(dict(r)) if r else None
            except sqlite3.OperationalError:
                if attempt == 0 and self._ensure_tables():
                    continue
                return None
            except Exception:
                return None
        return None

    def has_invalidating_child(self, parent_event_id: str,
                               event_types: Sequence[str]) -> bool:
        """이 이벤트를 **부모로 가리키는** 무효화 이벤트가 있는가.

        ★★★ [2026-08-20 Supervisor 지적 P0-2] `list_events()` 로 대신하면 안 된다:

          · `LIMIT` 이 있다 — 철회 뒤에 **무관한 이벤트가 100건 넘게 쌓이면** 철회가
            조회 범위 밖으로 밀려나고 **원 승인이 되살아난다.**
          · 판독 실패를 **빈 배열로 접는다** — 그러면 원장 장애가 「철회 없음」이 된다.

        ★ 그래서 여기서는 **제한 없이 인덱스로** 묻고, 못 읽으면 **던진다.**
          「모르니까 유효」는 승인 판정에서 가장 위험한 기본값이다.

        ⚠️ 판독 실패는 `DecisionLedgerError` 다 — 호출부가 그것을 «없음» 으로 접지
          못하게 예외로 올린다."""
        pid = str(parent_event_id or "").strip()
        wanted = tuple(str(t).strip() for t in (event_types or ()) if str(t).strip())
        if not pid or not wanted:
            return False
        self._ready()
        marks = ",".join("?" * len(wanted))
        sql = ("SELECT 1 FROM decision_ledger_events "
               f"WHERE parent_event_id=? AND event_type IN ({marks}) LIMIT 1")
        last = None
        for attempt in (0, 1):
            try:
                with self._connect() as conn:
                    row = conn.execute(sql, (pid, *wanted)).fetchone()
                return row is not None
            except sqlite3.OperationalError as exc:
                last = exc
                if attempt == 0 and self._ensure_tables():
                    continue
                break
            except Exception as exc:                       # pragma: no cover - 방어
                last = exc
                break
        #: ⚠️ 빈 결과로 접지 않는다 — 「못 읽었다」와 「철회가 없다」는 다른 사실이다.
        raise DecisionLedgerError(
            f"원장을 읽지 못했습니다"
            f"(무효화 이벤트 조회): {last}")

    def get_event_strict(self, event_id: str) -> Optional[Dict[str, Any]]:
        """`get_event` 와 같지만 **판독 실패를 던진다.**

        ★★★ [2026-08-20 Supervisor 지적] `get_event()` 는 DB 장애를 `None` 으로 접는다.
          조회 화면에서는 그편이 편하지만, **승인 판정**에서는 그것이 곧
          「승인 이벤트가 없다」가 되고 — 더 위험하게는 반대로, 장애가 나면 승인이
          조용히 거부/허용되는 쪽으로 기운다.

        ⚠️ 승인처럼 «모르면 막아야 하는» 자리는 **모른다는 사실 자체를 알아야** 한다.
          그래서 여기서는 `DecisionLedgerError` 로 올린다."""
        self._ready()
        last = None
        for attempt in (0, 1):
            try:
                with self._connect() as conn:
                    r = conn.execute(
                        "SELECT * FROM decision_ledger_events WHERE event_id=?",
                        (event_id,)).fetchone()
                return self._to_public(dict(r)) if r else None
            except sqlite3.OperationalError as exc:
                last = exc
                if attempt == 0 and self._ensure_tables():
                    continue
                break
            except Exception as exc:                       # pragma: no cover - 방어
                last = exc
                break
        raise DecisionLedgerError(
            f"원장을 읽지 못했습니다"
            f"(승인 이벤트 조회): {last}")

    def list_events(self, subject_type: str = "", subject_id: str = "",
                    event_type: str = "", project_id: str = "", blueprint_id: str = "",
                    tenant_id: str = "", entity_mode: str = "",
                    limit: int = 100) -> List[Dict[str, Any]]:
        self._ready()
        sql = "SELECT * FROM decision_ledger_events"
        where, params = [], []
        for col, val in (("subject_type", subject_type), ("subject_id", subject_id),
                         ("event_type", event_type), ("project_id", project_id),
                         ("blueprint_id", blueprint_id), ("tenant_id", tenant_id),
                         ("entity_mode", entity_mode)):
            if val:
                where.append(f"{col}=?")
                params.append(val)
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY seq DESC LIMIT ?"
        params.append(max(1, min(int(limit or 100), 1000)))
        for attempt in (0, 1):
            try:
                with self._connect() as conn:
                    return [self._to_public(dict(r))
                            for r in conn.execute(sql, params).fetchall()]
            except sqlite3.OperationalError:
                if attempt == 0 and self._ensure_tables():
                    continue
                return []
        return []

    def list_events_strict(self, subject_type: str = "", subject_id: str = "",
                           event_type: str = "", project_id: str = "",
                           blueprint_id: str = "", tenant_id: str = "",
                           entity_mode: str = "", limit: int = 100) -> List[Dict[str, Any]]:
        """`list_events` 와 같지만 **판독 실패와 절단을 던진다.**

        ★★★ [4.1c-E P0-2] `list_events()` 는 두 가지를 조용히 접는다:

          · SQLite 판독 실패 → **빈 배열.** 그러면 「사건이 없다」와 「못 읽었다」가
            같은 모양이 되고, 장애 중에 보고가 「0건」이라고 말한다 — 아무 문제도 없다는
            뜻으로 읽힌다.
          · `LIMIT` 초과 → **부분 결과.** 부분 결과를 전체로 읽으면 집계가 틀리고,
            그 틀린 숫자가 「우리는 N건을 검토했다」로 쓰인다.

        ★ 세는 자리·판정하는 자리에서는 **모른다는 사실 자체를 알아야** 한다. 화면 목록은
          `list_events` 로 편하게 읽어도 되지만, 감사 집계는 이 함수를 쓴다.

        ⚠️ 한도에 닿으면 예외다. 「경고를 찍고 부분 결과를 돌려주는」 선택은 호출부가
          그것을 전체로 쓰는 것을 막지 못한다(실제로 그렇게 썼다)."""
        self._ready()
        cap = max(1, min(int(limit or 100), 1000))
        sql = "SELECT * FROM decision_ledger_events"
        where, params = [], []
        for col, val in (("subject_type", subject_type), ("subject_id", subject_id),
                         ("event_type", event_type), ("project_id", project_id),
                         ("blueprint_id", blueprint_id), ("tenant_id", tenant_id),
                         ("entity_mode", entity_mode)):
            if val:
                where.append(f"{col}=?")
                params.append(val)
        if where:
            sql += " WHERE " + " AND ".join(where)
        #: ★ 한도보다 **하나 더** 읽는다 — 그래야 「잘렸다」를 알 수 있다. 정확히 한도만
        #:   읽으면 «딱 맞는 경우» 와 «넘친 경우» 를 구분할 수 없다.
        sql += " ORDER BY seq DESC LIMIT ?"
        last = None
        for attempt in (0, 1):
            try:
                with self._connect() as conn:
                    rows = conn.execute(sql, (*params, cap + 1)).fetchall()
                if len(rows) > cap:
                    raise DecisionLedgerError(
                        f"원장 조회가 한도({cap})를 넘었습니다 — 부분 결과를 전체로 쓰지 "
                        f"않습니다. 조건을 좁히거나 페이지네이션이 필요합니다.")
                return [self._to_public(dict(r)) for r in rows]
            except sqlite3.OperationalError as exc:
                last = exc
                if attempt == 0 and self._ensure_tables():
                    continue
                break
            except DecisionLedgerError:
                raise
            except Exception as exc:                       # pragma: no cover - 방어
                last = exc
                break
        raise DecisionLedgerError(f"원장을 읽지 못했습니다(목록 조회): {last}")

    def subject_history(self, subject_type: str, subject_id: str) -> List[Dict[str, Any]]:
        self._ready()
        """한 대상의 결정 이력(오래된 것부터). "왜 이렇게 됐나"에 답하는 기본 조회."""
        rows = self.list_events(subject_type=subject_type, subject_id=subject_id, limit=1000)
        return sorted(rows, key=lambda r: r["seq"])

    # ── 변조 탐지 ─────────────────────────────────────────────────────────
    def verify_chain(self) -> Dict[str, Any]:
        self._ready()
        """해시 체인을 재계산해 불일치를 찾는다.

        ⚠️ **한계**: 이것은 DB 파일 직접 조작을 *막지* 못한다. 탐지만 한다. 중간 이벤트를 고치면
          그 이후 전부 불일치로 뜨므로 어디서부터 손댔는지는 알 수 있다. 진짜 위조 방지는 외부
          append-only 저장소나 서명이 필요하며 이 단계의 범위가 아니다."""
        try:
            with self._connect() as conn:
                rows = [dict(r) for r in conn.execute(
                    "SELECT * FROM decision_ledger_events ORDER BY seq").fetchall()]
        except Exception as e:
            return {"ok": False, "checked": 0, "broken": [], "error": str(e)}
        broken, prev = [], ""
        for r in rows:
            expected = _compute_hash(r, prev)
            if r["event_hash"] != expected or (r.get("prev_hash") or "") != prev:
                broken.append({"event_id": r["event_id"], "seq": r["seq"]})
            prev = r["event_hash"]      # 체인은 저장된 값으로 이어간다(이후 전부 깨져 보이게)
        return {"ok": not broken, "checked": len(rows), "broken": broken,
                "hash_version": _HASH_VERSION,
                "limitation": "직접 DB 조작을 막지는 못하며 불일치 탐지만 가능합니다."}


class _LedgerTransaction:
    """`DecisionLedger.transaction()` 안에서만 산다.

    ★ 어휘를 **원장의 말**로 유지한다 — 「열린 계약 검토 요청」 같은 도메인 개념을
      여기에 넣지 않는다. 그러면 원장이 계약을 알게 되고, 다음 도메인이 생길 때
      또 하나가 들어온다. 조합은 호출부가 한다."""

    def __init__(self, ledger: "DecisionLedger", conn: sqlite3.Connection):
        self._ledger = ledger
        self._conn = conn

    def find_events(self, *, event_type: str = "", project_id: str = "",
                    subject_type: str = "", subject_id: str = "",
                    limit: int = 100) -> List[Dict[str, Any]]:
        """조건에 맞는 이벤트를 **오래된 순**으로 돌려준다.

        ⚠️ 오래된 순인 것이 중요하다 — 「가장 처음 열린 요청」이 정본이어야 재시작이
          겹쳐도 같은 답이 나온다."""
        where, params = [], []
        for col, val in (("event_type", event_type), ("project_id", project_id),
                         ("subject_type", subject_type), ("subject_id", subject_id)):
            if val:
                where.append(f"{col}=?")
                params.append(val)
        sql = "SELECT * FROM decision_ledger_events"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY seq ASC LIMIT ?"
        params.append(int(limit))
        rows = self._conn.execute(sql, tuple(params)).fetchall()
        return [self._ledger._to_public(dict(r)) for r in rows]

    def child_event_types(self, parent_event_id: str) -> List[str]:
        """이 이벤트를 부모로 삼는 자식들의 `event_type` 목록."""
        if not parent_event_id:
            return []
        rows = self._conn.execute(
            "SELECT event_type FROM decision_ledger_events WHERE parent_event_id=? "
            "ORDER BY seq ASC", (parent_event_id,)).fetchall()
        return [str(r["event_type"]) for r in rows]

    def append(self, **kwargs) -> Dict[str, Any]:
        """`DecisionLedger.append` 와 **같은 검증·같은 체인**으로 기록한다."""
        row = self._ledger._build_row(**kwargs)
        self._ledger._insert(self._conn, row)
        return self._ledger._to_public(row)



def visible_events(rows: Sequence[Dict[str, Any]], *, unrestricted: bool,
                   readable_dept_ids: Any = (), actor_id: str = "") -> List[Dict[str, Any]]:
    """원장 사건을 **부서 범위로** 거른다. 이 규칙의 **정본은 여기 하나**다.

    ★★★ [4.1c-E P0-1] 앞 판은 이 규칙이 `api/routes/ledger_control._filter_by_dept` 에만
      있었고, 미물질화 승인 보고는 **아무 필터도 지나지 않았다.** 그래서 A 조직 관리자가
      B 조직의 승인 ID·행위자·대상 지문과 **건수**를 볼 수 있었다(실측).

    ⚠️ 같은 규칙을 두 곳에 쓰면 새로 만드는 쪽이 언제나 느슨하게 태어난다 — 이 저장소에서
      원장 철회 검증이 정확히 그렇게 갈렸다(4.1c-B P0-4). 그래서 규칙을 원장 모듈로
      끌어올리고 라우트가 이것을 쓴다.

    규칙:
      · `enterprise_scope_id` 는 **부서 id** 다(ECM-lite — E1 에서 노드로 승격 예정).
      · 범위가 비어 있는 사건은 **무제한 권한자와 행위자 본인에게만** 보인다.
        귀속 불명을 통과시키면 「누구 것도 아닌 승인」이 전원에게 보인다(fail-closed).
    """
    if unrestricted:
        return list(rows)
    readable = {str(x) for x in (readable_dept_ids or ()) if str(x)}
    me = str(actor_id or "")
    out = []
    for r in rows:
        scope = str(r.get("enterprise_scope_id") or "")
        if scope and scope in readable:
            out.append(r)
        elif not scope and me and str(r.get("actor_id") or "") == me:
            out.append(r)          # 귀속 없는 사건이라도 자기 이력은 볼 수 있다
    return out

decision_ledger = DecisionLedger()
