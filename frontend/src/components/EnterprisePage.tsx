// [UI 설계서 §3.1 · §4 · §5.1] `/enterprise` — **경영 홈(Decision Canvas).**
//
// ## §1.2 승인 시안에서 «고정할 요소» 7가지를 이 화면이 전부 들고 있어야 한다
//
//   ① 좌측 역할 기반 의사결정 대기열     ② 중앙 Enterprise Digital Thread
//   ③ 업무 위의 DATA·SW·TWIN 레이어      ④ 하단 Trust Foundation
//   ⑤ 우측 회사 범위 Atlas               ⑥ 상단 회사·사업부·공장 Context
//   ⑦ LS Blue 는 구조, LS Red 는 결정·주의·핵심 행동에 **제한** 사용
//
// ⚠️ 첫 구현(2026-08-09 오전)은 ①④⑤ 만 만들고 ②③⑥ 을 빠뜨렸으며, 토큰 대신 인라인 색을
//   쓰고(존재하지 않는 `--afs-border` 를 참조했다) §1.3 최소 글자 크기도 어겼다.
//   「큰 모양은 맞는데 세부가 틀리다」는 지적이 정확했다. 이 파일은 그 재작성이다.
//
// ## §1.3 프로덕션 보정 — 프로토타입의 8~11px 를 그대로 쓰지 않는다
//
//   본문 14px+ / 폼 라벨·보조문 12px+ / 버튼 13px+·높이 36px+ / 핵심 행동 42~48px /
//   KPI 22px+ / **10~11px 는 해시·ID·타임스탬프 같은 기술 메타데이터에만**
//
// ## §2.4 간격 — 화면 24~32, 카드 내부 16~20, 패널 gap 16, 버튼 r6, 카드 r8
//
// ## ⚠️ 데이터를 지어내지 않는다
//
// 큐·KPI 는 전사 브리핑이, Trust 4카드는 각 도메인 API 가 실제로 주는 것을 쓴다. 서버가 주지
// 않는 값(담당 역할·기한·공정 프로필)은 **«미지정» 으로 적고 빈칸을 만들지 않는다.**
import { useCallback, useEffect, useMemo, useState } from 'react';

import { failed, loading, ok, type Loaded } from '../design/DataState';
import { CanvasJarvisRail } from './CanvasJarvisRail';
import { getEnterpriseContext , API_BASE_URL} from '../lib/api';
import {
  fetchBriefing, type Briefing, type BriefingItem,
} from '../lib/briefingApi';
import { getReadiness, listInstances } from '../lib/dataPrepApi';
//: ★★★ [2026-08-25] **이미 있는 것을 쓴다.** 처음에 `dataPrepApi` 에 계산 준비도
//:   클라이언트를 새로 만들었는데, `calculationApi.getReadiness` 가 같은 경로·같은
//:   타입으로 이미 있었다(`GateState`·`Gate`·`Readiness`).
//: ⚠️ 같은 질문에 두 벌이 생기면 서버가 관문을 늘릴 때 한쪽만 고쳐진다.
import {
  getReadiness as getCalcReadiness,
  type Gate as CalcGate, type Readiness as CalcReadiness,
} from '../lib/calculationApi';
import {
  DEFAULT_THREAD_OVERLAY_BY_NODE, listProfiles, type ThreadNode, type ThreadOverlay,
  type ThreadOverlayLayer,
} from '../lib/companyApi';
import { orgApi, type Dept } from '../lib/orgApi';
import { DecisionDrawer } from './DecisionDrawer';
import '../design/enterprise-canvas.css';
import { ServerText } from '../design/ServerText';
import { fetchCanvas, type Canvas } from '../lib/canvasApi';
import { fetchScopeNodes, labelForScope, type ScopeNode } from '../lib/scopeLabel';
import {
  actingScope, governanceBlockReason, UNKNOWN_SCOPE, type ActingScope,
} from '../lib/actingScope';

/** §4.2 상태. **색만으로 전달하지 않는다**(§2.1) — 낱말을 함께 싣는다. */

type QueueRow = BriefingItem & { section: string };

/** §4.5 LayerOverlay — DATA·SW·TWIN. **모두 끄는 것도 허용한다.** */
type Layer = ThreadOverlayLayer;
//: ⚠️ [설계 §9.1 WCAG AA] **브랜드 원색을 그대로 쓰면 안 된다.** 이 칩은 켜졌을 때 색 면
//  위에 흰 글자를 얹고, 꺼졌을 때는 그 색을 글자로 쓴다. 원색은 흰색 대비가 cyan 3.31 ·
//  orange 3.12 로 둘 다 4.5:1 에 못 미친다(실측으로 잡았다). 면·글자 모두 어두운 변형을 쓴다 —
//  원색은 테두리·아이콘처럼 **글자가 얹히지 않는 자리**에만 남긴다.
/** §4.4 `status` → 화면 낱말. ⚠️ 모르는 상태를 «정상» 으로 떨어뜨리지 않는다. */
const NODE_STATUS_KO: Record<string, string> = {
  normal: '정상', attention: '확인 필요', decision_required: '결정 필요',
  blocked: '막힘', unknown: '확인 못 함',
};

/** §5.1 Decision Focus 의 영향 4칸.
 *
 *  ⚠️ 시안의 `₩428억`·`8.0%` 는 `PROTOTYPE · SAMPLE DATA` 다. 채택 결정문이 「실제 API
 *    근거가 있을 때만」을 못박았으므로 값은 비운다 — 자리는 지킨다.
 *
 *  ## ⚠️⚠️ [2026-08-25] **라벨이 우리가 못 내는 값을 약속하고 있었다**
 *
 *  종전 넷은 시안의 `예상 매출 · 영업이익률 · 납기 준수율 · 결정 신뢰도` 였다. 그런데
 *  이 시스템의 계산(`core/calc_graph.OUTPUTS`)이 내는 것은 **다섯**이고 그중 어느 것도
 *  저 넷이 아니다:
 *
 *      production_qty 생산량 · ending_inventory 기말재고 · purchase_payment 구매지급
 *      · ending_cash 기말현금 · operating_profit 영업이익
 *
 *  ★ 영원히 채울 수 없는 라벨을 걸어 두면 그 자리는 **영원히 고장**이다. 실제로 낼 수
 *    있는 이름으로 바꾼다. `구매지급` 은 결정의 «결과» 보다 «투입» 에 가까워 넷에서 뺐다.
 *  ⚠️ 이 목록은 `core/calc_graph.OUTPUTS` 의 **복제**다 — 서버가 다섯을 바꾸면 여기도
 *    바뀌어야 한다. 값을 실을 때는 응답의 `labels` 를 쓰고, 여기 이름은 **빈 상태의
 *    자리표시**로만 쓴다. */
const IMPACT_SLOTS: { label: string; tone: string }[] = [
  { label: '생산량', tone: '' },
  { label: '기말재고', tone: 'risk' },
  { label: '기말현금', tone: 'good' },
  { label: '영업이익', tone: '' },
];

const LAYERS: { id: Layer; label: string; desc: string; color: string }[] = [
  { id: 'DATA', label: 'DATA 근거', desc: '업무가 참조하는 인증 데이터·계약·현장 이벤트',
    color: 'var(--cyan)' },
  { id: 'SW', label: 'SW 도구', desc: '업무를 실행하는 현업 앱·프로젝트·릴리스',
    color: 'var(--ls-red)' },
  { id: 'TWIN', label: 'TWIN 예측', desc: '변화의 영향을 비교하는 기준선·시나리오·Backtest',
    color: 'var(--warm)' },
];

/** §4.6 TrustFoundationStrip 의 카드 4종. 설계가 지정한 이름·핵심 정보·경고 그대로. */
type TrustCard = {
  key: string; title: string;
  /** ★ KPI 가 쓰는 숫자. **카드와 KPI 가 같은 조회를 두 번 하지 않게** 여기 남긴다.
   *  ⚠️ `null` = 아직/못 읽음. 0 으로 채우면 「없다」와 「모른다」가 같아진다. */
  n?: number | null;
  state: 'loading' | 'ok' | 'warn' | 'error' | 'blocked';
  headline: string;      // 상태의 완전성 — 숫자보다 먼저
  detail: string;        // 핵심 정보
  warn?: string;         // 설계가 지정한 경고
};

/** 관문 → 그 일을 하는 화면. ★ 서버의 관문 이름(`demo_readiness`)과 메뉴 id 를 잇는
 *  **한 곳**이다. ⚠️ 표에 없는 관문은 링크를 그리지 않는다 — 엉뚱한 화면으로 보내는 것은
 *  아무 데도 안 보내는 것보다 나쁘다. */
const GATE_DEST: Record<string, string> = {
  instance: 'dataprep',
  snapshots: 'dataprep',
  baseline: 'scenario',
  capabilities: 'calc-approval',
};

/** 지금 **멈춰 세운 관문** 하나. ⚠️ `UNKNOWN` 은 「앞 관문이 안 서서 판정 안 함」이므로
 *  범인이 아니다 — 그것을 사유로 적으면 사용자가 엉뚱한 곳을 고치러 간다. */
function blockingGate(w: CalcReadiness): CalcGate | undefined {
  return (w.gates || []).find((g) => g.state === 'FAILED')
      || (w.gates || []).find((g) => g.state === 'NOT_YET');
}

export function EnterprisePage({ onOpenBuild, onOpenMenu, onOpenDataReadiness }: {
  onOpenBuild: () => void;
  onOpenMenu: (id: string) => void;
  onOpenDataReadiness: () => void;
}) {
  const [data, setData] = useState<Loaded<Briefing>>(loading<Briefing>());
  const [selected, setSelected] = useState<QueueRow | null>(null);
  const [layers, setLayers] = useState<Layer[]>(['DATA', 'SW', 'TWIN']);
  const [nodes, setNodes] = useState<Dept[]>([]);
  const [nodeNote, setNodeNote] = useState('');
  const [trust, setTrust] = useState<TrustCard[]>([]);
  //: ★ Trust Foundation 중 운영 연결·외부지표는 거버넌스 권한이 필요한 조회다.
  //: ⚠️ 권한 밖인 사용자에게 일단 요청을 보내 403을 받은 뒤 오류 카드로 바꾸면,
  //:   정상적인 권한 경계가 화면에서는 제품 장애로 보인다. 서버가 준 자격을 먼저 읽고
  //:   권한 밖이면 요청 자체를 보내지 않는다. 판정 규칙은 `actingScope` 한 곳만 쓴다.
  const [trustScope, setTrustScope] = useState<ActingScope | null>(actingScope.peek());
  const [trustScopeSettled, setTrustScopeSettled] = useState(Boolean(actingScope.peek()));
  useEffect(() => {
    let alive = true;
    const apply = (s: ActingScope) => {
      if (!alive) return;
      setTrustScope(s);
      setTrustScopeSettled(true);
    };
    actingScope.load().then(apply).catch(() => apply(UNKNOWN_SCOPE));
    const unsubscribe = actingScope.subscribe(apply);
    return () => { alive = false; unsubscribe(); };
  }, []);
  //: §5.1 Decision Drawer — 안건 하나를 끝까지 처리하는 자리(520px).
  const [drawer, setDrawer] = useState<QueueRow | null>(null);
  //: ★★★ [로드맵 §4.2] Javis 가 「필요한 데이터셋과 누락 항목을 선제안」하려면 준비도를
  //:   **알아야** 한다. 종전에는 `{queue, layers}` 만 실어서, 비서는 우리 데이터를 하나도
  //:   모른 채 「확인할 수 없습니다」만 답했다(2026-08-20 실측).
  //: ⚠️ `null` = 아직 못 읽음, `[]` = 정말 0건. 둘을 같게 실으면 비서가 「데이터가 없다」로
  //:   말하고, 그것은 «조회 실패 ≠ 0건» 규칙이 비서 답변에서 무너지는 것이다.
  const [readiness, setReadiness] = useState<any[] | null>(null);
  //: ★★★ [2026-08-25] **왜 지금 계산이 안 도는가.** 영향 4칸이 `—` 만 그리면 「고장」으로
  //:   읽힌다 — 서버가 관문별로 답을 갖고 있으므로 그것을 그대로 옮긴다.
  //: ⚠️ `null` = 아직 못 읽음. 「못 읽음」과 「막힘 없음」을 같게 그리지 않는다.
  const [calcWhy, setCalcWhy] = useState<CalcReadiness | null>(null);
  //: ★★★ [2026-08-25] **회사별 업무 연결구성**(`process_profile`).
  //:
  //: ⚠️⚠️ 설계는 「process profile 기반 동적 렌더링」을 요구하는데 이 화면은 조직 트리를
  //:   업무 축으로 쓰고 있었다. 원천이 없다고 적혀 있었지만, `profile_kind` 닫힌 목록에는
  //:   `process_profile` 이 처음부터 있었다 — **부르는 곳이 없었을 뿐이다.**
  //: ★ 승인된 것만 쓴다(`is_effective`). 초안으로 그리면 검토 전 구성이 화면에 뜬다.
  //: ⚠️ 없으면 조직 트리로 되돌아가고, **그 사실을 화면에 적는다**(아래 `threadNote`).
  const [thread, setThread] = useState<ThreadNode[] | null>(null);
  const [threadState, setThreadState] = useState<'loading' | 'configured' | 'fallback' | 'error'>('loading');
  const [threadRevision, setThreadRevision] = useState(0);
  useEffect(() => {
    const refresh = () => setThreadRevision((v) => v + 1);
    window.addEventListener('factory:enterprise-context-changed', refresh);
    window.addEventListener('factory:company-configuration-changed', refresh);
    return () => {
      window.removeEventListener('factory:enterprise-context-changed', refresh);
      window.removeEventListener('factory:company-configuration-changed', refresh);
    };
  }, []);
  useEffect(() => {
    let alive = true;
    setThreadState('loading');
    const scope = (getEnterpriseContext().scopeNodeId || '').trim();
    (async () => {
      // 조직별 승인 구성이 있으면 그것을 쓰고, 없으면 회사 전체 승인 구성으로 내려간다.
      // 빈 scope 조회를 「전체 프로필」로 쓰지 않는다 — company_wide가 저장 경계를 못박는다.
      const scoped = scope ? await listProfiles(scope, 'process_profile') : [];
      const scopedEffective = scoped.find((r) => r.is_effective) || null;
      const rows = scopedEffective
        ? [scopedEffective]
        : await listProfiles('', 'process_profile', true);
      return rows;
    })()
      .then((rows) => {
        if (!alive) return;
        const eff = rows.find((r) => r.is_effective);
        const configured = eff?.payload?.nodes?.length ? eff.payload.nodes : null;
        setThread(configured);
        setThreadState(configured ? 'configured' : 'fallback');
      })
      .catch(() => { if (alive) { setThread(null); setThreadState('error'); } });
    return () => { alive = false; };
  }, [threadRevision]);

  const load = useCallback(async () => {
    setData(loading<Briefing>());
    try {
      //: ⚠️ `fetchBriefing()` 은 **`{ data, permission }` 봉투**를 돌려준다 — 봉투째 넣으면
      //:   `sections` 가 undefined 가 되어 화면이 오류 없이 전부 «—» 를 그린다(실측으로 잡았다).
      const r = await fetchBriefing();
      setData(ok(r.data));
    } catch (e) {
      setData(failed<Briefing>(e));
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  //: ★ 인스턴스가 **딱 하나**일 때만 그것으로 묻는다.
  //: ⚠️ 여럿이면 고르지 않는다 — 서버도 「아무 인스턴스나 골라 주지 않는다」로 두었다.
  //:   골라 버리면 그 답이 어느 인스턴스의 것인지 화면이 말할 수 없다.
  useEffect(() => {
    let alive = true;
    (async () => {
      let only = '';
      try {
        const r = await listInstances();
        const rows = r?.instances || [];
        if (rows.length === 1) only = String(rows[0]?.instance_id || '');
      } catch { /* 목록을 못 읽으면 인스턴스 없이 묻는다 — 관문에서 멈춘 답이 온다 */ }
      try {
        const w = await getCalcReadiness(only);
        if (alive) setCalcWhy(w);
      } catch { /* ⚠️ 실패를 «막힘 없음» 으로 그리지 않는다 — null 로 둔다 */ }
    })();
    return () => { alive = false; };
  }, []);

  /** §4.3 EnterpriseThreadCanvas — 업무 노드.
   *
   * ⚠️ 설계는 「**process profile** 기반 동적 렌더링」을 요구하는데 서버에 그 원천이 없다
   *   (`/master/domains` 404). 지어내지 않고 **조직 트리**를 업무 축으로 쓰고, 그것이
   *   공정 프로필이 아니라는 사실을 화면에 적는다. */
  useEffect(() => {
    let alive = true;
    orgApi.tree()
      .then(({ rows, blockedReason }) => {
        if (!alive) return;
        setNodes(rows || []);
        setNodeNote(blockedReason || '');
      })
      .catch((e) => { if (alive) setNodeNote(e?.message || '업무 노드를 받지 못했습니다.'); });
    return () => { alive = false; };
  }, []);

  /** §4.6 Trust Foundation 4카드 — 각 도메인 API 를 실제로 부른다. */
  useEffect(() => {
    let alive = true;
    const j = (p: string) => fetch(`${API_BASE_URL}${p}`).then((r) => (r.ok ? r.json() : Promise.reject(r)));

    const cards: TrustCard[] = [
      { key: 'mdm', title: 'MDM', state: 'loading', headline: '확인 중', detail: '' },
      { key: 'ops', title: '운영 데이터', state: 'loading', headline: '확인 중', detail: '' },
      { key: 'knowledge', title: '지식', state: 'loading', headline: '확인 중', detail: '' },
      { key: 'external', title: '외부지표', state: 'loading', headline: '확인 중', detail: '' },
    ];
    setTrust(cards);
    const put = (key: string, patch: Partial<TrustCard>) => {
      if (!alive) return;
      setTrust((prev) => prev.map((c) => (c.key === key ? { ...c, ...patch } : c)));
    };

    j('/api/v1/master/types')
      .then((r) => put('mdm', { state: 'ok', n: (r.data || []).length,
        headline: `유형 ${(r.data || []).length}종 등록`,
        detail: '연결 도메인·범위 커버리지' }))
      .catch(() => put('mdm', { state: 'error', headline: '확인하지 못했습니다',
        detail: '0 건이 아니라 조회 실패입니다' }));

    j('/api/v1/knowledge/packs')
      .then((r) => {
        const packs = r.data || [];
        put('knowledge', { state: 'ok', n: packs.length,
          headline: `승인 팩 ${packs.length}개`,
          detail: '문서·청크·검토 대기' });
      })
      .catch(() => put('knowledge', { state: 'error', headline: '확인하지 못했습니다', detail: '' }));

    if (trustScopeSettled) {
      const blockedReason = governanceBlockReason(trustScope);
      if (blockedReason) {
        const blocked = { state: 'blocked' as const, n: null,
          headline: '권한 범위에서 제외', detail: blockedReason };
        put('ops', blocked);
        put('external', blocked);
      } else {
        j('/api/v1/crosswalk/systems/coverage')
          .then((r) => {
            const d = r.data || {};
            const un = Number(d.unscoped || 0);
            put('ops', {
              state: un > 0 ? 'warn' : 'ok',
              n: d.total ?? null,
              headline: `연결 시스템 ${d.total ?? 0}개`,
              detail: `범위 지정 ${d.scoped ?? 0} · 미지정 ${un}`,
              warn: un > 0 ? '범위 미지정 시스템이 있습니다 — 모든 조직에 노출됩니다.' : '',
            });
          })
          .catch(() => put('ops', { state: 'error', headline: '확인하지 못했습니다', detail: '' }));

        j('/api/v1/external/readiness')
          .then((r) => {
            const d = r.data || {};
            const blocked = Number(d.blocked || 0);
            put('external', {
              state: blocked > 0 ? 'warn' : 'ok',
              headline: `지표 ${d.total ?? 0}개 중 사용 가능 ${d.usable_for_baseline ?? 0}개`,
              detail: 'vintage·지연 확인 필요',
              warn: blocked > 0 ? `${blocked}개가 기준선 사용 차단 상태입니다.` : '',
            });
          })
          .catch(() => put('external', { state: 'error', headline: '확인하지 못했습니다', detail: '' }));
      }
    }

    return () => { alive = false; };
  }, [trustScope, trustScopeSettled]);

  const d = data.value;

  const rows = useMemo<QueueRow[]>(() => {
    if (!d) return [];
    const out: QueueRow[] = [];
    for (const key of ['my_decisions', 'blocked'] as const) {
      const sec = (d.sections as any)?.[key];
      for (const it of (sec?.items || [])) out.push({ ...it, section: key });
    }
    const order: Record<string, number> = { high: 0, medium: 1, low: 2, info: 3 };
    return out.sort((a, b) => (order[a.severity] ?? 9) - (order[b.severity] ?? 9));
  }, [d]);

  useEffect(() => { if (!selected && rows.length) setSelected(rows[0]); }, [rows, selected]);

  //: 준비도를 읽어 **요약만** 싣는다.
  //: ⚠️ 원본 행을 통째로 실으면 프롬프트가 길어지고, 비서가 사람 화면에 없는 값을 인용한다.
  //: ⚠️ 실패해도 홈 화면을 죽이지 않는다 — 다만 «못 읽었다» 를 `null` 로 남긴다.
  useEffect(() => {
    let alive = true;
    listInstances()
      .then(async (d) => {
        const out: any[] = [];
        //: 최대 3개까지만 본다 — 홈 화면이 느려지면 아무도 안 쓴다.
        for (const it of (d.instances || []).slice(0, 3)) {
          try {
            const r = await getReadiness(it.instance_id);
            out.push({
              업무키트: it.label || it.kit_id,
              조직: it.scope_node_id,
              준비상태: r.status,
              필요: r.coverage?.required, 준비됨: r.coverage?.ready,
              막힘: r.coverage?.blocked,
              //: ★ 「무엇을 해야 하는가」가 핵심이다 — 상태만 주면 비서도 상태만 말한다.
              다음행동: (r.datasets || [])
                .filter((x: any) => x.next_action)
                .map((x: any) => `${x.label || x.dataset_contract_key}: ${x.next_action}`)
                .slice(0, 6),
              가능한산출물: r.available_outputs || [],
              막힌산출물: (r.blocked_outputs || []).map((o: any) => o.output),
            });
          } catch {
            //: 이 인스턴스만 못 읽었다 — 그 사실을 적는다(빠뜨리면 «없는 것» 이 된다).
            out.push({ 업무키트: it.label || it.instance_id, 준비상태: '조회 실패' });
          }
        }
        if (alive) setReadiness(out);
      })
      .catch(() => { if (alive) setReadiness(null); });
    return () => { alive = false; };
  }, []);

  /**
   * §5.1 상단 KPI **최대 4개** — 설계서 기본은
   * 「업무 도메인 / Master Data / 연결 / 근거 충실도」다.
   *
   * ## ⚠️⚠️ [2026-08-24] 왜 되돌렸는가
   *
   * 종전에는 「내가 결정할 것 / 막혀 있는 것 / 업무 도메인 / **LLM 비용**」이었다.
   * `LLM 비용` 은 **설계서 어디에도 없다** — 설계서는 비용을 §5.7 Agent 화면과
   * 「AI/품질 관리자」의 일로 배정한다. 경영 홈은 경영진·부서장의 결정 화면이고,
   * 경영자가 `$0.00 · 0콜` 을 보고 할 수 있는 일이 없다. **네 칸을 채우려고 넣은
   * 숫자**였다.
   *
   * ★ 「내가 결정할 것 / 막혀 있는 것」은 바로 아래 의사결정 대기열이 **제목과 함께**
   *   보여 준다. KPI 로 한 번 더 세면 같은 것을 두 번 말하면서 자리는 잃는다.
   * ⚠️ 값은 신뢰 기반(§4.6)이 이미 조회한 것을 **그대로 쓴다** — 같은 것을 두 곳에서
   *   따로 세면 언젠가 두 숫자가 갈라진다.
   */
  const kpis = useMemo(() => {
    const t = (k: string) => trust.find((c) => c.key === k);
    const val = (k: string) => {
      const c = t(k);
      //: 조회 실패·미완료는 `null` 이다 — 0 으로 떨어뜨리지 않는다.
      return c && c.state !== 'loading' && c.state !== 'error' ? (c.n ?? null) : null;
    };
    return [
      //: ⚠️ 조직을 **못 읽었으면** 개수를 쓰지 않는다. 종전에는 `nodes.length` 를 그냥
      //:   썼는데, 권한으로 막히면 그것이 0 이 되어 「업무 도메인 0」으로 보인다 —
      //:   「없다」와 「못 봤다」가 같아진다(`nodeNote` 가 그 구분을 들고 있다).
      { label: '업무 도메인', value: nodeNote ? null : (nodes.length || null),
        hint: nodeNote ? '조직을 확인하지 못했습니다' : '조직 트리 기준' },
      { label: 'Master Data', value: val('mdm'), hint: '등록된 기준정보 유형' },
      { label: '연결', value: val('ops'), hint: '연결된 외부 시스템' },
      { label: '근거 충실도', value: val('knowledge'), hint: '승인된 지식팩' },
    ];
  }, [trust, nodes, nodeNote]);

  const ctx = getEnterpriseContext();
  //: ★ 조직 이름은 **상단바와 같은 곳**에서 얻는다(`lib/scopeLabel`).
  //: ⚠️ 종전에는 `ctx.scopeNodeId` 원시 id 를 그대로 찍어 `node_41402723bc90` 처럼
  //:   아무 뜻 없는 값이 화면 맨 위에 떴다(2026-08-24 사용자 지적).
  //: ★★★ [LE-01] 승인 시안의 중앙 축 — **수주→손익 일곱 단계.**
  //: ⚠️ 종전에는 조직 트리로 대체돼 있었다(줄 API 가 없어서). 이제 단일 Read Model 이 준다.
  const [canvas, setCanvas] = useState<Canvas | null>(null);
  const [canvasErr, setCanvasErr] = useState('');
  //: ★★★ [2026-08-25 사용자 지적] 「클릭하면 포커스 이동이 안되네요」.
  //:
  //: ⚠️⚠️ 종전에는 **한 변수**(`pickedNode`)를 대기열과 공정 노드가 같이 썼다. 그런데
  //:   대기열은 `ref`(안건 식별자)를, 공정 노드는 `key`(`order`·`purchase`)를 넣는다.
  //:   그래서 노드를 누르면 `q.find(i => i.ref === 'purchase')` 가 **늘 못 찾고**
  //:   첫 안건으로 되돌아갔다 — 눌러도 아무 일이 없는 것처럼 보였다.
  //: ★ 두 배역에 같은 값을 쓰면 결함이 숨는다. **따로 둔다.**
  const [pickedRef, setPickedRef] = useState('');
  const [pickedStep, setPickedStep] = useState<{ key: string; label: string } | null>(null);
  useEffect(() => {
    let alive = true;
    fetchCanvas()
      .then((c) => { if (alive) { setCanvas(c); setCanvasErr(''); } })
      //: ⚠️ 실패를 빈 화면으로 접지 않는다 — 「없다」와 「못 읽었다」는 다르다.
      .catch((e) => { if (alive) setCanvasErr(e?.message || '불러오지 못했습니다.'); });
    return () => { alive = false; };
  }, []);

  const [scopeNodes, setScopeNodes] = useState<ScopeNode[]>([]);
  useEffect(() => {
    let alive = true;
    void fetchScopeNodes().then((rows) => { if (alive) setScopeNodes(rows); });
    return () => { alive = false; };
  }, []);
  const scopeName = labelForScope(scopeNodes, ctx.scopeNodeId || '');

  /** §4.2 대기열 한 줄의 «시각/도메인» — 시안의 `10:30 · 생산계획` 자리.
   *
   *  ⚠️ 도메인을 지어내지 않는다. 서버가 아직 항목에 단계를 싣지 않으므로 성격
   *    (결정/막힘/자료/프로그램)을 적는다 — 빈칸으로 두면 무엇인지도 모른다. */
  const SECTION_KO: Record<string, string> = {
    my_decisions: '결정', blocked: '막힘', data_health: '자료', programs: '프로그램',
  };
  const q = canvas?.decision_queue ?? [];
  const decisions = q.filter((i) => i.section !== 'programs');
  const programs = q.filter((i) => i.section === 'programs');
  const focus = q.find((i) => i.ref === pickedRef) || decisions[0] || null;
  //: ★ 지금 초점이 무엇인가를 **한 곳**에서 만든다 — 가운데 패널과 비서가 같은 말을 해야 한다.
  const focusLabel = pickedStep ? pickedStep.label
    : (focus ? (SECTION_KO[focus.section] || focus.section) : '');
  const processKeys = thread?.map((n) => n.key)
    || canvas?.domain_nodes?.map((n) => n.id) || [];
  const processCount = Math.max(1, processKeys.length);
  //: ★ 보조정보는 업무 노드와 **같은 프로필·같은 열**에 산다. 종전에는 고정 상수 다섯을
  //:   단계 수에 맞춰 비율 배치해 회사가 단계를 바꾸면 엉뚱한 노드 아래로 이동했다.
  //: ⚠️ `null` 은 «그 단계에 등록된 카드가 없음»이다. 칸 자체를 없애면 사용자는 카드가
  //:   없는 것과 화면이 정렬을 놓친 것을 구분할 수 없다.
  const overlaySlots: (ThreadOverlay | null)[] = processKeys.map((key, index) => {
    if (thread) {
      const node = thread[index];
      if (node && Object.prototype.hasOwnProperty.call(node, 'overlay')) {
        return node.overlay || null;
      }
      // 옛 승인 프로필에는 `overlay` 필드가 없다. 그 경우에만 제품 기본값을 한 번 승계한다.
      // 새 판에서 사용자가 카드를 삭제해 `null`로 저장하면 이 기본값은 되살아나지 않는다.
      return DEFAULT_THREAD_OVERLAY_BY_NODE[key] || null;
    }
    return DEFAULT_THREAD_OVERLAY_BY_NODE[key] || null;
  });

  return (
    /* ★★★ 승인 시안(`uiux-prototypes/master-concept/index.html`, 2026-07-30 채택)의
       구조를 그대로 쓴다. 클래스 이름·배치·치수는 시안 CSS(`design/enterprise-canvas.css`)
       에서 온다 — 여기서 인라인으로 다시 그리지 않는다.
       ⚠️ 값은 실제 API 에서만 온다(채택 결정문). 시안 표본값을 옮겨 적지 않는다. */
    <div className="le-canvas">
      <div className="workspace">
        {/* ── 좌 258: 역할 기반 의사결정 대기열 ─────────────────────────── */}
        <aside className="work-rail">
          <span className="rail-kicker">ENTERPRISE DECISION CENTER</span>
          <h1>지금 결정해야 할<br />회사 업무입니다.</h1>
          <p>권한과 역할에 맞춰 영향도가 높은 순서로 정리했습니다.</p>

          <section className="queue">
            <div className="queue-label">
              <span>의사결정 대기</span>
              <b>{canvasErr ? '—' : String(decisions.length).padStart(2, '0')}</b>
            </div>
            {canvasErr ? (
              <p style={{ padding: '12px 2px', fontSize: 11, color: 'var(--ls-red)' }}>
                {canvasErr}
              </p>
            ) : !canvas ? (
              <p style={{ padding: '12px 2px', fontSize: 11 }}>불러오는 중…</p>
            ) : decisions.length === 0 ? (
              <p style={{ padding: '12px 2px', fontSize: 11, color: '#6e7480' }}>
                지금 답해야 할 것이 없습니다.
              </p>
            ) : decisions.map((it) => (
              <button
                key={`${it.kind}-${it.ref}-${it.title}`}
                className={`decision${it.severity === 'high' ? ' urgent' : ''}`
                  + (focus === it ? ' selected' : '')}
                //: ★ 대기열을 고르면 **단계 선택은 푼다** — 둘이 동시에 켜져 있으면
                //:   가운데가 어느 것을 말하는지 화면이 답할 수 없다.
                onClick={() => { setPickedRef(it.ref); setPickedStep(null); }}
              >
                <small>{SECTION_KO[it.section] || it.section}</small>
                <b>{it.title}</b>
                <span><ServerText text={it.why} /></span>
              </button>
            ))}

            <div className="queue-label">
              <span>진행 중인 제품</span>
              <b>{canvasErr ? '—' : String(programs.length).padStart(2, '0')}</b>
            </div>
            {programs.length === 0 ? (
              <p style={{ padding: '12px 2px', fontSize: 11, color: '#6e7480' }}>
                진행 중인 것이 없습니다.
              </p>
            ) : programs.map((it) => (
              <button key={`p-${it.ref}-${it.title}`} className="decision"
                onClick={() => onOpenMenu('workspace')}>
                <small>PROGRAM</small>
                <b>{it.title}</b>
                <span><ServerText text={it.why} /></span>
              </button>
            ))}
          </section>

          <div className="rail-tools">
            <button onClick={() => onOpenMenu('workspace')}>전체 업무 공간</button>
            <button onClick={onOpenBuild}>내 SW·시뮬레이터</button>
            <button onClick={onOpenDataReadiness}>데이터 준비 상태</button>
          </div>
        </aside>

        {/* ── 중앙: Enterprise Digital Thread ───────────────────────────── */}
        <section className="canvas">
          <header className="canvas-head">
            <div>
              <small>LIVE ENTERPRISE THREAD</small>
              <h2>업무·데이터·AI가 하나의 경영 결과로 이어집니다.</h2>
            </div>
            {/* §4.5 LayerOverlay — 모두 끄는 것도 허용한다 */}
            <div className="view-switch" role="group"
              aria-label="업무 흐름 위에 표시할 보조 정보 레이어">
              {LAYERS.map((l) => (
                <button key={l.id} title={l.desc}
                  aria-pressed={layers.includes(l.id)}
                  className={layers.includes(l.id) ? 'active' : ''}
                  onClick={() => setLayers((prev) => prev.includes(l.id)
                    ? prev.filter((x) => x !== l.id) : [...prev, l.id])}>
                  <span className="layer-color" style={{ background: l.color }} aria-hidden="true" />
                  {l.label}
                </button>
              ))}
            </div>
            <div className="context-stats">
              {kpis.map((k) => (
                <div key={k.label}>
                  {/* ⚠️ 「모른다」를 0 으로 쓰지 않는다 — 0 은 «없다» 이고 «못 셌다» 와 다르다. */}
                  <b>{k.value === null || k.value === undefined ? '—' : k.value}</b>
                  <span>{k.label}</span>
                </div>
              ))}
            </div>
          </header>

          <div className="enterprise-thread">
            <div className="thread-heading">
              <span className="thread-label">
                <b>ENTERPRISE DIGITAL THREAD</b> · 실제 운영 기준
              </span>
              <span className={`thread-source ${threadState}`}>
                {threadState === 'configured' ? '회사별 승인 구성'
                  : threadState === 'loading' ? '구성 확인 중'
                    : threadState === 'error' ? '구성 조회 실패 · 기본 흐름 표시'
                      : '기본 흐름 표시'}
              </span>
              <button type="button" className="thread-config"
                onClick={() => onOpenMenu('company')}>
                회사 등록 · 연결구성
              </button>
            </div>

            {/* ★ 업무 단계가 «연결돼 움직인다»는 시안의 핵심 인상.
                ⚠️ 하늘색 보조 점선은 무엇을 뜻하는지 설명할 수 없어 복원하지 않는다.
                회색 기반선 = 연결 구조, 붉은 이동선·펄스 = 현재 회사의 실행 흐름이다. */}
            <svg className="flow-svg" viewBox="0 0 1000 170" preserveAspectRatio="none"
              aria-hidden="true">
              <defs>
                <marker id="thread-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4"
                  orient="auto" markerUnits="strokeWidth">
                  <path d="M0,0 L8,4 L0,8 Z" className="flow-arrow" />
                </marker>
              </defs>
              <path className="flow-base"
                d="M40 40 C145 7 225 74 335 40 S520 7 620 40 S805 74 960 40" />
              <path className="flow-live"
                d="M40 40 C145 7 225 74 335 40 S520 7 620 40 S805 74 960 40"
                markerEnd="url(#thread-arrow)" />
              <circle className="flow-pulse" r="5">
                <animateMotion dur="4.8s" repeatCount="indefinite"
                  path="M40 40 C145 7 225 74 335 40 S520 7 620 40 S805 74 960 40" />
              </circle>
              <circle className="flow-pulse flow-pulse-late" r="4">
                <animateMotion dur="4.8s" begin="-2.4s" repeatCount="indefinite"
                  path="M40 40 C145 7 225 74 335 40 S520 7 620 40 S805 74 960 40" />
              </circle>
            </svg>

            {/* §4.4 DomainNode — 일곱 단계 */}
            {/* ★★★ [2026-08-25] **회사가 설정한 연결구성이 있으면 그것을 그린다.**
                ⚠️ 없으면 조직 트리로 되돌아간다 — 그 사실은 위 `nodeNote` 가 적는다. */}
            <div className="processes" style={{
              gridTemplateColumns: `repeat(${processCount}, minmax(0, 1fr))`,
            }}>
              {thread ? thread.map((n, i) => {
                const on = pickedStep?.key === n.key;
                return (
                  <button key={n.key || i}
                    className={`process${on ? ' active' : ''}`}
                    title={n.note || n.label}
                    aria-pressed={on}
                    onClick={() => setPickedStep(on ? null : { key: n.key, label: n.label })}>
                    <span className="process-dot">
                      {String(i + 1).padStart(2, '0')}
                    </span>
                    <b>{n.label}</b>
                    <small>{n.key}</small>
                    {/* ⚠️ 대표 지표는 아직 원천이 없다. 지어내지 않고 **비워 둔다** —
                        `note` 가 있으면 그것을 쓴다(사람이 적은 사실이다). */}
                    <em>{n.note || '—'}</em>
                  </button>
                );
              }) : (canvas?.domain_nodes ?? []).map((n) => {
                const on = pickedStep?.key === n.id;
                return (
                  <button key={n.id}
                    className={`process${on ? ' active' : ''}`}
                    title={n.reason || n.label}
                    aria-pressed={on}
                    onClick={() => setPickedStep(on ? null : { key: n.id, label: n.label })}>
                    <span className="process-dot">
                      {String(n.sequence).padStart(2, '0')}
                    </span>
                    <b>{n.label}</b>
                    <small>{n.systems}</small>
                    {/* ⚠️ 시안의 `수요 +3%` 는 표본값이다. 근거가 없으면 **상태**로 답한다 —
                        지어낸 숫자가 한 번 뜨면 그것이 실적으로 읽힌다. */}
                    <em>{n.primary_metric
                      ? `${n.primary_metric.label} ${n.primary_metric.value}`
                      : NODE_STATUS_KO[n.status] || '확인 못 함'}</em>
                  </button>
                );
              })}
            </div>

            {/* §4.5 레이어 오버레이 — **업무 단계가 하나 더 생긴 것이 아니다.**
                DATA=판단 근거, SW=실행 도구, TWIN=예측·비교 모델을 업무 흐름 위에
                겹쳐 보는 보조 정보다. 상단 스위치는 이 세 층의 표시만 켜고 끈다.
                지금은 각 층이 «무엇을 덮는가» 만 말한다.
                ⚠️ 시안처럼 개별 자산(「판매계획 v12 · 승인」)을 적으려면 노드별 자산
                  귀속이 있어야 한다. 없는 것을 적지 않는다. */}
            <div className="overlay-strip" style={{
              gridTemplateColumns: `repeat(${processCount}, minmax(0, 1fr))`,
            }}>
              {overlaySlots.map((item, index) => (
                <div key={processKeys[index] || index} className="overlay-slot"
                  data-node-key={processKeys[index] || ''}>
                  {item ? (
                    <div className={`overlay-item ${item.layer.toLowerCase()}`}
                      aria-hidden={!layers.includes(item.layer)}
                      style={layers.includes(item.layer) ? undefined
                        : { opacity: 0, visibility: 'hidden' }}>
                      <small>{item.kicker}</small>
                      <b>{item.body}</b>
                    </div>
                  ) : (
                    <div className="overlay-item empty" aria-label="등록된 보조정보 없음">
                      <small>보조정보</small>
                      <b>등록된 정보 없음</b>
                    </div>
                  )}
                </div>
              ))}
            </div>

            {/* §5.1 Decision Focus */}
            <article className="focus-panel">
              <div className="focus-copy">
                <small>DECISION POINT{focusLabel ? ` · ${focusLabel}` : ''}</small>
                <div className="focus-content">
                {/* ★★★ 고른 단계가 있으면 **그 단계를 말한다.** 종전에는 노드를 눌러도
                    가운데가 그대로여서 「눌러도 아무 일이 없다」로 보였다.
                    ⚠️ 단계와 안건을 잇는 원천이 아직 없다 — 그래서 «이 단계에 묶인 안건이
                      있다» 고 **지어내지 않고**, 무엇을 고른 상태인지만 사실대로 적는다. */}
                {pickedStep ? (
                  <>
                    <h3>{pickedStep.label}</h3>
                    {/* ⚠️ 한 줄로 둔다 — 이 패널은 시안에서 214px 이고, 두 줄이 되면
                        위 오버레이 띠를 덮는다(실측 14px 겹침). */}
                    <p>이 단계에 묶인 안건은 아직 없습니다 — 왼쪽에서 안건을 고르십시오.</p>
                  </>
                ) : (
                  <>
                    <h3>{focus ? focus.title : '지금 답해야 할 것이 없습니다.'}</h3>
                    <p>{focus
                      ? <ServerText text={focus.why} />
                      : '대기열이 비어 있습니다 — 새 항목이 생기면 여기에 먼저 보입니다.'}</p>
                  </>
                )}
                </div>
                {focus && (
                  <div className="focus-actions">
                    <button className="main" onClick={() => setDrawer(focus as QueueRow)}>
                      자세히 보고 처리
                    </button>
                    <button onClick={() => onOpenMenu('path-calc')}>영향 계산 열기</button>
                    <button onClick={() => onOpenMenu('decision-pkg')}>의사결정 안건</button>
                  </div>
                )}
                {/* ★ 오른쪽 영향 4칸이 **왜 비었는지**. 서버가 준 답을 그대로 옮긴다
                    (`GET /calculation/readiness`) — 문구를 지어내지 않는다.
                    ⚠️ 영향 칸 안에 두면 시안의 4칸 리듬이 깨진다(실측). 여유가 있는
                      이쪽(설명 열)에 둔다. */}
                <div className="impact-why">
                  {calcWhy === null ? (
                    // ⚠️ 「아직 못 읽음」과 「막힘 없음」은 다른 사실이다.
                    <span>계산이 도는지 확인하는 중…</span>
                  ) : calcWhy.status === 'READY' ? (
                    <span>계산 관문은 모두 서 있습니다 — 경로 계산을 돌리면 오른쪽 값이 채워집니다.</span>
                  ) : (
                    <>
                      {/* ★ 한 줄로 둔다 — 이 패널은 시안에서 214px 이고, 여기가 길어지면
                          위 오버레이 띠와 겹친다(실측 41px 겹침).
                          ⚠️ 다음 할 일을 **버리지 않는다**: 버튼의 이름으로 남기고, 누르면
                            그 화면이 같은 말을 다시 한다. */}
                      <b>{blockingGate(calcWhy)?.summary || '계산이 아직 돌지 않습니다.'}</b>
                      {GATE_DEST[blockingGate(calcWhy)?.gate || ''] ? (
                        <button type="button" className="impact-why-go"
                          title={calcWhy.next_action}
                          aria-label={calcWhy.next_action || '해당 화면 열기'}
                          onClick={() => onOpenMenu(GATE_DEST[blockingGate(calcWhy)!.gate])}>
                          해결하러 가기
                        </button>
                      ) : (
                        //: ⚠️ 갈 곳을 모르면 **다음 할 일이라도** 적는다 — 침묵보다 낫다.
                        calcWhy.next_action && <span>{calcWhy.next_action}</span>
                      )}
                    </>
                  )}
                </div>
              </div>
              {/* ★★★ [2026-08-25 사용자 지적] 「컨텐츠간 간격 여백이 틀어졌다」.
                  ⚠️⚠️ 원인은 내가 넣은 «왜 비었는지» 줄이었다. **두 번** 잘못 놓았다:
                    ① `.focus-panel`(2열)의 형제 → **세 번째 칸**이 되어 새 줄이 생겼고
                       패널이 자라 영향 4칸이 107 → 85 로 눌렸다.
                    ② `.impact`(2열) 안 → 이번엔 4칸의 리듬을 깼다(칸 71, 패널 250·311).
                  ★ 시안의 영향 칸은 **4칸뿐**이다. 그 리듬을 지킨다.
                  ⚠️ 안쪽 여백 값 자체는 시안과 같았다(7/7/14 · 패딩 27/19) — 재서 확인했다.
                    「여백이 틀어졌다」의 원인은 여백 값이 아니라 **격자 구조**였다. */}
              <div className="impact">
                {IMPACT_SLOTS.map((s) => (
                  <div key={s.label} className={s.tone}>
                    <span>{s.label}</span>
                    <b>—</b>
                  </div>
                ))}
              </div>
            </article>
          </div>

          {/* §4.6 Trust Foundation */}
          <section className="foundation">
            <div className="foundation-title">
              <small>TRUST FOUNDATION</small>
              <b>이 결과의 기반</b>
            </div>
            <div className="layers">
              {trust.map((c) => (
                <div key={c.key} className="layer">
                  <small>{c.title}</small>
                  <b>
                    <i style={c.state === 'ok' ? undefined : {
                      background: c.state === 'error' ? 'var(--ls-red)' : '#d39a58',
                    }} />
                    {c.headline}
                  </b>
                  <span>{c.warn || c.detail}</span>
                </div>
              ))}
            </div>
          </section>

          <div className="status-bar">
            <span>권한 <b>{scopeName || '권한 범위 전체'}</b></span>
            <span>실행 문맥 <b>{ctx.entityMode || 'REAL'}</b></span>
            <span>기준시각 <b>
              {d?.generated_at ? new Date(d.generated_at).toLocaleString() : '—'}
            </b></span>
            {/* ⚠️ 비용은 설계서상 Agent 화면의 값이다. 시안 상태바에는 있으므로 자리만
                지키되, 못 읽으면 «—» 다(0 이 아니다). */}
            <span className="cost">LLM COST <b>{
              (canvas?.cost_summary as any)?.cost_usd != null
                ? `$${Number((canvas!.cost_summary as any).cost_usd).toFixed(2)}`
                : '—'
            }</b></span>
          </div>
        </section>

        {/* ── 우 328: Atlas ─────────────────────────────────────────────── */}
        {/* ★★★ [2026-08-25] 시안 마크업으로 바꿨다(`AtlasRail`).
            ⚠️⚠️ 종전에는 `.atlas-rail` 안에 범용 `JarvisRail` 을 넣었다. 그래서 이식해 둔
              `.atlas-*` CSS 가 **한 줄도 쓰이지 않았고**(클래스를 쓰는 마크업이 없었다)
              화면이 시안과 전혀 달랐다. 기능(질문·답변)은 같은 `jarvisApi` 로 그대로 잇는다. */}
        <aside className="atlas-rail">
          <CanvasJarvisRail
            //: ★ 가운데와 **같은 초점**을 본다 — 두 곳이 다른 것을 말하면 사용자는
            //:   어느 쪽이 지금 문맥인지 알 수 없다.
            contextLabel={`지금 보는 것 · ${focusLabel || '전사'}`}
            title={pickedStep ? pickedStep.label
              : (focus ? focus.title : '지금 답해야 할 것이 없습니다.')}
            why={pickedStep ? '이 단계를 골랐습니다. 왼쪽 대기열에서 안건을 고르면 그 내용으로 바뀝니다.'
              : (focus ? focus.why : '대기열이 비어 있습니다 — 새 항목이 생기면 여기에 먼저 보입니다.')}
            //: ★ 「우리가 실제로 아는 것」만 싣는다. 시안의 96%·₩8.3억·48건은 표본값이다.
            //: ⚠️ 못 읽은 것을 0 으로 적지 않는다 — 「확인하지 못함」은 다른 사실이다.
            facts={[
              { label: '결정 대기', value: `${decisions.length}건` },
              ...(canvas ? [{ label: '업무 단계', value: `${canvas.domain_nodes.length}단계` }] : []),
              { label: '업무 데이터',
                value: readiness === null ? '확인하지 못함'
                  : readiness.length === 0 ? '적용된 업무키트 없음'
                    : readiness.map((x: any) => `${x.업무키트} ${x.준비상태}`).join(' · ') },
            ]}
            actions={[
              '왜 이 판단입니까?',
              '데이터가 부족합니까?',
              '관련 SW·에이전트 상태는 어떻습니까?',
              '시나리오로 보면 어떻게 됩니까?',
            ]}
            //: ⚠️ 「권고안 적용」은 우리 계산이 아직 못 낸다. 대신 **갈 수 있는 곳**으로 보낸다.
            recommendLabel="의사결정 안건으로 만들기"
            onRecommend={() => onOpenMenu('decision-pkg')}
            context={{
              current_module: 'enterprise',
              selected_object_type: focus?.ref_type || '',
              selected_object_id: focus?.ref || '',
              object_snapshot: {
                ...(focus
                  ? { title: focus.title, severity: focus.severity, section: focus.section }
                  : {}),
                업무_데이터_준비도: readiness === null
                  ? '조회 실패 — 지금 확인하지 못했습니다(없다는 뜻이 아닙니다)'
                  : readiness,
              },
              available_actions: [],
              evidence_refs: [],
            }} />
        </aside>
      </div>

      {/* §5.1 Decision Drawer — 520px */}
      {drawer && (
        <DecisionDrawer item={drawer} onClose={() => setDrawer(null)}
          onOpenRef={(refType) => {
            const t = (refType || '').toLowerCase();
            if (t.includes('release') || t.includes('promotion')) onOpenMenu('workspace');
            else if (t.includes('contract') || t.includes('data')) onOpenMenu('governance');
            else if (t.includes('agent') || t.includes('asset')) onOpenMenu('agent-gov');
            else onOpenMenu('briefing');
          }} />
      )}
    </div>
  );
}
