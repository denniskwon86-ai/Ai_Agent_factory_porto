# -*- coding: utf-8 -*-
"""[P03.2] **설치 스키마만으로 제품의 «쓰기» 가 성립하는가.**

## 왜 이 시험이 따로 있는가

`missing_objects_on()` 은 요구 목록(`REQUIRED`)에 적힌 표·컬럼이 있는지 본다. 그런데
요구 목록은 **내가 적은 것**이다. 제품이 실제로 건드리는 표가 그보다 넓으면, 확인은
「설치됨」이라고 말하고 제품은 깨진다 — 확인이 자기가 지킬 것을 스스로 정의한 꼴이다.

★★ 그래서 여기서는 목록을 보지 않고 **제품의 쓰기 API 를 실제로 부른다.** 제품이
  `ON CONFLICT(node_id, code)` · `ON CONFLICT(from_node_id, to_node_id, relation_type,
  effective_from)` 같은 복합 충돌 대상을 쓰므로, 대응 제약이 없으면 바로 여기서 깨진다.

⚠️ 이 시험은 SQLite 로 돈다. PG 방언 문제를 잡지는 못한다 — 그건 실제 PG 실행이
  할 일이다. 여기서 잠그는 것은 **설치 산출물의 «범위»** 다.

⚠️ 저장소 conftest 는 격리 러너에서 로드되지 않는다(`repository_conftest_loaded: false`).
  그래서 이 파일은 **자기 안에서** 임시 경로로 격리한다.
"""
from __future__ import annotations

import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.db import sqlite_factory
from core.db.managed_schema import STORE_ENTERPRISE_CONTEXT
from scripts.install_first_db_schema import apply_sqlite, sqlite_ddl_for

#: ⚠️ 값을 여기 다시 적지 않는다. 다시 적으면 harness 가 무엇을 쓰는지와 시험이
#:   무엇을 확인하는지가 갈리고, 그 어긋남이 «제품 결함» 처럼 보인다(실제로 한 번 그랬다).
from scripts.p03_pg_consumption import CHILD_NODE as CHILD  # noqa: E402
from scripts.p03_pg_consumption import ENTITY, TENANT  # noqa: E402
from scripts.p03_pg_consumption import ROOT_NODE as ROOT  # noqa: E402


@pytest.fixture()
def repo(tmp_path):
    """**설치 산출물만** 깔린 저장소. 기동 중 DDL 은 없다."""
    db_path = str(tmp_path / "ecm.db")
    apply_sqlite(db_path, sqlite_ddl_for(STORE_ENTERPRISE_CONTEXT))
    from core.enterprise_context.repository import EcmRepository
    return EcmRepository(db_path=db_path, connect=sqlite_factory(db_path), managed=True)


def _seed(repo):
    """`scripts/p03_pg_consumption.seed_context` 와 **같은 순서**를 부른다."""
    from scripts.p03_pg_consumption import seed_context
    return seed_context(repo)


def test_product_write_sequence_runs_on_the_installed_schema(repo):
    """★ 설치 스키마 위에서 테넌트→법인→노드→엣지→승인이 **끝까지** 간다."""
    out = _seed(repo)
    assert out["upsert_is_idempotent"] is True
    assert out["edge_children"] == [CHILD]
    assert out["edge_parents"] == [ROOT]
    assert out["entity_approved_status"] == "ACTIVE"


def test_upsert_is_repeatable_not_a_primary_key_crash(repo):
    """⚠️ 두 번째 호출이 깨지면 제품의 «갱신» 이 성립하지 않는다는 뜻이다."""
    _seed(repo)
    second = _seed(repo)
    assert second["upsert_is_idempotent"] is True
    assert len(repo.list_nodes(tenant_id=TENANT)) == 2, "되풀이가 행을 늘렸다"


def test_code_alias_history_needs_its_composite_unique(repo):
    """★★ `ON CONFLICT(node_id, code)` 는 **대응 UNIQUE 가 있어야** 성립한다.

    없으면 SQLite 는 `ON CONFLICT clause does not match any PRIMARY KEY or UNIQUE
    constraint` 로 거절한다 — 설치 산출물이 제품의 충돌 대상을 못 따라간 경우다.

    ⚠️ 처음 코드를 붙일 때는 별칭이 남지 않는다. 별칭은 **바뀐 옛 코드**를 남기는
      것이다(`reason="code_changed"`). 처음에 그걸 「기록 실패」로 읽고 시험을 틀리게
      썼다 — 고치기 전에 제품이 무엇을 하는지부터 읽어야 했다."""
    out = _seed(repo)
    assert out["alias_history_after_code_change"] == ["PGROOT"], out
    #: 옛 코드로도 여전히 찾아진다 — 별칭을 남기는 이유가 그것이다.
    assert out["alias_lookup_finds_old_code"] == [ROOT]
    assert out["find_by_current_code"] == ROOT

    aliases = repo.code_aliases_of(ROOT)
    assert aliases[0]["replaced_by"] == "PGROOT2"
    assert aliases[0]["reason"] == "code_changed"


def test_second_run_takes_the_do_update_branch_of_the_alias_upsert(repo):
    """★★ 되풀이 실행은 별칭 행이 **이미 있는** 상태에서 같은 충돌 대상을 다시 친다.

    처음 실행은 `INSERT` 만 지나므로, `DO UPDATE` 쪽이 성립하는지는 두 번째에야 드러난다."""
    _seed(repo)
    second = _seed(repo)
    #: 두 번째 실행은 PGROOT2 → PGROOT → PGROOT2 로 돌아 별칭이 둘 다 쌓인다.
    assert set(second["alias_history_after_code_change"]) == {"PGROOT", "PGROOT2"}, second
    assert len(repo.list_nodes(tenant_id=TENANT)) == 2, "되풀이가 노드를 늘렸다"


def test_installed_schema_is_narrower_than_what_the_repository_touches(repo):
    """★★★ **알고 있는 결손을 시험으로 고정한다.**

    저장소는 `enterprise_profiles` 를 쓰는데 설치 산출물에는 없다. 그래서 관리 모드
    확인은 통과하고 프로필 경로는 깨진다. 이 시험은 그 상태를 «정상» 이라고 말하지
    않는다 — **결손이 사라지면 여기서 실패**하고, 그때 이 시험과 요구 목록을 함께
    고치라는 뜻이다.

    ⚠️ 관리 모드에서 저장소는 빈 목록으로 숨기지 않고 **소리내어 깨진다.** 그 성질이
      사라지는 것도 회귀다 — 조용한 `[]` 는 화면에 「자료 없음」으로 보인다."""
    with pytest.raises(sqlite3.OperationalError):
        repo.list_profiles()


def test_first_path_read_still_works_while_profiles_are_absent(repo):
    """⚠️ 결손이 **첫 경로까지** 번지지 않는지 본다. 번지면 범위 판정이 틀린 것이다."""
    _seed(repo)
    assert repo.get_node(ROOT).name_ko == "합성PG본부"
    assert repo.get_tenant(TENANT)["tenant_id"] == TENANT
    assert repo.get_entity(ENTITY).status == "ACTIVE"


def test_importing_the_harness_does_not_change_managed_mode_globally():
    """★★ harness 를 **읽는 것만으로** 남의 시험이 관리 모드가 되면 안 된다.

    예전에 설치 CLI 가 import 시점에 전역 환경변수를 세워 무관한 22건을 깨뜨렸다."""
    before = os.environ.get("AFS_DB_MANAGED_STORES")
    import importlib

    import scripts.p03_pg_consumption as harness
    importlib.reload(harness)
    assert os.environ.get("AFS_DB_MANAGED_STORES") == before
