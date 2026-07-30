"""M2 스키마 레지스트리 + 키 크로스워크.

우리 기준정보(M1 골든 레코드) ↔ 외부 연계 시스템의 키·필드를 매핑한다. 매핑은 **LLM/휴리스틱이
초안을 제안하고 사람이 승인해야만 유효**(confirmed=1)하다. M2 는 메타데이터(주소록)만 저장하고
실제 값 조회는 M3(온디맨드)의 몫이다. 설계: docs/design_master_data_m2.md.

[(a) 확정] 스키마·저수준 접근(DDL·_connect·별칭감지)은 M1 core/master_data.py 소유를 재사용하고,
본 모듈은 크로스워크 '비즈니스 로직'만 담당한다(내부 골든[LLM0콜] vs 외부 매핑[Flash] 격리).
"""
import re
from datetime import datetime, timezone

from core.master_data import master_data, MasterData, MasterDataError

_SYS_RE = re.compile(r"^[a-z0-9_-]{2,32}$")
_FIELD_MAX = 128


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class CrosswalkError(ValueError):
    """검증/충돌 등 4xx 로 전달할 도메인 오류."""


class Crosswalk:
    def __init__(self, md: MasterData = None):
        # [(a)] 같은 master.db·연결·별칭감지를 공유. DDL 은 master_data 가 이미 초기화.
        self.md = md or master_data

    def _connect(self):
        return self.md._connect()

    @staticmethod
    def _check_system_id(system_id: str):
        if not _SYS_RE.match(system_id or ""):
            raise CrosswalkError("잘못된 system_id 형식입니다 (^[a-z0-9_-]{2,32}$).")

    @staticmethod
    def _clean_field(v: str, label: str) -> str:
        v = (v or "").strip()
        if not v:
            raise CrosswalkError(f"{label} 는 비어 있을 수 없습니다.")
        if len(v) > _FIELD_MAX or any(ord(c) < 32 for c in v):
            raise CrosswalkError(f"{label} 형식이 올바르지 않습니다(제어문자/{_FIELD_MAX}자 초과).")
        return v

    # ── 연계 시스템 (external_systems) ────────────────────────────────
    def list_systems(self, scope_node_id: str = "", tenant_id: str = "",
                     entity_mode: str = "REAL",
                     # [§6-2] 등급이 낮으면 제목만 남기고 내용을 가린다(빈 값 = 가리지 않는다)
                     viewer_clearance: str = "") -> list:
        """[ECM E2] 조직 범위 가시성을 적용해 연계 시스템을 나열한다.

        범위를 주지 않으면 필터하지 않는다(ECM 미도입 흐름 보존 — `scoping` 규칙 3)."""
        conn = self._connect()
        try:
            rows = [dict(r) for r in conn.execute(
                "SELECT * FROM external_systems ORDER BY system_id").fetchall()]
        finally:
            conn.close()
        from core.enterprise_context.scoping import filter_visible
        return filter_visible(rows, scope_node_id, tenant_id, entity_mode,
                              viewer_clearance=viewer_clearance)

    def is_system_visible(self, system_id: str, scope_node_id: str = "",
                          tenant_id: str = "", entity_mode: str = "REAL") -> bool:
        """이 문맥에서 그 시스템에 접근할 수 있는가.

        ★ 자식 자원(스키마·매핑·제안·MCP 조회)의 접근 판정은 **전부 이 함수 하나를 탄다.**
          자식 테이블에 범위 키를 복제하지 않기로 한 결정(D-013 계열)의 대가로, 판정 지점을
          하나로 모으지 않으면 어느 경로에서만 열리는 구멍이 생긴다."""
        row = self.get_system(system_id)
        if not row:
            return False
        from core.enterprise_context.scoping import is_visible
        return is_visible(row, scope_node_id, tenant_id, entity_mode)

    def require_system_visible(self, system_id: str, scope_node_id: str = "",
                               tenant_id: str = "", entity_mode: str = "REAL",
                               actor: str = "", actor_scopes=None):
        """보이지 않으면 도메인 오류. **'없음'과 같은 문구를 쓴다** — 다른 조직 시스템의
        존재 여부까지 알려주면 그 자체가 정보 유출이다.

        ★ [M2 관문 B-2] 거부하는 **그 순간** 감사로그에 남긴다. 응답은 은폐하되 기록은
          실제 대상 식별자를 담는다 — 그러지 않으면 운영자가 침해 시도를 볼 수 없다.
          `actor` 는 라우트가 인증 주체에서 넘긴다(비면 `anonymous` 로 기록된다)."""
        if not self.is_system_visible(system_id, scope_node_id, tenant_id, entity_mode):
            try:
                from core.enterprise_context import audit
                audit.denied_scope("external_system", system_id, actor=actor,
                                   actor_scopes=actor_scopes, requested_scope=scope_node_id,
                                   detail=f"entity_mode={entity_mode} tenant={tenant_id}")
            except Exception:
                pass    # 감사 기록 실패가 차단을 막지 않는다(차단은 유지된다)
            raise CrosswalkError(f"존재하지 않거나 접근 권한이 없는 system_id 입니다: {system_id}")

    def systems_coverage(self) -> dict:
        """범위 미지정(= 모든 조직에 노출) 시스템 수 관측 (D-014 — 점진 도입의 의무 관측)."""
        conn = self._connect()
        try:
            rows = [dict(r) for r in conn.execute("SELECT * FROM external_systems").fetchall()]
        finally:
            conn.close()
        from core.enterprise_context.scoping import coverage
        cov = coverage(rows, "연계 시스템")
        cov["unscoped_systems"] = [r["system_id"] for r in rows
                                   if not (r.get("enterprise_scope_id") or "").strip()]
        return cov

    def get_system(self, system_id: str) -> dict | None:
        conn = self._connect()
        try:
            r = conn.execute("SELECT * FROM external_systems WHERE system_id=?", (system_id,)).fetchone()
            return dict(r) if r else None
        finally:
            conn.close()

    def create_system(self, system_id: str, name: str, mcp_endpoint: str = "",
                      auth_ref: str = "", scope: str = "read",
                      tenant_id: str = "tenant_default", enterprise_scope_id: str = "",
                      entity_mode: str = "REAL") -> dict:
        self._check_system_id(system_id)
        if scope not in ("read", "read-write"):
            raise CrosswalkError("scope 는 read | read-write 여야 합니다.")
        conn = self._connect()
        try:
            if conn.execute("SELECT 1 FROM external_systems WHERE system_id=?", (system_id,)).fetchone():
                raise CrosswalkError(f"이미 존재하는 system_id 입니다: {system_id}")
            conn.execute(
                "INSERT INTO external_systems(system_id,name,mcp_endpoint,auth_ref,scope,status,created_at,"
                "tenant_id,enterprise_scope_id,entity_mode) "
                "VALUES(?,?,?,?,?, 'inactive', ?,?,?,?)",
                (system_id, name or system_id, mcp_endpoint or "", auth_ref or "", scope, _now(),
                 tenant_id or "tenant_default", enterprise_scope_id or "", entity_mode or "REAL"))
            conn.commit()
        finally:
            conn.close()
        return self.get_system(system_id)

    def update_system(self, system_id: str, name: str = None, mcp_endpoint: str = None,
                      scope: str = None, status: str = None) -> dict:
        conn = self._connect()
        try:
            if not conn.execute("SELECT 1 FROM external_systems WHERE system_id=?", (system_id,)).fetchone():
                raise CrosswalkError(f"존재하지 않는 system_id 입니다: {system_id}")
            if status is not None and status not in ("active", "inactive"):
                raise CrosswalkError("status 는 active | inactive 여야 합니다.")
            if status == "active":
                n = conn.execute("SELECT COUNT(*) FROM key_crosswalk WHERE system_id=? AND confirmed=1",
                                 (system_id,)).fetchone()[0]
                if not n:
                    raise CrosswalkError("승인된 매핑이 1건 이상 있어야 활성화(active)할 수 있습니다.")
            sets, vals = [], []
            for col, v in (("name", name), ("mcp_endpoint", mcp_endpoint), ("scope", scope), ("status", status)):
                if v is not None:
                    sets.append(f"{col}=?"); vals.append(v)
            if sets:
                vals.append(system_id)
                conn.execute(f"UPDATE external_systems SET {','.join(sets)} WHERE system_id=?", vals)
                conn.commit()
        finally:
            conn.close()
        return self.get_system(system_id)

    def delete_system(self, system_id: str):
        conn = self._connect()
        try:
            conn.execute("DELETE FROM external_systems WHERE system_id=?", (system_id,))
            conn.execute("DELETE FROM external_schemas WHERE system_id=?", (system_id,))
            conn.execute("DELETE FROM key_crosswalk WHERE system_id=?", (system_id,))
            conn.execute("DELETE FROM crosswalk_proposals WHERE system_id=?", (system_id,))
            conn.commit()
        finally:
            conn.close()

    # ── 외부 스키마 (external_schemas) — '조인 컬럼 정의' 계층 ──────────
    def get_schema(self, system_id: str) -> list:
        conn = self._connect()
        try:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM external_schemas WHERE system_id=? ORDER BY entity, field",
                (system_id,)).fetchall()]
        finally:
            conn.close()

    def _require_system(self, conn, system_id: str):
        if not conn.execute("SELECT 1 FROM external_systems WHERE system_id=?", (system_id,)).fetchone():
            raise CrosswalkError(f"먼저 시스템을 등록하세요: {system_id}")

    def add_schema_field(self, system_id: str, entity: str, field: str, field_type: str = "",
                         is_key: bool = False, mapped_type: str = "", mapped_attr: str = "",
                         source: str = "user") -> dict:
        entity = self._clean_field(entity, "entity")
        field = self._clean_field(field, "field")
        conn = self._connect()
        try:
            self._require_system(conn, system_id)
            conn.execute(
                "INSERT OR REPLACE INTO external_schemas"
                "(system_id,entity,field,field_type,is_key,mapped_type,mapped_attr,note,source) "
                "VALUES(?,?,?,?,?,?,?,'',?)",
                (system_id, entity, field, field_type or "", 1 if is_key else 0,
                 mapped_type or "", mapped_attr or "", source))
            conn.commit()
        finally:
            conn.close()
        return {"system_id": system_id, "entity": entity, "field": field}

    def import_schema_rows(self, system_id: str, rows: list) -> dict:
        """CSV 행 일괄 등록(부분 성공). 행: {entity, field, field_type, is_key, mapped_type, mapped_attr}."""
        ok, failed = 0, []
        for i, row in enumerate(rows):
            try:
                self.add_schema_field(
                    system_id, row.get("entity", ""), row.get("field", ""),
                    field_type=row.get("field_type", ""),
                    is_key=str(row.get("is_key", "")).strip().lower() in ("1", "true", "y", "yes"),
                    mapped_type=row.get("mapped_type", ""), mapped_attr=row.get("mapped_attr", ""),
                    source="csv_import")
                ok += 1
            except Exception as e:
                failed.append({"row": i + 1, "error": str(e)})
        return {"imported": ok, "failed": failed, "total": len(rows)}

    def set_field_mapping(self, system_id: str, entity: str, field: str,
                          mapped_type: str = "", mapped_attr: str = "") -> dict:
        conn = self._connect()
        try:
            r = conn.execute("SELECT 1 FROM external_schemas WHERE system_id=? AND entity=? AND field=?",
                             (system_id, entity, field)).fetchone()
            if not r:
                raise CrosswalkError("존재하지 않는 스키마 필드입니다.")
            conn.execute("UPDATE external_schemas SET mapped_type=?, mapped_attr=? "
                         "WHERE system_id=? AND entity=? AND field=?",
                         (mapped_type or "", mapped_attr or "", system_id, entity, field))
            conn.commit()
        finally:
            conn.close()
        return {"system_id": system_id, "entity": entity, "field": field,
                "mapped_type": mapped_type, "mapped_attr": mapped_attr}

    # ── 매핑 초안 제안 (결정론 1차 + Flash 옵트인 2차) ─────────────────
    async def propose(self, system_id: str, use_llm: bool = False) -> dict:
        """external_schemas 의 (entity, field) 를 우리 골든 레코드(이름/별칭)와 대조해 매핑 후보를
        crosswalk_proposals(pending)로 적재한다. 1차 결정론(LLM 0콜), 2차 Flash 는 옵트인.
        external_key 후보는 '조인 컬럼' 포인터 "entity:field" 로 제안한다(값은 승인 시/ M3 에서 확정)."""
        conn = self._connect()
        try:
            self._require_system(conn, system_id)
            schema = [dict(r) for r in conn.execute(
                "SELECT DISTINCT entity, field, is_key FROM external_schemas WHERE system_id=?",
                (system_id,)).fetchall()]
        finally:
            conn.close()
        if not schema:
            raise CrosswalkError("등록된 외부 스키마가 없습니다. 먼저 스키마를 등록하세요.")

        records = self.md._cached_records()  # active 현행 레코드 + 별칭
        proposals = []          # (master_code, external_key, confidence, rationale)
        matched_codes = set()

        # 1) 결정론: 외부 entity/field 명이 우리 레코드 이름/별칭과 일치하는지(단어경계/부분)
        for rec in records:
            names = [rec["name"]] + list(rec.get("aliases", []))
            best = None
            for s in schema:
                token = f"{s['entity']} {s['field']}"
                for nm in names:
                    if not nm:
                        continue
                    conf, why = self._name_match(nm, s["entity"], s["field"], bool(s["is_key"]))
                    if conf and (best is None or conf > best[0]):
                        best = (conf, f"{s['entity']}:{s['field']}", why)
            if best:
                proposals.append((rec["master_code"], best[1], best[0], best[2]))
                matched_codes.add(rec["master_code"])

        # 2) Flash 옵트인: 결정론 미매칭 레코드에 한해 후보 제안(온톨로지 제약). 기본 off.
        llm_used = False
        if use_llm:
            unmatched = [r for r in records if r["master_code"] not in matched_codes]
            if unmatched:
                llm_used = True
                try:
                    proposals += await self._llm_propose(unmatched, schema)
                except Exception as e:
                    print(f"⚠️ [Crosswalk] Flash 제안 실패(결정론 결과만 사용): {e}")

        saved = self._save_proposals(system_id, proposals)
        return {"system_id": system_id, "proposed": saved, "deterministic": len(matched_codes),
                "llm_used": llm_used}

    @staticmethod
    def _name_match(name: str, entity: str, field: str, is_key: bool):
        """이름/별칭 ↔ 외부 entity/field 결정론 매칭. (confidence, rationale) 또는 (0, '')."""
        n = (name or "").strip().lower()
        e = (entity or "").strip().lower()
        f = (field or "").strip().lower()
        if not n:
            return 0.0, ""
        # 정확 일치(별칭이 외부 필드/엔티티명과 동일) — 키 필드면 가산
        if n == f or n == e:
            return (0.95 if is_key else 0.9), f"이름/별칭 '{name}' == 외부 {'키 ' if is_key else ''}'{field or entity}'"
        # 부분 포함(양방향) — 약한 후보
        if len(n) >= 3 and (n in f or f in n or n in e or e in n):
            return 0.6, f"이름/별칭 '{name}' 부분일치 '{entity}.{field}'"
        return 0.0, ""

    async def _llm_propose(self, unmatched_records: list, schema: list) -> list:
        """Flash 1콜: 미매칭 레코드에 대해 외부 스키마 후보를 온톨로지 제약 JSON 으로 제안."""
        from core.llm_gateway import gateway
        import json
        rec_lines = "\n".join(f"- {r['master_code']}: {r['name']} (별칭: {', '.join(r.get('aliases', []))})"
                              for r in unmatched_records[:40])
        sch_lines = "\n".join(f"- {s['entity']}.{s['field']}" for s in schema[:80])
        prompt = (
            "다음 '내부 기준정보 레코드'를 '외부 시스템 스키마 필드'에 대응시켜라. 확실한 것만.\n"
            "반드시 아래 JSON 만 출력(설명 금지):\n"
            '{"mappings":[{"master_code":"...","entity":"...","field":"...","confidence":0.0,"reason":"..."}]}\n\n'
            f"[내부 레코드]\n{rec_lines}\n\n[외부 스키마]\n{sch_lines}\n\n"
            "⚠️ 위 목록에 없는 master_code/entity/field 를 지어내지 말 것. 애매하면 제외.")
        raw = await gateway.aexecute(unmatched_records and _FakeState() or _FakeState(), prompt,
                                     is_heavy=False, output_mode="json", light=True)
        valid_codes = {r["master_code"] for r in unmatched_records}
        valid_ef = {(s["entity"], s["field"]) for s in schema}
        out = []
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
            for m in (data or {}).get("mappings", []):
                mc, en, fd = m.get("master_code"), m.get("entity"), m.get("field")
                if mc in valid_codes and (en, fd) in valid_ef:  # 환각 방어: 목록 밖 거부
                    out.append((mc, f"{en}:{fd}", float(m.get("confidence", 0.5)),
                                f"[Flash] {m.get('reason', '')}"[:200]))
        except Exception:
            pass
        return out

    def _save_proposals(self, system_id: str, proposals: list) -> int:
        conn = self._connect()
        n = 0
        try:
            for master_code, external_key, confidence, rationale in proposals:
                # 이미 승인된 매핑이 있으면 제안 스킵
                if conn.execute("SELECT 1 FROM key_crosswalk WHERE master_code=? AND system_id=? AND confirmed=1",
                                (master_code, system_id)).fetchone():
                    continue
                # 동일 (master_code, external_key) pending 중복 방지
                dup = conn.execute(
                    "SELECT 1 FROM crosswalk_proposals WHERE master_code=? AND system_id=? "
                    "AND external_key=? AND status='pending'", (master_code, system_id, external_key)).fetchone()
                if dup:
                    continue
                conn.execute(
                    "INSERT INTO crosswalk_proposals(master_code,system_id,external_key,confidence,rationale,status,created_at) "
                    "VALUES(?,?,?,?,?, 'pending', ?)",
                    (master_code, system_id, external_key, round(float(confidence), 3), rationale, _now()))
                n += 1
            conn.commit()
        finally:
            conn.close()
        return n

    def list_proposals(self, system_id: str, status: str = None) -> list:
        conn = self._connect()
        try:
            if status:
                rows = conn.execute("SELECT * FROM crosswalk_proposals WHERE system_id=? AND status=? "
                                    "ORDER BY confidence DESC, id", (system_id, status)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM crosswalk_proposals WHERE system_id=? "
                                    "ORDER BY status, confidence DESC, id", (system_id,)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ── 승인 / 기각 ───────────────────────────────────────────────────
    def system_of_proposal(self, proposal_id: int) -> str:
        """제안이 속한 시스템. 승인·기각의 범위 게이트가 이것으로 부모를 찾는다
        (제안 테이블에 범위 키를 복제하지 않기로 한 결정의 대가)."""
        conn = self._connect()
        try:
            r = conn.execute("SELECT system_id FROM crosswalk_proposals WHERE id=?",
                             (proposal_id,)).fetchone()
            return (r["system_id"] if r else "") or ""
        finally:
            conn.close()

    def approve_proposal(self, proposal_id: int, external_key: str = None) -> dict:
        """제안을 승인 → key_crosswalk(confirmed=1) 로 승격. external_key 를 주면 그 값으로 확정
        (인스턴스 값 지정: 'entity:field=value'). 미지정 시 제안된 포인터를 그대로 사용."""
        conn = self._connect()
        try:
            p = conn.execute("SELECT * FROM crosswalk_proposals WHERE id=?", (proposal_id,)).fetchone()
            if not p:
                raise CrosswalkError(f"존재하지 않는 제안입니다: {proposal_id}")
            if p["status"] != "pending":
                raise CrosswalkError(f"이미 처리된 제안입니다(status={p['status']}).")
            key = (external_key or p["external_key"]).strip()
            # 승인 = key_crosswalk UPSERT(confirmed=1). (master_code, system_id) 유일 → 재승인 시 교체.
            conn.execute(
                "INSERT INTO key_crosswalk(master_code,system_id,external_key,confirmed) VALUES(?,?,?,1) "
                "ON CONFLICT(master_code,system_id) DO UPDATE SET external_key=excluded.external_key, confirmed=1",
                (p["master_code"], p["system_id"], key))
            conn.execute("UPDATE crosswalk_proposals SET status='approved' WHERE id=?", (proposal_id,))
            conn.commit()
        finally:
            conn.close()
        return {"proposal_id": proposal_id, "master_code": p["master_code"],
                "system_id": p["system_id"], "external_key": key, "confirmed": True}

    def reject_proposal(self, proposal_id: int) -> dict:
        conn = self._connect()
        try:
            p = conn.execute("SELECT status FROM crosswalk_proposals WHERE id=?", (proposal_id,)).fetchone()
            if not p:
                raise CrosswalkError(f"존재하지 않는 제안입니다: {proposal_id}")
            conn.execute("UPDATE crosswalk_proposals SET status='rejected' WHERE id=?", (proposal_id,))
            conn.commit()
        finally:
            conn.close()
        return {"proposal_id": proposal_id, "status": "rejected"}

    def list_mappings(self, system_id: str) -> list:
        """승인된(confirmed=1) 크로스워크 — M3 '가상 통합 주소록'."""
        conn = self._connect()
        try:
            rows = conn.execute("SELECT master_code, system_id, external_key FROM key_crosswalk "
                                "WHERE system_id=? AND confirmed=1 ORDER BY master_code", (system_id,)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


class _FakeState:
    """gateway.aexecute 가 요구하는 최소 상태 대역(크로스워크 제안은 프로젝트 컨텍스트가 불필요)."""
    workspace_root = ""
    initial_idea = ""
    rfp_summary = ""
    prd_summary = ""
    template_id = "default"
    file_index = {}


crosswalk = Crosswalk()
