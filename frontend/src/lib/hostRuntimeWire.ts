/**
 * ★★★ [G1-B01-B / I-3] 호출 계약의 **프론트 사본**.
 *
 * 정본은 `core/host_runtime_wire.py` 다. 이 파일은 그것을 구현하기 위한 사본이고,
 * `tests/test_host_runtime_bridge_contract.py` 가 **두 파일이 어긋나면 실패**한다.
 *
 * ⚠️ 여기서 값을 «조금 다르게» 두지 않는다. 브리지가 자기 상한·자기 목록을 갖는 순간
 *   보안 계약이 다시 프론트에 분산되고, 그것이 교차검토가 지적한 바로 그 상태다.
 *
 * ## 이 파일이 서 있는 자리 — `event.origin` 은 경계가 아니다
 *
 * 생성 앱 iframe 은 `sandbox="allow-scripts"` 다(= `allow-same-origin` 없음). 그래서 출처가
 * **불투명(opaque)** 이고 `event.origin` 은 `"null"` 로 온다.
 *
 * ⚠️⚠️ **아무 사이트나** 샌드박스 프레임을 만들어 같은 값을 낼 수 있다. 유일한 1차 경계는
 *   `event.source === iframe.contentWindow` **동일성 비교**다.
 * ⚠️⚠️ 같은 이유로 부모는 `targetOrigin` 을 지정할 수 없다 — **응답은 `"*"` 로 나간다.**
 *   그래서 응답 투영(`projectDataset`/`projectRecord`)이 선택이 아니다.
 */

export const SDK_VERSION = 1;
export const ENVELOPE_KEY = 'afs';

export const MSG_HELLO = 'afs.hello';
export const MSG_INIT = 'afs.init';
export const MSG_REQ = 'afs.req';
export const MSG_RES = 'afs.res';

/** 앱이 보낼 수 있는 종류. 그 밖은 **답하지 않고 버린다**(답 자체가 탐침 신호다). */
export const FROM_APP = [MSG_HELLO, MSG_REQ] as const;

export const REQ_REQUIRED = ['type', 'sid', 'request_id', 'op'] as const;
export const RES_FIELDS = ['type', 'sid', 'request_id', 'ok', 'data', 'error_code'] as const;

export type Op =
  | 'data.schema' | 'data.list' | 'data.get'
  | 'data.create' | 'data.update' | 'data.remove';

export const OP_FIELDS: Record<Op, readonly string[]> = {
  'data.schema': ['dataset'],
  'data.list': ['dataset', 'page'],
  'data.get': ['dataset', 'record_id'],
  'data.create': ['dataset', 'payload', 'idempotency_key'],
  'data.update': ['dataset', 'record_id', 'payload', 'idempotency_key', 'version'],
  'data.remove': ['dataset', 'record_id', 'idempotency_key', 'version'],
};

/**
 * ★★ 바꾸는 요청에는 **멱등키가 필수**다. 이 계약은 `UNAVAILABLE`(결과를 알 수 없다)을
 * 받으면 재시도하라고 말한다 — 즉 키가 없으면 **계약이 스스로 중복 쓰기를 만든다.**
 */
export const OP_REQUIRED: Record<Op, readonly string[]> = {
  'data.schema': ['dataset'],
  'data.list': ['dataset'],
  'data.get': ['dataset', 'record_id'],
  'data.create': ['dataset', 'payload', 'idempotency_key'],
  'data.update': ['dataset', 'record_id', 'payload', 'idempotency_key'],
  'data.remove': ['dataset', 'record_id', 'idempotency_key'],
};

export const MUTATING_OPS: readonly Op[] = ['data.create', 'data.update', 'data.remove'];

/**
 * ★★★ 계약에는 있으나 **서버가 아직 검사하지 않는** 필드.
 *
 * `version`(낙관적 동시성)은 `app_records` 에 판 컬럼이 없어 **마지막 쓰기가 이긴다.**
 * ⚠️ 받아서 무시하면 앱은 충돌 보호가 있다고 믿고 화면에 그렇게 표시하면서 남의 수정을
 *   덮어쓴다 — 「조용한 거짓말」 그대로다. 서버가 검사할 때까지 **보내면 거부**한다.
 */
export const NOT_YET_HONORED = ['version'] as const;

/** 앱이 보내면 안 되는 필드. 보내와도 **지운다**(검증이 아니라 삭제). */
export const IGNORED_FROM_APP = [
  'release_id', 'app_id', 'tenant_id', 'entity_mode', 'scope_node_id',
  'owner_dept_id', 'owner_user_id', 'actor', 'user_id',
] as const;

// ── 한계값 (정본과 같아야 한다) ──────────────────────────────────────────
export const MAX_REQUEST_BYTES = 655360;      // 512KB(레코드 상한) + 128KB
export const MAX_RESPONSE_BYTES = 2097152;
export const MAX_PAGE_LIMIT = 100;
export const DEFAULT_PAGE_LIMIT = 50;
export const REQUEST_TIMEOUT_MS = 15000;
export const READY_TIMEOUT_MS = 5000;
export const MAX_INFLIGHT = 8;
export const MAX_CALLS_PER_MINUTE = 240;
export const MAX_ID_LEN = 128;
export const IDEMPOTENCY_TTL_MS = 60000;
export const MAX_IDEMPOTENCY_ENTRIES = 64;

// ── 앱 오류 코드 ─────────────────────────────────────────────────────────
export const ERR_NOT_FOUND = 'NOT_FOUND';
export const ERR_FORBIDDEN = 'FORBIDDEN';
export const ERR_EXPIRED = 'EXPIRED';
export const ERR_INVALID = 'INVALID';
/** ★★★ **판정이 아니라 전달의 실패.** 뜻은 「막혔다」가 아니라 「결과를 알 수 없다」다. */
export const ERR_UNAVAILABLE = 'UNAVAILABLE';

export const APP_ERROR_CODES = [
  ERR_NOT_FOUND, ERR_FORBIDDEN, ERR_EXPIRED, ERR_INVALID, ERR_UNAVAILABLE] as const;

export const ERROR_MESSAGE_KO: Record<string, string> = {
  [ERR_NOT_FOUND]: '요청한 데이터를 찾을 수 없습니다.',
  [ERR_FORBIDDEN]: '이 앱에는 그 작업이 허용되어 있지 않습니다.',
  [ERR_EXPIRED]: '연결이 만료되었습니다. 앱을 다시 열어 주세요.',
  [ERR_INVALID]: '요청 형식이 올바르지 않습니다.',
  //: ⚠️ 「실패했습니다」라고 쓰지 않는다. 쓰기가 **성공했을 수도 있다**.
  [ERR_UNAVAILABLE]: '지금 결과를 확인하지 못했습니다. 잠시 후 다시 시도해 주세요.',
};

/** ★★★ 「이 앱의 판은 사라졌다」. 만료와 **다른 상태코드**여야 부모가 다르게 행동한다 —
 *  만료는 새 증명으로 같은 프레임을 계속 쓰지만, 선언 변경은 **지금 도는 코드가 낡은 것**이라
 *  새 증명을 주면 「옛 앱이 새 증명으로 계속 도는」 상태가 된다. */
export const STATUS_STALE_APP = 410;

/** HTTP 상태 → 앱 오류 코드. ⚠️ 5xx·0 은 **`NOT_FOUND` 가 아니다**(§ERR_UNAVAILABLE). */
export function errorCodeForStatus(status: number): string {
  //: ★ 410 = 앱 선언이 바뀌었다. **앱에게는** 「다시 열면 된다」와 같은 말이지만, 부모는
  //:   재발급이 아니라 프레임 재생성을 해야 한다(`STATUS_STALE_APP`).
  if (status === 401 || status === STATUS_STALE_APP) return ERR_EXPIRED;
  if (status === 403) return ERR_FORBIDDEN;
  if (status === 404) return ERR_NOT_FOUND;
  if (status === 400 || status === 422) return ERR_INVALID;
  return ERR_UNAVAILABLE;
}

// ── 응답 투영 ────────────────────────────────────────────────────────────
//
// ★★★ 서버 응답을 그대로 넘기지 않는다. `GET /datasets/by-name` 은 행 전체를 주고 거기에
//   `owner_dept_id`·`scope_node_id`·`tenant_id`·`created_by` 가 들어 있다. 그대로 넘기면
//   SDK 가 `afs.user` 를 막아 놓고 **데이터로 같은 것을 흘리는** 셈이다.
// ⚠️ 금지목록이 아니라 **허용목록**이다 — 금지목록은 서버가 필드를 하나 늘리는 순간 뚫린다.
export const DATASET_PUBLIC_FIELDS = ['name', 'label', 'schema', 'record_count'] as const;
export const RECORD_PUBLIC_FIELDS = [
  'record_id', 'payload', 'created_at', 'updated_at', 'deleted'] as const;

function pick(row: any, keys: readonly string[]): Record<string, unknown> {
  if (!row || typeof row !== 'object' || Array.isArray(row)) return {};
  const out: Record<string, unknown> = {};
  for (const k of keys) if (k in row) out[k] = row[k];
  return out;
}

export const projectDataset = (row: any) => pick(row, DATASET_PUBLIC_FIELDS);
export const projectRecord = (row: any) => pick(row, RECORD_PUBLIC_FIELDS);

// ── 페이지 ───────────────────────────────────────────────────────────────
export function encodeCursor(offset: number): string {
  const n = Math.floor(Number(offset) || 0);
  return n > 0 ? `o${n}` : '';
}

/** ⚠️ 읽을 수 없으면 **0** — 「못 읽었으니 아무 데나」로 두지 않는다. */
export function decodeCursor(cursor: unknown): number {
  if (typeof cursor !== 'string' || !cursor.startsWith('o')) return 0;
  const body = cursor.slice(1);
  if (!body.length || !/^\d+$/.test(body)) return 0;
  return Math.min(parseInt(body, 10), 1000000);
}

export function normalizePage(page: unknown): { limit: number; offset: number } {
  let limit = DEFAULT_PAGE_LIMIT;
  let offset = 0;
  if (page && typeof page === 'object' && !Array.isArray(page)) {
    const raw = (page as any).limit;
    if (typeof raw === 'number' && Number.isInteger(raw)) {
      limit = Math.max(1, Math.min(raw, MAX_PAGE_LIMIT));
    }
    offset = decodeCursor((page as any).cursor);
  }
  return { limit, offset };
}

// ── 요청 판정 ────────────────────────────────────────────────────────────
export const VERDICT_OK = 'ok';
/** ⚠️ **답하지 않고 버린다.** 오류로 답하면 그 답이 곧 정보다. */
export const VERDICT_DROP = 'drop';
export const VERDICT_ERROR = 'error';

export interface Verdict { verdict: string; code: string; why: string; }

const bad = (why: string, code = ERR_INVALID): Verdict => ({ verdict: VERDICT_ERROR, code, why });
const drop = (why: string): Verdict => ({ verdict: VERDICT_DROP, code: '', why });

/**
 * 앱이 보낸 요청을 계약에 대고 본다. **모양만** 본다 —
 * 권한은 서버의 정책 결정점이 본다(두 곳에서 보면 두 판정이 어긋난다).
 */
export function validateRequest(msg: any, sid: string, inflight: Set<string>): Verdict {
  if (!msg || typeof msg !== 'object' || Array.isArray(msg)) return drop('봉투가 객체가 아니다');
  if (msg.type !== MSG_REQ) return drop(`우리 요청이 아니다: ${String(msg.type).slice(0, 40)}`);
  if (!sid || msg.sid !== sid) return drop('다른 세대의 메시지');

  const rid = msg.request_id;
  if (typeof rid !== 'string' || !rid.trim() || rid.length > MAX_ID_LEN) {
    return bad('request_id 가 없거나 너무 길다');
  }
  if (inflight.has(rid)) return bad(`이미 진행 중인 request_id: ${rid}`);

  const op = msg.op as Op;
  if (!(op in OP_FIELDS)) return bad(`알 수 없는 작업: ${String(msg.op).slice(0, 40)}`);

  const allowed = new Set<string>([...OP_FIELDS[op], ...REQ_REQUIRED]);
  const extra = Object.keys(msg).filter((k) => !allowed.has(k));
  if (extra.length) return bad(`${op} 에 쓸 수 없는 인자: ${extra.sort().join(',')}`);

  for (const f of OP_REQUIRED[op]) {
    const v = msg[f];
    if (v === undefined || v === null || (typeof v === 'string' && !v.trim())) {
      return bad(`${op} 에는 ${f} 가 필요하다`);
    }
  }

  for (const f of NOT_YET_HONORED) {
    if (msg[f] !== undefined && msg[f] !== null) {
      return bad(`${f} 는 아직 서버가 검사하지 않는다 — 지금 보내면 충돌 보호가 있는 것처럼 `
        + `보이지만 실제로는 마지막 쓰기가 이긴다`);
    }
  }

  for (const f of ['dataset', 'record_id', 'idempotency_key']) {
    const v = msg[f];
    if (v !== undefined && v !== null && (typeof v !== 'string' || v.length > MAX_ID_LEN)) {
      return bad(`${f} 는 ${MAX_ID_LEN}자 이내 문자열이어야 한다`);
    }
  }

  const payload = msg.payload;
  if (payload !== undefined && payload !== null) {
    if (typeof payload !== 'object' || Array.isArray(payload)) return bad('payload 는 객체여야 한다');
    const leaked = Object.keys(payload).filter((k) => (IGNORED_FROM_APP as readonly string[]).includes(k));
    //: ⚠️ 조용히 지우지 않고 **드러낸다** — 앱 코드가 권한 필드를 보내고 있다는 사실은
    //:   개발자가 알아야 할 결함이다.
    if (leaked.length) return bad(`payload 에 권한 관련 필드가 있다: ${leaked.sort().join(',')}`);
  }

  const page = msg.page;
  if (page !== undefined && page !== null
      && (typeof page !== 'object' || Array.isArray(page))) {
    return bad('page 는 {limit, cursor} 객체여야 한다');
  }

  return { verdict: VERDICT_OK, code: '', why: '' };
}

/** 응답 봉투. ⚠️ 성공에는 오류코드가, 실패에는 데이터가 실리지 않는다. */
export function buildResponse(
  sid: string, requestId: string, ok: boolean, data?: unknown, errorCode = '',
): Record<string, unknown> {
  const out: Record<string, unknown> = { type: MSG_RES, sid, request_id: requestId, ok: !!ok };
  if (ok) out.data = data === undefined || data === null ? {} : data;
  else out.error_code = errorCode || ERR_UNAVAILABLE;
  return out;
}

/** 세대·작업·데이터셋·키를 묶은 중복 판정 자리. ⚠️ 키만으로 묶으면 다른 데이터셋의 같은
 *  키가 서로를 가린다. */
export function idempotencySlot(sid: string, op: string, dataset: string, key: string): string {
  return [sid, op, dataset, key].join('');
}
