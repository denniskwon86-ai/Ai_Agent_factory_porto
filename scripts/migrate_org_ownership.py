r"""기존 프로젝트·릴리스에 소유 부서를 소급 부여한다 (설계서 Phase 3). **멱등**.

⚠️ 왜 필요한가:
  소유권 필드는 지금 추가됐으므로 기존 산출물은 전부 무소속이다. 무소속은 하위호환을 위해
  '전부 보임'으로 처리되는데, 그 상태로 권한을 켜면 **부서 격리가 사실상 작동하지 않는다.**
  이 스크립트가 기존 자산에 부서를 붙여 권한을 실질화한다.

추론 규칙:
  · 메가 서브 프로젝트 `<mega>_<domain>` → `domain` 이 부서면 그 부서
  · 메가 마스터(서브를 가진 것) → `hq` + `company`(전사 공개)
  · 그 외 독립 프로젝트 → 무소속 유지(`""`). 임의로 부서를 찍으면 남의 부서 자료가 된다.

⚠️ Chroma 재인덱싱은 하지 않는다 — 임베딩 비용이 크고, 과거 청크는 `project_id → ownership`
   폴백으로 해석할 수 있다.

사용: .\venv\Scripts\python.exe scripts\migrate_org_ownership.py [--apply]
      (기본은 dry-run — 무엇이 바뀌는지만 출력한다)
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.org_directory import org_directory
from core.org_seed import seed_departments

PROJECTS = "projects"
LIBRARY = "library"


def _load(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def _save(path: str, data: dict):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def infer_dept(project_id: str, dept_ids: set, all_ids: set) -> tuple:
    """(dept_id, visibility) 추론. 확신이 없으면 무소속으로 둔다."""
    # 메가 마스터: 자기 이름을 접두로 가진 서브가 존재
    if any(o != project_id and o.startswith(project_id + "_") for o in all_ids):
        return "hq", "company"
    if "_" in project_id:
        suffix = project_id.rsplit("_", 1)[-1]
        if suffix in dept_ids:
            return suffix, "dept"
    return "", "dept"


def main(apply: bool = False) -> int:
    seed_departments()   # 부서가 없으면 먼저 적재(멱등)
    dept_ids = {d["dept_id"] for d in org_directory.list_departments()}
    print(f"등록 부서 {len(dept_ids)}개: {sorted(dept_ids)}\n")

    changed = kept = 0
    if os.path.isdir(PROJECTS):
        all_ids = {p for p in os.listdir(PROJECTS) if os.path.isdir(os.path.join(PROJECTS, p))}
        for pid in sorted(all_ids):
            meta_path = os.path.join(PROJECTS, pid, "project_meta.json")
            if not os.path.isfile(meta_path):
                continue
            meta = _load(meta_path)
            if meta.get("owner_dept_id"):
                kept += 1
                continue                      # 이미 부여됨 — 덮어쓰지 않는다(멱등)
            dept, vis = infer_dept(pid, dept_ids, all_ids)
            if not dept:
                print(f"  · {pid:32} → 무소속 유지(추론 불가)")
                kept += 1
                continue
            print(f"  ✎ {pid:32} → {dept} ({vis})")
            changed += 1
            if apply:
                meta.update({"owner_dept_id": dept, "owner_user_id": meta.get("owner_user_id", ""),
                             "visibility": vis, "nature": meta.get("nature", ""),
                             "forked_from": meta.get("forked_from", {})})
                _save(meta_path, meta)
                org_directory.set_ownership("project", pid, dept_id=dept, visibility=vis)

    rel_changed = 0
    if os.path.isdir(LIBRARY):
        for rid in sorted(os.listdir(LIBRARY)):
            rel_path = os.path.join(LIBRARY, rid, "release.json")
            if not os.path.isfile(rel_path):
                continue
            rel = _load(rel_path)
            if rel.get("owner_dept_id"):
                continue
            # 릴리스는 원본 프로젝트의 소유를 따른다
            src = rel.get("project_id", "")
            src_meta = _load(os.path.join(PROJECTS, src, "project_meta.json")) if src else {}
            dept = src_meta.get("owner_dept_id", "")
            if not dept:
                continue
            print(f"  ✎ [release] {rid:28} → {dept}")
            rel_changed += 1
            if apply:
                rel["owner_dept_id"] = dept
                rel["visibility"] = src_meta.get("visibility", "dept")
                _save(rel_path, rel)
                org_directory.set_ownership("release", rid, dept_id=dept,
                                            visibility=rel["visibility"])

    print(f"\n프로젝트: 변경 {changed} / 유지 {kept} · 릴리스: 변경 {rel_changed}")
    if not apply:
        print("※ dry-run 입니다. 실제로 반영하려면 --apply 를 붙여 다시 실행하십시오.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(apply="--apply" in sys.argv))
