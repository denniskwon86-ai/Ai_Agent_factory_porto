/**
 * [LE-01] Living Enterprise Canvas — 경영 홈이 보는 **단 하나의 조회.**
 *
 * ⚠️⚠️ 종전에는 경영 홈이 여섯 군데를 스스로 긁어모아 조립했다:
 *   `/briefing` · `/master/types` · `/crosswalk/systems/coverage` · `/knowledge/packs`
 *   · `/external/readiness` · `/org/tree`.
 *   그러면 **판정이 화면에 있고**, 화면마다 조금씩 다르게 조립된다. 승인 시안의 매핑
 *   문서가 처음부터 단일 Read Model 을 요구한 이유가 이것이다.
 */
import { API_BASE_URL, getSessionToken } from './api';

/** §4.4 `DomainNodeVM`. ⚠️ `evidence_count: null` = 못 셌다(0 이 아니다). */
export interface DomainNode {
  id: string;
  sequence: number;
  label: string;
  systems: string;
  status: 'normal' | 'attention' | 'decision_required' | 'blocked' | 'unknown';
  reason: string;
  evidence_count: number | null;
  primary_metric: { label: string; value: string; status?: string } | null;
  required_keys: string[];
}

export interface CanvasQueueItem {
  kind: string;
  severity: string;
  title: string;
  why: string;
  suggested_action: string;
  ref: string;
  ref_type: string;
  /** 어느 섹션에서 왔는가 — 결정/막힘/자료/프로그램. */
  section: string;
  domain?: string;
}

export interface Canvas {
  context: { scope_node_id: string; tenant_id: string; entity_mode: string;
    kit_instance_id: string };
  decision_queue: CanvasQueueItem[];
  domain_nodes: DomainNode[];
  systems_verified: boolean;
  cost_summary: Record<string, unknown>;
  unavailable: { source: string; reason: string }[];
  generated_at: string;
}

/**
 * 경영 홈 집계 1건.
 *
 * ⚠️ 실패를 빈 캔버스로 접지 않는다 — 던진다. 「위험 0건」과 「못 읽었다」는 다르고,
 *   그 구분은 화면이 해야 한다.
 */
export async function fetchCanvas(): Promise<Canvas> {
  const res = await fetch(`${API_BASE_URL}/api/v1/briefing/canvas`, {
    headers: { 'X-Session-Token': getSessionToken() },
  });
  if (!res.ok) {
    throw new Error(res.status === 403
      ? '이 화면을 볼 권한이 없습니다.'
      : `경영 현황을 불러오지 못했습니다 (${res.status})`);
  }
  const body = await res.json();
  return (body?.data ?? body) as Canvas;
}
