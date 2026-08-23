

# ── [M0-4] 정본 manifest → 등록부 프로파일 어댑터 ─────────────────────────

def test_정본_manifest_의_dataset_id_를_읽는다():
    """★★★ [2026-08-23 실측] 정본 키트는 `dataset_id` 로 적고 등록부 독자는
    `dataset_contract_key` 를 찾는다 — raw 로 넣었더니 준비도 보드가 계약키를
    **0개**로 보고, 인증판 7종이 있는데 「required 0」 으로 답했다.

    ⚠️ 0은 「없다」로 읽힌다. 화면은 아무 말도 못 하고 사용자는 다음에 무엇을 할지 모른다."""
    from core.data_preparation import kit_registry as kr

    manifest = {
        "kit_id": "K", "version": "1.0.0", "name": "n",
        "datasets": [{"dataset_id": "PRC-02", "name": "구매주문 라인", "required": True},
                     {"dataset_id": "INV-01", "name": "재고 스냅샷"}],
        "app_blueprints": [{"app_id": "APP-01", "name": "구매 추적",
                            "datasets": ["PRC-02", "INV-01"]}],
    }
    p = kr.profile_from_manifest(manifest)
    assert kr.dataset_keys(p) == ["INV-01", "PRC-02"]
    #: ★ 사람이 읽는 이름도 함께 옮긴다 — 화면이 계약 이름을 앞세우지 않게.
    assert kr.dataset_labels(p)["PRC-02"]["label"] == "구매주문 라인"
    #: ⚠️ `purpose` 는 manifest 에 없다 — **비워 둔다.** 계약 이름을 복사하면 화면이
    #:   「이름이 없다」와 「이름이 계약과 같다」를 구분할 수 없다.
    assert kr.dataset_labels(p)["PRC-02"]["purpose"] == ""
    outs = kr.outputs(p)
    assert [o["output"] for o in outs] == ["APP-01"]
    assert outs[0]["requires"] == ["INV-01", "PRC-02"]


def test_없는_데이터를_요구하는_산출물은_거부한다():
    """⚠️⚠️ 아무것도 요구하지 않거나 **없는 것**을 요구하는 산출물은 데이터가 하나도
    없어도 「가능」으로 보인다 — 그 화면은 준비되지 않은 것을 준비됐다고 말한다."""
    import pytest

    from core.data_preparation import kit_registry as kr

    manifest = {
        "kit_id": "K", "version": "1.0.0", "name": "n",
        "datasets": [{"dataset_id": "PRC-02", "name": "구매주문 라인"}],
        "app_blueprints": [{"app_id": "APP-01", "datasets": ["PRC-02", "없는것"]}],
    }
    with pytest.raises(kr.KitLoadError, match="없는 데이터"):
        kr.profile_from_manifest(manifest)


def test_이름_없는_데이터셋을_조용히_건너뛰지_않는다():
    """⚠️ 건너뛰면 요구사항이 줄고, 그 산출물은 준비도에서 늘 「가능」이 된다."""
    import pytest

    from core.data_preparation import kit_registry as kr

    with pytest.raises(kr.KitLoadError):
        kr.profile_from_manifest({"datasets": [{"name": "이름만 있다"}]})


def test_요구하는_것이_없는_산출물은_등록하지_않는다():
    """⚠️ 아무것도 요구하지 않는 산출물은 **데이터가 없어도 가능**으로 보인다."""
    from core.data_preparation import kit_registry as kr

    p = kr.profile_from_manifest({
        "datasets": [{"dataset_id": "PRC-02"}],
        "app_blueprints": [{"app_id": "APP-01", "datasets": []}],
    })
    assert kr.outputs(p) == []
