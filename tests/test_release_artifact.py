"""[P1] 배포 산출물 계약 — 선별·내용·완결·기록을 **실행되는 검사**로 잠근다.

⚠️ 이 시험이 지키는 것은 「배포가 된다」가 아니라 **「검사기가 제 일을 한다」**이다.
  검사기가 틀리면 그 뒤의 모든 초록이 거짓이 된다.

⚠️ 격리 러너는 저장소 `conftest.py` 를 읽지 않는다 — 여기서는 **파일 경로로 직접 적재**하고
  합성 트리에서만 논다. 운영 자료·운영 DB 를 건드리지 않는다.
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_TOOL = os.path.join(os.path.dirname(_HERE), "scripts", "release_artifact.py")

_spec = importlib.util.spec_from_file_location("_release_artifact_under_test", _TOOL)
ra = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(ra)


# ── 합성 트리 ────────────────────────────────────────────────────────────
def _write(root, rel: str, body: str = "x\n") -> str:
    full = os.path.join(str(root), *rel.split("/"))
    os.makedirs(os.path.dirname(full), exist_ok=True)
    io.open(full, "w", encoding="utf-8", newline="").write(body)
    return rel


def _minimal_tree(root):
    """필수 자산까지 갖춘 «통과하는» 최소 트리 — 여기서부터 하나씩 망가뜨린다."""
    _write(root, "main.py", "import config\n")
    _write(root, "config.py", "VALUE = 1\n")
    _write(root, "requirements.txt", "fastapi\n")
    for name in ("runtime.js", "babel.js", "tailwind.js"):
        _write(root, f"frontend/dist/preview-vendor/{name}", "//\n")
    _write(root, "frontend/dist/index.html", "<html></html>")
    return root


# ── ① 선별 — 거부가 허용을 이긴다 ────────────────────────────────────────
def test_denied_paths_never_ship_even_inside_allowed_dirs(tmp_path):
    """⚠️ `core/**` 를 허용했다고 그 «안의» 무엇이든 나가면 안 된다."""
    _minimal_tree(tmp_path)
    _write(tmp_path, "core/real.py", "x = 1\n")
    _write(tmp_path, "core/.env", "SECRET=1\n")
    _write(tmp_path, "core/cache.db", "binary")
    _write(tmp_path, "core/app.log", "line\n")

    picked = set(ra.selected_files(str(tmp_path)))
    assert "core/real.py" in picked
    for denied in ("core/.env", "core/cache.db", "core/app.log"):
        assert denied not in picked, f"{denied} 가 산출물에 들어갔다"


def test_unlisted_top_level_directory_does_not_ship(tmp_path):
    """★ 허용목록 방식의 «핵심» — 새 디렉터리는 **조용히 딸려 나가지 않는다**."""
    _minimal_tree(tmp_path)
    _write(tmp_path, "brand_new_dir/thing.py", "x = 1\n")
    assert "brand_new_dir/thing.py" not in set(ra.selected_files(str(tmp_path)))


def test_business_formats_are_cut_outside_asset_prefixes(tmp_path):
    _minimal_tree(tmp_path)
    _write(tmp_path, "core/leaked_sheet.csv", "a,b\n1,2\n")
    assert "core/leaked_sheet.csv" not in set(ra.selected_files(str(tmp_path)))


def test_business_formats_survive_inside_asset_prefixes_and_are_counted(tmp_path):
    """★ 예외는 있어도 되지만 **조용하면 안 된다.**

    ⚠️ `starter_kits/` 의 CSV 를 형식 규칙으로 잘라 버리면 스타터 킷이 «반쪽» 으로
      나가고 아무도 모른다. 그래서 통과시키되 **숫자로 남긴다**."""
    _minimal_tree(tmp_path)
    _write(tmp_path, "starter_kits/KIT-A/1.0.0/rows.csv", "a,b\n1,2\n")
    files = ra.selected_files(str(tmp_path))
    assert "starter_kits/KIT-A/1.0.0/rows.csv" in set(files)
    assert ra.business_format_exceptions(files) == {"starter_kits/": 1}


def test_raw_business_data_is_never_an_asset_exception(tmp_path):
    """⚠️ `raw/` 는 스냅숏이 올린 **불변 원자료**다. 예외가 적용되면 안 된다."""
    _minimal_tree(tmp_path)
    _write(tmp_path, "raw/ds_x__EXT-02__2026-09-11.csv", "a,b\n")
    picked = set(ra.selected_files(str(tmp_path)))
    assert not [f for f in picked if f.startswith("raw/")]


# ── ② 내용 — 종류만 말하고 값은 싣지 않는다 ──────────────────────────────
def test_planted_private_key_is_found(tmp_path):
    _minimal_tree(tmp_path)
    _write(tmp_path, "core/oops.py",
           "KEY = '''-----BEGIN RSA PRIVATE KEY-----\nMIIabc\n'''\n")
    result = ra.verify(str(tmp_path))
    assert result["ok"] is False
    kinds = {f["kind"] for f in result["secret_findings"]}
    assert "개인키" in kinds, result["secret_findings"]


def test_a_clean_tree_reports_nothing(tmp_path):
    """★ 음성 대조 — 위 시험이 «늘 빨강» 이 아님을 보인다."""
    _minimal_tree(tmp_path)
    _write(tmp_path, "core/fine.py", "VALUE = 'ordinary text'\n")
    assert ra.verify(str(tmp_path))["secret_findings"] == []


def test_findings_never_carry_the_value(tmp_path):
    """⚠️⚠️ 경고문에 값을 실으면 **그 경고가 다시 유출 경로**가 된다."""
    _minimal_tree(tmp_path)
    secret = "AKIA" + "ABCDEFGHIJKLMNOP"
    _write(tmp_path, "core/oops.py", f"AWS = '{secret}'\n")
    findings = ra.verify(str(tmp_path))["secret_findings"]
    assert findings, "심은 키를 못 찾았다"
    assert secret not in json.dumps(findings, ensure_ascii=False)
    assert {"path", "line", "kind"} == set(findings[0])


def test_csv_that_ships_by_exception_is_also_scanned(tmp_path):
    """★ **나가는데 안 보는 자리**가 있으면 거기가 구멍이다."""
    _minimal_tree(tmp_path)
    _write(tmp_path, "starter_kits/KIT-A/1.0.0/rows.csv",
           "col\npostgresql://u:p@host/db\n")
    kinds = {f["kind"] for f in ra.verify(str(tmp_path))["secret_findings"]}
    assert "암호가 박힌 DSN" in kinds


# ── ③ 필수 자산 ─────────────────────────────────────────────────────────
@pytest.mark.parametrize("victim", [
    "frontend/dist/index.html",
    "frontend/dist/preview-vendor/runtime.js",
    "frontend/dist/preview-vendor/babel.js",
    "frontend/dist/preview-vendor/tailwind.js",
])
def test_missing_required_asset_fails(tmp_path, victim):
    """★ [DEP-09] `preview-vendor` 3종이 빠지면 **미리보기가 통째로 죽는다.**

    index/chunk 만 보는 검사는 그 산출물을 «정상» 이라고 말한다."""
    _minimal_tree(tmp_path)
    os.remove(os.path.join(str(tmp_path), *victim.split("/")))
    result = ra.verify(str(tmp_path))
    assert result["ok"] is False
    assert victim in result["missing_required"]


# ── ④ 완결성 — 이 검사가 실제 결함 2건을 잡았다 ──────────────────────────
def test_module_imported_but_not_allowlisted_is_reported(tmp_path):
    """★ 이 검사가 없었다면 **조용히 깨진 산출물**이 나갔다.

    실제로 이 도구의 첫 초안에서 `config.py`(19곳 import)와 `nodes/` 22모듈이
    허용목록 밖이었는데 선별·필수·내용 검사는 **전부 초록**이었다."""
    _minimal_tree(tmp_path)
    _write(tmp_path, "main.py", "import config\nimport secret_helper\n")
    _write(tmp_path, "secret_helper.py", "x = 1\n")  #: 허용목록에 없는 루트 모듈
    result = ra.verify(str(tmp_path))
    assert result["ok"] is False
    assert "secret_helper.py" in result["missing_imported_modules"]


def test_allowlisted_import_is_not_reported(tmp_path):
    """★ 음성 대조 — 허용된 모듈까지 신고하면 이 검사는 쓸 수 없다."""
    _minimal_tree(tmp_path)
    _write(tmp_path, "main.py", "import config\nfrom core import thing\n")
    _write(tmp_path, "core/__init__.py", "")
    _write(tmp_path, "core/thing.py", "x = 1\n")
    assert ra.verify(str(tmp_path))["missing_imported_modules"] == []


def test_dunder_import_with_a_literal_is_followed(tmp_path):
    """⚠️ `core/agent_graph.py` 가 실제로 `__import__("nodes.vision_qa", …)` 를 쓴다.

    이름이 다르다고 놓치면 **패키지 하나가 통째로** 빠진 채 초록이 된다."""
    _minimal_tree(tmp_path)
    _write(tmp_path, "main.py",
           'x = __import__("hidden_pkg.leaf", fromlist=["go"]).go\n')
    _write(tmp_path, "hidden_pkg/__init__.py", "")
    _write(tmp_path, "hidden_pkg/leaf.py", "def go(): pass\n")
    missing = ra.verify(str(tmp_path))["missing_imported_modules"]
    assert "hidden_pkg/leaf.py" in missing and "hidden_pkg/__init__.py" in missing


def test_package_init_is_pulled_in_with_its_module(tmp_path):
    """⚠️ `__init__.py` 가 빠지면 그 아래 모듈은 **import 자체가 안 된다.**"""
    _write(tmp_path, "main.py", "from deep.pkg import leaf\n")
    _write(tmp_path, "deep/__init__.py", "")
    _write(tmp_path, "deep/pkg/__init__.py", "")
    _write(tmp_path, "deep/pkg/leaf.py", "x = 1\n")
    closure = ra.imported_local_files(str(tmp_path))
    assert {"deep/__init__.py", "deep/pkg/__init__.py", "deep/pkg/leaf.py"} <= closure


def test_completeness_does_not_execute_the_code_it_reads(tmp_path):
    """⚠️⚠️ **앱을 import 해서 알아내면 안 된다** — import 는 DDL·seed 를 돌리고

    자료를 바꾼다. 실행했다면 이 모듈에서 죽는다."""
    _write(tmp_path, "main.py", "import landmine\n")
    _write(tmp_path, "landmine.py",
           "raise SystemExit('이 모듈이 실행되면 안 된다')\n")
    assert "landmine.py" in ra.imported_local_files(str(tmp_path))


def test_unreadable_syntax_does_not_crash_the_walk(tmp_path):
    _write(tmp_path, "main.py", "import broken\n")
    _write(tmp_path, "broken.py", "def (((\n")
    assert "broken.py" in ra.imported_local_files(str(tmp_path))


# ── ⑤ manifest — 무엇을 배포했는지 나중에 답할 수 있어야 한다 ────────────
def test_manifest_hash_follows_content(tmp_path):
    _minimal_tree(tmp_path)
    before = ra.build_manifest(["config.py"], str(tmp_path))["files"]["config.py"]
    _write(tmp_path, "config.py", "VALUE = 2\n")
    after = ra.build_manifest(["config.py"], str(tmp_path))["files"]["config.py"]
    assert before["sha256"] != after["sha256"]


def test_manifest_is_not_written_when_the_check_fails(tmp_path, monkeypatch, capsys):
    """⚠️ 걸린 트리로 만든 manifest 는 **「검사를 통과했다」는 기록처럼** 쓰인다."""
    _minimal_tree(tmp_path)
    os.remove(os.path.join(str(tmp_path), "frontend", "dist", "index.html"))
    out = tmp_path / "artifacts" / "manifest.json"
    monkeypatch.setattr(ra, "ROOT", str(tmp_path))
    monkeypatch.setattr(sys, "argv",
                        ["release_artifact.py", "--manifest", str(out)])
    assert ra.main() == 1
    capsys.readouterr()
    assert not out.exists(), "검사에 걸렸는데 manifest 가 만들어졌다"


# ── ⑥ 실제 나무 — 계약이 «오늘» 성립하는가 ───────────────────────────────
#: ⚠️ 건수를 박지 않는다(자연히 변한다). 불변식만 단언한다.
def test_real_tree_passes_every_gate():
    result = ra.verify()
    assert result["missing_required"] == [], result["missing_required"]
    assert result["missing_imported_modules"] == [], result["missing_imported_modules"]
    assert result["secret_findings"] == [], result["secret_findings"]
    assert result["ok"] is True


def test_real_tree_never_ships_operational_data():
    """⚠️ 운영 자료·DB·로그가 한 건이라도 섞이면 즉시 빨강."""
    bad = [f for f in ra.selected_files()
           if f.startswith(("data/", "raw/", "output/", "library/", "projects/",
                            "workspace/", "venv/"))
           or f.endswith((".db", ".sqlite", ".jsonl", ".log", ".env"))]
    assert bad == [], bad


def test_real_tree_ships_no_scripts_except_named_ones():
    """★ `deploy/*.sh` 도 `afs.service` 도 `scripts/` 를 부르지 않는다(실측).

    그런데 그 안에는 **운영 DB 에 자료를 심는 도구**가 있다 — 호스트가 들고 있을
    이유가 없다. 다만 승격 판정을 내리는 준비도 탐침은 **노드 위에 있어야** 한다.

    ⚠️ 그래서 «전부 금지» 가 아니라 **이름을 적은 것만 허용**이다. 디렉터리째 다시
      열면 자료 심는 도구가 조용히 따라 들어온다."""
    shipped = [f for f in ra.selected_files() if f.startswith("scripts/")]
    assert shipped == ["scripts/serving_readiness_probe.py"], shipped
