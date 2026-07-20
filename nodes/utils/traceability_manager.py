import os
import re
import json
from typing import Dict, Any, List
from filelock import FileLock

# ──────────────────────────────────────────────────────────────────────────────
# G1 추적성 유틸(모듈 함수) — 전부 LLM 0콜 순수 함수. 추출/대조/리포트의 SSOT.
# ID 표기 규약: 접두사(FR/REQ) + 구분자('-' 또는 '_') + 숫자 1~4자리.
# 정규화: 대문자 접두사 + '-' + 3자리 제로패딩(FR-1 == FR-001 로 통일, 1000 이상은 그대로).
# ──────────────────────────────────────────────────────────────────────────────
_TRACE_ID_RE: Dict[str, Any] = {}  # prefix → 컴파일된 정규식 캐시


def extract_ids(text: str, prefix: str = "FR") -> List[str]:
    """텍스트에서 요구 ID(FR-001, fr_2 등)를 추출해 표기를 정규화(FR-002)하고
    등장 순서를 보존하며 중복 제거해 반환한다.
    (공백 구분 'FR 3' 표기는 오탐 위험이 커서 의도적으로 제외 — 하이픈/언더스코어만 인정)"""
    if not text:
        return []
    pat = _TRACE_ID_RE.get(prefix)
    if pat is None:
        pat = re.compile(rf"\b{prefix}[-_](\d{{1,4}})\b", re.IGNORECASE)
        _TRACE_ID_RE[prefix] = pat
    out: List[str] = []
    seen = set()
    for m in pat.finditer(text):
        canon = f"{prefix.upper()}-{int(m.group(1)):03d}"
        if canon not in seen:
            seen.add(canon)
            out.append(canon)
    return out


def extract_req_links(prd_text: str) -> Dict[str, List[str]]:
    """PRD 텍스트에서 FR↔REQ 연결을 라인 단위로 추출한다.
    같은 줄에 FR-ID 와 REQ-ID 가 함께 등장하면 연결로 간주(표/목록형 PRD 의 일반 표기:
    'FR-001: 로그인 (REQ-002)'). 줄을 넘는 연결은 오탐 위험이 커서 의도적으로 미지원."""
    links: Dict[str, List[str]] = {}
    for line in (prd_text or "").splitlines():
        frs = extract_ids(line, "FR")
        if not frs:
            continue
        reqs = extract_ids(line, "REQ")
        if not reqs:
            continue
        for fr in frs:
            cur = links.setdefault(fr, [])
            for r in reqs:
                if r not in cur:
                    cur.append(r)
    return links


def read_mappings(workspace_root: str) -> List[Dict[str, Any]]:
    """추적성 맵을 '읽기 전용'으로 로드(파일 미존재 시 빈 리스트).
    ⚠️ TraceabilityManager 생성자는 맵 파일을 만들어버리는 부수효과가 있으므로,
    채점기(criteria) 등 검사 경로에서는 반드시 이 함수를 쓸 것."""
    try:
        path = os.path.join(workspace_root or "", "traceability_map.json")
        if not workspace_root or not os.path.exists(path):
            return []
        with open(path, "r", encoding="utf-8") as f:
            return (json.load(f) or {}).get("mappings", []) or []
    except Exception:
        return []


def compute_coverage(prd_text: str, mappings: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """PRD 에 정의된 FR 전수 vs 추적성 맵에 매핑(구현)된 FR 을 결정론 대조.
    반환: {'defined': [...], 'implemented': [...], 'missing': [...]} (전부 정규화 표기)"""
    defined = extract_ids(prd_text, "FR")
    implemented: List[str] = []
    seen = set()
    for m in mappings or []:
        for raw in m.get("fr_ids", []) or []:
            for c in extract_ids(str(raw), "FR"):  # 저장값도 재정규화(과거 표기 편차 방어)
                if c not in seen:
                    seen.add(c)
                    implemented.append(c)
    missing = [f for f in defined if f not in seen]
    return {"defined": defined, "implemented": implemented, "missing": missing}


def build_coverage_report(rfp_text: str, prd_text: str, mappings: List[Dict[str, Any]]) -> str:
    """수용검수(Supervisor) 근거용 '요구 추적성 현황' 마크다운 표를 생성한다(LLM 0콜).
    PRD 가 FR 체계를 쓰지 않으면 빈 문자열(비SW 산출물 등은 표 없이 진행)."""
    cov = compute_coverage(prd_text, mappings)
    if not cov["defined"]:
        return ""
    links = extract_req_links(prd_text)

    # FR → 구현 태스크/파일 역인덱스
    fr_tasks: Dict[str, List[str]] = {}
    fr_files: Dict[str, set] = {}
    for m in mappings or []:
        t = m.get("task_id", "") or ""
        fl = m.get("files", []) or []
        for raw in m.get("fr_ids", []) or []:
            for c in extract_ids(str(raw), "FR"):
                fr_tasks.setdefault(c, [])
                if t and t not in fr_tasks[c]:
                    fr_tasks[c].append(t)
                fr_files.setdefault(c, set()).update(fl)

    done = len(cov["defined"]) - len(cov["missing"])
    lines = [
        "## 🔗 요구 추적성 현황 (결정론 집계 — 코드가 계산한 사실이므로 판정 근거로 사용할 것)",
        f"- PRD 정의 FR {len(cov['defined'])}건 / 구현 매핑 {done}건 / **미매핑 {len(cov['missing'])}건**",
        "",
        "| FR | 연결 REQ | 구현 태스크 | 파일 수 | 상태 |",
        "|---|---|---|---|---|",
    ]
    for fr in cov["defined"][:40]:
        reqs = ", ".join(links.get(fr, [])) or "-"
        tasks = ", ".join(fr_tasks.get(fr, [])) or "-"
        nf = len(fr_files.get(fr, ()))
        status = "⚠️ 미매핑" if fr in cov["missing"] else "✅ 매핑"
        lines.append(f"| {fr} | {reqs} | {tasks} | {nf} | {status} |")
    if len(cov["defined"]) > 40:
        lines.append(f"| (외 {len(cov['defined']) - 40}건 생략) | | | | |")
    if cov["missing"]:
        lines.append("")
        lines.append(f"⚠️ 미매핑 FR: {', '.join(cov['missing'])} — 구현 누락이거나 WBS 태스크가 FR-ID 를 인용하지 않은 경우.")
    # RFP REQ 커버리지(참고): RFP 에 정의된 REQ 중 PRD 의 FR 로 연결 표기가 없는 항목
    reqs_defined = extract_ids(rfp_text or "", "REQ")
    if reqs_defined:
        linked = {r for v in links.values() for r in v}
        unlinked = [r for r in reqs_defined if r not in linked]
        if unlinked:
            lines.append(f"ℹ️ RFP REQ 중 PRD FR 연결 표기가 없는 항목: {', '.join(unlinked[:15])}")
    return "\n".join(lines)


class TraceabilityManager:
    def __init__(self, workspace_root: str):
        self.workspace_root = workspace_root
        self.map_file_path = os.path.join(self.workspace_root, "traceability_map.json")
        self._lock = FileLock(self.map_file_path + ".lock")
        os.makedirs(self.workspace_root, exist_ok=True)
        self._init_if_not_exists()

    def _init_if_not_exists(self) -> None:
        if not os.path.exists(self.map_file_path):
            with self._lock:
                if not os.path.exists(self.map_file_path): # Double-check after acquiring lock
                    with open(self.map_file_path, "w", encoding="utf-8") as f:
                        json.dump({"mappings": []}, f, indent=4, ensure_ascii=False)

    def _read_unlocked(self) -> Dict[str, Any]:
        try:
            with open(self.map_file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"mappings": []}

    def update_mapping(self, task_id: str, fr_ids: List[str], files: List[str]) -> None:
        """새로 생성/수정된 파일들을 해당 태스크의 요구사항(FR-ID)과 맵핑하여 저장합니다."""
        if not fr_ids and not files:
            return
            
        with self._lock:
            data = self._read_unlocked()
            mappings = data.get("mappings", [])
            
            # Remove existing mapping for this task if it exists (for rework/retries)
            mappings = [m for m in mappings if m.get("task_id") != task_id]
            
            mappings.append({
                "task_id": task_id,
                "fr_ids": list(set(fr_ids)),
                "files": list(set(files))
            })
            
            data["mappings"] = mappings
            
            with open(self.map_file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)

    def get_mappings(self) -> List[Dict[str, Any]]:
        """저장된 모든 추적성 맵핑 데이터를 반환합니다."""
        with self._lock:
            data = self._read_unlocked()
            return data.get("mappings", [])
