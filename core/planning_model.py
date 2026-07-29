"""[M4] 경영계획 디지털트윈 — 데이터 모델과 **결정론적 계산 엔진**. LLM 0콜.

명세서 §11(경영 시뮬레이션) · §17(첫 파일럿: 경영계획–실적–시나리오)의 데이터 계층이다.

## 이 모듈이 지키는 단 하나의 규칙

> **실제(Actual) · 계획(Plan) · 예측(Forecast) · 시나리오(Scenario)를 절대 섞지 않는다**(§11.3).

이것을 `value_kind` 라는 **필수 컬럼**으로 강제한다. 기본값을 두지 않는다 — 기본값이 있으면
호출자가 생각 없이 넣고, 그 순간 "실적처럼 보이는 계획"이 만들어진다. 경영 보고에서 그것은
숫자 하나가 틀린 것이 아니라 **보고 전체의 신뢰가 무너지는 사건**이다.

## 계산은 왜 LLM 이 아닌가

§11.3 은 "수치 계산은 재현 가능한 함수·규칙·제약조건 모델로 구현한다"고 못박는다.
§17.3 의 파일럿 성공 기준에는 **"세 개의 시나리오를 동일 기준선에서 재현한다"** 가 있다.
LLM 은 같은 입력에 같은 출력을 보장하지 않으므로 이 기준을 원리적으로 만족할 수 없다.
LLM 의 몫은 가정 후보 제안·결과 설명·이상 탐지 **보조**뿐이다(§11.3).

## 범위 계약을 처음부터 넣는다

M2 의 범위 계약(`docs/design_m2_scope_contract_and_audit.md` §2)을 **테이블 생성 시점에**
넣는다. 나중에 붙이면 마이그레이션이 필요하고, 그 마이그레이션은 이 저장소에서 가장
되돌리기 어려운 작업이다. 경영 데이터는 특히 그렇다 — 조직별 손익은 새어 나가면 끝이다.

⚠️ 기본값은 `ORG_PRIVATE`(소유 조직만). "미지정 = 전사 공용"은 D-014 로 폐기됐다.
"""
import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

_DB_PATH = os.path.join("data", "planning.db")

# ── 값의 성격 (§11.3) — 섞이면 안 되는 네 가지 ────────────────────────────────
ACTUAL = "ACTUAL"        # 실제로 일어난 일
PLAN = "PLAN"            # 승인된 계획
FORECAST = "FORECAST"    # 현재 시점의 전망
SCENARIO = "SCENARIO"    # 가정 세트를 적용한 계산 결과
VALUE_KINDS = (ACTUAL, PLAN, FORECAST, SCENARIO)

# 범위 계약(§2.2) — 기본값은 소유 조직 전용이다.
SCOPE_ORG_PRIVATE = "ORG_PRIVATE"
SCOPE_ORG_SHARED = "ORG_SHARED"
SCOPE_ENTERPRISE_SHARED = "ENTERPRISE_SHARED"
SCOPE_SANDBOX = "SANDBOX"
SCOPE_LEGACY = "LEGACY_UNSCOPED"
SCOPE_TYPES = (SCOPE_ORG_PRIVATE, SCOPE_ORG_SHARED, SCOPE_ENTERPRISE_SHARED,
               SCOPE_SANDBOX, SCOPE_LEGACY)

# ── 계정 분류 ────────────────────────────────────────────────────────────────
#: 손익계산서에 들어가는 분류.
PL_CATEGORIES = ("REVENUE", "COGS", "SGA", "OTHER_INCOME", "OTHER_EXPENSE", "TAX")
#: 현금흐름에만 쓰이는 분류. **손익에는 들어가지 않는다** —
#  감가상각은 비용이지만 현금 유출이 아니고, CAPEX 는 현금 유출이지만 당기 비용이 아니다.
#  이 둘을 한 표에 섞으면 "이익이 나는데 현금이 없다"는 현실을 설명할 수 없다.
CF_CATEGORIES = ("DEPRECIATION", "WORKING_CAPITAL", "CAPEX", "FINANCING")

_DDL = """
-- 계정 체계 (§11.2 기준정보). 손익 계산의 뼈대.
CREATE TABLE IF NOT EXISTS plan_accounts (
    account_code TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    -- REVENUE | COGS | SGA | OTHER_INCOME | OTHER_EXPENSE | TAX
    category     TEXT NOT NULL,
    -- 부호 규약: 수익은 +1, 비용은 -1. 이것을 데이터로 두는 이유는 산식에 부호를
    -- 하드코딩하면 계정을 늘릴 때마다 코드를 고쳐야 하기 때문이다.
    sign         INTEGER NOT NULL DEFAULT 1,
    parent_code  TEXT DEFAULT '',
    created_at   TEXT NOT NULL
);

-- 계획/실적 값. **한 행이 하나의 (조직·계정·기간·성격) 사실**이다.
CREATE TABLE IF NOT EXISTS plan_facts (
    fact_id      TEXT PRIMARY KEY,
    org_id       TEXT NOT NULL,            -- 조직(ECM node)
    account_code TEXT NOT NULL,
    period       TEXT NOT NULL,            -- 'YYYY-MM' 또는 'YYYY'
    value_kind   TEXT NOT NULL,            -- ★ ACTUAL|PLAN|FORECAST|SCENARIO (기본값 없음)
    amount       REAL NOT NULL,
    currency     TEXT NOT NULL DEFAULT 'KRW',
    scenario_id  TEXT DEFAULT '',          -- SCENARIO 일 때만 채워진다
    version      INTEGER NOT NULL DEFAULT 1,
    source_ref   TEXT DEFAULT '',          -- 어디서 온 값인가(파일·연계·수기)
    created_at   TEXT NOT NULL,
    -- 범위 계약(M2 §2.1) — 처음부터 넣는다
    tenant_id            TEXT NOT NULL DEFAULT 'tenant_default',
    owner_organization_id TEXT NOT NULL DEFAULT '',
    scope_type           TEXT NOT NULL DEFAULT 'ORG_PRIVATE',
    classification       TEXT NOT NULL DEFAULT 'INTERNAL',
    entity_mode          TEXT NOT NULL DEFAULT 'REAL'
);
CREATE INDEX IF NOT EXISTS idx_fact_lookup
    ON plan_facts(org_id, period, value_kind, account_code);
CREATE INDEX IF NOT EXISTS idx_fact_scope
    ON plan_facts(tenant_id, owner_organization_id, scope_type, entity_mode);

-- 시나리오 (§11.5)
CREATE TABLE IF NOT EXISTS scenarios (
    scenario_id      TEXT PRIMARY KEY,
    name             TEXT NOT NULL,
    org_id           TEXT NOT NULL DEFAULT '',
    baseline_kind    TEXT NOT NULL DEFAULT 'PLAN',   -- 무엇 위에 가정을 얹는가
    baseline_period  TEXT NOT NULL DEFAULT '',
    status           TEXT NOT NULL DEFAULT 'draft',  -- draft | fixed
    owner            TEXT DEFAULT '',
    created_at       TEXT NOT NULL,
    tenant_id            TEXT NOT NULL DEFAULT 'tenant_default',
    owner_organization_id TEXT NOT NULL DEFAULT '',
    scope_type           TEXT NOT NULL DEFAULT 'ORG_PRIVATE',
    entity_mode          TEXT NOT NULL DEFAULT 'REAL'
);

-- 시나리오 가정 (§11.5 scenario_assumptions)
CREATE TABLE IF NOT EXISTS scenario_assumptions (
    assumption_id TEXT PRIMARY KEY,
    scenario_id   TEXT NOT NULL,
    target_kind   TEXT NOT NULL DEFAULT 'account',  -- account | driver
    target_code   TEXT NOT NULL,                    -- 계정코드 또는 동인 코드
    operator      TEXT NOT NULL,                    -- pct | delta | set
    value         REAL NOT NULL,
    unit          TEXT DEFAULT '',
    rationale     TEXT DEFAULT '',                  -- ★ 근거 없는 가정은 재현이 아니라 창작이다
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_assumption_scn ON scenario_assumptions(scenario_id);

-- 시뮬레이션 실행 이력 (§11.5 simulation_runs) — 재현성의 근거
CREATE TABLE IF NOT EXISTS simulation_runs (
    run_id         TEXT PRIMARY KEY,
    scenario_id    TEXT NOT NULL,
    engine_version TEXT NOT NULL,
    input_hash     TEXT NOT NULL,      -- 입력 스냅샷 지문
    status         TEXT NOT NULL DEFAULT 'completed',
    started_at     TEXT NOT NULL,
    completed_at   TEXT DEFAULT '',
    metrics_json   TEXT DEFAULT '{}'
);
"""

#: 산식이 바뀌면 올린다. 과거 실행 결과가 **어느 엔진으로 나왔는지** 모르면 재현이 불가능하다.
ENGINE_VERSION = "1.0.0"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class PlanningError(ValueError):
    """검증 실패 — 호출자에게 4xx 로 전달할 도메인 오류."""


class PlanningStore:
    def __init__(self, db_path: str = _DB_PATH):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

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

    # ── 계정 ──────────────────────────────────────────────────────────
    def upsert_account(self, account_code: str, name: str, category: str,
                       sign: int = 1, parent_code: str = "") -> dict:
        category = (category or "").upper()
        if category not in PL_CATEGORIES + CF_CATEGORIES:
            raise PlanningError(
                f"알 수 없는 계정 분류입니다: {category}. "
                f"손익 {PL_CATEGORIES} / 현금흐름 {CF_CATEGORIES}")
        if sign not in (1, -1):
            raise PlanningError("sign 은 +1(수익) 또는 -1(비용)이어야 합니다.")
        conn = self._connect()
        try:
            conn.execute(
                "INSERT INTO plan_accounts(account_code,name,category,sign,parent_code,created_at) "
                "VALUES(?,?,?,?,?,?) ON CONFLICT(account_code) DO UPDATE SET "
                "name=excluded.name, category=excluded.category, sign=excluded.sign, "
                "parent_code=excluded.parent_code",
                (account_code, name, category, sign, parent_code or "", _now()))
            conn.commit()
            r = conn.execute("SELECT * FROM plan_accounts WHERE account_code=?",
                             (account_code,)).fetchone()
            return dict(r)
        finally:
            conn.close()

    def list_accounts(self) -> List[dict]:
        conn = self._connect()
        try:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM plan_accounts ORDER BY category, account_code")]
        finally:
            conn.close()

    # ── 사실(계획/실적) ────────────────────────────────────────────────
    def put_fact(self, org_id: str, account_code: str, period: str, value_kind: str,
                 amount: float, currency: str = "KRW", scenario_id: str = "",
                 source_ref: str = "", owner_organization_id: str = "",
                 scope_type: str = SCOPE_ORG_PRIVATE, classification: str = "INTERNAL",
                 tenant_id: str = "tenant_default", entity_mode: str = "REAL") -> dict:
        """사실 1건 기록. **`value_kind` 는 필수이고 기본값이 없다.**

        ⚠️ 기본값을 두면 호출자가 생각 없이 넣고, 그 순간 '실적처럼 보이는 계획'이 만들어진다.
          경영 보고에서 그것은 숫자 하나가 틀린 것이 아니라 보고 전체의 신뢰가 무너지는 일이다."""
        vk = (value_kind or "").upper()
        if vk not in VALUE_KINDS:
            raise PlanningError(
                f"value_kind 는 {'|'.join(VALUE_KINDS)} 중 하나여야 합니다(받은 값: {value_kind!r}). "
                "실제·계획·예측·시나리오를 섞지 않는 것이 이 모델의 첫 번째 규칙입니다.")
        if vk == SCENARIO and not scenario_id:
            raise PlanningError("SCENARIO 값에는 scenario_id 가 필요합니다 — "
                                "어느 가정에서 나온 숫자인지 모르면 재현할 수 없습니다.")
        if vk != SCENARIO and scenario_id:
            raise PlanningError(f"{vk} 값에는 scenario_id 를 붙일 수 없습니다 — "
                                "시나리오 결과가 실적·계획으로 섞여 들어가는 경로입니다.")
        if (scope_type or "") not in SCOPE_TYPES:
            raise PlanningError(f"scope_type 은 {'|'.join(SCOPE_TYPES)} 중 하나여야 합니다.")
        if not str(period or "").strip():
            raise PlanningError("period 는 필수입니다('YYYY-MM' 또는 'YYYY').")

        fid = f"{org_id}|{account_code}|{period}|{vk}|{scenario_id}"
        conn = self._connect()
        try:
            prev = conn.execute("SELECT version FROM plan_facts WHERE fact_id=?", (fid,)).fetchone()
            version = (prev["version"] + 1) if prev else 1
            conn.execute(
                "INSERT INTO plan_facts(fact_id,org_id,account_code,period,value_kind,amount,"
                "currency,scenario_id,version,source_ref,created_at,tenant_id,"
                "owner_organization_id,scope_type,classification,entity_mode) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(fact_id) DO UPDATE SET amount=excluded.amount, "
                "version=excluded.version, source_ref=excluded.source_ref, "
                "created_at=excluded.created_at",
                (fid, org_id, account_code, period, vk, float(amount), currency or "KRW",
                 scenario_id or "", version, source_ref or "", _now(),
                 tenant_id or "tenant_default", owner_organization_id or org_id,
                 scope_type, classification or "INTERNAL", entity_mode or "REAL"))
            conn.commit()
            return dict(conn.execute("SELECT * FROM plan_facts WHERE fact_id=?", (fid,)).fetchone())
        finally:
            conn.close()

    def list_facts(self, org_id: str = "", period: str = "", value_kind: str = "",
                   scenario_id: str = "", scope_node_id: str = "",
                   tenant_id: str = "", entity_mode: str = "REAL") -> List[dict]:
        """사실 조회. 조직 범위를 주면 **M2 범위 계약**으로 걸러진다."""
        sql = "SELECT * FROM plan_facts WHERE 1=1"
        args: List[Any] = []
        for col, val in (("org_id", org_id), ("period", period),
                         ("value_kind", (value_kind or "").upper()),
                         ("scenario_id", scenario_id)):
            if val:
                sql += f" AND {col}=?"
                args.append(val)
        conn = self._connect()
        try:
            rows = [dict(r) for r in conn.execute(sql + " ORDER BY account_code, period", args)]
        finally:
            conn.close()
        if not (scope_node_id or tenant_id):
            return rows
        from core.enterprise_context.scoping import filter_visible
        # 범위 판정은 `enterprise_scope_id` 키를 본다 — 소유 조직을 그 키로 넘겨 재사용한다
        # (판정 로직을 복제하면 반드시 어긋난다).
        for r in rows:
            r["enterprise_scope_id"] = r.get("owner_organization_id") or ""
        return filter_visible(rows, scope_node_id, tenant_id, entity_mode)


planning_store = PlanningStore()
