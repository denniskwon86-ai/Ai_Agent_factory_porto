// [이관 1/10] 지식 허브 API 클라이언트
//
// ⚠️ 예전 `KnowledgeHubPanel` 은 **자기 `API_BASE_URL` 을 선언**하고 `fetch` 를 직접 썼으며,
//   실패를 `console.error` 로 삼켰다. 그 결과 두 가지가 동시에 일어났다:
//     ① 조회가 실패해도 화면은 «등록된 지식팩이 없습니다» 라고 말했다 — 사용자는 자료가
//        없다고 믿고 다시 올리려 한다.
//     ② 오류 원인이 화면 어디에도 남지 않아, 신고를 받아도 확인할 방법이 없었다.
//
// ★ 여기서는 공용 `closedLoopFetch` 만 쓴다. 401/404/422/400 규약이 폐루프 화면과 같아지고,
//   실패는 **호출자에게 던진다**(삼키지 않는다 — 삼키면 화면이 «0건»으로 표시한다).
import { API_BASE_URL } from './api';
import { closedLoopEnvelopeFetch, closedLoopFetch as req } from './closedLoopFetch';

export type PackDoc = {
  filename: string;
  chunks: number;
  source: string;
  added_at: string;
};

export type Pack = {
  pack_id: string;
  name: string;
  description: string;
  created_at: string;
  documents: PackDoc[];
};

export type ReferenceSummary = {
  total: number;
  supported: number;
  conversion_required: number;
  pending_review: number;
  by_pack: Record<string, number>;
};

export type SearchHit = {
  content: string;
  distance: number;
  metadata?: { filename?: string; [k: string]: any };
};

export type PackList = {
  packs: Pack[];
  blockedReason: string;
  /** 가려진 것이 있는가(누구에게나). */
  hiddenPresent: boolean;
  /** 몇 건인가 — DA·관리자에게만 온다. `null` 은 «모른다»이며 0 과 다르다. */
  hiddenCount: number | null;
};

export const knowledgeApi = {
  packs: async (): Promise<PackList> => {
    const envelope = await closedLoopEnvelopeFetch<Pack[]>('GET', '/api/v1/knowledge/packs');
    return {
      packs: envelope.data || [],
      blockedReason: String(envelope.blocked_reason || ''),
      hiddenPresent: Boolean(envelope.hidden_present),
      hiddenCount: envelope.hidden_count === undefined || envelope.hidden_count === null
        ? null : Number(envelope.hidden_count),
    };
  },

  createPack: (body: { pack_id: string; name: string; description: string }) =>
    req<Pack>('POST', '/api/v1/knowledge/packs', body),

  deletePack: (packId: string) =>
    req<unknown>('DELETE', `/api/v1/knowledge/packs/${encodeURIComponent(packId)}`),

  removeDoc: (packId: string, filename: string) =>
    req<unknown>('DELETE',
      `/api/v1/knowledge/packs/${encodeURIComponent(packId)}/documents/${encodeURIComponent(filename)}`),

  search: (packId: string, query: string, nResults = 3) =>
    req<SearchHit[]>('POST',
      `/api/v1/knowledge/packs/${encodeURIComponent(packId)}/search`,
      { query, n_results: nResults }),

  referenceSummary: () => req<ReferenceSummary>('GET', '/api/v1/reference/summary'),

  referenceScan: () => req<unknown>('POST', '/api/v1/reference/scan'),

  /** 파일 업로드만 `FormData` 라 별도다. **`Content-Type` 을 직접 지정하지 않는다** —
   *  지정하면 boundary 가 빠져 서버가 본문을 파싱하지 못한다. */
  uploadDoc: async (packId: string, file: File): Promise<void> => {
    const form = new FormData();
    form.append('file', file);
    const r = await fetch(
      `${API_BASE_URL}/api/v1/knowledge/packs/${encodeURIComponent(packId)}/documents`,
      { method: 'POST', body: form });
    if (!r.ok) {
      const j = await r.json().catch(() => ({}));
      const err = new Error((j as any)?.detail || `등록 실패 (${r.status})`) as Error & { status?: number };
      err.status = r.status;
      throw err;
    }
  },
};

/** 원본 자료의 처리 가능 여부. **«변환 필요»를 «실패»로 표시하지 않는다** — 사용자가 할 일이
 *  다르다(전자는 파일을 바꾸면 되고, 후자는 원인을 찾아야 한다). */
export const REFERENCE_TONE: Record<string, 'success' | 'warn' | 'data' | 'muted'> = {
  supported: 'success',
  conversion_required: 'warn',
  pending_review: 'data',
};
