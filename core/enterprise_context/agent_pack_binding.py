"""[ECM E2 잔여] 에이전트팩 바인딩 — **어떤 조직에서 어떤 에이전트가 도는가.**

## 지금까지의 문제

에이전트 구성은 `departments.domain_agents` 라는 **부서별 평면 목록**이었다. 그래서:

- 전사 표준 에이전트를 하나 추가하려면 **모든 부서의 목록을 각각 고쳐야** 한다. 한 곳을 빠뜨리면
  그 부서만 조용히 다른 구성으로 돈다 — 이 저장소가 하드코딩 맵 3개에서 겪은 문제와 같은 형태다
  (`org_seed` 주석: "세 맵이 서로 어긋나도 아무도 알아채지 못했다").
- "이 에이전트가 왜 도는가"에 답할 수 없다. 목록에 이름이 있다는 사실 외에 근거가 없다.

## 이 모듈의 방식

설계서 §4.3/§9 의 바인딩 모델을 그대로 따른다 — **원본 1 : 적용범위 N**. `master_scope_bindings`
와 같은 표 모양(`scope_node_id` · `entity_mode` · `inherit_descendants` · 유효기간 · 승인)을 쓴다.
같은 개념을 다른 모양으로 두면 두 규칙이 갈라지기 때문이다.

해석 결과는 **어디서 왔는지를 함께** 돌려준다(`provenance`). 상속으로 온 것인지 그 조직이 직접
바인딩한 것인지 구분되지 않으면, 구성을 고칠 때 어디를 고쳐야 하는지 알 수 없다.

## 지키는 규칙

1. **승인된 팩만 해석에 쓴다.** DRAFT 팩이 실행에 끼어들면 검증되지 않은 에이전트가 산출물을 만든다.
2. **상속은 조상 → 하위**(`OPERATING_PARENT` 체인). `CONSOLIDATION_SCOPE` 는 따라가지 않는다 —
   지분 집계를 따라가면 다른 법인의 구성이 넘어온다.
3. **가상 문맥 바인딩은 살아 있는 시나리오 안에서만.** 기준정보 바인딩과 같은 규율이다.
4. **만료된 바인딩은 해석에서 빠진다.** 유효기간을 두고 지키지 않으면 기간은 장식이다.
5. **비었으면 비었다고 말한다.** 조용히 빈 목록을 주면 "에이전트가 없다"와 "바인딩이 안 됐다"가
   같아진다 — 이 저장소가 반복해서 막아 온 조용한 실패다.

LLM 0콜.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

DRAFT = "DRAFT"
APPROVED = "APPROVED"
ACTIVE = "active"
REVOKED = "revoked"

_DDL = """
CREATE TABLE IF NOT EXISTS agent_packs (
    pack_id      TEXT PRIMARY KEY,
    tenant_id    TEXT NOT NULL DEFAULT 'tenant_default',
    name         TEXT NOT NULL,
    purpose      TEXT NOT NULL,
    agents_json  TEXT NOT NULL DEFAULT '[]',
    status       TEXT NOT NULL DEFAULT 'DRAFT',
    version      INTEGER NOT NULL DEFAULT 1,
    created_by   TEXT NOT NULL DEFAULT '',
    approved_by  TEXT NOT NULL DEFAULT '',
    approved_at  TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS agent_pack_bindings (
    binding_id   TEXT PRIMARY KEY,
    tenant_id    TEXT NOT NULL DEFAULT 'tenant_default',
    scope_node_id TEXT NOT NULL,
    pack_id      TEXT NOT NULL,
    entity_mode  TEXT NOT NULL DEFAULT 'REAL',
    inherit_descendants INTEGER NOT NULL DEFAULT 1,
    effective_from TEXT NOT NULL DEFAULT '',
    effective_to   TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL DEFAULT 'active',
    approved_by  TEXT NOT NULL DEFAULT '',
    approved_at  TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    UNIQUE (tenant_id, scope_node_id, pack_id, entity_mode, effective_from)
);
CREATE INDEX IF NOT EXISTS idx_apb_scope ON agent_pack_bindings(scope_node_id);
"""


class AgentPackError(ValueError):
    """정책 위반 — 4xx 로 전달한다."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AgentPackStore:
    def __init__(self, repository=None, resolver=None, clone=None):
        self._lock = threading.RLock()
        self._repo_override = repository
        self._resolver_override = resolver
        self._clone_override = clone

    # 호출 시점에 얻는다 — 값으로 바인딩하면 테스트 monkeypatch 가 안 먹는다.
    @property
    def _repo(self):
        if self._repo_override is not None:
            return self._repo_override
        from core.enterprise_context.repository import ecm_repository
        return ecm_repository

    @property
    def _resolver(self):
        if self._resolver_override is not None:
            return self._resolver_override
        from core.enterprise_context.resolver import ecm_resolver
        return ecm_resolver

    @property
    def _clone(self):
        if self._clone_override is not None:
            return self._clone_override
        from core.enterprise_context.clone_service import clone_service
        return clone_service

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._repo.db_path)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA busy_timeout = 5000")
        except Exception:
            pass
        conn.executescript(_DDL)
        return conn

    # ── 팩 ────────────────────────────────────────────────────────────────
    def create_pack(self, name: str, purpose: str, agents: List[str],
                    tenant_id: str = "tenant_default", actor: str = "") -> Dict[str, Any]:
        """에이전트팩을 만든다(DRAFT)."""
        if not (name or "").strip():
            raise AgentPackError("팩 이름(name)은 필수입니다.")
        if not (purpose or "").strip():
            raise AgentPackError(
                "팩의 목적(purpose)은 필수입니다 — 목적 없는 구성은 나중에 누구도 손대지 못합니다.")
        ags = [str(a).strip() for a in (agents or []) if str(a).strip()]
        if not ags:
            raise AgentPackError("에이전트 목록(agents)이 비어 있습니다.")
        dup = sorted({a for a in ags if ags.count(a) > 1})
        if dup:
            raise AgentPackError(f"팩 안에 중복된 에이전트가 있습니다: {dup}")
        pid = f"pack_{uuid.uuid4().hex[:12]}"
        now = _now()
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO agent_packs (pack_id, tenant_id, name, purpose, agents_json, "
                "status, version, created_by, created_at, updated_at) VALUES (?,?,?,?,?,?,1,?,?,?)",
                (pid, tenant_id, name.strip(), purpose.strip(),
                 json.dumps(ags, ensure_ascii=False), DRAFT, actor or "", now, now))
            conn.commit()
        self._audit(pid, actor, "에이전트팩 생성", f"{len(ags)}개: {', '.join(ags[:6])}")
        return self.get_pack(pid)

    def approve_pack(self, pack_id: str, actor: str = "") -> Dict[str, Any]:
        """승인 — **승인된 팩만 바인딩·해석에 쓸 수 있다.**"""
        self._require_pack(pack_id)
        now = _now()
        with self._lock, self._connect() as conn:
            conn.execute("UPDATE agent_packs SET status=?, approved_by=?, approved_at=?, "
                         "updated_at=? WHERE pack_id=?", (APPROVED, actor or "", now, now, pack_id))
            conn.commit()
        self._audit(pack_id, actor, "에이전트팩 승인", "이후 조직에 바인딩 가능")
        return self.get_pack(pack_id)

    def get_pack(self, pack_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            r = conn.execute("SELECT * FROM agent_packs WHERE pack_id=?", (pack_id,)).fetchone()
        if not r:
            return None
        d = dict(r)
        try:
            d["agents"] = json.loads(d.pop("agents_json") or "[]")
        except Exception:
            d["agents"] = []
        return d

    def list_packs(self, status: str = "", tenant_id: str = "") -> List[Dict[str, Any]]:
        """팩 목록.

        ⚠️ [D-017 §2.4] 예전에는 **요청자 가시 범위나 테넌트로 필터하지 않았다** — 다른
          테넌트의 팩 이름·목적·에이전트 구성이 그대로 보였다. `tenant_id` 를 주면 그 테넌트
          것만 돌려준다. 주지 않으면 종전 동작이다(ECM 미도입 흐름 보존)."""
        where, params = [], []
        if status:
            where.append("status=?"); params.append(status)
        if tenant_id:
            where.append("tenant_id=?"); params.append(tenant_id)
        sql = "SELECT pack_id FROM agent_packs"
        if where:
            sql += " WHERE " + " AND ".join(where)
        with self._connect() as conn:
            ids = [r[0] for r in conn.execute(sql + " ORDER BY created_at DESC",
                                              tuple(params)).fetchall()]
        return [self.get_pack(i) for i in ids]

    def _require_pack(self, pid: str) -> Dict[str, Any]:
        p = self.get_pack(pid)
        if not p:
            raise AgentPackError(f"에이전트팩을 찾을 수 없습니다: {pid}")
        return p

    # ── 바인딩 ────────────────────────────────────────────────────────────
    def bind(self, pack_id: str, scope_node_id: str, tenant_id: str = "tenant_default",
             entity_mode: str = "REAL", inherit_descendants: bool = True,
             effective_from: str = "", effective_to: str = "", actor: str = "") -> Dict[str, Any]:
        """팩을 조직 노드에 적용한다.

        ⚠️ `master_scope_bindings` 와 같은 UNIQUE 키를 쓴다(기간이 같으면 **덮어쓴다**). 같은
          개념을 다른 규칙으로 두면 관리 UI 에서 사용자가 두 동작을 구분하지 못한다."""
        pack = self._require_pack(pack_id)
        if pack["status"] != APPROVED:
            raise AgentPackError(
                f"승인되지 않은 팩은 바인딩할 수 없습니다(현재 {pack['status']}) — 검증되지 않은 "
                f"에이전트가 산출물을 만들게 됩니다.")
        if not (scope_node_id or "").strip():
            raise AgentPackError("scope_node_id 는 필수입니다.")
        if entity_mode == "COMPETITOR_REFERENCE":
            raise AgentPackError("경쟁사 참조 문맥에는 에이전트를 바인딩하지 않습니다.")
        if entity_mode == "VIRTUAL":
            # 기준정보 바인딩과 **같은 규율** — 살아 있는 시나리오 안에서만.
            if not self._clone.active_scenario_of_node(scope_node_id):
                raise AgentPackError(
                    f"'{scope_node_id}' 에 유효한 가상 시나리오가 없습니다 — 가상 문맥 바인딩은 "
                    f"살아 있는 시나리오 안에서만 가능합니다.")
        elif entity_mode != "REAL":
            raise AgentPackError(f"알 수 없는 entity_mode 입니다: {entity_mode}")
        if effective_to and effective_from and effective_to < effective_from:
            raise AgentPackError("유효기간이 거꾸로입니다(effective_to < effective_from).")

        bid = f"apb_{uuid.uuid4().hex[:12]}"
        now = _now()
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO agent_pack_bindings (binding_id, tenant_id, scope_node_id, pack_id, "
                "entity_mode, inherit_descendants, effective_from, effective_to, status, "
                "approved_by, approved_at, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(tenant_id, scope_node_id, pack_id, entity_mode, effective_from) "
                "DO UPDATE SET inherit_descendants=excluded.inherit_descendants, "
                "effective_to=excluded.effective_to, status='active', "
                "approved_by=excluded.approved_by, approved_at=excluded.approved_at, "
                "updated_at=excluded.updated_at",
                (bid, tenant_id, scope_node_id, pack_id, entity_mode,
                 1 if inherit_descendants else 0, effective_from, effective_to, ACTIVE,
                 actor or "", now if actor else "", now, now))
            conn.commit()
        self._audit(scope_node_id, actor, "에이전트팩 바인딩",
                    f"pack={pack_id}({pack['name']}) mode={entity_mode} "
                    f"상속={'예' if inherit_descendants else '아니오'} "
                    f"기간={effective_from or '-'}~{effective_to or '-'}")
        return {"binding_id": bid, "pack_id": pack_id, "scope_node_id": scope_node_id}

    def unbind(self, binding_id: str, actor: str = "") -> bool:
        """바인딩 해제(소프트). **물리 삭제하지 않는다** — "언제 무엇이 이 조직에서 돌았나"는
        산출물의 근거이고, 지우면 과거 산출물을 설명할 수 없다."""
        with self._lock, self._connect() as conn:
            cur = conn.execute("UPDATE agent_pack_bindings SET status=?, updated_at=? "
                               "WHERE binding_id=?", (REVOKED, _now(), binding_id))
            conn.commit()
            ok = cur.rowcount > 0
        if ok:
            self._audit(binding_id, actor, "에이전트팩 바인딩 해제", "소프트 — 이력 보존")
        return ok

    def list_bindings(self, scope_node_id: str = "", pack_id: str = "",
                      include_revoked: bool = False) -> List[Dict[str, Any]]:
        sql, params, where = "SELECT * FROM agent_pack_bindings", [], []
        if scope_node_id:
            where.append("scope_node_id=?"); params.append(scope_node_id)
        if pack_id:
            where.append("pack_id=?"); params.append(pack_id)
        if not include_revoked:
            where.append("status=?"); params.append(ACTIVE)
        if where:
            sql += " WHERE " + " AND ".join(where)
        with self._connect() as conn:
            rows = conn.execute(sql + " ORDER BY created_at DESC", tuple(params)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["inherit_descendants"] = bool(d["inherit_descendants"])
            out.append(d)
        return out

    # ── 해석 ──────────────────────────────────────────────────────────────
    def resolve_agents(self, scope_node_id: str, today: str = "",
                       entity_mode: str = "REAL") -> Dict[str, Any]:
        """이 조직에서 실제로 도는 에이전트와 **그 근거**.

        상속 순서: 조상(상위) → 자신. 같은 에이전트가 여러 팩에 있으면 한 번만 세지만, **어느
        팩에서 왔는지는 전부 남긴다** — 구성을 고칠 때 어디를 고쳐야 하는지 알아야 한다.
        ⚠️ 결과가 비면 `bound=False` 로 말한다. 조용히 빈 목록을 주면 "에이전트가 없다"와
          "바인딩이 안 됐다"가 같아진다."""
        node = (scope_node_id or "").strip()
        if not node:
            raise AgentPackError("scope_node_id 는 필수입니다.")
        ref = date.fromisoformat(today) if today else datetime.now(timezone.utc).date()

        try:
            # `ancestors()` 는 **가까운 조상부터** 준다. 뒤집어서 최상위(전사)부터 넣는다 —
            # 전사 표준이 먼저 오고 그 다음 사업부, 마지막에 자기 조직 고유 구성이 얹힌다.
            # 순서는 실행 순서가 아니라 **읽는 사람이 이해하는 순서**다(전사 → 조직 고유).
            chain = list(reversed(self._resolver.ancestors(node))) + [node]
        except Exception as e:
            print(f"⚠️ [agent_pack] 조상 해석 실패(자기 노드만 사용): {e}")
            chain = [node]
        chain = [n for i, n in enumerate(chain) if n not in chain[:i]]

        agents: List[str] = []
        provenance: Dict[str, List[Dict[str, str]]] = {}
        skipped: List[Dict[str, str]] = []
        for owner in chain:
            for b in self.list_bindings(scope_node_id=owner):
                if b["entity_mode"] != entity_mode:
                    continue
                if owner != node and not b["inherit_descendants"]:
                    skipped.append({"pack_id": b["pack_id"], "at": owner,
                                    "why": "상속 안 함(inherit_descendants=false)"})
                    continue
                if not self._in_effect(b, ref):
                    skipped.append({"pack_id": b["pack_id"], "at": owner,
                                    "why": f"유효기간 밖({b['effective_from'] or '-'}~"
                                           f"{b['effective_to'] or '-'})"})
                    continue
                pack = self.get_pack(b["pack_id"])
                if not pack or pack["status"] != APPROVED:
                    skipped.append({"pack_id": b["pack_id"], "at": owner,
                                    "why": f"승인되지 않은 팩({(pack or {}).get('status', '없음')})"})
                    continue
                for a in pack["agents"]:
                    if a not in agents:
                        agents.append(a)
                    provenance.setdefault(a, []).append(
                        {"pack_id": pack["pack_id"], "pack_name": pack["name"],
                         "bound_at": owner,
                         "how": "직접" if owner == node else f"상속({owner})"})
        return {
            "scope_node_id": node, "entity_mode": entity_mode,
            "agents": agents, "provenance": provenance, "skipped": skipped,
            "bound": bool(agents),
            "note": ("" if agents else
                     "이 조직에 적용된 에이전트팩이 없습니다 — 에이전트가 없는 것이 아니라 "
                     "**바인딩이 없는** 상태입니다(상위 조직에 표준팩을 바인딩하면 상속됩니다)."),
        }

    @staticmethod
    def _in_effect(b: Dict[str, Any], ref: date) -> bool:
        """유효기간 안인가. 빈 값은 '제한 없음'으로 본다."""
        try:
            if b["effective_from"] and date.fromisoformat(b["effective_from"]) > ref:
                return False
            if b["effective_to"] and date.fromisoformat(b["effective_to"]) < ref:
                return False
        except ValueError:
            # 형식이 깨진 기간은 **적용하지 않는다**(해석 불가를 통과시키면 통제가 사라진다)
            return False
        return True

    @staticmethod
    def _audit(resource_id: str, actor: str, reason: str, detail: str) -> None:
        try:
            from core.enterprise_context import audit
            audit.record(audit.AGENT_PACK_CHANGED, resource_type="agent_pack",
                         resource_id=resource_id, actor=actor or "", outcome="allowed",
                         reason=reason, detail=detail)
        except Exception as e:                                       # pragma: no cover
            print(f"⚠️ [agent_pack] 감사 기록 실패({resource_id}): {e}")


agent_packs = AgentPackStore()
