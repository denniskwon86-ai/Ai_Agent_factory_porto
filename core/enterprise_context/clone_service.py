"""[ECM E3] 가상 기업 Sandbox — **격리된 복제본을 만든다. 운영계 우회 통로가 아니다.**

## 이 모듈이 여는 문과 닫는 문

설계서 §7.1 의 흐름은 "실제 조직 또는 승인된 템플릿 선택 → 복제 범위·목적·유효기간 → 복사 정책
확인 → 가정값 → 격리 스냅샷 → 계산 → 비교/승인" 이다. 그동안 `CREATABLE_ENTITY_MODES` 가
`REAL` 만 허용해 `VIRTUAL` 생성을 막아 왔다(E3 선행 조건). 그 안전장치를 **없애지 않고** 문을 연다:

★ **가상 엔터티는 직접 생성할 수 없고 복제로만 만들어진다.** 일반 생성 경로
  (`POST /entities`)는 그대로 `REAL` 만 받는다. 이 모듈이 유일한 문이고, 문을 통과하려면
  원본·목적·유효기간·복사 정책이 함께 있어야 한다.
  ⚠️ 이유: 흐름을 안내 문구로만 적어 두면 지켜지지 않는다. `entity_mode="VIRTUAL"` 을 그냥
    허용하면 원본도 목적도 만료도 없는 가상 조직이 생기고, 그 조직의 가정값이 실제값과 섞인 채
    쌓인다(§13 위험표의 첫 줄). 흐름은 **구조로** 강제해야 한다.

## 복사 정책 — 무엇을 가져오고 무엇을 절대 안 가져오는가 (§7.1)

정책을 코드 한 곳(`COPY_POLICY` · `NEVER_COPIED`)에 두고 실행 결과를 시나리오 행에 남긴다.
"무엇을 복사했는지"를 나중에 알 수 없으면 가상 결과의 근거를 설명할 수 없다.

⚠️ `NEVER_COPIED` 는 **선택 항목이 아니다.** 호출자가 요청해도 거부한다 — 실거래·원장·개인정보와
  외부 시스템 자격증명·쓰기 권한이 복제되는 순간 "안전한 복제본"이라는 전제가 사라진다.

## 격리

- 복제된 노드는 **새 node_id 와 접두사 붙은 code** 를 갖는다(`V{n}_원본코드`). 같은 코드가 두
  문맥에 존재하면 `find_node_by_code` 가 어느 쪽을 돌려줄지 정렬 순서가 정하게 된다 —
  이 저장소는 이미 그 유형의 사고를 겪었다(부서 1:N 매핑).
- 가시성은 `scoping` 이 `entity_mode` 로 분리한다. 이 모듈은 트리를 섞지 않는 것만 보장한다.
- 가상 문맥의 외부 시스템 호출은 `assert_external_allowed()` 가 막는다(§8.3).

LLM 0콜.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from core.enterprise_context.context import (ENTITY_MODE_COMPETITOR, ENTITY_MODE_REAL,
                                             ENTITY_MODE_VIRTUAL)
from core.enterprise_context.models import (EnterpriseEntity, EnterpriseProfile,
                                            OrganizationEdge, OrganizationNode)
from core.enterprise_context.repository import EcmError, ecm_repository

#: 선택 복사 항목 — 기본값과 이유를 함께 둔다. 화면은 이 표를 그대로 보여주면 된다.
COPY_POLICY: Dict[str, Dict[str, Any]] = {
    "org_nodes": {"default": True, "label": "조직·노드 구조",
                  "why": "새 조직 설계의 출발점(§7.1)"},
    "profiles": {"default": True, "label": "회사 프로필·동의어",
                 "why": "업종·공정·용어 특성이 없으면 설계를 시작할 수 없다"},
    "process_kpi": {"default": False, "label": "표준 프로세스·KPI·에이전트 바인딩",
                    "why": "유사 사업을 빠르게 시작(선택 복사)"},
    "catalog": {"default": False, "label": "데이터 카탈로그 정의·데이터 계약",
                "why": "필요한 데이터셋을 명확히 함(참조 또는 선택 복사)"},
    "snapshots": {"default": False, "label": "승인된 집계 스냅샷",
                  "why": "기준선 비교와 시뮬레이션(선택 복사)"},
}

#: **절대 복사하지 않는다.** 호출자가 요청해도 거부한다(§7.1 복사 금지 행).
NEVER_COPIED: Dict[str, str] = {
    "transactions": "실제 거래·원장·개인정보 — 실제값 오염·보안 위험",
    "credentials": "외부 시스템 자격증명·MCP 쓰기 권한 — 가상환경의 운영계 접근 차단",
}

_ACTIVE = "ACTIVE"
_CLOSED = "CLOSED"
_PROMOTION_REQUESTED = "PROMOTION_REQUESTED"
_STATUSES = (_ACTIVE, _CLOSED, _PROMOTION_REQUESTED)

_DDL = """
CREATE TABLE IF NOT EXISTS scenario_entities (
    scenario_id       TEXT PRIMARY KEY,
    tenant_id         TEXT NOT NULL DEFAULT 'tenant_default',
    entity_id         TEXT NOT NULL,          -- 생성된 가상 엔터티
    clone_source_id   TEXT NOT NULL,          -- 복제 원본(실제 엔터티)
    snapshot_id       TEXT NOT NULL DEFAULT '',
    assumption_set_id TEXT NOT NULL DEFAULT '',
    purpose           TEXT NOT NULL,
    valid_until       TEXT NOT NULL,          -- YYYY-MM-DD (만료 없는 가상 조직은 없다)
    copied_json       TEXT NOT NULL DEFAULT '{}',
    refused_json      TEXT NOT NULL DEFAULT '{}',
    status            TEXT NOT NULL DEFAULT 'ACTIVE',
    created_by        TEXT NOT NULL DEFAULT '',
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_scenario_entity ON scenario_entities(entity_id);
CREATE INDEX IF NOT EXISTS idx_scenario_status ON scenario_entities(status);
"""


class SandboxError(ValueError):
    """정책 위반 — 4xx 로 전달한다."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def assert_external_allowed(entity_mode: str, what: str = "외부 시스템 호출") -> None:
    """§8.3 — 가상·경쟁사 문맥에서는 외부 운영 시스템을 부르지 않는다.

    ⚠️ 이 한 줄이 "가상 조직은 운영계의 우회 통로가 아니다"(비협상 4)의 실질이다. 가상 실험이
      운영 시스템을 읽기 시작하면, 그 결과는 더 이상 가정이 아니라 실제와 섞인 값이 된다.
      승인된 정적 스냅샷 또는 익명화된 안전 데이터만 쓴다."""
    if (entity_mode or ENTITY_MODE_REAL) in (ENTITY_MODE_VIRTUAL, ENTITY_MODE_COMPETITOR):
        raise SandboxError(
            f"가상·경쟁사 문맥에서는 {what}를 할 수 없습니다(§8.3) — 승인된 정적 스냅샷이나 "
            f"익명화된 데이터만 사용하십시오. 실제 문맥으로 전환한 뒤 다시 시도하십시오.")


class CloneService:
    def __init__(self, repository=None):
        self._lock = threading.RLock()
        self._repo = repository or ecm_repository

    # ── 저장소 ────────────────────────────────────────────────────────────
    def _connect(self) -> sqlite3.Connection:
        # ★ 경로를 캐시하지 않는다 — 테스트가 `db_path` 를 monkeypatch 하면 즉시 따라야 한다.
        conn = sqlite3.connect(self._repo.db_path)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA busy_timeout = 5000")
        except Exception:
            pass
        conn.executescript(_DDL)
        return conn

    # ── 복제 ──────────────────────────────────────────────────────────────
    def clone_to_virtual(self, base_entity_id: str, name_ko: str, purpose: str,
                         valid_until: str, actor: str = "", copy: Dict[str, bool] = None,
                         tenant_id: str = "tenant_default",
                         assumption_set_id: str = "", snapshot_id: str = "",
                         today: str = "") -> Dict[str, Any]:
        """실제 엔터티를 **격리된 가상 시나리오**로 복제한다.

        요구 항목이 하나라도 없으면 만들지 않는다 — 목적 없는 가상 조직은 아무도 정리하지 못하고,
        만료 없는 가상 조직은 영구 조직이 된다(이 저장소가 '한시 예외'에서 이미 겪은 유형)."""
        src = self._repo.get_entity(base_entity_id)
        if not src:
            raise SandboxError(f"복제 원본을 찾을 수 없습니다: {base_entity_id}")
        if src.entity_mode != ENTITY_MODE_REAL:
            # 가상의 가상은 계보를 추적할 수 없다 — 무엇을 근거로 한 가정인지 답할 수 없게 된다.
            raise SandboxError(
                f"복제 원본은 실제 운영 문맥이어야 합니다(현재 {src.entity_mode}) — "
                f"가상·경쟁사 모델을 다시 복제하면 어떤 실제 조직에서 나온 가정인지 알 수 없습니다.")
        if not (name_ko or "").strip():
            raise SandboxError("가상 조직 이름(name_ko)은 필수입니다.")
        if not (purpose or "").strip():
            raise SandboxError(
                "복제 목적(purpose)은 필수입니다 — 목적이 없는 가상 조직은 나중에 아무도 "
                "정리하지 못하고 영구 조직이 됩니다.")
        vu = self._check_valid_until(valid_until, today)

        # 복사 정책 확정 — 호출자가 준 값은 **선택 항목에만** 적용된다.
        chosen = {k: bool(v["default"]) for k, v in COPY_POLICY.items()}
        for k, v in (copy or {}).items():
            if k in NEVER_COPIED:
                raise SandboxError(
                    f"'{k}' 는 복사할 수 없습니다 — {NEVER_COPIED[k]}. 이 항목은 선택 사항이 "
                    f"아닙니다(§7.1).")
            if k not in COPY_POLICY:
                raise SandboxError(f"알 수 없는 복사 항목입니다: {k} (가능: {sorted(COPY_POLICY)})")
            chosen[k] = bool(v)

        scenario_id = f"scn_{uuid.uuid4().hex[:12]}"
        prefix = f"V{scenario_id[-4:]}_"

        with self._lock:
            virt = self._repo.upsert_entity(EnterpriseEntity(
                tenant_id=tenant_id, entity_type=src.entity_type,
                entity_mode=ENTITY_MODE_VIRTUAL, name_ko=name_ko.strip(),
                legal_name="",                       # 가상 조직에 법인명을 붙이지 않는다
                industry_code=src.industry_code, base_entity_id=src.entity_id,
                status="DRAFT",                      # 승인 전에는 초안이다(§4.1)
                source_ref=f"clone:{src.entity_id}"))

            counts = {"org_nodes": 0, "profiles": 0, "edges": 0}
            id_map: Dict[str, str] = {}
            if chosen["org_nodes"]:
                for n in self._source_nodes(src.entity_id, src.tenant_id or tenant_id):
                    new = self._repo.upsert_node(OrganizationNode(
                        entity_id=virt.entity_id, tenant_id=tenant_id, node_type=n.node_type,
                        code=(prefix + n.code) if n.code else "", name_ko=n.name_ko,
                        # dept_id 는 복사하지 않는다 — 실제 부서가 가상 노드를 가리키면
                        # 실제 사용자의 권한이 가상 문맥으로 새어 들어간다.
                        dept_id="", path_hint=n.path_hint, status=n.status))
                    id_map[n.node_id] = new.node_id
                    counts["org_nodes"] += 1
                # 구조(엣지)도 함께 옮긴다 — 노드만 복사하면 상하관계가 사라져 상속이 끊긴다.
                for e in self._repo.list_edges(tenant_id=src.tenant_id or tenant_id):
                    if e.from_node_id in id_map and e.to_node_id in id_map:
                        self._repo.add_edge(OrganizationEdge(
                            tenant_id=tenant_id, from_node_id=id_map[e.from_node_id],
                            to_node_id=id_map[e.to_node_id], relation_type=e.relation_type,
                            weight=e.weight, status=e.status))
                        counts["edges"] += 1
            if chosen["profiles"]:
                for old_id, new_id in id_map.items():
                    for pr in self._repo.list_profiles(scope_node_id=old_id):
                        self._repo.upsert_profile(EnterpriseProfile(
                            tenant_id=tenant_id, scope_node_id=new_id,
                            industry_code=pr.industry_code, profile_kind=pr.profile_kind,
                            payload=dict(pr.payload or {}),
                            inheritance_mode=pr.inheritance_mode,
                            # 승인은 복사하지 않는다 — 원본의 승인이 가상 가정의 승인이 될 수 없다.
                            status="DRAFT", approved_by="", approved_at=""))
                        counts["profiles"] += 1

            now = _now()
            copied = {k: (counts.get(k, 0) if k in counts else chosen[k]) for k in COPY_POLICY}
            copied["edges"] = counts["edges"]
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO scenario_entities (scenario_id, tenant_id, entity_id, "
                    "clone_source_id, snapshot_id, assumption_set_id, purpose, valid_until, "
                    "copied_json, refused_json, status, created_by, created_at, updated_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (scenario_id, tenant_id, virt.entity_id, src.entity_id, snapshot_id,
                     assumption_set_id, purpose.strip(), vu,
                     json.dumps(copied, ensure_ascii=False),
                     json.dumps(NEVER_COPIED, ensure_ascii=False),
                     _ACTIVE, actor or "", now, now))
                conn.commit()

        self._audit(scenario_id, actor, "가상 시나리오 생성",
                    f"원본={src.entity_id}({src.name_ko}) 가상={virt.entity_id} "
                    f"목적={purpose.strip()[:80]} 만료={vu} 복사={json.dumps(copied, ensure_ascii=False)}")
        return self.get_scenario(scenario_id)

    def _source_nodes(self, entity_id: str, tenant_id: str) -> List[OrganizationNode]:
        """복제 범위의 노드들 = 원본 엔터티의 노드 + **운영 하위 트리 전체.**

        ★★ [2026-07-31 실측] 엔터티의 노드만 복제하면 실제 데이터에서 **1건**만 복사된다.
          이 저장소의 조직도는 노드마다 엔터티가 1:1 이고 계층은 **엔터티 사이의 엣지**에 있다
          (LS → LS MnM → 사업부 → 공장). 그래서 "배터리소재 사업부를 복제" 하면 제1·제2공장이
          따라오지 않고, 복제본은 노드 하나짜리 껍데기가 된다 — 기능은 있는데 쓸 수 없는 상태다.
        ⚠️ `OPERATING_PARENT` 만 따라간다. `CONSOLIDATION_SCOPE`(지분 집계)를 따라가면 법인
          경계를 넘어 다른 회사가 복제된다 — 경영진 드릴다운에서 이미 같은 이유로 금지한 경로다."""
        from core.enterprise_context.models import REL_OPERATING_PARENT

        roots = [n for n in self._repo.list_nodes(tenant_id=tenant_id)
                 if n.entity_id == entity_id]
        seen = {n.node_id: n for n in roots}
        frontier = [n.node_id for n in roots]
        while frontier:
            nxt = []
            for nid in frontier:
                for child_id in self._repo.children(nid, REL_OPERATING_PARENT):
                    if child_id in seen:
                        continue
                    ch = self._repo.get_node(child_id)
                    if ch:
                        seen[child_id] = ch
                        nxt.append(child_id)
            frontier = nxt
        return list(seen.values())

    @staticmethod
    def _check_valid_until(valid_until: str, today: str = "") -> str:
        """만료일은 필수이고 미래여야 한다.

        ⚠️ 만료 없는 가상 조직은 영구 조직이 된다. 이 저장소는 같은 실패를 이미 봤다 —
          '한시 예외'가 만료를 갖지 않아 상시 규칙이 됐다."""
        vu = (valid_until or "").strip()
        if not vu:
            raise SandboxError(
                "유효기간(valid_until, YYYY-MM-DD)은 필수입니다 — 만료 없는 가상 조직은 "
                "영구 조직이 되고, 그 가정값이 계속 실제와 섞입니다.")
        try:
            d = date.fromisoformat(vu)
        except ValueError:
            raise SandboxError(f"유효기간 형식은 YYYY-MM-DD 입니다: {valid_until}")
        ref = date.fromisoformat(today) if today else datetime.now(timezone.utc).date()
        if d <= ref:
            raise SandboxError(f"유효기간이 이미 지났습니다({vu} ≤ {ref.isoformat()}).")
        return vu

    # ── 조회 ──────────────────────────────────────────────────────────────
    def get_scenario(self, scenario_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            r = conn.execute("SELECT * FROM scenario_entities WHERE scenario_id=?",
                             (scenario_id,)).fetchone()
        return self._row(r) if r else None

    def list_scenarios(self, status: str = "", entity_id: str = "",
                       today: str = "") -> List[Dict[str, Any]]:
        sql, params = "SELECT * FROM scenario_entities", []
        where = []
        if status:
            where.append("status=?"); params.append(status)
        if entity_id:
            where.append("entity_id=?"); params.append(entity_id)
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY created_at DESC"
        with self._connect() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [self._row(r, today) for r in rows]

    def active_scenario_of_node(self, node_id: str, today: str = "") -> Optional[Dict[str, Any]]:
        """이 노드가 속한 **살아 있는** 가상 시나리오. 만료된 것은 돌려주지 않는다."""
        n = self._repo.get_node(node_id)
        if not n:
            return None
        for s in self.list_scenarios(status=_ACTIVE, entity_id=n.entity_id, today=today):
            if not s["expired"]:
                return s
        return None

    def _row(self, r: sqlite3.Row, today: str = "") -> Dict[str, Any]:
        d = dict(r)
        for k in ("copied_json", "refused_json"):
            try:
                d[k[:-5]] = json.loads(d.pop(k) or "{}")
            except Exception:
                d[k[:-5]] = {}
        ref = date.fromisoformat(today) if today else datetime.now(timezone.utc).date()
        try:
            d["expired"] = date.fromisoformat(d["valid_until"]) <= ref
        except Exception:
            d["expired"] = True          # 해석 불가 = 만료로 본다(안전한 방향)
        d["visibility"] = ("만료됨 — 가상 문맥으로 유효하지 않습니다" if d["expired"]
                           else f"{d['valid_until']} 까지 유효한 가상 문맥")
        return d

    # ── 종료·승격 ─────────────────────────────────────────────────────────
    def close_scenario(self, scenario_id: str, actor: str = "", reason: str = "") -> Dict[str, Any]:
        """시나리오를 닫는다. **삭제하지 않는다** — 어떤 가정으로 무엇을 판단했는지가 감사 대상이다."""
        s = self.get_scenario(scenario_id)
        if not s:
            raise SandboxError(f"시나리오를 찾을 수 없습니다: {scenario_id}")
        with self._lock, self._connect() as conn:
            conn.execute("UPDATE scenario_entities SET status=?, updated_at=? WHERE scenario_id=?",
                         (_CLOSED, _now(), scenario_id))
            conn.commit()
        self._audit(scenario_id, actor, "가상 시나리오 종료", reason or "(사유 없음)")
        return self.get_scenario(scenario_id)

    def request_promotion(self, scenario_id: str, actor: str = "",
                          rationale: str = "") -> Dict[str, Any]:
        """가상 설계를 실제 조직 초안으로 **승격 요청**한다(§9 `promote-request`).

        ⚠️ 요청까지만이다. 자동 반영은 없다 — "가상 시나리오 결과를 실제 시스템에 자동 반영하지
          않는다"(§8.3)가 이 기능의 경계다. 승인은 사람이 실제 문맥에서 별도로 한다."""
        s = self.get_scenario(scenario_id)
        if not s:
            raise SandboxError(f"시나리오를 찾을 수 없습니다: {scenario_id}")
        if s["status"] == _CLOSED:
            raise SandboxError("종료된 시나리오는 승격 요청할 수 없습니다.")
        if s["expired"]:
            raise SandboxError(
                f"만료된 시나리오는 승격 요청할 수 없습니다(만료 {s['valid_until']}) — "
                f"만료된 가정으로 실제 조직을 바꿀 수 없습니다.")
        if not (rationale or "").strip():
            raise SandboxError("승격 사유(rationale)는 필수입니다 — 근거 없는 승격은 승인할 수 없습니다.")
        with self._lock, self._connect() as conn:
            conn.execute("UPDATE scenario_entities SET status=?, updated_at=? WHERE scenario_id=?",
                         (_PROMOTION_REQUESTED, _now(), scenario_id))
            conn.commit()
        self._audit(scenario_id, actor, "실제 조직 승격 요청(자동 반영 아님)", rationale.strip()[:400])
        out = self.get_scenario(scenario_id)
        out["note"] = ("승격 **요청**만 기록됐습니다. 실제 조직은 바뀌지 않았습니다 — "
                       "실제 문맥에서 사람이 승인해야 합니다(§8.3).")
        return out

    # ── 감사 ──────────────────────────────────────────────────────────────
    @staticmethod
    def _audit(scenario_id: str, actor: str, reason: str, detail: str) -> None:
        try:
            from core.enterprise_context import audit
            audit.record(audit.VIRTUAL_SCENARIO_CHANGED, resource_type="scenario",
                         resource_id=scenario_id, actor=actor or "",
                         outcome="allowed", reason=reason, detail=detail)
        except Exception as e:                                       # pragma: no cover
            print(f"⚠️ [clone] 시나리오 감사 기록 실패({scenario_id}): {e}")


clone_service = CloneService()
