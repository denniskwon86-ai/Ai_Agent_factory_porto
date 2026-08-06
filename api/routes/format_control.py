"""산출물 서식(Output Format) REST API. prefix /api/v1/factory/formats.

## [2026-08-07 · 트랙 G] 무방비 라우트 봉합 — 이 파일도 **4개 전부**가 무방비였다

실측(2026-08-07, 트랙 G 게이트가 잡았다):

```
익명 GET    /api/v1/factory/formats  → 200, 서식 정의 전체(`prompt_injection` 본문 포함)
익명 POST   /api/v1/factory/formats  → 422  ← ⚠️ **막힌 것이 아니다.** 본문을 채우면 등록된다
익명 PUT    /api/v1/factory/formats/{id} → 422 (같음)
익명 DELETE /api/v1/factory/formats/{id} → 404 (자원이 없어서일 뿐, 있으면 지워진다)
```

★★★ **읽기보다 쓰기가 훨씬 위험하다.** `prompt_injection` 은 에이전트 프롬프트에 그대로
들어가는 문자열이다. 즉 이 라우트는 «설정 API» 가 아니라 **플랫폼 전체 프롬프트에 문장을
심는 통로**였고, 익명에게 열려 있었다. 지운 서식을 쓰던 프로젝트는 산출물 형식을 잃는다.

⚠️ **422·404 를 «차단» 으로 세면 이 셋을 영원히 못 본다.** 2026-08-05 실측에서 무방비 GET
  109개 중 17개가 422 였고 그것을 차단으로 세고 있었다 — 값을 채우면 열리는 경로들이다.
  `tests/test_track_g_route_sealing.py` 가 401/403 만 통과로 센다.

## 권한 배정 근거

`templates/output_formats.json` 은 **조직별이 아니라 전역 공유 파일**이다. 한 사람이 고치면
모든 프로젝트의 에이전트 프롬프트가 바뀐다. 그러므로 D-017 P0-3 «전역 reset·default 수정은
플랫폼 관리자 전용» 이 그대로 적용된다 → 쓰기 3개는 `system.default.edit`.
읽기는 화면이 서식을 고르는 데 필요하므로 **식별**까지만 요구한다.

⚠️ `FORMATS_FILE` 이 상대경로인 것은 **일부러 두었다.** 절대경로로 고치면 테스트의 `chdir`
  격리가 깨져 스위트가 저장소의 실제 서식 파일을 덮어쓴다(D-018 이행 때 실제로 겪은 함정).
  경로 고정은 트랙 G 가 아니라 그 이행의 몫이다.
"""
import os
import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional

from api.deps import Principal, assert_identified, current_principal, require_caps
from core.admin_capability import SYSTEM_DEFAULT_EDIT

router = APIRouter(prefix="/api/v1/factory/formats")

FORMATS_FILE = "templates/output_formats.json"

#: 사용자에게 보일 자료 이름. 조사(을/를)는 `deps.eul` 이 맞춘다.
WHAT = "산출물 서식"


class OutputFormat(BaseModel):
    id: str
    name: str
    description: str
    prompt_injection: str
    view_type: Optional[str] = "react_app"


def _assert_may_edit(p: Principal, action: str) -> None:
    """전역 서식을 바꿔도 되는 주체인가. **쓰기 3개가 같은 한 줄을 쓴다.**

    ★ 라우트마다 `require_caps` 를 따로 적지 않는 이유는 이 저장소가 아홉 번 확인한 것과
      같다 — 판정이 세 곳에 있으면 그중 하나만 고쳐지는 날이 온다."""
    assert_identified(p, WHAT)
    require_caps(p, SYSTEM_DEFAULT_EDIT, resource="output_format", action=action)


def load_formats() -> List[dict]:
    if not os.path.exists(FORMATS_FILE):
        return []
    try:
        with open(FORMATS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading formats: {e}")
        return []


def save_formats(formats: List[dict]):
    os.makedirs(os.path.dirname(FORMATS_FILE), exist_ok=True)
    with open(FORMATS_FILE, "w", encoding="utf-8") as f:
        json.dump(formats, f, ensure_ascii=False, indent=2)


@router.get("")
async def list_formats(p: Principal = Depends(current_principal)):
    assert_identified(p, WHAT)
    formats = load_formats()
    return {"status": "success", "data": formats}


@router.post("")
async def create_format(fmt: OutputFormat, p: Principal = Depends(current_principal)):
    _assert_may_edit(p, "create")
    formats = load_formats()
    if any(f["id"] == fmt.id for f in formats):
        raise HTTPException(status_code=400, detail="이미 존재하는 포맷 ID입니다.")
    formats.append(fmt.model_dump())
    save_formats(formats)
    return {"status": "success", "data": fmt.model_dump()}


@router.put("/{format_id}")
async def update_format(format_id: str, fmt: OutputFormat,
                        p: Principal = Depends(current_principal)):
    _assert_may_edit(p, "update")
    formats = load_formats()
    for i, f in enumerate(formats):
        if f["id"] == format_id:
            formats[i] = fmt.model_dump()
            save_formats(formats)
            return {"status": "success", "data": fmt.model_dump()}
    raise HTTPException(status_code=404, detail="포맷을 찾을 수 없습니다.")


@router.delete("/{format_id}")
async def delete_format(format_id: str, p: Principal = Depends(current_principal)):
    _assert_may_edit(p, "delete")
    if format_id == "default":
        raise HTTPException(status_code=400, detail="기본 포맷은 삭제할 수 없습니다.")
    formats = load_formats()
    new_formats = [f for f in formats if f["id"] != format_id]
    if len(formats) == len(new_formats):
        raise HTTPException(status_code=404, detail="포맷을 찾을 수 없습니다.")
    save_formats(new_formats)
    return {"status": "success"}
