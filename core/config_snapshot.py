"""[D-017 §9 P3-2] **무엇이 실제로 돌았는가**를 프로젝트·릴리스에 남긴다.

## 왜 필요한가 — 두 가지 결함이 같은 뿌리에서 나온다

`agent_graph.get_runtime_app()` 은 컴파일된 그래프를 **`template_id` 로만 캐시**한다. 그리고
그 주석이 스스로 한계를 적어 두었다: 「조직 자산을 개정하면 이 캐시가 낡는다」.

거기서 두 가지가 동시에 생긴다.

1. **개정이 먹지 않는다.** 워크플로우를 고쳐 승인해도 서버를 재시작하기 전까지 옛 그래프가
   돈다. 사용자는 고쳤다고 믿고, 산출물은 옛 구성으로 나온다.
2. **무엇이 돌았는지 알 수 없다.** 산출물만 보고는 어느 버전의 어떤 에이전트 구성이
   만들었는지 되짚을 수 없다. 문제가 생겼을 때 「그때 무엇이 돌았나」에 답할 수 없다.

★ 둘 다 «구성의 신원» 이 없어서 생긴다. 그래서 **구성에 지문을 만든다.**
  지문이 캐시 키가 되면 ①이 사라지고, 지문을 기록하면 ②가 사라진다.

## 지문에 무엇을 넣는가

**실행 결과를 바꾸는 것만** 넣는다. 표시용 이름·설명은 넣지 않는다 — 넣으면 오탈자 수정에도
지문이 바뀌어 그래프가 다시 컴파일되고, 「무엇이 달라졌나」를 물어도 답이 소음이 된다.

· 에이전트 id 와 순서 · enabled · HOTL 중단점 · 스킬 파일 · 모델 티어 · LLM 사용 여부
· 자산이면 **버전과 상태**(승인본이 아니면 애초에 실행되지 않지만, 무엇이 승인본이었는지는 남는다)

## ⚠️ 모르면 «없음» 이라고 쓰지 않는다

구성을 읽지 못하면 지문은 `""` 이고 `resolved=False` 다. 빈 지문을 «구성이 비었다» 로 읽으면
안 된다 — 그래서 스냅샷은 `error` 를 함께 들고 다닌다. 이 저장소의 «조회 실패 ≠ 0건» 이다.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

#: 프로젝트 작업공간에 남기는 파일 이름.
SNAPSHOT_FILE = "config_snapshot.json"

#: 지문 계산에 넣는 에이전트 필드. **실행 결과를 바꾸는 것만.**
#: ⚠️ `name_ko`·`role` 같은 표시용 필드를 넣지 말 것 — 오탈자 수정이 재컴파일을 부른다.
_AGENT_KEYS = ("id", "enabled", "hotl_after", "skill", "stage", "model_tier", "llm", "debate")


@dataclass(frozen=True)
class ConfigSnapshot:
    """한 번의 실행이 쓴 구성의 신원."""
    template_id: str = ""
    #: 구성 지문. 같은 지문이면 같은 그래프가 나온다. 빈 문자열이면 **확인하지 못한 것**이다.
    fingerprint: str = ""
    #: 자산일 때의 버전·상태. 파일 템플릿이면 빈 값이다.
    asset_version: str = ""
    asset_status: str = ""
    #: 실행에 참여하는 에이전트 id(순서 포함)
    agents: List[str] = field(default_factory=list)
    #: HOTL 중단점
    interrupt_after: List[str] = field(default_factory=list)
    #: 이 구성을 승인·결정한 근거. 원장(`decision_ledger`) 이벤트 id 가 있으면 그것을 쓴다.
    policy_decision_id: str = ""
    resolved_at: str = ""
    #: 읽지 못했을 때의 이유. **빈 구성과 구분하기 위해 반드시 함께 본다.**
    error: str = ""

    @property
    def resolved(self) -> bool:
        return bool(self.fingerprint)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["resolved"] = self.resolved
        return d


def _digest(payload: Dict[str, Any]) -> str:
    """정렬된 JSON 의 해시. **키 순서에 흔들리지 않아야** 같은 구성이 같은 지문을 낸다."""
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _shape(reg: Dict[str, Any]) -> Dict[str, Any]:
    agents = []
    for a in (reg.get("agents") or []):
        agents.append({k: a.get(k) for k in _AGENT_KEYS if k in a})
    return {"agents": agents}


def capture(template_id: str, *, policy_decision_id: str = "") -> ConfigSnapshot:
    """지금 이 template_id 로 실행하면 **무엇이 도는지**를 확정해 기록한다.

    ⚠️ `require_runnable=True` 로 부른다 — 실제 실행과 **같은 판정**을 지나야 스냅샷이
      «실행될 것» 을 말한다. 조회용 완화를 쓰면 승인되지 않은 구성을 스냅샷이 정당화한다."""
    tid = (template_id or "").strip() or "default"
    now = datetime.now().isoformat(timespec="seconds")
    try:
        from core.agent_asset_adapter import resolve_workflow
        reg = resolve_workflow(tid) or {}
    except Exception as e:
        # ★ 빈 스냅샷이 아니라 **이유가 붙은 미확인**을 돌려준다.
        return ConfigSnapshot(template_id=tid, resolved_at=now,
                              policy_decision_id=policy_decision_id,
                              error=f"{type(e).__name__}: {e}")

    shape = _shape(reg)
    agents = [a.get("id") for a in shape["agents"] if a.get("id")]
    enabled = [a for a in shape["agents"] if a.get("enabled", True)]
    interrupt = [a["id"] for a in enabled if a.get("hotl_after")]
    return ConfigSnapshot(
        template_id=tid,
        fingerprint=_digest({"template_id": tid, **shape}),
        asset_version=str(reg.get("version") or ""),
        asset_status=str(reg.get("status") or ""),
        agents=agents, interrupt_after=interrupt,
        policy_decision_id=policy_decision_id, resolved_at=now)


def write(workspace_root: str, snap: ConfigSnapshot) -> str:
    """작업공간에 남긴다. **덮어쓰지 않고 이력으로 쌓는다.**

    ⚠️ 마지막 것만 남기면 「3주 전 산출물은 무엇으로 만들었나」에 답할 수 없다. 그 질문이
      나오는 시점은 언제나 문제가 생긴 뒤이고, 그때는 이미 구성이 여러 번 바뀌어 있다."""
    path = os.path.join(workspace_root, SNAPSHOT_FILE)
    history: List[Dict[str, Any]] = []
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
            history = data.get("history") or []
        except Exception:
            history = []               # 읽지 못하면 이력을 잃지만, 새 기록을 막지는 않는다
    entry = snap.to_dict()
    # 같은 지문이 연달아 나오면 쌓지 않는다 — 재개할 때마다 같은 줄이 늘어난다.
    if not (history and history[-1].get("fingerprint") == entry["fingerprint"]
            and entry["fingerprint"]):
        history.append(entry)
    os.makedirs(workspace_root, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"current": entry, "history": history[-50:]}, f,
                  ensure_ascii=False, indent=2)
    os.replace(tmp, path)              # 중간에 죽어도 반쪽 파일이 남지 않게
    return path


def read(workspace_root: str) -> Optional[Dict[str, Any]]:
    """마지막 스냅샷과 이력. 없으면 `None` — **빈 dict 와 구분한다.**"""
    path = os.path.join(workspace_root, SNAPSHOT_FILE)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None
