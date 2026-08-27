"""[I-4 5a] Typed SDK Adapter 생성기 — **LLM 이 데이터셋 문자열을 쓰지 않게 한다.**

승인된 계약에서 `src/generated/afs-contract.ts` 를 **결정론적으로** 만든다. 앱 코드는
이 어댑터만 `import` 하고, `window.afs.data.*` 를 직접 부르면 정적 검사의
`undeclared_dataset` 이 잡는다(§9).

## 왜 어댑터인가

★★★ 계약의 `allowed_actions` 에 없는 동작은 **함수 자체가 생성되지 않는다.** 없는
  함수는 타입 검사에서 먼저 걸린다 — 미선언 데이터셋·동적 이름·오탈자·허용되지 않은
  update/delete 를 **정규식 추정이 아니라 구조로** 막는다. 그리고 LLM 이 쓸 코드가
  줄어 토큰과 실패 확률이 함께 준다.

⚠️⚠️ **어댑터는 두 번째 그물이다.** 서버의 2차 판정(§6)이 첫 번째다 — 어댑터만 믿으면
  브라우저에서 고쳐 부르는 순간 통제가 없다. 이 파일이 만드는 것은 «실수를 막는 도구»
  이지 «권한 경계» 가 아니다.

⚠️ 승인되지 않은 계약으로는 만들지 않는다. 만들면 앱 코드가 **승인 전 계약에 맞춰
  작성되고**, 나중에 계약이 바뀌면 코드가 통째로 어긋난다.
"""
import re
from typing import Any, Dict, List, NamedTuple

from core import app_runtime_contract as arc

#: 생성 파일의 자리. 앱 코드가 `import { … } from "./generated/afs-contract"` 로 쓴다.
ADAPTER_DIR = "src/generated"
ADAPTER_FILE = "afs-contract.ts"
ADAPTER_PATH = ADAPTER_DIR + "/" + ADAPTER_FILE

#: 계약의 행동 → 어댑터 함수 이름. **표를 여기 하나만 둔다.**
#: ⚠️ `delete` 를 `remove` 로 부르는 것은 JS 예약어 회피다 — 두 이름이 갈리면
#:   「계약에는 있는데 어댑터에는 없다」가 되고, 그 원인은 아무도 못 찾는다.
ACTION_METHODS = (
    ("read", "list"),
    ("read", "get"),
    ("create", "create"),
    ("update", "update"),
    ("delete", "remove"),
)

#: 계약 타입 → TypeScript 타입. 모르는 타입은 `unknown` 이다.
#: ⚠️ `any` 로 두면 타입 검사가 **그 필드에서만 꺼진다** — 그리고 꺼진 줄 아무도 모른다.
#:   `unknown` 은 쓰려면 좁혀야 하므로 작성자가 알아챈다.
TS_TYPES = {"string": "string", "text": "string", "number": "number",
            "integer": "number", "boolean": "boolean", "date": "string",
            "datetime": "string", "json": "Record<string, unknown>"}

_IDENT = re.compile(r"[^0-9a-zA-Z_]+")


class AdapterResult(NamedTuple):
    """생성 결과. `source` 가 비어 있으면 **만들지 않았다**는 뜻이고 `reason` 이 말한다."""
    source: str
    reason: str
    dataset_names: List[str]

    @property
    def ok(self) -> bool:
        return bool(self.source)


def camel(name: Any) -> str:
    """`material_arrivals` → `materialArrivals`. 식별자로 쓸 수 없는 문자는 버린다.

    ⚠️ 숫자로 시작하면 앞에 `ds` 를 붙인다 — 그대로 두면 **문법 오류가 나는 파일**을
      만들고, 그 실패는 빌드 단계에서야 드러난다."""
    raw = _IDENT.sub("_", str(name or "")).strip("_")
    if not raw:
        return ""
    parts = [p for p in raw.split("_") if p]
    head = parts[0][:1].lower() + parts[0][1:]
    out = head + "".join(p[:1].upper() + p[1:] for p in parts[1:])
    return out if not out[:1].isdigit() else "ds" + out[:1].upper() + out[1:]


def pascal(name: Any) -> str:
    c = camel(name)
    return c[:1].upper() + c[1:] if c else ""


def ts_type(raw: Any) -> str:
    return TS_TYPES.get(str(raw or "").strip().lower(), "unknown")


def _record_interface(ds: Dict[str, Any]) -> str:
    """데이터셋의 레코드 타입. **필수 여부까지 옮긴다** — 그래야 작성자가 빠뜨린 것을 안다."""
    name = pascal(ds.get("dataset_key") or ds.get("name"))
    lines = [f"export interface {name} {{"]
    for f in (ds.get("fields") or []):
        if not isinstance(f, dict) or not str(f.get("name", "")):
            continue
        key = str(f["name"])
        opt = "" if f.get("required") else "?"
        unit = str(f.get("unit", "") or "")
        cls = str(f.get("classification", "") or "")
        note = " · ".join(x for x in (f"단위 {unit}" if unit else "", f"등급 {cls}") if x)
        if note:
            lines.append(f"  /** {note} */")
        lines.append(f"  {key}{opt}: {ts_type(f.get('type'))};")
    lines.append("}")
    return "\n".join(lines)


def _dataset_block(ds: Dict[str, Any]) -> str:
    """데이터셋 하나의 어댑터. **허용되지 않은 동작은 아예 나오지 않는다.**"""
    resource = str(ds.get("name", ""))
    var = camel(ds.get("dataset_key") or resource)
    rec = pascal(ds.get("dataset_key") or resource)
    allowed = {str(a) for a in (ds.get("allowed_actions") or [])}

    body: List[str] = []
    for action, method in ACTION_METHODS:
        if action not in allowed:
            continue
        if method == "list":
            #: ★★★ [2026-08-28 실측] **브리지가 실제로 돌려주는 이름을 쓴다.**
            #:
            #: ⚠️⚠️ 종전에는 `{ items }` 라고 약속했다. 그런데 런타임 브리지는
            #:   `{ records, total, cursor }` 를 돌려준다
            #:   (`frontend/src/lib/hostRuntimeBridge.ts` 의 `data.list`).
            #:   같은 계약을 두 곳이 각자 선언했고 **정본은 어디에도 없었다.**
            #:   그래서 어댑터 타입을 따라 쓴 앱은 `data.items` 가 `undefined` 라
            #:   반드시 죽는다 — 실측: 생성된 앱이 화면에서
            #:   「Uncaught TypeError: Cannot read properties of undefined
            #:    (reading 'forEach')」로 멈췄다. 데이터는 **200 으로 잘 왔는데**
            #:   이름이 달라서 못 읽었다.
            #: ★ 실제로 도는 쪽(브리지)이 진실이므로 어댑터를 그쪽에 맞춘다.
            #:   `tests/test_typed_sdk_adapter_shape.py` 가 둘이 어긋나면 운다.
            body.append(f"  list: (page?: {{ limit?: number; cursor?: string }}) =>\n"
                        f"    window.afs.data.list('{resource}', page) as Promise<"
                        f"{{ records: {rec}[]; total: number; cursor?: string }}>,")
        elif method == "get":
            body.append(f"  get: (recordId: string) =>\n"
                        f"    window.afs.data.get('{resource}', recordId) as Promise<{rec}>,")
        elif method == "create":
            body.append(f"  create: (payload: {rec}) =>\n"
                        f"    window.afs.data.create('{resource}', payload) as Promise<{rec}>,")
        elif method == "update":
            body.append(f"  update: (recordId: string, payload: Partial<{rec}>) =>\n"
                        f"    window.afs.data.update('{resource}', recordId, payload) "
                        f"as Promise<{rec}>,")
        elif method == "remove":
            body.append(f"  remove: (recordId: string) =>\n"
                        f"    window.afs.data.remove('{resource}', recordId) as Promise<void>,")

    #: ⚠️ 만들어지지 **않은** 동작을 주석으로 남긴다. 없는 이유를 못 보면 작성자는
    #:   「어댑터가 불완전하다」고 읽고 `window.afs.data.*` 를 직접 부른다.
    missing = [m for a, m in ACTION_METHODS if a not in allowed]
    note = ""
    if missing:
        note = (f"\n/** ⚠️ 계약의 allowed_actions 에 없어 생성하지 않은 동작: "
                f"{', '.join(sorted(set(missing)))} — 필요하면 계약을 고치고 재승인하십시오. */")
    return f"{note}\nexport const {var} = {{\n" + "\n".join(body) + "\n};"


def generate(contract: Any) -> AdapterResult:
    """승인된 계약 → 어댑터 소스. **던지지 않는다.**

    ⚠️ 승인되지 않은 계약으로는 만들지 않는다 — 만들면 앱 코드가 승인 전 계약에
      맞춰 작성되고, 계약이 바뀌면 코드가 통째로 어긋난다."""
    if not isinstance(contract, dict):
        return AdapterResult("", "계약이 객체가 아닙니다.", [])
    if str((contract.get("approval") or {}).get("status", "")) != "APPROVED":
        return AdapterResult("", "승인되지 않은 계약으로는 어댑터를 만들지 않습니다.", [])

    errs = arc.validate(contract)
    if errs:
        return AdapterResult("", f"계약을 읽을 수 없습니다: {errs[0]}", [])

    #: ★ 이름순으로 만든다 — 같은 계약이 늘 같은 파일을 낸다(지문과 같은 이유).
    datasets = sorted((d for d in (contract.get("datasets") or []) if isinstance(d, dict)),
                      key=lambda d: str(d.get("name", "")))
    names = [str(d.get("name", "")) for d in datasets]

    fp = str(contract.get("semantic_fingerprint", ""))
    header = (
        "// src/generated/afs-contract.ts\n"
        "// ⚠️ 자동 생성 — 손으로 고치지 않는다. 계약을 고치고 재승인하면 다시 만들어진다.\n"
        f"// contract_id: {contract.get('contract_id', '')}\n"
        f"// revision: {contract.get('revision', '')}\n"
        f"// semantic_fingerprint: {fp}\n"
        "//\n"
        "// 앱 코드는 이 어댑터만 import 한다. `window.afs.data.*` 를 직접 부르면\n"
        "// 정적 검사의 `undeclared_dataset` 이 릴리스를 막는다.\n"
    )
    if not datasets:
        #: ★ 데이터셋 0개도 **유효한 계약**이다(0개라는 선언 자체가 통제다). 빈 어댑터를
        #:   내되 왜 비었는지 적는다 — 파일이 없으면 「생성이 실패했다」로 읽힌다.
        return AdapterResult(
            header + "\n// 이 계약은 데이터셋을 선언하지 않았습니다(데이터셋 0개).\n"
                     "export {};\n",
            "", [])

    blocks = [_record_interface(d) for d in datasets]
    blocks += [_dataset_block(d) for d in datasets]
    return AdapterResult(header + "\n" + "\n\n".join(blocks) + "\n", "", names)
