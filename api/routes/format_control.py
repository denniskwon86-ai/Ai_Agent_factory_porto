import os
import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional

router = APIRouter(prefix="/api/v1/factory/formats")

FORMATS_FILE = "templates/output_formats.json"

class OutputFormat(BaseModel):
    id: str
    name: str
    description: str
    prompt_injection: str
    view_type: Optional[str] = "react_app"

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
async def list_formats():
    formats = load_formats()
    return {"status": "success", "data": formats}

@router.post("")
async def create_format(fmt: OutputFormat):
    formats = load_formats()
    if any(f["id"] == fmt.id for f in formats):
        raise HTTPException(status_code=400, detail="이미 존재하는 포맷 ID입니다.")
    formats.append(fmt.model_dump())
    save_formats(formats)
    return {"status": "success", "data": fmt.model_dump()}

@router.put("/{format_id}")
async def update_format(format_id: str, fmt: OutputFormat):
    formats = load_formats()
    for i, f in enumerate(formats):
        if f["id"] == format_id:
            formats[i] = fmt.model_dump()
            save_formats(formats)
            return {"status": "success", "data": fmt.model_dump()}
    raise HTTPException(status_code=404, detail="포맷을 찾을 수 없습니다.")

@router.delete("/{format_id}")
async def delete_format(format_id: str):
    if format_id == "default":
        raise HTTPException(status_code=400, detail="기본 포맷은 삭제할 수 없습니다.")
    formats = load_formats()
    new_formats = [f for f in formats if f["id"] != format_id]
    if len(formats) == len(new_formats):
        raise HTTPException(status_code=404, detail="포맷을 찾을 수 없습니다.")
    save_formats(new_formats)
    return {"status": "success"}
