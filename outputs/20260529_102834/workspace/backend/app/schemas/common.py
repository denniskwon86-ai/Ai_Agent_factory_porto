from pydantic import BaseModel, Field

class ErrorResponse(BaseModel):
    """
    API 에러 응답의 표준 스키마입니다.
    """
    detail: str = Field(..., example="Resource not found")