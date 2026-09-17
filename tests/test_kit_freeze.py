"""[P1] 확정 판본 동결 — 검증이 끝난 키트가 다시 생성되지 않는지.

이 시험이 지키는 것: **`KIT-MFG-NONFERROUS-PROCUREMENT 1.0.0` 사고의 재발.**
`VALIDATED_FOR_DEMO` 판본에 생성기를 한 번 더 돌리자 `generated_at` 이 바뀌었는데
아무 오류도 나지 않았다.
"""
import json
import os

import pytest

from core.data_preparation import kit_freeze as kf

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NONFERROUS = os.path.join(REPO, "starter_kits", "KIT-MFG-NONFERROUS-PROCUREMENT", "1.0.0")
NONFERROUS_110 = os.path.join(REPO, "starter_kits", "KIT-MFG-NONFERROUS-PROCUREMENT", "1.1.0")


def _kit(tmp_path, status="GENERATED_UNDER_VALIDATION"):
    root = tmp_path / "KIT-X" / "1.0.0"
    (root / "samples").mkdir(parents=True)
    (root / "manifest.json").write_text(
        json.dumps({"kit_id": "KIT-X", "version": "1.0.0", "status": status}),
        encoding="utf-8")
    (root / "samples" / "A-01.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    return str(root)


# ── 무엇을 얼어 있다고 보는가

def test_생성직후_판본은_얼어있지_않다(tmp_path):
    """아직 검증 중인 것까지 막으면 만들 수가 없다."""
    assert kf.is_frozen(_kit(tmp_path)) is False


@pytest.mark.parametrize("status", ["VALIDATED_FOR_DEMO", "APPROVED", "CERTIFIED_FOR_DEMO"])
def test_확정상태는_표식이_없어도_얼어있다(tmp_path, status):
    """`.frozen` 을 깜빡해도 manifest 상태가 이중 안전장치다."""
    assert kf.is_frozen(_kit(tmp_path, status)) is True


def test_표식이_있으면_상태와_무관하게_얼어있다(tmp_path):
    root = _kit(tmp_path)
    kf.write_freeze(root, reason="시험")
    assert kf.is_frozen(root) is True


# ── 쓰기를 막는가

def test_얼어있으면_guard가_막는다(tmp_path):
    root = _kit(tmp_path, "VALIDATED_FOR_DEMO")
    with pytest.raises(kf.FrozenKitError) as e:
        kf.guard(root)
    # 사람이 무엇을 해야 하는지 메시지에 있어야 한다 — 막기만 하면 --force 로 뚫는다
    assert "새 판본" in str(e.value)


def test_force면_통과한다(tmp_path):
    kf.guard(_kit(tmp_path, "VALIDATED_FOR_DEMO"), force=True)


def test_없는_디렉터리는_막지_않는다(tmp_path):
    """처음 만드는 판본까지 막으면 아무것도 못 만든다."""
    kf.guard(str(tmp_path / "아직없음" / "1.0.0"))


# ── 지문 대조

def test_생성중인_판본은_대장이_없어도_통과시킨다(tmp_path):
    """아직 안 얼린 판본까지 실패로 만들면 생성 중인 것을 못 쓴다."""
    ok, problems = kf.verify(_kit(tmp_path))
    assert ok and problems == []


def test_봉인했는데_대장이_없으면_실패한다(tmp_path):
    """★ **봉인했다면서 지킬 대장이 없으면 내용을 보증하지 못한다.**

    예전에는 여기서도 통과했다. 그 결과 1.1.0 이 대장 없이 `frozen: true ·
    fingerprint: PASS` 를 냈고, **파일을 고쳐도 검증 406 건이 그대로 통과했다**
    (2026-09-17 실증). 1.0.0 이 머지로 조용히 바뀐 사고와 같은 구조였다.
    """
    root = _kit(tmp_path)
    open(os.path.join(root, kf.FROZEN_MARK), "w").close()
    ok, problems = kf.verify(root)
    assert not ok, "봉인 표식이 있는데 대장 없이 통과했다"
    assert "지문 대장" in problems[0]


@pytest.mark.parametrize("status", ["VALIDATED_FOR_DEMO", "VALIDATED"])
def test_검증만_통과한_판본은_대장이_없어도_된다(tmp_path, status):
    """★ **「검증 통과」와 「봉인」은 다르다.**

    `is_frozen()` 은 manifest 가 `VALIDATED_*` 이기만 해도 참이다. 그것까지 대장을
    요구하면 **검증을 두 번 돌리는 것만으로 실패한다** — 첫 번째가 manifest 를
    `VALIDATED_FOR_DEMO` 로 바꾸기 때문이다. 실제로 그렇게 만들었다가 되돌렸다.
    """
    root = _kit(tmp_path, status=status)
    assert kf.is_frozen(root), "manifest 상태만으로도 guard 는 막아야 한다"
    ok, problems = kf.verify(root)
    assert ok, f"봉인 전인데 대조에서 막혔다: {problems}"


def test_내용이_바뀌면_잡는다(tmp_path):
    root = _kit(tmp_path)
    kf.write_freeze(root)
    ok, _ = kf.verify(root)
    assert ok
    with open(os.path.join(root, "samples", "A-01.csv"), "a", encoding="utf-8") as f:
        f.write("3,4\n")
    ok, problems = kf.verify(root)
    assert not ok and any("변경됨" in p for p in problems)


def test_파일이_사라지거나_늘면_잡는다(tmp_path):
    root = _kit(tmp_path)
    kf.write_freeze(root)
    with open(os.path.join(root, "samples", "B-01.csv"), "w", encoding="utf-8") as f:
        f.write("x\n")
    ok, problems = kf.verify(root)
    assert not ok and any("추가됨" in p for p in problems)

    os.remove(os.path.join(root, "samples", "B-01.csv"))
    os.remove(os.path.join(root, "samples", "A-01.csv"))
    ok, problems = kf.verify(root)
    assert not ok and any("사라짐" in p for p in problems)


def test_대장과_표식은_지문에서_뺀다(tmp_path):
    """자기 자신을 넣으면 쓰는 순간 지문이 달라져 영원히 대조가 실패한다."""
    root = _kit(tmp_path)
    kf.write_freeze(root)
    prints = kf.fingerprint_dir(root)
    assert kf.FROZEN_MARK not in prints and kf.FINGERPRINT_FILE not in prints
    ok, _ = kf.verify(root)
    assert ok


def test_경로는_슬래시로_맞춘다(tmp_path):
    """Windows 에서 만든 대장을 Linux 에서 대조해도 같아야 한다."""
    prints = kf.fingerprint_dir(_kit(tmp_path))
    assert "samples/A-01.csv" in prints


# ── 실제 판본

def test_비철키트_1_0_0_은_동결돼_있고_대조를_통과한다():
    assert kf.is_frozen(NONFERROUS), "1.0.0 이 동결돼 있어야 한다"
    assert kf.load_fingerprints(NONFERROUS), "지문 대장이 있어야 한다"
    ok, problems = kf.verify(NONFERROUS)
    assert ok, f"1.0.0 이 변경됐다: {problems[:5]}"


def test_비철키트_1_1_0_도_동결돼_있고_대조를_통과한다():
    """1.1.0 은 **2026-09-17 까지 대장이 없었다.** 확정 판본인데 아무것도 그 내용을
    보증하지 않았고, 값을 바꿔도 검증이 통과했다."""
    assert kf.is_frozen(NONFERROUS_110), "1.1.0 이 동결돼 있어야 한다"
    assert kf.load_fingerprints(NONFERROUS_110), "지문 대장이 있어야 한다"
    ok, problems = kf.verify(NONFERROUS_110)
    assert ok, f"1.1.0 이 변경됐다: {problems[:5]}"
