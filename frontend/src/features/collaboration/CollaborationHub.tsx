// [CL-1 · UIUX] 협업 허브 — 승인 시안(Living Enterprise Canvas) 기준선 위에서 동작하는 실제 화면
//
// 이 화면이 반드시 보여줘야 하는 것(서버가 문구까지 준다 — 화면이 지어내지 않는다):
//   ① 수락 후 "데이터 접근 범위는 넓어지지 않았습니다" — 없으면 사용자는 앱을 받으면 자료도
//      보인다고 믿는다. 그 오해가 곧 권한 우회에 대한 잘못된 안심이다.
//   ② 401 과 404 의 구분 — "사용자를 지정하십시오"와 "그 요청은 없습니다"는 다른 행동을 요구한다.
//   ③ 앱이 요구하는 권한(Capability Manifest)과 "별도 로그인 없음" — 자체 로그인 화면을 만난
//      순간 사용자가 이상하다고 신고할 수 있어야 한다.
//
// ⚠️ 브라우저 `prompt()`/`alert()` 를 쓰지 않는다. 승인 시안에 없고, 키보드 접근·스크린리더
//   대응이 되지 않으며 스타일도 입힐 수 없다 — 화면 안 입력으로 처리한다.
import { useCallback, useEffect, useMemo, useState } from 'react';

import { Banner, HubShell, Panel, ScreenHead, type RailItem } from '../../design/HubShell';
import { HubDialog } from '../../design/HubDialog';
import { JarvisRail } from '../../design/JarvisRail';
import type { JarvisContext } from '../../lib/jarvisApi';
import {
  collaborationApi, DELIVERY_STATUS_KO, type CapabilityManifest, type Delivery,
  type DeliveryPreflight, type PocketApp,
} from '../../lib/collaborationApi';
import { EmptyOrError, failed, loading, ok, type Loaded } from '../../design/DataState';
import { reportRequestFailure, reportRequestSuccess } from '../../lib/backendHealth';
import { DecisionCenter, type DecisionJarvis } from './DecisionCenter';
import { PublicationCenter, type PublicationJarvis } from './PublicationCenter';

// [CL-2] 목표 정보구조(§4)의 «의사결정 센터»를 같은 허브 안에 둔다. 별도 모달을 하나 더 띄우면
// 사용자는 전달·결정·발간이 서로 다른 제품이라고 읽는다 — 이것들은 하나의 폐루프다.
type View = 'inbox' | 'apps' | 'deliver' | 'sent' | 'decisions' | 'publications';

/** [UIUX-AUDIT-29 §1] **화면 문맥은 활성 모듈을 따라간다.**
 *
 * 감사 지적: 의사결정 센터와 발간 화면에서도 상단이 계속 «협업 — 앱 전달·수락·내 앱», «개인
 * 전달은…», «앱 전달과 공동 업무» 였다. 사용자는 상단 문구로 «내가 지금 어디에 있는가»를
 * 읽는다. 그것이 화면 내용과 다르면, 화면이 자기 위치를 잘못 말하는 것이다.
 *
 * ★ 그래서 제목·설명·좌하단 안전 카드를 **한 곳에서** 모듈별로 정의한다. 세 군데에 흩어 놓으면
 *   하나만 고쳐지고 다시 어긋난다. */
type ModuleContext = {
  dialogLabel: string;
  barTitle: string;
  barNote: string;
  kicker: string;
  title: string;
  subtitle: string;
  /** 좌측 하단 카드 — **그 모듈에서 가장 오해하기 쉬운 통제**를 적는다. */
  guard: { kicker: string; title: string; body: string };
};

const MODULE_CONTEXT: Record<View, ModuleContext> = {
  inbox: {
    dialogLabel: '협업 허브 — 받은 앱',
    barTitle: '받은 앱',
    barNote: '수락해도 데이터 접근 범위는 넓어지지 않습니다',
    kicker: 'COLLABORATION', title: '받은 앱과 응답',
    subtitle: '다른 사용자가 나에게 전달한 앱입니다. 수락하면 내 주머니에 담깁니다.',
    guard: { kicker: 'APP-IN-APP', title: '플랫폼 인증 상속',
      body: '전달된 앱은 자체 로그인을 갖지 않습니다. 현재 사용자·조직·역할로 실행되며, 수락해도 볼 수 있는 자료가 늘어나지 않습니다.' },
  },
  apps: {
    dialogLabel: '협업 허브 — 내 앱',
    barTitle: '내 앱',
    barNote: '수락한 앱은 현재 사용자 권한으로 실행됩니다',
    kicker: 'COLLABORATION', title: '내 앱 주머니',
    subtitle: '수락한 앱을 여기서 실행합니다. 별도 로그인이 없습니다.',
    guard: { kicker: 'APP-IN-APP', title: '플랫폼 인증 상속',
      body: '앱은 호스트 권한으로 실행됩니다. 앱이 자체 로그인 화면을 띄우면 관리자에게 알려 주십시오.' },
  },
  deliver: {
    dialogLabel: '협업 허브 — 사용자에게 전달',
    barTitle: '사용자에게 전달',
    barNote: '개인 전달은 부서 공유·전사 승격과 별개입니다',
    kicker: 'COLLABORATION', title: '앱 전달',
    subtitle: '지정한 한 사람에게 앱을 전달합니다. 부서 공유·전사 승격과는 다른 경로입니다.',
    guard: { kicker: 'SCOPE', title: '권한은 넓어지지 않습니다',
      body: '수락해도 상대가 원래 볼 수 없던 자료는 앱에서도 보이지 않습니다. 자료 권한이 필요하면 조직 권한을 별도로 부여해야 합니다.' },
  },
  sent: {
    dialogLabel: '협업 허브 — 보낸 요청',
    barTitle: '보낸 요청',
    barNote: '수락 전에는 언제든 회수할 수 있습니다',
    kicker: 'COLLABORATION', title: '보낸 전달과 응답',
    subtitle: '내가 보낸 전달의 상태입니다. 회수하면 상대 주머니에 회수 사실이 남습니다.',
    guard: { kicker: 'TRACE', title: '회수는 이력을 지우지 않습니다',
      body: '회수해도 «누가 언제 무엇을 보냈는가»는 원장에 남습니다. 상태만 덮어쓰면 나중에 설명할 수 없습니다.' },
  },
  decisions: {
    dialogLabel: '의사결정 센터 — 한 문서 · 세 관점',
    barTitle: '의사결정 센터',
    barNote: '세 관점은 같은 문서의 다른 렌더링입니다',
    kicker: 'DECISIONS', title: '의사결정 패키지',
    subtitle: '시뮬레이션 결과를 하나의 Package 로 만들고, 요청자·의사결정자·영향부서가 같은 문서를 관점별로 봅니다.',
    guard: { kicker: 'ONE PACKAGE', title: '숫자를 자동으로 갱신하지 않습니다',
      body: '검토 요청 후 근거가 바뀌면 조용히 고치지 않고 «근거 변경됨»으로 세워 사람이 다시 보게 합니다. 참석자가 읽은 문서와 결정된 문서가 달라지면 회의록이 거짓이 됩니다.' },
  },
  publications: {
    dialogLabel: '대내외 발간 — 나가기 전에 막습니다',
    barTitle: '대내외 발간',
    barNote: '대외 발간은 임원 승인과 법무·공시 검토를 모두 통과해야 나갑니다',
    kicker: 'PUBLICATIONS', title: '보고서 발간',
    subtitle: '승인된 결정 Snapshot 에서 보고서를 만들고, 게이트를 통과한 것만 내보냅니다.',
    guard: { kicker: 'GATE', title: '차단은 서버에서 합니다',
      body: '대외 발간은 화면 버튼뿐 아니라 API 도 함께 막습니다 — 주소를 알아도 게시되지 않습니다. 게시 어댑터가 없으면 배포는 «실패»로 기록되고 상태는 올라가지 않습니다.' },
  },
};

const STATUS_CHIP: Record<string, string> = {
  PENDING: 'warn', ACCEPTED: 'success', REJECTED: 'muted', EXPIRED: 'muted', REVOKED: 'danger',
};
const DOT: Record<string, string> = {
  PENDING: 'wait', ACCEPTED: 'good', REJECTED: 'off', EXPIRED: 'off', REVOKED: 'bad',
};

function StatusChip({ status }: { status: Delivery['status'] }) {
  const s = DELIVERY_STATUS_KO[status] ?? { label: status };
  return <span className={`state-chip ${STATUS_CHIP[status] || 'muted'}`}>{s.label}</span>;
}

/** 앱이 요구하는 권한. **비어 있으면 "요구 없음"이라고 말한다** — 빈 카드를 두면 사용자는
 *  화면이 덜 만들어진 것으로 읽고 그냥 수락한다. */
function CapabilityManifestCard({ m }: { m: CapabilityManifest }) {
  const caps = useMemo(() => {
    if (m?.required_capabilities?.length) return m.required_capabilities;
    return (m?.capabilities || []).map((c) => {
      const i = c.lastIndexOf('.');
      return i > 0 ? { resource: c.slice(0, i), actions: [c.slice(i + 1)] }
        : { resource: c, actions: [] as string[] };
    });
  }, [m]);
  const inherited = m?.auth_mode === 'PLATFORM_INHERITED';
  return (
    <div className="capability-manifest">
      <header>
        <b>이 앱이 요구하는 것</b>
        <span>{inherited ? '플랫폼 인증 상속' : (m?.auth_mode || '인증 방식 미지정')}</span>
      </header>
      {caps.length === 0 ? (
        <ul><li><i aria-hidden="true">–</i><div><b>요구하는 데이터 권한이 없습니다</b>
          <small>이 앱은 별도 자료 접근 없이 동작합니다.</small></div></li></ul>
      ) : (
        <ul>
          {caps.map((c) => (
            <li key={c.resource}>
              <i aria-hidden="true">✓</i>
              <div>
                <b>{c.resource}</b>
                <small>{c.actions.length ? c.actions.join(' · ') : '동작 미지정'}</small>
              </div>
            </li>
          ))}
        </ul>
      )}
      {/* ★ [설계 §5.3] 「플랫폼 인증 상속 · 기능 권한 · 요구 데이터 범위 · **금지 기능**을
          구분한다」 — 처음에는 데이터 범위를 꼬리말에 이어 붙이고 금지 기능은 아예 그리지
          않았다. 금지 기능은 «이 앱이 무엇을 못 하는가» 이고, 수락 판단에서 요구 권한만큼
          중요하다. 넷을 같은 무게의 구획으로 나눈다. */}
      <div className="manifest-facets">
        <div>
          <span>요구 데이터 범위</span>
          {m?.required_data_scopes?.length
            ? <b>{m.required_data_scopes.join(' · ')}</b>
            : <b className="muted">요구 없음</b>}
          {/* ⚠️ 설계: 「데이터 권한 부족은 **자동 부여 체크박스가 아니라** 별도 권한 요청
              경로로 표시한다」 — 여기서 켜서 줄 수 있는 것은 없다고 못박는다. */}
          <small>
            부족한 자료 권한은 이 화면에서 부여되지 않습니다 — 조직 권한을 별도로 요청하십시오.
          </small>
        </div>
        <div>
          <span>금지 기능</span>
          {m?.forbidden_features?.length
            ? <b className="danger">{m.forbidden_features.join(' · ')}</b>
            : <b className="muted">명시된 금지 기능 없음</b>}
          <small>
            {m?.forbidden_features?.length
              ? '이 기능은 앱 안에서 차단됩니다.'
              : '금지 목록이 비어 있다는 뜻이며, 무엇이든 허용된다는 뜻이 아닙니다.'}
          </small>
        </div>
      </div>

      <footer>
        {inherited
          ? '별도 로그인 없이 현재 사용자·조직 권한으로 실행됩니다. 앱이 자체 로그인 화면을 띄우면 관리자에게 알려 주십시오.'
          : '인증 방식이 확인되지 않았습니다 — 관리자에게 문의하십시오.'}
      </footer>
    </div>
  );
}

export function CollaborationHub({ onClose, initialView = 'inbox', releaseIds = [],
  simulationRunIds = [] }: {
  onClose: () => void;
  initialView?: View;
  releaseIds?: string[];
  simulationRunIds?: string[];
}) {
  const [view, setView] = useState<View>(initialView);
  // [CL-2] 의사결정 센터가 **자기가 강조 중인 객체**를 올려 준다. 허브가 추측하지 않는다 —
  //   Jarvis 가 참조하는 객체와 화면이 보여 주는 객체가 갈라지면 가장 찾기 어려운 오답이 된다.
  const [decisionCtx, setDecisionCtx] = useState<DecisionJarvis | null>(null);
  const [pubCtx, setPubCtx] = useState<PublicationJarvis | null>(null);
  // [UIUX-AUDIT-30] CL-1 에도 «조회 실패 ≠ 0건» 계약을 적용한다. 감사 실측: API 가
  //   실패했는데 화면은 «대기 없음» 칩과 «응답을 기다리는 요청이 없습니다» 를 함께 띄웠다 —
  //   받는 사람은 «나에게 온 앱이 없다»로 읽는다.
  const [data, setData] = useState<Loaded<{
    inbox: Delivery[]; sent: Delivery[]; apps: PocketApp[];
  }>>(loading());
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<{ msg: string; status?: number } | null>(null);
  const [flash, setFlash] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string>('');

  const load = useCallback(async () => {
    setBusy('불러오는 중'); setErr(null);
    try {
      const [i, s, a] = await Promise.all([
        collaborationApi.inbox(), collaborationApi.outbox(), collaborationApi.myApps(),
      ]);
      setData(ok({ inbox: i, sent: s, apps: a }));
      reportRequestSuccess();
    } catch (e: any) {
      // 빈 배열로 떨어뜨리지 않는다. 그 순간 «받은 앱 0건»이 되고, 그것은 사실이 아니다.
      setData(failed(e));
      reportRequestFailure(e?.status);
    } finally { setBusy(null); }
  }, []);

  useEffect(() => { load(); }, [load]);

  // ★ 사용자가 바뀌면 이전 수신함·주머니를 **즉시 폐기**한다(§CL-FE-03). 남겨 두면 다른
  //   사용자의 목록이 화면에 그대로 남고, 그것이 곧 유출이다.
  useEffect(() => {
    const h = () => { setData(loading()); setSelectedId(''); load(); };
    window.addEventListener('factory:acting-user-changed', h);
    return () => window.removeEventListener('factory:acting-user-changed', h);
  }, [load]);

  const act = async (label: string, fn: () => Promise<any>) => {
    setBusy(label); setErr(null); setFlash(null);
    try {
      const r = await fn();
      // 서버가 준 문구를 그대로 보여준다 — 화면이 지어내면 서버 규칙과 갈라진다.
      setFlash(r?.scope_note || r?.note || null);
      await load();
      return r;
    } catch (e: any) {
      setErr({ msg: e?.message || String(e), status: e?.status });
    } finally { setBusy(null); }
  };

  const okData = data.status === 'ok';
  const inbox = data.value?.inbox || [];
  const sent = data.value?.sent || [];
  const apps = data.value?.apps || [];
  const pending = inbox.filter((d) => d.status === 'PENDING');
  const selected = useMemo(
    () => inbox.find((d) => d.delivery_id === selectedId) || pending[0] || inbox[0] || null,
    [inbox, pending, selectedId]);

  const items: RailItem[] = [
    // 조회에 실패했으면 배지 숫자를 **표시하지 않는다.** «0» 배지는 «없다»로 읽힌다.
    { id: 'inbox', label: '받은 앱', hint: '나에게 전달된 요청', icon: 'inbox',
      count: okData ? pending.length : undefined },
    { id: 'apps', label: '내 앱', hint: '수락해서 쓰는 앱', icon: 'apps',
      count: okData ? apps.length : undefined },
    { id: 'deliver', label: '사용자에게 전달', hint: '지정한 한 사람에게', icon: 'deliver' },
    { id: 'sent', label: '보낸 요청', hint: '응답 상태와 회수', icon: 'sent' },
    { id: 'decisions', label: '의사결정 센터', hint: '한 문서 · 세 관점', icon: 'decision' },
    { id: 'publications', label: '대내외 발간', hint: '나가면 되돌릴 수 없다', icon: 'publish' },
  ];

  const ctx = MODULE_CONTEXT[view];
  /** 전달 3화면(받은 앱·내 앱·전달·보낸 요청)에서만 허브 자신의 상태를 말한다. */
  const isCollab = view !== 'decisions' && view !== 'publications';

  // Jarvis 문맥 — **선택된 객체**를 그대로 넘긴다. Task ID 를 사용자에게 묻지 않는다(§3-8).
  const jarvisCtx = (() => {
    if (view === 'publications') {
      return pubCtx
        ? { title: pubCtx.title, desc: pubCtx.desc, ev: pubCtx.ev }
        : { title: '대내외 발간', desc: '대외 발간은 두 승인을 모두 통과해야 나갑니다.', ev: [] };
    }
    if (view === 'decisions') {
      return decisionCtx
        ? { title: decisionCtx.title, desc: decisionCtx.desc, ev: decisionCtx.ev }
        : { title: '의사결정 센터', desc: '내가 참여자로 지정된 안건만 보입니다.', ev: [] };
    }
    if (view === 'apps') {
      return { title: apps.length ? `내 앱 ${apps.length}개` : '내 앱 없음',
        desc: '수락한 앱은 현재 사용자·조직 권한으로 실행됩니다.',
        ev: apps.slice(0, 3).map((a) => ({ label: a.display_name, value: a.release_id })) };
    }
    if (view === 'sent') {
      return { title: sent.length ? `보낸 요청 ${sent.length}건` : '보낸 요청 없음',
        desc: '수락 전에는 언제든 회수할 수 있습니다.',
        ev: sent.slice(0, 3).map((d) => ({ label: d.recipient_user_id, value: DELIVERY_STATUS_KO[d.status]?.label || d.status })) };
    }
    if (selected) {
      return {
        title: selected.release_id,
        desc: selected.purpose,
        ev: [
          { label: '보낸 사람', value: selected.sender_user_id },
          { label: '상태', value: DELIVERY_STATUS_KO[selected.status]?.label || selected.status },
          { label: 'Manifest 지문', value: (selected.manifest_fingerprint || '').slice(0, 12) || '없음' },
          { label: '만료', value: selected.expires_at || '없음' },
        ],
      };
    }
    return { title: '협업', desc: '앱 전달·수락·내 앱을 한곳에서 다룹니다.', ev: [] };
  })();

  // ★ [지적 4] Jarvis 가 참조하는 객체 = 화면이 강조 중인 객체. 두 값이 갈라지면 사용자는
  //   A 를 보면서 B 에 대한 답을 읽는다 — 가장 발견하기 어려운 오답이다.
  const jarvisContext: JarvisContext = view === 'publications' ? {
    current_module: 'collaboration/publications',
    selected_object_type: 'publication',
    selected_object_id: pubCtx?.objectId || '',
    object_snapshot: pubCtx?.snapshot || {},
    available_actions: pubCtx?.actions || [],
    evidence_refs: [],
  } : view === 'decisions' ? {
    current_module: 'collaboration/decisions',
    selected_object_type: 'decision_case',
    selected_object_id: decisionCtx?.objectId || '',
    object_snapshot: decisionCtx?.snapshot || {},
    available_actions: decisionCtx?.actions || [],
    evidence_refs: decisionCtx?.snapshot?.evidence_hash
      ? [{ evidence_hash: decisionCtx.snapshot.evidence_hash,
        package_version: decisionCtx.snapshot.package_version }] : [],
  } : {
    current_module: `collaboration/${view}`,
    selected_object_type: view === 'apps' ? 'app_pocket' : 'app_delivery',
    selected_object_id: view === 'apps' ? (apps[0]?.pocket_id || '') : (selected?.delivery_id || ''),
    object_snapshot: selected ? {
      release_id: selected.release_id, purpose: selected.purpose, status: selected.status,
      expires_at: selected.expires_at, sender: selected.sender_user_id,
      capabilities: selected.manifest_snapshot?.capabilities || [],
      auth_mode: selected.manifest_snapshot?.auth_mode,
    } : { inbox_count: inbox.length, apps_count: apps.length, sent_count: sent.length },
    available_actions: selected?.can_respond
      ? ['수락', '거절', '재배정 요청'] : selected?.can_revoke ? ['회수'] : [],
    evidence_refs: selected?.manifest_fingerprint
      ? [{ manifest_fingerprint: selected.manifest_fingerprint }] : [],
  };

  return (
    // ★ [교차검토 지적 1] 손으로 만든 `fixed div` 는 모달이 아니었다 — dialog semantics·배경
    //   inert·포커스 트랩·Escape·포커스 복귀·스크롤 잠금이 모두 없었다. 셸 공통 기반으로 옮겼다.
    <HubDialog label={ctx.dialogLabel} onClose={onClose}>
      <div className="afs-dialog-bar">
        {/* [UIUX-AUDIT-29 §1] 제목·설명이 활성 모듈을 따라간다. 고정 문구는 화면이 자기
            위치를 잘못 말하는 것이다. */}
        <b>{ctx.barTitle}</b>
        <span>{ctx.barNote}</span>
        <div className="bar-actions">
          {isCollab && busy && <span className="busy">{busy}…</span>}
          <button onClick={onClose} className="secondary-button" style={{ minHeight: 32 }}>
            닫기 <span aria-hidden="true" style={{ opacity: .7 }}>(Esc)</span>
          </button>
        </div>
      </div>

      <div className="afs-dialog-body">
          <HubShell
            kicker={ctx.kicker}
            title={ctx.title}
            subtitle={ctx.subtitle}
            items={items} activeId={view} onSelect={(id) => setView(id as View)}
            footer={
              // ★ 안전 카드도 모듈을 따라간다. 의사결정·발간 화면에서 «App-in-App 인증»은
              //   가장 중요한 통제가 아니다 — 그 자리에는 그 화면에서 가장 오해하기 쉬운
              //   통제가 있어야 한다(감사 §1).
              <div className="inheritance-card">
                <span>{ctx.guard.kicker}</span>
                <b>{ctx.guard.title}</b>
                <p>{ctx.guard.body}</p>
              </div>
            }
            jarvis={
              // ⚠️ [지적 3] 고정 문자열 응답을 제거했다. 실제 어댑터(`lib/jarvisApi.ts`)를 호출하고
              //   대화는 레일 안에서 유지된다. 연결 실패는 숨기지 않고 그대로 표시한다.
              <JarvisRail
                contextTitle={jarvisCtx.title}
                contextDescription={jarvisCtx.desc}
                evidence={jarvisCtx.ev}
                context={jarvisContext}
                quickQuestions={view === 'publications' ? [
                  '이 보고서는 지금 왜 나갈 수 없습니까?',
                  '대외 발간에서 무엇이 제외됩니까?',
                  '배포가 실패한 대상이 있습니까?',
                ] : view === 'decisions' ? [
                  '이 안건은 무엇을 승인하는 것입니까?',
                  '지금 결정할 수 없는 이유가 무엇입니까?',
                  '세 관점이 같은 근거를 보고 있습니까?',
                ] : [
                  '이 앱은 어떤 자료를 요구합니까?',
                  '수락하면 제 권한이 넓어집니까?',
                  '이 요청은 언제 만료됩니까?',
                ]}
              />
            }
          >
            {/* [UIUX-AUDIT-29 §2] 허브의 전달 목록 오류를 **의사결정·발간 화면에서 띄우지
                않는다.** 그 화면들은 자기 오류를 스스로 말하며, 두 배너가 겹치면 화면이
                오류로 뒤덮이고 정작 «무엇을 해야 하는가»가 안 보인다. */}
            {isCollab && err && (
              <Banner tone="error"
                title={err.status === 401 ? '사용자 지정이 필요합니다'
                  : err.status === 404 ? '요청을 찾을 수 없습니다' : '오류'}>
                {err.msg}
                {err.status !== 401 && (
                  <div style={{ marginTop: 10 }}>
                    <button className="secondary-button" onClick={load}>다시 시도</button>
                  </div>
                )}
              </Banner>
            )}
            {isCollab && flash && <Banner tone="info">{flash}</Banner>}

            {view === 'inbox' && (
              <InboxScreen list={inbox} state={data} onRetry={load}
                selectedId={selected?.delivery_id || ''}
                onSelect={setSelectedId}
                onAccept={(d) => act('수락 중', () => collaborationApi.accept(d.delivery_id))}
                onReject={(d, n) => act('거절 중', () => collaborationApi.reject(d.delivery_id, n))}
                onReassign={(d, n) => act('재배정 요청 중', () => collaborationApi.reassign(d.delivery_id, n))} />
            )}
            {view === 'apps' && (
              <AppsScreen list={apps} state={data} onRetry={load}
                onPin={(a) => act('갱신 중', () => collaborationApi.patchApp(a.pocket_id, { pinned: !a.pinned }))}
                onRename={(a, n) => act('이름 변경 중', () => collaborationApi.patchApp(a.pocket_id, { display_name: n }))}
                //: ⚠️ 앱을 실제로 띄우는 실행 경로는 아직 서버에 없다. **여는 척하지 않는다** —
                //  열람 사실만 기록하고, 산출물이 어디 있는지 그대로 알린다.
                onOpen={(a) => act('여는 중', () => collaborationApi.patchApp(
                  a.pocket_id, { mark_opened: true }))} />
            )}
            {view === 'deliver' && (
              <DeliverScreen releaseIds={releaseIds}
                onSubmit={async (f) => {
                  const r = await act('전달 중', () => collaborationApi.create({
                    release_id: f.release_id, recipient_user_id: f.recipient, purpose: f.purpose,
                    expires_in_days: f.expires_in_days,
                    // 중복 클릭에도 하나만 생기게 — 서버가 같은 키를 재생한다.
                    idempotency_key: `${f.release_id}|${f.recipient}|${f.purpose}`.slice(0, 120),
                  }));
                  if (r) setView('sent');
                }} />
            )}
            {view === 'sent' && (
              <SentScreen list={sent} state={data} onRetry={load}
                onRevoke={(d, r) => act('회수 중', () => collaborationApi.revoke(d.delivery_id, r))} />
            )}
            {view === 'decisions' && (
              <DecisionCenter onJarvis={setDecisionCtx} simulationRunIds={simulationRunIds} />
            )}
            {view === 'publications' && (
              <PublicationCenter onJarvis={setPubCtx} />
            )}
          </HubShell>
      </div>
    </HubDialog>
  );
}

// ── 받은 앱 ──────────────────────────────────────────────────────────────────
function InboxScreen({ list, state, onRetry, selectedId, onSelect, onAccept, onReject,
  onReassign }: {
  list: Delivery[]; state: Loaded<any>; onRetry: () => void;
  selectedId: string; onSelect: (id: string) => void;
  onAccept: (d: Delivery) => void;
  onReject: (d: Delivery, note: string) => void;
  onReassign: (d: Delivery, note: string) => void;
}) {
  const [filter, setFilter] = useState<'all' | 'pending'>('pending');
  // 화면 안 입력 — `prompt()` 를 쓰지 않는다(키보드·스크린리더·스타일 모두 안 되기 때문).
  const [form, setForm] = useState<{ id: string; kind: 'reject' | 'reassign'; note: string } | null>(null);

  const shown = filter === 'pending' ? list.filter((d) => d.status === 'PENDING') : list;
  const pendingCount = list.filter((d) => d.status === 'PENDING').length;

  return (
    <>
      <ScreenHead kicker="INBOX" title="받은 앱"
        description="다른 사용자가 나에게 전달한 앱입니다. 수락하면 내 앱 주머니에 담기며, 데이터 접근 범위는 넓어지지 않습니다."
        chip={state.status !== 'ok'
          // 실패했는데 «대기 없음»(초록)을 띄우지 않는다 — 감사에서 실측된 결함이다.
          ? { label: state.status === 'forbidden' ? '접근 불가' : '조회 불가', tone: 'danger' }
          : { label: pendingCount ? `응답 대기 ${pendingCount}건` : '대기 없음',
            tone: pendingCount ? 'warn' : 'success' }} />

      <Panel kicker="REQUESTS" title="전달 요청"
        action={
          <div className="filter-pills">
            <button className={filter === 'pending' ? 'active' : ''} onClick={() => setFilter('pending')}>대기</button>
            <button className={filter === 'all' ? 'active' : ''} onClick={() => setFilter('all')}>전체</button>
          </div>
        }>
        {shown.length === 0 ? (
          <EmptyOrError state={state.status} error={state.error} onRetry={onRetry}
            emptyText={filter === 'pending'
              ? '응답을 기다리는 요청이 없습니다. 전체를 보려면 위의 «전체» 를 누르십시오.'
              : '받은 앱 요청이 없습니다. 다른 사용자가 앱을 전달하면 여기에 나타납니다.'} />
        ) : shown.map((d) => (
          <article key={d.delivery_id}
            className={`request-card ${d.delivery_id === selectedId ? 'active' : ''}`}>
            {/* ⚠️ [지적 4] 이전에는 `onMouseEnter` 로만 선택이 바뀌어 **키보드 사용자는 Jarvis
                문맥을 바꿀 수 없었다.** 명시적 선택 버튼 + focus 선택으로 바꿨다. */}
            <button type="button" className="request-select"
              aria-pressed={d.delivery_id === selectedId}
              onClick={() => onSelect(d.delivery_id)}
              onFocus={() => onSelect(d.delivery_id)}>
              <span className="app-mark" aria-hidden="true">{d.release_id.slice(-2)}</span>
              <span className="request-select-main">
                <small>{d.release_version ? `v${d.release_version}` : 'RELEASE'}</small>
                <b>{d.release_id}</b>
                <span className="purpose">{d.purpose}</span>
              </span>
              <span className="request-select-side">
                <StatusChip status={d.status} />
                <time>{(d.created_at || '').slice(0, 10)}</time>
                <em>{d.delivery_id === selectedId ? '선택됨' : '선택'}</em>
              </span>
            </button>

            {/* [설계 §5.3] IncomingAppRequestCard 필수 표시 —
                발신자·부서 / 앱·릴리스 / 요청 사유 / 최소 권한 / 데이터 범위 / 만료 / 감사 대상.
                앱·릴리스와 사유는 위 선택 버튼이, 최소 권한·데이터 범위는 Manifest 카드가 든다. */}
            <div className="request-scope">
              <div><span>보낸 사람</span><b>{d.sender_user_id}</b></div>
              {/* ⚠️ 부서를 서버가 확인하지 못했으면 «미확인» 이라고 적는다 — 빈칸으로 두면
                  받는 사람은 부서가 없는 것으로 읽는다. */}
              <div><span>부서</span><b>{d.sender_dept_id || '미확인'}</b></div>
              <div><span>만료</span><b>{d.expires_at || '없음'}</b></div>
              <div><span>감사 대상</span>
                <b>{d.manifest_snapshot?.audit_mode
                  ? (d.manifest_snapshot.audit_mode === 'NONE' ? '아니오' : d.manifest_snapshot.audit_mode)
                  : '미지정'}</b></div>
              <div><span>Manifest 지문</span><b>{(d.manifest_fingerprint || '').slice(0, 12) || '없음'}</b></div>
            </div>

            <div style={{ padding: '0 15px' }}>
              <CapabilityManifestCard m={d.manifest_snapshot} />
            </div>

            {/* 권한이 넓어지지 않는다는 사실을 **수락 전에** 말한다 — 수락 후에만 말하면 늦다. */}
            <div className="request-alert" style={{ marginTop: 12 }}>
              <i aria-hidden="true">i</i>
              <div>
                <b>수락해도 볼 수 있는 자료가 늘어나지 않습니다</b>
                <small>앱은 현재 사용자 권한으로 실행됩니다. 원래 보이지 않던 자료는 앱에서도 보이지 않습니다.</small>
              </div>
            </div>

            {d.note && (
              <div className="request-alert warn" style={{ marginTop: 8 }}>
                <i aria-hidden="true">!</i><div><b>{d.note}</b></div>
              </div>
            )}

            {d.can_respond ? (
              <>
                {/* ★★ [설계 §5.3] 「수락·거절은 카드 하단에 나란히 두되 **수락을 무조건
                    기본값으로 강조하지 않는다**」.
                    ⚠️ 이전에는 수락만 채워진 주 버튼(`primary-button`)이었다. 권한을 받아들이는
                      쪽을 시각적 기본값으로 두면 사람은 Manifest 를 읽지 않고 강조된 것을
                      누른다 — 그것이 바로 이 카드가 막으려는 일이다. 둘을 같은 무게로 둔다. */}
                <footer>
                  <button className="text-button"
                    onClick={() => setForm({ id: d.delivery_id, kind: 'reassign', note: '' })}>
                    담당 아님 · 재배정 요청
                  </button>
                  <button className="danger-ghost"
                    onClick={() => setForm({ id: d.delivery_id, kind: 'reject', note: '' })}>
                    거절
                  </button>
                  <button className="secondary-button" onClick={() => onAccept(d)}>
                    수락하고 내 앱에 추가
                  </button>
                </footer>
                {form?.id === d.delivery_id && (
                  <div style={{ padding: '0 15px 15px' }}>
                    <label className="field-label" htmlFor={`note-${d.delivery_id}`}>
                      {form.kind === 'reject'
                        ? '거절 사유 (보낸 사람이 다시 판단할 근거가 됩니다)'
                        : '누가 담당인지 알려 주십시오 (시스템이 자동 배정하지 않습니다)'}
                    </label>
                    <textarea id={`note-${d.delivery_id}`} className="afs-textarea" value={form.note}
                      onChange={(e) => setForm({ ...form, note: e.target.value })} />
                    <div style={{ display: 'flex', gap: 7, marginTop: 8, justifyContent: 'flex-end' }}>
                      <button className="secondary-button" onClick={() => setForm(null)}>취소</button>
                      <button className="primary-button" disabled={!form.note.trim()}
                        onClick={() => {
                          const n = form.note.trim();
                          if (!n) return;
                          if (form.kind === 'reject') onReject(d, n); else onReassign(d, n);
                          setForm(null);
                        }}>
                        {form.kind === 'reject' ? '거절 보내기' : '재배정 요청 보내기'}
                      </button>
                    </div>
                  </div>
                )}
              </>
            ) : (
              <footer style={{ justifyContent: 'flex-start', color: 'var(--muted)', fontSize: 11 }}>
                {d.responded_at ? `${d.responded_at.slice(0, 10)} 응답` : '응답할 수 없는 상태입니다'}
                {d.response_note ? ` · ${d.response_note}` : ''}
              </footer>
            )}
          </article>
        ))}
      </Panel>
    </>
  );
}

// ── 내 앱 ────────────────────────────────────────────────────────────────────
function AppsScreen({ list, state, onRetry, onPin, onRename, onOpen }: {
  list: PocketApp[]; state: Loaded<any>; onRetry: () => void;
  onPin: (a: PocketApp) => void; onRename: (a: PocketApp, n: string) => void;
  onOpen: (a: PocketApp) => void;
}) {
  const [editing, setEditing] = useState<{ id: string; name: string } | null>(null);
  const colors = ['blue', 'green', 'orange', 'violet'];
  return (
    <>
      <ScreenHead kicker="MY APPS" title="내 앱"
        description="수락한 앱입니다. 현재 사용자·조직 권한으로 실행되며 별도 로그인이 없습니다."
        chip={state.status !== 'ok'
          ? { label: '조회 불가', tone: 'danger' }
          : { label: `${list.length}개`, tone: list.length ? 'success' : 'muted' }} />
      <Panel kicker="POCKET" title="앱 주머니">
        {list.length === 0 ? (
          <EmptyOrError state={state.status} error={state.error} onRetry={onRetry}
            emptyText={<>수락한 앱이 없습니다. <b>받은 앱</b>에서 요청을 수락하면 여기에 담깁니다.</>} />
        ) : (
          <div className="app-pocket">
            {list.map((a, idx) => (
              <div key={a.pocket_id}>
                <i className={colors[idx % colors.length]} aria-hidden="true">
                  {a.display_name.slice(0, 2)}
                </i>
                <div>
                  {editing?.id === a.pocket_id ? (
                    <div style={{ display: 'flex', gap: 6 }}>
                      <input className="afs-input" value={editing.name} autoFocus
                        onChange={(e) => setEditing({ ...editing, name: e.target.value })}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' && editing.name.trim()) {
                            onRename(a, editing.name.trim()); setEditing(null);
                          }
                          if (e.key === 'Escape') setEditing(null);
                        }} />
                      <button className="secondary-button" style={{ minHeight: 32 }}
                        onClick={() => { if (editing.name.trim()) onRename(a, editing.name.trim()); setEditing(null); }}>
                        저장
                      </button>
                    </div>
                  ) : (
                    <>
                      <b>{a.display_name}</b>
                      <small>{a.release_id} · {a.accepted_at ? `${a.accepted_at.slice(0, 10)} 수락` : ''}</small>
                      {/* ★ [설계 §5.3] 「수락 후 MyAppPocket 에는 **실행, 세부 권한, 버전 변경,
                          전달 출처, 회수 상태**를 표시한다」 — 이전에는 이름·수락일뿐이어서
                          받은 사람은 누가 준 앱인지도, 회수됐는지도 알 수 없었다. */}
                      <div className="pocket-facts">
                        <span>전달 출처{' '}
                          <b>{a.source_user_id || '확인 불가'}
                            {a.source_dept_id ? ` · ${a.source_dept_id}` : ''}</b>
                        </span>
                        <span>버전{' '}
                          <b>{a.accepted_version ? `v${a.accepted_version}` : '미기록'}</b>
                        </span>
                        {a.version_changed && (
                          <span className="warn">
                            ⚠️ 게시된 버전이 v{a.current_version} 로 바뀌었습니다 — 다시 전달받아야
                            최신 앱을 씁니다.
                          </span>
                        )}
                        {(a.status === 'REVOKED' || a.delivery_status === 'REVOKED') && (
                          <span className="danger">
                            회수됨 — 이 앱은 실행할 수 없습니다.
                            {a.revoke_note ? ` 사유: ${a.revoke_note}` : ''}
                          </span>
                        )}
                      </div>
                      {/* 세부 권한 — 접어 둔다. 목록에서 전부 펼치면 무엇도 읽히지 않는다. */}
                      <details className="pocket-caps">
                        <summary>세부 권한 보기</summary>
                        {a.manifest_snapshot
                          ? <CapabilityManifestCard m={a.manifest_snapshot} />
                          : <div className="empty-note" style={{ margin: '8px 0 0' }}>
                              이 앱의 권한 기록을 찾지 못했습니다 — 전달 기록이 남아 있지 않습니다.
                            </div>}
                      </details>
                    </>
                  )}
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  {/* 실행 — 회수된 앱은 누를 수 없다. 이유를 위 카드가 이미 말한다. */}
                  <button className="secondary-button"
                    disabled={a.status === 'REVOKED' || a.delivery_status === 'REVOKED'}
                    onClick={() => onOpen(a)}>
                    실행
                  </button>
                  <button className="text-button" onClick={() => setEditing({ id: a.pocket_id, name: a.display_name })}>
                    이름 변경
                  </button>
                  <button className={`pin-button ${a.pinned ? 'on' : ''}`} onClick={() => onPin(a)}
                    aria-label={a.pinned ? '고정 해제' : '고정'} title={a.pinned ? '고정 해제' : '고정'}>
                    ★
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </Panel>
    </>
  );
}

// ── 사용자에게 전달 ──────────────────────────────────────────────────────────
/** [설계 §5.3 `/collaboration/deliver/:releaseId`]
 *
 * 「중앙은 **릴리스 확인 → 수신자 선택 → 권한 Manifest → 전달 검토** 4단 Wizard」.
 *
 * ⚠️ 첫 구현은 `앱 선택 → 받는 사람 → 전달 목적 → 전달` 이었다. 겉보기 4단이지만 **3단계가
 *   권한이 아니라 목적 입력**이어서, 보내는 사람은 무엇을 전달하는지(요구 권한·데이터 범위·
 *   금지 기능) 모른 채 보냈다. 조건을 못 보고 누르는 마법사는 설계의 요점을 잃는다.
 *   서버 `preflight` 를 붙여 3단계에서 **실제 Manifest** 를 읽는다.
 */
function DeliverScreen({ releaseIds, onSubmit }: {
  releaseIds: string[];
  onSubmit: (f: {
    release_id: string; recipient: string; purpose: string; expires_in_days: number;
  }) => void;
}) {
  const [f, setF] = useState({
    release_id: releaseIds[0] || '', recipient: '', purpose: '', expires_in_days: 14,
  });
  //: 3단계의 원천. 릴리스가 바뀌면 다시 읽는다.
  const [pre, setPre] = useState<Loaded<DeliveryPreflight>>(loading<DeliveryPreflight>());

  useEffect(() => {
    const rid = f.release_id.trim();
    if (!rid) { setPre(loading<DeliveryPreflight>()); return; }
    let alive = true;
    setPre(loading<DeliveryPreflight>());
    collaborationApi.preflight(rid)
      .then((r) => { if (alive) { setPre(ok(r)); setF((x) => ({ ...x, expires_in_days: r.default_expires_in_days || 14 })); } })
      .catch((e) => { if (alive) setPre(failed<DeliveryPreflight>(e)); });
    return () => { alive = false; };
  }, [f.release_id]);

  const p = pre.value;
  //: ⚠️ 전달 가능 여부는 **서버 판정**을 그대로 쓴다 — 화면에서 다시 판단하면 두 판정이 갈린다.
  const deliverable = pre.status === 'ok' && !!p?.deliverable;
  const steps = ['릴리스 확인', '수신자 선택', '권한 Manifest', '전달 검토'];
  //: 3단계(권한 Manifest)는 «읽었는가» 가 아니라 «읽을 수 있게 되었는가» 로 넘어간다 —
  //  읽음을 체크박스로 강요하면 사람은 체크만 하고 읽지 않는다.
  const step = !f.release_id ? 0
    : !(f.recipient.trim() && f.purpose.trim()) ? 1
      : pre.status !== 'ok' ? 2
        : 3;
  const ready = step === 3 && deliverable;

  return (
    <>
      <ScreenHead kicker="DELIVER" title="사용자에게 전달"
        description="지정한 한 사람에게 앱을 전달합니다. 부서 공유·전사 승격과는 다른 경로입니다."
        chip={{ label: ready ? '보낼 준비 완료' : '입력 중', tone: ready ? 'success' : 'data' }} />

      <ol className="step-line">
        {steps.map((s, i) => (
          <li key={s} className={i < step ? 'done' : i === step ? 'active' : ''}>
            <i aria-hidden="true">{i < step ? '✓' : i + 1}</i>
            <div><b>{s}</b><small>{i < step ? '완료' : i === step ? '진행 중' : '대기'}</small></div>
          </li>
        ))}
      </ol>

      <div className="delivery-grid">
        {/* ① 릴리스 확인 */}
        <Panel kicker="STEP 1 · RELEASE" title="릴리스 확인" className="release-card">
          <div style={{ paddingTop: 14 }}>
            <label className="field-label" htmlFor="rel">릴리스</label>
            {releaseIds.length > 0 ? (
              <select id="rel" className="afs-select" value={f.release_id}
                onChange={(e) => setF({ ...f, release_id: e.target.value })}>
                <option value="">— 선택 —</option>
                {releaseIds.map((r) => <option key={r} value={r}>{r}</option>)}
              </select>
            ) : (
              <input id="rel" className="afs-input" value={f.release_id} placeholder="release_id"
                onChange={(e) => setF({ ...f, release_id: e.target.value })} />
            )}
            {releaseIds.length === 0 && (
              <div className="empty-note" style={{ margin: '10px 0 0' }}>
                게시된 릴리스가 없습니다. 프로젝트를 완료해 릴리스를 게시하면 목록에 나타납니다.
              </div>
            )}
            <div className="release-facts">
              <div><span>버전</span>
                <b>{p?.release_version || (f.release_id ? '확인 중' : '—')}</b>
                <small>게시된 릴리스</small></div>
              <div><span>전달 방식</span><b>개인</b><small>한 사람에게</small></div>
              <div><span>권한 확대</span><b>없음</b><small>자료는 그대로</small></div>
            </div>
            {/* ⚠️ 차단 사유는 **누르기 전에** 보여 준다. 전에는 눌러야 알 수 있었다. */}
            {pre.status === 'ok' && !p?.deliverable && (
              <Banner tone="danger" title="이 릴리스는 전달할 수 없습니다"
                text={p?.blocked_reason || '사유를 확인하지 못했습니다.'} />
            )}
            {pre.status === 'error' && f.release_id && (
              <Banner tone="danger" title="릴리스를 확인하지 못했습니다"
                text={String((pre.error as any)?.message || pre.error
                  || '전달 조건을 읽지 못했습니다 — 0건이 아니라 조회 실패입니다.')} />
            )}
          </div>
        </Panel>

        <Panel kicker="STEP 2 · RECIPIENT" title="수신자 선택">
          <div style={{ padding: 18 }}>
            <label className="field-label" htmlFor="rcp">받는 사람 (사용자 ID)</label>
            <div className="search-field">
              <span aria-hidden="true">🔍</span>
              <input id="rcp" value={f.recipient} placeholder="예: hikwon@lsmnm.com"
                onChange={(e) => setF({ ...f, recipient: e.target.value })} />
            </div>

            <label className="field-label" htmlFor="pps">전달 목적 (필수)</label>
            <textarea id="pps" className="afs-textarea" value={f.purpose}
              placeholder="받는 사람이 수락 여부를 판단할 근거가 됩니다"
              onChange={(e) => setF({ ...f, purpose: e.target.value })} />

            <label className="field-label" htmlFor="exp">
              만료 (1~{p?.max_expires_in_days || 90}일)
            </label>
            <input id="exp" className="afs-input" type="number" min={1}
              max={p?.max_expires_in_days || 90} value={f.expires_in_days}
              onChange={(e) => setF({ ...f, expires_in_days: Number(e.target.value) || 1 })} />

            {/* ③ 권한 Manifest — 설계가 지정한 3단계. */}
            <div style={{ marginTop: 18, borderTop: '1px solid var(--line)', paddingTop: 14 }}>
              <div className="field-label" style={{ marginTop: 0 }}>STEP 3 · 권한 Manifest</div>
              {pre.status === 'ok' && p?.manifest_snapshot
                ? <CapabilityManifestCard m={p.manifest_snapshot} />
                : (
                  <div className="empty-note" style={{ margin: '8px 0 0' }}>
                    {f.release_id
                      ? (pre.status === 'error'
                        ? '권한 Manifest 를 읽지 못했습니다 — 무엇을 전달하는지 확인할 수 없으므로 전달할 수 없습니다.'
                        : '권한 Manifest 를 읽는 중입니다.')
                      : '릴리스를 먼저 선택하면 이 앱이 요구하는 권한을 표시합니다.'}
                  </div>
                )}
            </div>

            {/* ④ 전달 검토 — 설계: 최종 CTA 는 **대상·버전·만료·영향 요약과 같은 시야**에 둔다. */}
            <div className="permission-summary" style={{ marginTop: 16 }}>
              <b>이 조건으로 전달합니다</b>
              <span>
                {f.recipient || '수신자 미지정'} · {f.release_id || '릴리스 미지정'}
                {p?.release_version ? ` v${p.release_version}` : ''} · {f.expires_in_days}일 후 만료
              </span>
              <small>
                수락하면 상대의 «내 앱» 에 앱 1개가 생깁니다. 데이터 접근 범위는 변하지 않습니다 —
                상대가 원래 볼 수 없던 자료는 이 앱에서도 보이지 않습니다.
                {p?.manifest_fingerprint
                  ? ` Manifest 지문 ${p.manifest_fingerprint.slice(0, 12)}.`
                  : ''}
              </small>
            </div>

            <button className="primary-wide" disabled={!ready} onClick={() => onSubmit(f)}>
              이 조건으로 사용자에게 전달
            </button>
            {!ready && (
              <div className="empty-note" style={{ margin: '8px 0 0' }}>
                {step < 1 ? '릴리스를 선택하십시오.'
                  : step < 2 ? '받는 사람과 전달 목적을 입력하십시오.'
                    : !deliverable && pre.status === 'ok'
                      ? '위 사유로 이 릴리스는 전달할 수 없습니다.'
                      : '권한 Manifest 를 확인하는 중입니다.'}
              </div>
            )}
          </div>
        </Panel>
      </div>
    </>
  );
}

// ── 보낸 요청 ────────────────────────────────────────────────────────────────
function SentScreen({ list, state, onRetry, onRevoke }: {
  list: Delivery[]; state: Loaded<any>; onRetry: () => void;
  onRevoke: (d: Delivery, reason: string) => void;
}) {
  const [form, setForm] = useState<{ id: string; reason: string } | null>(null);
  const accepted = list.filter((d) => d.status === 'ACCEPTED').length;
  return (
    <>
      <ScreenHead kicker="SENT" title="보낸 요청"
        description="내가 보낸 전달과 상대의 응답 상태입니다. 수락된 앱을 회수하면 상대 주머니에 회수 사실이 남습니다."
        chip={state.status !== 'ok'
          ? { label: '조회 불가', tone: 'danger' }
          : { label: `수락 ${accepted} / 전체 ${list.length}`, tone: 'data' }} />
      <Panel kicker="OUTBOX" title="전달 이력">
        {list.length === 0 ? (
          <EmptyOrError state={state.status} error={state.error} onRetry={onRetry}
            emptyText="보낸 전달 요청이 없습니다." />
        ) : (
          <div className="sent-requests">
            {list.map((d) => (
              <div key={d.delivery_id}>
                <i className={DOT[d.status] || 'off'} aria-hidden="true" />
                <div>
                  <b>{d.release_id} → {d.recipient_user_id}</b>
                  <small>
                    {d.purpose}
                    {d.response_note ? ` · 응답: ${d.response_note}` : ''}
                  </small>
                  {form?.id === d.delivery_id && (
                    <div style={{ marginTop: 8 }}>
                      <label className="field-label" htmlFor={`rv-${d.delivery_id}`}>
                        회수 사유 (받는 사람에게 남습니다)
                      </label>
                      <textarea id={`rv-${d.delivery_id}`} className="afs-textarea" value={form.reason}
                        onChange={(e) => setForm({ ...form, reason: e.target.value })} />
                      <div style={{ display: 'flex', gap: 7, marginTop: 8 }}>
                        <button className="secondary-button" onClick={() => setForm(null)}>취소</button>
                        <button className="danger-ghost" disabled={!form.reason.trim()}
                          onClick={() => { onRevoke(d, form.reason.trim()); setForm(null); }}>
                          회수하기
                        </button>
                      </div>
                    </div>
                  )}
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <StatusChip status={d.status} />
                  {d.can_revoke && form?.id !== d.delivery_id && (
                    <button className="text-button" onClick={() => setForm({ id: d.delivery_id, reason: '' })}>
                      회수
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </Panel>
    </>
  );
}
