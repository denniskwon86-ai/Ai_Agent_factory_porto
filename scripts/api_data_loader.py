"""마스터데이터(M1~M4) 정규화 주입 로더.

[재작성 배경] 이전 버전은 M1 JSON 전체를 단일 레코드(BATT-001)의 attributes 로 통째 밀어넣어,
M1 저장소의 핵심(자재/설비/KPI 개별 골든레코드 → 별칭 감지·결정론 주입)이 무력화됐다.
이 로더는 각 섹션을 순회하며 **항목 하나 = 골든레코드 하나**로 정규화 주입한다.

- master_code: 소스의 고유 ID(RM-MHP-001 등)를 대문자 정규화해 재사용(정규식 ^[A-Z0-9][A-Z0-9_-]{1,31}$).
- attributes: 해당 항목의 속성만(정형 수치 보존).
- aliases: 명칭 + 괄호 안 한글명 자동 추출(예: "Flash Smelting Furnace (자용로)" → 자용로).
- domains: 파일별 도메인 태그. is_core: 대표 레코드(완제품/설비/KPI/배출계수/재무).
- 동일 code 재-POST 는 개정(version+1)이라 멱등 재실행 가능. cleanup 으로 과거 오주입을 정리한다.

전제: 백엔드가 http://localhost:8080 에서 실행 중이어야 한다(REST API 주입).
실행: .venv/Scripts/python.exe scripts/api_data_loader.py
"""
import os
import re
import json
import urllib.request
import urllib.error

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS_DIR = os.path.join(BASE_DIR, "docs", "master_data")
API_BASE = "http://localhost:8080/api/v1/master"

_stats = {"types": 0, "records": 0, "revised": 0, "failed": 0, "deleted": 0}


# ── HTTP 헬퍼 ──────────────────────────────────────────────────────────
def _request(method, endpoint, payload=None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(f"{API_BASE}/{endpoint}", data=data,
                                 headers={"Content-Type": "application/json"}, method=method)
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read().decode("utf-8")), None
    except urllib.error.HTTPError as e:
        return None, (e.code, e.read().decode("utf-8", errors="replace"))
    except Exception as e:
        return None, (0, str(e))


def ensure_type(type_id, name_ko, description):
    _, err = _request("POST", "types", {"type_id": type_id, "name_ko": name_ko,
                                         "description": description, "attr_schema": {}})
    if err and err[0] != 409:
        print(f"  [WARN] 타입 생성 실패 {type_id}: {err}")
    else:
        _stats["types"] += 1 if not err else 0


def upsert_record(code, type_id, name, attributes, domains, aliases, is_core):
    data, err = _request("POST", "records", {
        "master_code": code, "type_id": type_id, "name": name,
        "attributes": attributes, "domains": domains, "aliases": aliases, "is_core": is_core,
    })
    if err:
        print(f"  [FAIL] {code}: {err}")
        _stats["failed"] += 1
        return
    ver = (data or {}).get("data", {}).get("version", 1)
    if ver and ver > 1:
        _stats["revised"] += 1
    else:
        _stats["records"] += 1


def delete_record(code):
    _, err = _request("DELETE", f"records/{code}", None)
    if not err:
        _stats["deleted"] += 1
        print(f"  [CLEAN] soft-retire: {code}")


# ── 변환 유틸 ──────────────────────────────────────────────────────────
def to_code(raw, prefix=""):
    """소스 ID/문자열을 master_code 규격(^[A-Z0-9][A-Z0-9_-]{1,31}$)으로 정규화."""
    s = f"{prefix}{raw}".upper()
    s = re.sub(r"[^A-Z0-9_-]+", "-", s).strip("-")
    s = re.sub(r"-{2,}", "-", s)
    if not s:
        s = "X"
    if not re.match(r"[A-Z0-9]", s[0]):
        s = "X" + s
    return s[:32]


def aliases_from_name(name):
    """명칭에서 별칭 추출: 원문 + 괄호 안(한글명 등) + 괄호 제거 본명."""
    name = (name or "").strip()
    if not name:
        return []
    out = [name]
    for m in re.findall(r"[(（]([^)）]+)[)）]", name):
        out.append(m.strip())
    base = re.sub(r"\s*[(（][^)）]+[)）]", "", name).strip()
    if base and base != name:
        out.append(base)
    # 중복 제거(순서 보존), 2자 미만 별칭 제거(감지 오탐 방지 정책과 일치)
    seen, res = set(), []
    for a in out:
        if a and len(a) >= 2 and a not in seen:
            seen.add(a)
            res.append(a)
    return res


def _attrs(item, drop_keys):
    return {k: v for k, v in item.items() if k not in drop_keys}


# ── 타입 온톨로지 ──────────────────────────────────────────────────────
TYPES = [
    ("material", "품목 마스터", "원자재·재공품·완제품·부산물 규격(단가·리드타임·UOM 등)"),
    ("equipment", "설비 마스터", "생산 설비 규격(CAPA·OEE·MTBF·MTTR 등)"),
    ("bom", "BOM(자재명세)", "완제품별 구성 자재·수율·부산물"),
    ("quality_spec", "품질 규격", "제품별 검사법·임계 결함·Cpk"),
    ("finance_param", "재무·시장 파라미터", "시장가(LME 등)·원가구조·SLA/패널티"),
    ("kpi", "KPI 정의", "ISO22400 등 지표 정의·산식·임계값"),
    ("emission_factor", "탄소 배출계수", "유틸리티별 CO2e 배출계수(ESG/CBAM)"),
    ("sensor_spec", "PDM 센서 규격", "예지보전 센서 임계값"),
    ("standard_field", "표준 필드(KS X 9101)", "표준 필드코드↔레거시 매핑(크로스워크 기준)"),
    ("simulation_node", "시뮬레이션 물리 노드", "디지털 트윈 3D 공간 제약 노드"),
]


# ── 도메인 파일(M1/M2) 정규화 ──────────────────────────────────────────
def load_domain_file(filename, domains, dom_prefix):
    path = os.path.join(DOCS_DIR, filename)
    if not os.path.exists(path):
        print(f"  (건너뜀: {filename} 없음)")
        return
    d = json.load(open(path, encoding="utf-8"))
    print(f"\n[{filename}] domains={domains}")

    for m in d.get("material_master", []):
        code = to_code(m.get("material_id", ""))
        upsert_record(code, "material", m.get("material_name", code),
                      _attrs(m, {"material_id", "material_name"}),
                      domains, aliases_from_name(m.get("material_name", "")),
                      is_core=(m.get("type") == "Finished Good"))

    for e in d.get("equipment_master", []):
        code = to_code(e.get("equipment_id", ""))
        upsert_record(code, "equipment", e.get("equipment_name", code),
                      _attrs(e, {"equipment_id", "equipment_name"}),
                      domains, aliases_from_name(e.get("equipment_name", "")), is_core=True)

    for b in d.get("bill_of_materials", []):
        pid = b.get("parent_id", "UNKNOWN")
        upsert_record(to_code(pid, "BOM-"), "bom", f"BOM: {pid}", b, domains, [], is_core=False)

    for q in d.get("quality_master", []):
        pid = q.get("product_id", "UNKNOWN")
        upsert_record(to_code(pid, "QC-"), "quality_spec", f"품질규격: {pid}", q, domains, [], is_core=False)

    for i, fin in enumerate(d.get("siop_finance_master", [])):
        cat = fin.get("category", f"P{i}")
        upsert_record(to_code(f"{dom_prefix}-{cat}", "FIN-"), "finance_param", f"[{dom_prefix}] {cat}",
                      fin, domains, aliases_from_name(cat), is_core=True)


# ── M3 글로벌 표준(정형 항목만 master, 서술 표준은 지식허브가 담당) ─────
def load_m3(filename="global_standard_m3.json"):
    path = os.path.join(DOCS_DIR, filename)
    if not os.path.exists(path):
        print(f"  (건너뜀: {filename} 없음)")
        return
    d = json.load(open(path, encoding="utf-8"))
    print(f"\n[{filename}] 정형 항목 → master (서술형은 지식허브 유지)")

    for k in d.get("iso22400_kpi_dictionary", []):
        code = to_code(k.get("kpi_id", ""))
        upsert_record(code, "kpi", k.get("name", code), k, ["standard", "manufacturing"],
                      aliases_from_name(k.get("name", "")), is_core=True)

    for ef in d.get("esg_cbam_master", {}).get("emission_factors", []):
        ut = ef.get("utility_type", "UNKNOWN")
        upsert_record(to_code(ut, "EF-"), "emission_factor", ut, ef, ["esg", "manufacturing"],
                      aliases_from_name(ut), is_core=True)

    for s in d.get("pdm_sensor_schema", []):
        st = s.get("sensor_type", "UNKNOWN")
        upsert_record(to_code(st, "SNS-"), "sensor_spec", st, s, ["pdm", "simulation"],
                      aliases_from_name(st), is_core=False)

    for f in d.get("ks_x_9101_national_standard", {}).get("data_model_dictionary_part1", []):
        fc = f.get("standard_field_code", "UNKNOWN")
        # legacy_mappings 를 별칭으로 → 크로스워크(M2) 자동 매핑 후보로 활용
        al = [x for x in f.get("legacy_mappings", []) if isinstance(x, str)]
        upsert_record(to_code(fc, "STD-"), "standard_field", fc, f, ["standard"], al, is_core=False)


# ── M4 시뮬레이션 3D 노드 ──────────────────────────────────────────────
def load_m4(filename="digital_twin_simulation_m4.json"):
    path = os.path.join(DOCS_DIR, filename)
    if not os.path.exists(path):
        print(f"  (건너뜀: {filename} 없음)")
        return
    d = json.load(open(path, encoding="utf-8"))
    nodes = d.get("spatial_3d_fab_layout", {}).get("nodes", [])
    print(f"\n[{filename}] 3D 노드 {len(nodes)}개")
    for node in nodes:
        nid = node.get("node_id", "UNKNOWN")
        upsert_record(to_code(nid), "simulation_node", f"3D Node: {nid}", node,
                      ["simulation", "logistics"], aliases_from_name(node.get("node_name", "")), is_core=True)


# ── 과거 오주입 정리 ───────────────────────────────────────────────────
def cleanup_legacy():
    print("\n[정리] 과거 오주입/테스트 잔재 제거")
    for bad in ["BATT-001", "PROC-ASSY-01"]:
        delete_record(bad)


def run():
    print("=== 마스터데이터 정규화 주입 시작 ===")
    print("타입 온톨로지 생성...")
    for t in TYPES:
        ensure_type(*t)
    cleanup_legacy()
    load_domain_file("battery_material_m1.json", ["battery", "manufacturing"], "BATT")
    load_domain_file("copper_smelting_m2.json", ["copper", "manufacturing"], "CU")
    load_m3()
    load_m4()
    print("\n=== 완료 ===")
    print(f"신규 레코드 {_stats['records']} · 개정 {_stats['revised']} · 실패 {_stats['failed']} · "
          f"정리 {_stats['deleted']} · 타입 {_stats['types']}")


if __name__ == "__main__":
    run()
