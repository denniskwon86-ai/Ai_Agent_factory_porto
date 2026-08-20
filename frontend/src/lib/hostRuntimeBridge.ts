/**
 * ★★★ [I-3] **Host Runtime 브리지 — 부모 쪽 절반.**
 *
 * 생성 앱은 자기 로그인도 자기 백엔드도 갖지 않는다. 데이터는 **여기를 통해서만** 드나들고,
 * 그 통로에 이미 있는 통제를 전부 태운다.
 *
 * 계약 정본은 `core/host_runtime_wire.py`, 프론트 사본은 `./hostRuntimeWire.ts` 다.
 * **이 파일은 그 계약을 구현할 뿐 늘리지 못한다.**
 *
 * ## 기본은 «켬» 이다 — 2026-08-20 에 뒤집혔다
 *
 * 교차검토 지시는 「I-3 를 Shadow/비활성 상태로 구현하고 **격리된 카나리 환경에서 종단
 * 검증한 뒤 전환한다**」였다. 그 종단 검증이 끝나서 전환했다(Supervisor 지시):
 *
 *   · `tests/test_end_to_end_canary.py` — API 수준 종단
 *   · `scripts/drive_generated_app.py` — **브라우저 수준** 종단(브리지·투영까지)
 *
 * ⚠️⚠️ 그 브라우저 검증에서 실제 결함이 하나 나왔다 — 파일 판 경로가 «평평한 행» 을
 *   돌려줘 SDK 투영에 하나도 안 걸렸고, 앱은 「3건」을 받고 **모든 칸이 빈** 표를
 *   그렸다. 개수가 맞으니 아무도 고장으로 보지 않았다. 켜기 전에 고쳤다.
 *
 * ★★★ **끄는 스위치는 남는다** — `VITE_AFS_HOST_RUNTIME='0'` 이면 꺼진다.
 *   ⚠️ 기본값이 꺼짐이던 이유는 「끄는 것을 잊었다」가 사고가 되지 않게 하려는 것이었다.
 *     이제 반대 위험이 있다 — 「켜는 것을 잊었다」면 앱이 데이터를 못 읽고 사용자는
 *     제품이 고장 났다고 읽는다. 검증이 끝난 뒤에는 그쪽이 더 큰 손해다.
 *   ⚠️ 저장소가 `.env*` 를 **전부 무시**한다(루트 `.gitignore`). 그래서 이 전환을
 *     env 파일로 할 수 없었다 — 그렇게 하면 내 컴퓨터에서만 켜진다.
 *
 * 켜지려면 여전히 **릴리스가 있어야** 한다(`release_id`). 릴리스가 없는 미리보기는
 * 데이터 평면에 접근할 수 없다.
 *
 * ⚠️ 릴리스가 없는 미리보기(생성 중인 코드)는 **데이터 평면에 접근할 수 없다.** 붙일
 *   `release_id` 가 없으면 서버가 무엇을 판정할지 정할 수 없고, 그 상태에서 열면 「무엇에
 *   대한 권한인가」가 비어 있는 요청이 된다.
 *
 * ## ★★★ 앱은 `release_id` 를 말하지 않는다
 *
 * 부모가 붙인다(설계 §7-4). 앱이 자기 릴리스를 말할 수 있으면 남의 앱 데이터를 요청할 수
 * 있다. 그래서 앱이 보낸 권한 관련 필드는 **검증하지 않고 지운다** — 검증하면
 * 「맞으면 쓴다」가 되고, 그러면 언젠가 맞는 값을 보내는 코드가 생긴다.
 *
 * ## ⚠️ 자격증명은 이 파일을 지나가지 않는다
 *
 * 서버 호출은 `apiFetch` 로 하고, 세션 토큰은 전역 인터셉터가 붙인다(`lib/api.ts`).
 * 브리지는 토큰을 **읽지도 들고 있지도** 않으며, 응답에도 싣지 않는다(B02).
 */
import { apiFetch } from './api';
import {
  DATASET_PUBLIC_FIELDS, ERR_INVALID, ERR_NOT_FOUND, ERR_UNAVAILABLE, IGNORED_FROM_APP,
  ERR_EXPIRED, MAX_CALLS_PER_MINUTE, MAX_INFLIGHT, MAX_REQUEST_BYTES, MAX_RESPONSE_BYTES,
  MSG_HELLO, STATUS_STALE_APP, STEP_RETURN, STEP_STALE, nextStep,
  MSG_INIT, MSG_REQ, MUTATING_OPS, REQUEST_TIMEOUT_MS, SDK_VERSION, VERDICT_DROP,
  VERDICT_OK, buildResponse, encodeCursor, errorCodeForStatus, idempotencySlot,
  normalizePage, projectDataset, projectRecord, validateRequest,
} from './hostRuntimeWire';
import type { Op } from './hostRuntimeWire';

//: ★★★ [G1-B 3.5] **전용 경로만 쓴다.** 관리 API(`/api/v1/appdata/*`)는 사람의 표면이고,
//:   거기에 「증명 없으면 세션으로」 폴백을 두면 앱이 **헤더 하나를 생략해** 사람의 넓은
//:   권한으로 데이터를 만질 수 있다(교차검토 [G1-B-I3-REVIEW-82]).
const RUNTIME = '/api/v1/appdata/runtime';
//: 앱 증명을 싣는 헤더. ⚠️ 이 값은 **이 모듈의 메모리에만** 있다 — iframe·localStorage·로그
//:   어디에도 가지 않는다.
const PROOF_HEADER = 'X-App-Proof';

/** 켜는 조건 ①. **명시적으로 `'0'` 일 때만 꺼진다**(2026-08-20 전환, 위 머리말 참조).
 *
 *  ⚠️ 오탈자를 «켜짐» 으로 읽지 않는다 — `'0'` 이 아닌 값은 전부 켜짐이므로, 끄려는
 *    사람은 정확히 `'0'` 을 써야 한다. 반대로 두면(「'1' 일 때만 켬」) env 를 못 쓰는
 *    이 저장소에서는 **아무 데서도 안 켜진다.** */
export const HOST_RUNTIME_FLAG: boolean =
  String((import.meta as any).env?.VITE_AFS_HOST_RUNTIME ?? '') !== '0';

export interface BridgeDeps {
  /** 우리 프레임. **동일성 비교**의 대상이다(§`event.origin` 은 경계가 아니다). */
  getFrame: () => Window | null | undefined;
  /** 현재 프레임 세대. 바뀌면 옛 프레임의 늦은 메시지가 버려진다. */
  getSid: () => string;
  /** 부모가 붙이는 릴리스. **앱이 말하지 않는다.** */
  releaseId: string;
  appId?: string;
  /** 시험 주입용. 기본은 실제 `apiFetch`. */
  fetchImpl?: (path: string, init?: RequestInit) => Promise<Response>;
  /** 브리지가 무엇을 했는지 화면이 알 수 있게 하는 훅(선택). */
  onActivity?: (info: {
    op: string; ok: boolean; errorCode?: string;
    /** 앱 정의가 바뀌어 **지금 도는 코드가 낡았다**. 프레임을 다시 만들어도 소용없다. */
    staleApp?: boolean;
    /** 부모 화면에 그대로 보여 줄 문장(서버가 사용자에게 할 말을 준 경우에만). */
    message?: string;
    /** 사용자가 조직 범위를 골라야 하는 상태인가. */
    needsScope?: boolean;
  }) => void;
}

interface Pending { at: number; }

export interface HostBridge {
  /** 이 메시지를 브리지가 처리했는가. `false` 면 호출부의 기존 처리를 계속한다. */
  handle: (event: MessageEvent) => boolean;
  enabled: boolean;
  /** 세대가 바뀔 때 부른다 — 캐시·진행 중 요청·멱등 기록을 버린다. */
  resetGeneration: () => void;
}

export function createHostBridge(deps: BridgeDeps): HostBridge {
  const enabled = HOST_RUNTIME_FLAG && !!(deps.releaseId || '').trim();
  const fetchImpl = deps.fetchImpl || apiFetch;

  /** ★★★ 앱 증명. **이 변수 말고 어디에도 두지 않는다** — iframe·localStorage·로그 금지.
   *  ⚠️ 세대가 바뀌면 버린다(아래 `resetGeneration`). */
  let proof = '';
  /** ★★★ 앱 선언이 바뀌었다 = **지금 도는 코드가 낡았다.**
   *
   *  ⚠️⚠️ 이 표시는 `resetGeneration()` 으로 지워지지 않는다. 프레임만 다시 만들면 **같은
   *    낡은 코드**가 새 증명을 받아 계속 돌고, 그것이 매니페스트 결속을 우회하는 길이다.
   *    사용자가 목록에서 앱을 **다시 열어야** 새 브리지(=새 릴리스)가 만들어진다. */
  let staleApp = false;
  const inflight = new Set<string>();
  const pending = new Map<string, Pending>();
  /** 멱등 자리 → 직전 결과. ⚠️ 「정확히 한 번」이 아니다 — **한 세대 안의 중복**만 막는다. */
  let idem = new Map<string, { at: number; body: Record<string, unknown> }>();
  let callTimes: number[] = [];

  function resetGeneration() {
    //: ⚠️ 증명도 버린다. 프레임이 바뀌면 «지금 그 앱을 열고 있다» 는 사실도 새로 세워야 한다.
    proof = '';
    idem = new Map();
    inflight.clear();
    pending.clear();
    callTimes = [];
  }

  function post(body: Record<string, unknown>) {
    const frame = deps.getFrame();
    if (!frame) return;
    //: ⚠️ 불투명 출처에는 이름이 없어 `targetOrigin` 을 지정할 수 없다 — `'*'` 로 나간다.
    //:   그래서 **응답에 비밀이 실리면 그것이 곧 유출**이고, 투영이 필수인 이유가 그것이다.
    try { frame.postMessage(body, '*'); } catch { /* 프레임이 사라졌다 */ }
  }

  function reply(requestId: string, ok: boolean, data?: unknown, code = '') {
    const sid = deps.getSid();
    const body = buildResponse(sid, requestId, ok, data, code);
    post(body);
    deps.onActivity?.({ op: '', ok, errorCode: ok ? undefined : String(body.error_code || '') });
    return body;
  }

  /** 앱이 보낸 권한 관련 필드를 **지운다**(검증이 아니라 삭제). */
  function stripIgnored(payload: any): Record<string, unknown> {
    if (!payload || typeof payload !== 'object' || Array.isArray(payload)) return {};
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(payload)) {
      if (!(IGNORED_FROM_APP as readonly string[]).includes(k)) out[k] = v;
    }
    return out;
  }

  /** 호출 예산. ⚠️ 폭주하는 앱 하나가 서버를 두드리는 것을 막는다. */
  function withinBudget(): boolean {
    const now = Date.now();
    callTimes = callTimes.filter((t) => now - t < 60000);
    if (callTimes.length >= MAX_CALLS_PER_MINUTE) return false;
    callTimes.push(now);
    return true;
  }

  /** 앱 증명을 받아 온다. **서버가 사실을 정한다** — 여기서 보내는 것은 릴리스뿐이다. */
  async function fetchProof(): Promise<boolean> {
    //: ⚠️ 낡은 코드에는 새 증명을 주지 않는다. 여기서 막지 않으면 프레임을 다시 만드는
    //:   순간 악수→발급이 돌아 **옛 앱이 되살아난다.**
    if (staleApp) return false;
    const r = await call('POST', `${RUNTIME}/proof`, { release_id: deps.releaseId },
                         { withProof: false });
    if (r.status !== 200 || !r.json?.data?.token) {
      //: ★ 서버가 «사용자가 할 일이 있다» 고 말한 경우(조직 범위 미선택 = 409)는 그 문장을
      //:   그대로 화면에 올린다. 「연결 실패」로 뭉개면 사용자는 원인을 알 수 없다.
      //: ⚠️ 실패 사유를 앱에게 옮기지 않는다. 화면(부모)에는 남긴다 — 사용자가 조직 범위를
      //:   골라야 하는 경우가 있고, 그때 「데이터가 없다」로 보이면 아무도 원인을 모른다.
      deps.onActivity?.({
        op: 'proof', ok: false,
        errorCode: String(r.status),
        //: ⚠️ 서버 문장을 그대로 쓰되 **부모 화면에만** 간다 — iframe 에는 가지 않는다.
        message: (r.status === 409 && typeof r.json?.detail === 'string')
          ? r.json.detail : '',
        needsScope: r.status === 409,
      });
      return false;
    }
    proof = String(r.json.data.token);
    return true;
  }

  async function call(method: string, path: string, body?: unknown,
                      opt: { withProof?: boolean } = {}): Promise<{
    status: number; json: any;
  }> {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), REQUEST_TIMEOUT_MS);
    try {
      //: ★★★ 증명에 묶인 응답은 URL 만으로 재사용할 수 없다. 브라우저 캐시가 이전 증명의
      //:   410 을 새 증명에도 돌려주면, 사용자가 앱을 다시 열어도 서버 호출 없이 계속
      //:   «앱 정의 변경» 으로 막힌다. 서버도 no-store 를 강제하지만 클라이언트에서도
      //:   명시해 중간 캐시·개발 프록시의 잘못된 재사용을 막는다.
      const init: RequestInit = { method, signal: ctrl.signal, cache: 'no-store' };
      if (opt.withProof !== false) {
        //: ⚠️ 증명이 없으면 **부르지 않는다.** 「증명 없이 한 번 시도해 보고 안 되면」은
        //:   서버가 폴백을 갖고 있을 때만 뜻이 있는데, 서버는 폴백을 갖지 않는다.
        if (!proof) return { status: 0, json: null };
        (init as any).headers = { [PROOF_HEADER]: proof };
      }
      if (body !== undefined) {
        const text = JSON.stringify(body);
        //: ⚠️ 서버 레코드 상한(512KB)과 정합해야 한다 — 어긋나면 「서버가 허용하는 값을 앱이
        //:   보낼 수 없는」 구간이 생기고, 사용자에게는 그 관계가 어디에도 보이지 않는다.
        if (text.length > MAX_REQUEST_BYTES) return { status: 413, json: null };
        init.body = text;
        //: ⚠️ 덮어쓰지 않는다 — 여기서 `=` 를 쓰면 위에서 붙인 증명 헤더가 사라지고,
        //:   그러면 모든 쓰기가 「증명 없음」으로 막힌다.
        init.headers = { ...((init as any).headers || {}),
                         'Content-Type': 'application/json' };
      }
      const r = await fetchImpl(path, init);
      let json: any = null;
      try { json = await r.json(); } catch { json = null; }
      return { status: r.status, json };
    } catch {
      //: ★ 시간 초과·네트워크 실패는 **「없다」가 아니다.** 0 은 `errorCodeForStatus` 에서
      //:   `UNAVAILABLE` 로 간다 — 앱이 할 일은 지우기가 아니라 재시도다.
      return { status: 0, json: null };
    } finally {
      clearTimeout(timer);
    }
  }

  /** 응답이 상한을 넘으면 **잘라서 주지 않는다** — 자르면 조용한 거짓말이 된다. */
  function tooLarge(data: unknown): boolean {
    try { return JSON.stringify(data).length > MAX_RESPONSE_BYTES; } catch { return true; }
  }

  async function run(msg: any): Promise<{
    ok: boolean; data?: unknown; code?: string; stale?: boolean;
  }> {
    const op = msg.op as Op;
    //: ★★★ 데이터셋을 **이름으로** 부른다. 릴리스는 서버가 증명에서 읽는다 —
    //:   브리지가 id 를 들고 다니지 않으므로 «남의 id 를 실어 보내는» 경로 자체가 없다.
    const base = `${RUNTIME}/datasets/${encodeURIComponent(String(msg.dataset || ''))}`;
    const rid = encodeURIComponent(String(msg.record_id || ''));

    //: 실패 응답을 한 곳에서 만든다 — 자리마다 손으로 쓰면 `stale` 을 빠뜨리는 곳이 생긴다.
    const _err = (status: number) => ({
      ok: false, code: errorCodeForStatus(status), stale: status === STATUS_STALE_APP,
    });

    if (op === 'data.schema') {
      const r = await call('GET', `${base}/schema`);
      if (r.status !== 200) return _err(r.status);
      return { ok: true, data: projectDataset(r.json?.data) };
    }
    if (op === 'data.list') {
      const { limit, offset } = normalizePage(msg.page);
      const r = await call('GET', `${base}/records?limit=${limit}&offset=${offset}`);
      if (r.status !== 200) return _err(r.status);
      const rows = Array.isArray(r.json?.data?.records)
        ? r.json.data.records.map(projectRecord) : [];
      const total = Number(r.json?.data?.total ?? rows.length);
      const nextOffset = offset + rows.length;
      const data = {
        records: rows,
        total,
        //: ★ 앱은 offset 을 계산하지 않는다. 다음 커서가 비면 «더 없음» 이다.
        cursor: nextOffset < total ? encodeCursor(nextOffset) : '',
      };
      if (tooLarge(data)) {
        return { ok: false, code: ERR_INVALID };   // 더 작은 page 로 나눠 요청하라
      }
      return { ok: true, data };
    }
    if (op === 'data.get') {
      const r = await call('GET', `${base}/records/${rid}`);
      if (r.status !== 200) return _err(r.status);
      return { ok: true, data: projectRecord(r.json?.data) };
    }
    if (op === 'data.create') {
      const r = await call('POST', `${base}/records`, { payload: stripIgnored(msg.payload) });
      if (r.status !== 200) return _err(r.status);
      return { ok: true, data: projectRecord(r.json?.data) };
    }
    if (op === 'data.update') {
      const r = await call('PUT', `${base}/records/${rid}`, { payload: stripIgnored(msg.payload) });
      if (r.status !== 200) return _err(r.status);
      return { ok: true, data: projectRecord(r.json?.data) };
    }
    if (op === 'data.remove') {
      const r = await call('DELETE', `${base}/records/${rid}`);
      if (r.status !== 200) return _err(r.status);
      return { ok: true, data: projectRecord(r.json?.data) };
    }
    return { ok: false, code: ERR_INVALID };
  }

  /** 증명을 갖춘 상태로 한 요청을 처리한다. **요청마다 최대 한 번** 재발급하고 재시도한다.
   *
   * ⚠️⚠️ [2026-08-14 교차검토 지적 4] 종전에는 재발급 횟수를 **Preview 수명 전체**로 셌다.
   *   그러면 두 번째 정상 만료부터 앱이 **영구적으로 실패**한다 — 15분짜리 증명이므로
   *   조금만 오래 열어 두면 반드시 도달하는 상태다. 「루프를 막는다」와 「한 번 쓰고 버린다」는
   *   다른 말이었고, 종전 코드는 뒤쪽이었다.
   * ★ 그래도 폭주는 막힌다: 재발급도 호출 예산(`withinBudget`)을 쓰고, 한 요청은 재시도를
   *   한 번만 한다 — 즉 실패가 계속돼도 **요청 수에 비례**할 뿐 스스로 증식하지 않는다. */
  async function runWithProof(msg: any): Promise<{ ok: boolean; data?: unknown; code?: string }> {
    if (!proof && !(await fetchProof())) return { ok: false, code: ERR_UNAVAILABLE };
    const first = await run(msg);
    const step = nextStep(first);
    if (step === STEP_RETURN) return first;
    //: ★★★ 앱 선언이 바뀐 것은 **재발급으로 풀리지 않는다.** 새 증명을 주면 옛 코드가
    //:   그것으로 계속 돈다 — 화면에 알리고 프레임을 버린다.
    if (step === STEP_STALE) {
      staleApp = true;
      //: ⚠️ 들고 있던 증명도 **즉시 버린다.** 남겨 두면 진행 중인 다른 호출들이 그것으로
      //:   계속 서버를 두드려 410 과 거부 감사가 쌓인다 — 아무 소용도 없이.
      proof = '';
      deps.onActivity?.({
        op: String(msg.op || ''), ok: false, errorCode: ERR_EXPIRED, staleApp: true,
        message: '앱 정의가 바뀌었습니다. 목록에서 이 앱을 다시 열어 주십시오.',
      });
      return first;
    }
    proof = '';
    if (!withinBudget() || !(await fetchProof())) return { ok: false, code: ERR_EXPIRED };
    return run(msg);
  }

  function handle(event: MessageEvent): boolean {
    //: ★★★ ① 소스 동일성이 **1차 경계**다. `event.origin` 은 `"null"` 이고 아무 샌드박스
    //:   프레임이나 같은 값을 낸다 — 그것으로는 아무것도 판별할 수 없다.
    const frame = deps.getFrame();
    if (!frame || event.source !== frame) return false;

    const d: any = event.data;
    if (!d || typeof d !== 'object') return false;
    if (d.type !== MSG_HELLO && d.type !== MSG_REQ) return false;   // 우리 것이 아니다

    //: ★ 꺼져 있으면 **악수에만** 답한다. 앱이 「호스트가 없다」를 알아야 화면에 그렇게
    //:   쓸 수 있다 — 조용히 무응답이면 앱은 로딩에서 영원히 멈춘다.
    if (!enabled) {
      if (d.type === MSG_HELLO) {
        post({ type: MSG_INIT, sid: deps.getSid(), version: SDK_VERSION,
               ok: false, error_code: ERR_UNAVAILABLE });
      } else if (typeof d.request_id === 'string') {
        reply(d.request_id, false, undefined, ERR_UNAVAILABLE);
      }
      return true;
    }

    if (d.type === MSG_HELLO) {
      //: ⚠️ 같은 세대에서 `hello` 를 여러 번 받아도 **같은 sid** 를 돌려준다. 새 sid 를
      //:   내주면 앱이 반복 hello 로 진행 중인 요청을 전부 무효화할 수 있다.
      const min = d.min_version;
      const okVer = typeof min !== 'number' || (Number.isInteger(min) && min >= 1 && min <= SDK_VERSION);
      post({
        type: MSG_INIT, sid: deps.getSid(), version: SDK_VERSION, ok: okVer,
        //: ★ 문맥은 **표시용 둘뿐**이다. 사용자·테넌트·조직범위를 넣으면 그것은 앱이 아는
        //:   사실이 되고, 앱은 LLM 이 쓴 코드다.
        context: okVer ? { app_id: deps.appId || '', release_id: deps.releaseId } : undefined,
        error_code: okVer ? undefined : ERR_INVALID,
      });
      return true;
    }

    const sid = deps.getSid();
    const v = validateRequest(d, sid, inflight);
    if (v.verdict === VERDICT_DROP) {
      //: ⚠️ 답하지 않는다 — 오류 응답 자체가 「여기 부모가 있고 sid 가 틀렸다」는 정보다.
      return true;
    }
    if (v.verdict !== VERDICT_OK) {
      console.warn('[afs] 계약 위반:', v.why);
      reply(String(d.request_id), false, undefined, v.code);
      return true;
    }

    if (inflight.size >= MAX_INFLIGHT || !withinBudget()) {
      //: ★ 「너무 많다」는 재시도로 풀린다. `INVALID`(앱 코드 문제)로 두면 앱이 포기한다.
      reply(String(d.request_id), false, undefined, ERR_UNAVAILABLE);
      return true;
    }

    const requestId = String(d.request_id);
    const isMutating = (MUTATING_OPS as readonly string[]).includes(d.op);
    const slot = isMutating
      ? idempotencySlot(sid, String(d.op), String(d.dataset || ''), String(d.idempotency_key || ''))
      : '';
    if (slot) {
      const hit = idem.get(slot);
      if (hit) {
        //: ★ 같은 화면에서 저장을 두 번 누른 경우. **서버를 다시 부르지 않는다.**
        post({ ...hit.body, request_id: requestId });
        return true;
      }
    }

    inflight.add(requestId);
    pending.set(requestId, { at: Date.now() });
    runWithProof(d)
      .then((out) => {
        const body = reply(requestId, out.ok, out.data, out.code);
        if (slot && out.ok) idem.set(slot, { at: Date.now(), body });
      })
      .catch(() => {
        //: ⚠️ 브리지 결함이 앱에게 «없다» 로 보이면 안 된다.
        reply(requestId, false, undefined, ERR_UNAVAILABLE);
      })
      .finally(() => {
        inflight.delete(requestId);
        pending.delete(requestId);
      });
    return true;
  }

  return { handle, enabled, resetGeneration };
}

/** 화면이 「왜 데이터가 없는가」를 쓸 수 있게 하는 설명. ⚠️ 빈 화면으로 두지 않는다. */
export function bridgeStatusKo(enabled: boolean, hasRelease: boolean): string {
  if (enabled) return '';
  if (!hasRelease) return '이 미리보기는 아직 릴리스가 없어 데이터에 연결되지 않습니다.';
  return 'Host Runtime 이 아직 켜지지 않았습니다(검증 중). 데이터는 연결되지 않습니다.';
}

export const DATASET_FIELDS_FOR_DOC = DATASET_PUBLIC_FIELDS;
export const NOT_FOUND_FOR_DOC = ERR_NOT_FOUND;
