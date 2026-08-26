"""★★★ 릴리스가 **게시 당시 테넌트**를 싣는다 — 없으면 재게시가 500 이 난다. (2026-08-26 실측)

## ⚠️⚠️ 무엇이 있었나

`app_data.release_identity` 는 릴리스의 `tenant_id` 를 읽어 `(tenant, app)` 을 돌려준다.
그 칸이 없어서 `('', 'TEST001')` 이 나왔고, 그래서:

    데이터셋을 **만들 때**  : tenant = 호출자의 조직 문맥('tenant-afs-demo-materials')
    데이터셋을 **찾을 때**  : tenant = release_identity()  → ''  ← 못 찾는다

`adopt_dataset` 이 영영 못 찾으니 재게시마다 새로 만들려 했고,
`UNIQUE(tenant_id, app_id, dataset_key)` 에 걸려 **같은 프로젝트를 두 번 게시하면 500** 이
났다(스택트레이스가 그대로 사용자에게 나갔다).

★ 쓰는 곳과 찾는 곳의 출처가 다르면, 둘 다 «맞는 값» 을 쓰면서 서로를 못 찾는다.
"""
import json
import os

import pytest


def test_게시_경로가_테넌트를_릴리스에_찍는다():
    """★★★ **이 파일의 요지.** 이 한 칸이 없어서 재게시가 깨졌다."""
    import inspect

    import api.routes.factory_control as fc

    src = inspect.getsource(fc.create_release)
    assert '"tenant_id"' in src, "릴리스에 테넌트를 찍지 않는다"


def test_테넌트는_게시_당시_소유_정보에서_온다():
    """⚠️ 요청 문맥에서 가져오면 **누가 게시했느냐**에 따라 같은 프로젝트가 다른 테넌트로
    굳는다. 소유 부서와 같은 출처(`project_meta.json`)를 쓴다."""
    import inspect

    import api.routes.factory_control as fc

    src = inspect.getsource(fc.create_release)
    i = src.index('"tenant_id"')
    line = src[i:i + 160]
    assert "_rel_own" in line, "게시 당시 소유 정보가 아니라 다른 곳에서 가져온다"


def test_조직_문맥_세_칸을_모두_찍는다():
    """★★★ 테넌트만 찍고 나머지를 두면 **절반만 고친 것**이다.

    `app_proof.resource_scope` 는 테넌트·조직범위·실행모드를 함께 읽는다. 하나라도 비면
    「이 자원이 어느 조직의 무엇인가」가 확정되지 않아 증명이 발급되지 않는다 —
    실측에서 `entity_mode=''`·`scope_node_id=''` 로 404 가 났다."""
    import inspect

    import api.routes.factory_control as fc

    src = inspect.getsource(fc.create_release)
    for key in ('"tenant_id"', '"enterprise_scope_id"', '"entity_mode"'):
        assert key in src, f"릴리스에 {key} 를 찍지 않는다"


def test_릴리스에_테넌트가_있으면_신원이_풀린다(tmp_path, monkeypatch):
    """★ `release_identity` 가 **둘 다** 채워 돌려줘야 adopt 가 기존 데이터셋을 찾는다."""
    from core import app_data, library_paths

    rid = "PX_20260826_000001"
    monkeypatch.setattr(library_paths, "library_dir", lambda: str(tmp_path), raising=False)
    d = os.path.join(str(tmp_path), rid)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "release.json"), "w", encoding="utf-8") as f:
        json.dump({"project_id": "PX", "tenant_id": "tenant-x"}, f, ensure_ascii=False)

    assert app_data.release_identity(rid) == ("tenant-x", "PX")


def test_테넌트가_없으면_빈_값이_그대로_드러난다(tmp_path, monkeypatch):
    """⚠️ **대조군.** 못 읽은 것을 그럴듯한 기본값으로 채우지 않는다 — 채우면 남의
    테넌트 데이터셋에 결속될 수 있다(`release_identity` 머리말이 경고하는 P0)."""
    from core import app_data, library_paths

    rid = "PY_20260826_000002"
    monkeypatch.setattr(library_paths, "library_dir", lambda: str(tmp_path), raising=False)
    d = os.path.join(str(tmp_path), rid)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "release.json"), "w", encoding="utf-8") as f:
        json.dump({"project_id": "PY"}, f, ensure_ascii=False)

    assert app_data.release_identity(rid) == ("", "PY")


def test_승인된_계약의_매니페스트를_릴리스가_싣는다():
    """★★★ [2026-08-26 실측] 릴리스 매니페스트가 늘 **빈 능력**이었다 —
    `state.app_manifest` 만 봤고 그 값은 계약 절차에서 언제나 `null` 이다.

    그 결과 증명 발급이 「매니페스트 미선언」으로 거절돼 **앱이 데이터를 한 줄도 못 읽었다.**
    ⚠️ 승인된 계약만 쓴다 — 승인 전 선언을 실으면 아무도 동의하지 않은 권한이
      「선언된 것」으로 남는다."""
    import inspect

    import api.routes.factory_control as fc

    src = inspect.getsource(fc.create_release)
    assert "contract_path" in src, "릴리스가 계약 매니페스트를 보지 않는다"
    assert '"APPROVED"' in src, "승인 여부를 확인하지 않고 계약을 싣는다"


def test_승인된_계약을_릴리스에_봉인한다():
    """★★★ [2026-08-26 실측] **운영 승격이 여기서 막혔다.**

        계약↔물질화: 실행 가능한 앱인데 승인된 런타임 계약이 없습니다

    `app_contract_gate.release_contract` 는 `release["runtime_contract"]` 를 읽는다
    («그 릴리스가 실제로 쓴 판» 을 봐야 하므로 workspace 파일이 아니라 이쪽이다).
    그런데 게시 경로가 그 칸을 **한 번도 채우지 않았다** — 계약은 승인까지 끝나 있었는데도.
    매니페스트가 비어 있던 것과 같은 누락이다."""
    import inspect

    import api.routes.factory_control as fc

    src = inspect.getsource(fc.create_release)
    assert '"runtime_contract"' in src, "릴리스에 계약을 봉인하지 않는다"


def test_승인_전_계약은_봉인하지_않는다():
    """⚠️⚠️ **대조군.** 승인 전 판을 봉인하면 그 릴리스는 「승인된 계약이 있는 것」으로
    읽히고, 그 순간 검토 게이트가 이름만 남는다."""
    import inspect

    import api.routes.factory_control as fc

    src = inspect.getsource(fc.create_release)
    i = src.index('release["runtime_contract"]')
    head = src[max(0, i - 400):i]
    assert "_c_approved" in head, "승인 여부를 보지 않고 봉인한다"
