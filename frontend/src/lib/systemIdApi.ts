import { API_BASE_URL } from './api';

/** 내부 객체 ID는 사용자 입력이 아니라 서버의 단일 채번 규칙에서 발급한다. */
export async function allocateSystemIds(objectType: string, count = 1): Promise<string[]> {
  const res = await fetch(`${API_BASE_URL}/api/v1/factory/identifiers/allocate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ object_type: objectType, count }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok || data.status !== 'success' || !Array.isArray(data.ids) || data.ids.length !== count) {
    throw new Error(String(data?.detail || '시스템 식별자를 발급하지 못했습니다.'));
  }
  return data.ids.map((id: unknown) => String(id));
}
