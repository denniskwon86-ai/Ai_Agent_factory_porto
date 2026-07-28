"""[§6.3 / §6.1] 데이터 계보 — "이 값이 바뀌면 무엇이 틀어지나".

§6.1: "원천→변환→앱→보고서→**결정**의 영향 관계 — 추적성 그래프의 근거".

## 이 모듈이 지키는 것

1. **근거 없는 선을 긋지 않는다.** 모든 간선은 `origin`(user|derived)과 `evidence_ref` 를 남긴다.
   추측으로 만든 영향 분석은 **"영향 없음"을 잘못 말해서** 사고를 만든다 — 틀린 영향 분석은
   없는 영향 분석보다 위험하다. 그래서 LLM 이 긋는 간선은 지금 만들지 않는다.
2. **도출은 결정론이다.** `derive_edges()` 는 이미 저장된 사실(카탈로그 링크, 필드↔기준정보
   매핑, 용어↔기준정보 연결)에서만 간선을 만든다. 없는 관계를 상상하지 않는다.
3. **탐색은 반드시 끝난다.** 순환·깊이 상한을 둔다. 조직 데이터에 순환이 없다고 가정하면
   언젠가 무한 루프로 서버가 멈춘다.
4. **영향 분석이 불완전할 수 있음을 결과에 적는다.** 계보는 등록된 만큼만 안다. "영향 0건"이
   "안전하다"로 읽히면 안 된다.
"""
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.master_data import MasterData, master_data

NODE_TYPES = ("system", "asset", "field", "master", "term", "requirement",
              "blueprint", "project", "release")
RELATION_TYPES = ("feeds", "derives_from", "references", "produces", "confirms")

_MAX_DEPTH = 6          # 조직 데이터에서 6단계를 넘는 영향 추적은 실용성이 없다
_MAX_NODES = 500        # 폭주 방지 — 넘으면 잘렸다는 사실을 결과에 적는다


class LineageError(ValueError):
    """검증 오류."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class DataLineage:
    def __init__(self, md: MasterData = None):
        self.md = md or master_data

    def _connect(self):
        return self.md._connect()

    # ── 간선 ──────────────────────────────────────────────────────────────
    def add_edge(self, from_type: str, from_id: str, to_type: str, to_id: str,
                 relation_type: str = "feeds", confidence: float = 1.0,
                 evidence_ref: str = "", origin: str = "user") -> dict:
        for nm, v, allowed in (("from_type", from_type, NODE_TYPES),
                               ("to_type", to_type, NODE_TYPES),
                               ("relation_type", relation_type, RELATION_TYPES)):
            if v not in allowed:
                raise LineageError(f"{nm} 은 {list(allowed)} 중 하나여야 합니다.")
        if not (from_id or "").strip() or not (to_id or "").strip():
            raise LineageError("from_id 와 to_id 는 필수입니다.")
        if (from_type, from_id) == (to_type, to_id):
            raise LineageError("자기 자신을 가리키는 간선은 만들 수 없습니다.")
        if not (0.0 <= float(confidence) <= 1.0):
            raise LineageError("confidence 는 0.0~1.0 이어야 합니다.")

        eid = f"le_{uuid.uuid4().hex[:12]}"
        now = _now()
        with self.md._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO lineage_edges(edge_id,from_type,from_id,to_type,to_id,"
                "relation_type,confidence,evidence_ref,origin,status,created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,'active',?) "
                "ON CONFLICT(from_type,from_id,to_type,to_id,relation_type) DO UPDATE SET "
                "confidence=excluded.confidence, evidence_ref=excluded.evidence_ref, "
                "origin=excluded.origin, status='active'",
                (eid, from_type, from_id, to_type, to_id, relation_type, float(confidence),
                 evidence_ref, origin, now))
            row = conn.execute(
                "SELECT * FROM lineage_edges WHERE from_type=? AND from_id=? AND to_type=? "
                "AND to_id=? AND relation_type=?",
                (from_type, from_id, to_type, to_id, relation_type)).fetchone()
        return dict(row)

    def remove_edge(self, edge_id: str) -> bool:
        """소프트 삭제 — 과거 산출물이 왜 그 값을 썼는지 설명하려면 지난 연결이 남아야 한다."""
        with self.md._lock, self._connect() as conn:
            return conn.execute(
                "UPDATE lineage_edges SET status='removed' WHERE edge_id=? AND status='active'",
                (edge_id,)).rowcount > 0

    def edges_of(self, node_type: str, node_id: str, direction: str = "both") -> List[dict]:
        sql = "SELECT * FROM lineage_edges WHERE status='active' AND "
        if direction == "out":
            sql += "(from_type=? AND from_id=?)"
            params = (node_type, node_id)
        elif direction == "in":
            sql += "(to_type=? AND to_id=?)"
            params = (node_type, node_id)
        else:
            sql += "((from_type=? AND from_id=?) OR (to_type=? AND to_id=?))"
            params = (node_type, node_id, node_type, node_id)
        with self._connect() as conn:
            return [dict(r) for r in conn.execute(sql, params).fetchall()]

    # ── 영향 분석 ─────────────────────────────────────────────────────────
    def impact_of(self, node_type: str, node_id: str, direction: str = "downstream",
                  max_depth: int = _MAX_DEPTH) -> dict:
        """이 노드가 바뀌면 무엇이 영향을 받나(하류) / 이 노드는 무엇에서 오나(상류).

        ⚠️ **계보는 등록된 만큼만 안다.** "영향 0건"이 "안전하다"로 읽히면 안 되므로 결과에
          그 한계를 명시한다. 이것을 빼면 미등록 자산에 대한 변경이 안전하다고 오독된다."""
        if direction not in ("downstream", "upstream"):
            raise LineageError("direction 은 downstream|upstream 이어야 합니다.")
        start = (node_type, node_id)
        seen = {start}
        nodes: List[dict] = []
        path_edges: List[dict] = []
        truncated = False

        q = deque([(start, 0)])
        while q:
            (ntype, nid), depth = q.popleft()
            if depth >= max_depth:
                truncated = True
                continue
            step = self.edges_of(ntype, nid, "out" if direction == "downstream" else "in")
            for e in step:
                nxt = ((e["to_type"], e["to_id"]) if direction == "downstream"
                       else (e["from_type"], e["from_id"]))
                path_edges.append(e)
                if nxt in seen:
                    continue                     # 순환 가드 — 없으면 무한 루프
                if len(seen) >= _MAX_NODES:
                    truncated = True
                    continue
                seen.add(nxt)
                nodes.append({"node_type": nxt[0], "node_id": nxt[1], "depth": depth + 1,
                              "via": e["relation_type"], "confidence": e["confidence"],
                              "origin": e["origin"]})
                q.append((nxt, depth + 1))

        weak = [n for n in nodes if n["confidence"] < 1.0]
        return {
            "root": {"node_type": node_type, "node_id": node_id},
            "direction": direction,
            "impacted": sorted(nodes, key=lambda n: (n["depth"], n["node_type"], n["node_id"])),
            "impacted_count": len(nodes),
            "edges": path_edges,
            "truncated": truncated,
            "low_confidence_count": len(weak),
            "limitation": ("계보는 **등록된 관계만** 안다. 영향 0건이 곧 안전을 뜻하지 않는다 — "
                           "등록되지 않은 사용처는 여기에 나타나지 않는다."),
        }

    # ── 결정론적 도출 ─────────────────────────────────────────────────────
    def derive_edges(self, catalog=None, glossary=None) -> dict:
        """이미 저장된 사실에서 간선을 만든다(멱등, LLM 0콜).

        만드는 선은 넷뿐이고 전부 **명시된 링크**에 근거한다:
          · 연계 시스템 → 자산      (`data_assets.system_id`)
          · 자산 → 필드            (`data_asset_fields`)
          · 필드 → 기준정보        (`data_asset_fields.master_code`)
          · 용어 → 기준정보        (`business_terms.master_code`)
        추론으로 만드는 선은 없다 — 이름이 비슷하다고 잇기 시작하면 영향 분석을 믿을 수 없다."""
        from core.data_catalog import data_catalog
        from core.business_glossary import business_glossary
        cat = catalog or data_catalog
        glo = glossary or business_glossary

        made = {"system_to_asset": 0, "asset_to_field": 0, "field_to_master": 0,
                "term_to_master": 0}
        for a in cat.list_assets():
            aid = a["asset_id"]
            if a["system_id"]:
                self.add_edge("system", a["system_id"], "asset", aid, "feeds",
                              evidence_ref=f"data_assets.system_id={a['system_id']}",
                              origin="derived")
                made["system_to_asset"] += 1
            for f in cat.get_asset(aid)["fields"]:
                fid = f"{aid}.{f['name']}"
                self.add_edge("asset", aid, "field", fid, "feeds",
                              evidence_ref="data_asset_fields", origin="derived")
                made["asset_to_field"] += 1
                if f.get("master_code"):
                    self.add_edge("field", fid, "master", f["master_code"], "references",
                                  evidence_ref="data_asset_fields.master_code", origin="derived")
                    made["field_to_master"] += 1
        for t in glo.list_terms():
            if t.get("master_code"):
                self.add_edge("term", t["term_id"], "master", t["master_code"], "references",
                              evidence_ref="business_terms.master_code", origin="derived")
                made["term_to_master"] += 1
        made["total"] = sum(v for k, v in made.items() if k != "total")
        made["note"] = ("명시된 링크에서만 도출합니다. 이름 유사도 같은 추론으로는 잇지 않습니다 — "
                        "믿을 수 없는 영향 분석은 없는 것보다 위험합니다.")
        return made


data_lineage = DataLineage()
