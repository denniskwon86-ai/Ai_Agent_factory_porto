"""W03.2 원자 저장 — 정본 파일이 «반쯤 쓰인 상태»로 읽히지 않는다.

⚠️ 여기서 증명하는 것은 **부분 파일 방지**뿐이다. 동시 writer 가 남의 새 판본을 자기 낡은
  내용으로 덮는 것(lost update)은 **다른 문제**이고 이 파일은 그것을 다루지 않는다.
  `os.replace` 하나로 둘 다 됐다고 읽지 말 것.

⚠️ 독립 프로세스 경쟁 증거는 여기 없다 — 격리 러너가 `subprocess.Popen` 을 막는다.
  그것은 `scripts/w03_atomic_write_probe.py compare` 로 러너 밖에서 만들고 결과 문서에 남긴다.
"""
import hashlib
import json
import os
from pathlib import Path

import pytest

from core import atomic_write

#: ⚠️ `monkeypatch.setattr(atomic_write.os, "replace", ...)` 는 `atomic_write.os` 가 곧 전역
#:   `os` 모듈이라 **`os.replace` 자체**를 바꾼다. 패치 뒤에 `os.replace` 를 집으면 가짜를
#:   집게 되므로(한 번 당했다) 진짜를 모듈 적재 시점에 잡아 둔다.
_REAL_REPLACE = os.replace


def _digest(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _strays(folder) -> list:
    return sorted(p.name for p in Path(folder).iterdir() if p.name != "state.json")


@pytest.fixture
def target(tmp_path):
    """이전 판본이 이미 있는 상태. 「실패해도 이게 남아야 한다」의 기준이 된다."""
    path = tmp_path / "state.json"
    atomic_write.replace_json(path, {"revision": 1, "who": "before"}, indent=2)
    return path


def test_normal_write_is_visible_whole_and_leaves_nothing_behind(target):
    atomic_write.replace_json(target, {"revision": 2, "who": "after"}, indent=2)
    assert json.loads(target.read_text(encoding="utf-8"))["revision"] == 2
    assert _strays(target.parent) == [], "임시 파일이 남았다"


def test_serialization_failure_never_touches_the_target(target):
    """직렬화가 깨지면 파일에 손도 대지 않는다 — 대상도 임시 파일도 그대로."""
    before = _digest(target)
    with pytest.raises((TypeError, ValueError)):
        atomic_write.replace_json(target, {"bad": {1, 2, 3}}, indent=2)  # set 은 JSON 이 아니다
    assert _digest(target) == before
    assert _strays(target.parent) == []


def test_failure_during_replace_keeps_the_previous_version(target, monkeypatch):
    """★ 교체 직전에 끊겨도 이전 판본이 온전히 남고, 반쪽짜리가 보이지 않는다."""
    before = _digest(target)

    def boom(*_args, **_kwargs):
        raise OSError("교체 중 끊김")

    monkeypatch.setattr(atomic_write.os, "replace", boom)
    with pytest.raises(OSError):
        atomic_write.replace_json(target, {"revision": 99, "who": "never"}, indent=2)
    assert _digest(target) == before, "실패했는데 대상이 바뀌었다"
    assert json.loads(target.read_text(encoding="utf-8"))["who"] == "before"
    assert _strays(target.parent) == [], "실패 뒤 임시 파일이 남았다"


def test_legacy_way_does_tear_the_file(target):
    """음성 대조군 — 옛 방식(직접 `open(w)`)은 같은 조건에서 **대상을 깬다.**

    이게 깨지지 않으면 위 시험들은 아무것도 증명하지 못한다. 옛 방식은 대상 파일을 먼저
    비우고 쓰기 때문에, 중간에 끊기면 읽는 쪽이 부서진 JSON 을 본다.
    """
    with pytest.raises(ValueError):
        with open(target, "w", encoding="utf-8") as stream:
            stream.write('{"revision": 99, "who": "half')  # 쓰다 말았다
            raise ValueError("중간 실패")
    with pytest.raises(json.JSONDecodeError):
        json.loads(target.read_text(encoding="utf-8"))


def test_temporary_file_sits_next_to_the_target(target, monkeypatch):
    """임시 파일은 **같은 디렉터리**여야 한다. 다른 볼륨이면 교체가 원자적이지 않다."""
    seen = {}

    def capture(src, dst):
        seen["src_parent"] = Path(src).parent
        seen["dst_parent"] = Path(dst).parent
        return _REAL_REPLACE(src, dst)

    monkeypatch.setattr(atomic_write.os, "replace", capture)
    atomic_write.replace_json(target, {"revision": 3}, indent=2)
    assert seen["src_parent"] == seen["dst_parent"] == target.parent


def test_replace_retries_a_locked_target_then_gives_up_loudly(target, monkeypatch):
    """Windows 공유 위반은 짧게 다시 건다. 끝내 안 되면 **예외를 올린다** — 삼키지 않는다."""
    calls = {"n": 0}

    def always_locked(*_args, **_kwargs):
        calls["n"] += 1
        raise PermissionError("사용 중")

    monkeypatch.setattr(atomic_write.time, "sleep", lambda _s: None)
    monkeypatch.setattr(atomic_write.os, "replace", always_locked)
    with pytest.raises(PermissionError):
        atomic_write.replace_json(target, {"revision": 4}, indent=2)
    assert calls["n"] == len(atomic_write._RETRY_DELAYS) + 1, "재시도 횟수가 계약과 다르다"
    assert _strays(target.parent) == []

    # 한 번 막혔다가 풀리면 성공해야 한다 — 재시도가 장식이 아니다.
    attempts = {"n": 0}

    def locked_once(src, dst):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise PermissionError("사용 중")
        return _REAL_REPLACE(src, dst)

    monkeypatch.setattr(atomic_write.os, "replace", locked_once)
    atomic_write.replace_json(target, {"revision": 5}, indent=2)
    assert json.loads(target.read_text(encoding="utf-8"))["revision"] == 5


def test_serialization_policy_stays_with_the_caller(tmp_path):
    """★ `sort_keys` 를 모듈이 강제하면 **내용이 같은데 digest 가 달라진다.**

    W03.1 은 판본 동일성을 digest 로 본다. 그 증거를 깨지 않으려면 정책이 호출자에게 있어야
    한다. 두 정책이 실제로 다른 바이트를 내는지로 확인한다.
    """
    value = {"b": 1, "a": 2}
    plain, sorted_ = tmp_path / "plain.json", tmp_path / "sorted.json"
    atomic_write.replace_json(plain, value, indent=2)
    atomic_write.replace_json(sorted_, value, indent=2, sort_keys=True)
    assert plain.read_bytes() != sorted_.read_bytes()
    assert list(json.loads(plain.read_text(encoding="utf-8"))) == ["b", "a"]


def test_studio_promotion_write_keeps_its_own_policy_and_is_atomic(tmp_path, monkeypatch):
    """B3 승격 저장은 구현을 공용으로 옮긴 뒤에도 **같은 바이트**를 내야 한다(회귀)."""
    from core import studio_project_files

    path = tmp_path / "state.json"
    value = {"b": 1, "a": 2, "nested": {"z": 0, "y": 1}}
    studio_project_files.write_json(path, value)
    expected = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
    assert path.read_text(encoding="utf-8") == expected

    # 그리고 여전히 원자적이다 — 교체가 깨지면 이전 판본이 남는다.
    before = _digest(path)
    monkeypatch.setattr(atomic_write.os, "replace", lambda *a, **k: (_ for _ in ()).throw(OSError("끊김")))
    with pytest.raises(OSError):
        studio_project_files.write_json(path, {"a": 9})
    assert _digest(path) == before
    assert _strays(path.parent) == []


@pytest.mark.parametrize("module_name, attribute", [
    ("core.kit_app_builder", "atomic_write"),
    ("core.async_orchestrator", "atomic_write"),
    ("api.routes.factory_control", "atomic_write"),
    ("api.routes.advisor_control", "atomic_write"),
])
def test_product_write_sites_are_wired_to_the_shared_helper(module_name, attribute):
    """배선 확인 — 정본을 쓰는 모듈이 공용 헬퍼를 **실제로 들고 있다.**

    ⚠️ 이것만으로 「그 함수가 호출된다」는 증명은 아니다. 호출 자체는
    `test_advisor_state_write_is_atomic` 과 probe 가 본다.
    """
    import importlib

    module = importlib.import_module(module_name)
    assert getattr(module, attribute, None) is atomic_write


def test_advisor_state_write_is_atomic(tmp_path, monkeypatch):
    """제품 쓰기 함수를 **직접 불러서** 원자 경로를 타는지 본다(소스 문자열 검사가 아니다)."""
    from api.routes import advisor_control

    path = tmp_path / "state.json"
    advisor_control._write_json(str(path), {"revision": 1})
    before = _digest(path)

    monkeypatch.setattr(atomic_write.os, "replace", lambda *a, **k: (_ for _ in ()).throw(OSError("끊김")))
    with pytest.raises(OSError):
        advisor_control._write_json(str(path), {"revision": 2})
    assert _digest(path) == before, "제품 쓰기가 원자 경로를 타지 않는다"
    assert _strays(path.parent) == []


@pytest.mark.skipif(os.name == "nt", reason="Windows 심볼릭 링크 생성은 별도 권한이 필요하다")
def test_a_linked_target_stays_a_link(tmp_path):
    """공유 저장을 링크로 걸어 둔 구성에서 링크를 일반 파일로 바꾸지 않는다."""
    real = tmp_path / "real.json"
    atomic_write.replace_json(real, {"revision": 1}, indent=2)
    link = tmp_path / "link.json"
    link.symlink_to(real)

    atomic_write.replace_json(link, {"revision": 2}, indent=2)
    assert link.is_symlink(), "링크가 일반 파일로 바뀌었다 — 공유가 끊긴다"
    assert json.loads(real.read_text(encoding="utf-8"))["revision"] == 2
