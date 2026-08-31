// [이관 4/10] 조직·권한 — 부서는 «기준정보»다
//
// 개편하면 새 버전이 생기고 구판은 이력으로 보존된다(과거 산출물의 소유 부서 해석이 깨지면
// 안 되기 때문). 폐지도 물리 삭제가 아니라 soft-retire 다.
//
// ★★ 이 화면에서 가장 중요한 값은 **부서의 조직 범위(`scope_node_id`)** 다. 이 값이 비면
//   그 부서 사람들에게 조직 소유 자료(지식팩·참고문서·기준정보)가 **하나도 보이지 않는다**
//   (관문 A: 미지정 = 비노출). 그래서 미지정을 조용히 두지 않고 경고로 세운다.
//
// ⚠️ 종전 구현에서 제거한 것:
//   · `prompt()` 6곳 — 특히 **조직 범위를 prompt 로 입력**받고 있었다. 오타 하나로 부서 전체가
//     자료를 못 보게 되는데, 브라우저 대화상자는 오타를 잡아 줄 방법이 없다. 이미 쓰이고 있는
//     값에서 **고르게** 바꿨다(새 값도 화면 안 입력으로 넣을 수 있다).
//   · `confirm()` 2곳 → `ConfirmInline`(키보드·스크린리더·스타일 모두 대응)
//   · 자체 `API_BASE_URL` 선언(저장소에서 열 번째)과 직접 fetch → `lib/orgApi.ts`
//   · 실패를 «없음»으로 쓰던 코드 — 403 상태에서도 «등록된 부서가 없습니다» 가 떴다.
//   · `asUser` 임시 오버라이드 입력창 — 상단 바의 활동 사용자 선택이 이미 그 일을 한다.
//     같은 일을 두 곳에서 하면 둘이 어긋나고, «지금 누구로 보고 있는가»가 두 답을 갖는다.
//   · 사용자마다 부서 수만큼(12개) 셀렉트를 그리던 역할 편집 — 한 사용자를 골라 편집한다.
import { useCallback, useEffect, useMemo, useState } from 'react';

import {
  ConfirmInline, EvidenceStrip, FormField, FoundationList, FoundationToolbar, VersionHistory,
  useConfirm, type FoundationRow,
} from '../design/DataFoundationShell';
import { EmptyOrError, Metric, failed, loading, ok, type Loaded } from '../design/DataState';
import { useLatestOnly } from '../design/useLatestOnly';
import { HubDialog } from '../design/HubDialog';
import { Banner, HubShell, Panel, ScreenHead, type RailItem } from '../design/HubShell';
import { JarvisRail } from '../design/JarvisRail';
import { DEPT_ROLE_KO, deptRoleKo, orgStatusKo } from '../design/terms';
import { reportRequestFailure, reportRequestSuccess } from '../lib/backendHealth';
import { errorTitle } from '../lib/closedLoopFetch';
import { setEnterpriseContext } from '../lib/api';
import { orgApi, type Dept, type MyScope, type OrgEdge, type OrgUser } from '../lib/orgApi';
import { fetchOrgNodes, type FlatNode } from '../lib/governanceApi';

type View = 'chart' | 'graph' | 'users' | 'history' | 'myscope';

const MODULE: Record<View, { kicker: string; title: string; subtitle: string; desc: string }> = {
  chart: {
    kicker: 'ORG CHART', title: '조직도',
    subtitle: '부서는 기준정보입니다. 개편하면 새 버전이 됩니다.',
    desc: '부서의 조직 범위가 자료 노출을 정합니다. 범위가 비면 그 부서에는 아무 자료도 보이지 않습니다.',
  },
  //: [설계 §5.8] 「기본 트리와 **의미 그래프를 탭으로 구분**한다. 트리는 탐색, 그래프는
  //  소유/운영/공유/연결 관계 편집에 사용한다.」 둘을 한 화면에 겹치면 «보러 왔는데 고치게»
  //  되고, 관계 편집은 되돌리기 어렵다.
  graph: {
    kicker: 'STRUCTURE', title: '의미 그래프',
    subtitle: '조직 사이의 관계입니다. 트리는 탐색용, 여기는 관계용입니다.',
    desc: '권한 상속은 OPERATING_PARENT 만 따릅니다 — 소유·공유·연결은 권한을 물려주지 않습니다.',
  },
  users: {
    kicker: 'PEOPLE', title: '사용자',
    subtitle: '계정의 권한과 부서 역할을 관리합니다.',
    desc: '권한 표식은 전사 범위를 넓힙니다. 부서 역할은 그 부서 안에서만 유효하고 하위로 상속됩니다.',
  },
  history: {
    kicker: 'LINEAGE', title: '개편 이력',
    subtitle: '부서가 언제 어떻게 바뀌었는지 봅니다.',
    desc: '구판이 보존되므로 과거 산출물의 소유 부서를 계속 해석할 수 있습니다.',
  },
  myscope: {
    kicker: 'MY ACCESS', title: '내 권한',
    subtitle: '지금 내가 무엇을 볼 수 있는지 그 근거와 함께 봅니다.',
    desc: '«왜 안 보이는가»의 답이 여기 있습니다. 부족하면 무엇을 요청해야 하는지도 함께 적습니다.',
  },
};

/** 권한 표식 — 무엇을 넓히는지 한 줄로 말한다. 표식 이름만으로는 결과를 알 수 없다. */
const FLAGS: { key: 'is_admin' | 'is_executive' | 'is_data_admin'; label: string; what: string }[] = [
  { key: 'is_admin', label: '관리자', what: '조직 편집·표준 관리·전사 실행 전부' },
  { key: 'is_executive', label: '경영진', what: '전 부서 열람과 전사 실행. 조직 편집은 불가' },
  { key: 'is_data_admin', label: '데이터 관리자', what: '표준·카탈로그 전권과 메타 전사 열람' },
];

export function OrgChartPanel({ onClose, page = false }: { onClose: () => void; page?: boolean }) {
  //: [설계 §6.1] 늦게 온 응답을 버리는 표 — 다른 것을 고른 뒤 옛 응답이 그려지지 않게.
  const claim = useLatestOnly();
  const [view, setView] = useState<View>('chart');
  const [flat, setFlat] = useState<Loaded<Dept[]>>(loading<Dept[]>());
  const [users, setUsers] = useState<Loaded<OrgUser[]>>(loading<OrgUser[]>());
  const [hidden, setHidden] = useState<{ present: boolean; count: number | null }>(
    { present: false, count: null });
  const [me, setMe] = useState<Loaded<MyScope | null>>(loading<MyScope | null>());
  const [selDept, setSelDept] = useState('');
  const [selUser, setSelUser] = useState('');
  const [hist, setHist] = useState<Loaded<Dept[]>>(ok<Dept[]>([]));
  const [search, setSearch] = useState('');
  const [deptSearch, setDeptSearch] = useState('');
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<{ msg: string; status?: number } | null>(null);
  const [flash, setFlash] = useState<string | null>(null);

  // 화면 안 편집 폼 — `prompt()` 를 쓰지 않는다.
  const [deptForm, setDeptForm] = useState({ name: '', parent: '' });
  const [scopeDraft, setScopeDraft] = useState('');
  const [scopeNodes, setScopeNodes] = useState<FlatNode[]>([]);
  const [userForm, setUserForm] = useState({ id: '', name: '' });

  const retire = useConfirm<Dept>();
  const seed = useConfirm<string>();

  const load = useCallback(async () => {
    setFlat(loading<Dept[]>());
    setUsers(loading<OrgUser[]>()); setMe(loading<MyScope | null>());
    // ⚠️ 세 조회를 **따로** 담는다. 하나가 실패했다고 나머지를 «없음»으로 만들지 않는다.
    // ★ [2026-08-05] 종전에는 `orgApi.tree()` 도 같이 불러 `tree` 상태에 담았지만 **화면에서
    //   한 번도 읽지 않았다**(`flat` 으로 그린다). 결과를 버리는 호출이라 지웠다 — 그 호출도
    //   권한 판정을 타므로, 쓰지 않는 조회는 실패했을 때 «이유 없는 오류» 만 늘린다.
    //   트리 표시를 넣을 때 다시 부르면 된다.
    const [d, u, m, n] = await Promise.allSettled([
      orgApi.departments(), orgApi.users(), orgApi.me(), fetchOrgNodes(),
    ]);
    const asLoaded = <T,>(r: PromiseSettledResult<{ rows: T[]; blockedReason: string }>) => {
      if (r.status !== 'fulfilled') {
        // 401/403 은 통제가 작동한 것이므로 «서버 이상»으로 세지 않는다.
        reportRequestFailure((r.reason as any)?.status);
        return failed<T[]>(r.reason);
      }
      reportRequestSuccess();
      return r.value.blockedReason
        ? { status: 'forbidden' as const, value: null, error: r.value.blockedReason, httpStatus: 403 }
        : ok(r.value.rows);
    };
    setFlat(asLoaded<Dept>(d));
    setUsers(asLoaded<OrgUser>(u));
    if (u.status === 'fulfilled') {
      setHidden({ present: u.value.hiddenPresent, count: u.value.hiddenCount });
    } else setHidden({ present: false, count: null });
    setMe(m.status === 'fulfilled' ? ok(m.value) : failed<MyScope | null>(m.reason));
    setScopeNodes(n.status === 'fulfilled' ? n.value : []);
  }, []);

  const loadHistory = useCallback(async (deptId: string) => {
    if (!deptId) { setHist(ok<Dept[]>([])); return; }
    const isCurrent = claim();   // §6.1 — 요청 직전에 표를 뽑는다
    setHist(loading<Dept[]>());
    try {
      const rows = await orgApi.deptHistory(deptId);
      // ★ [§6.1] 부서를 연달아 고르면 다른 부서의 개편 이력이 그려질 수 있다.
      if (!isCurrent()) return;
      setHist(ok(rows)); reportRequestSuccess();
    } catch (e: any) {
      if (!isCurrent()) return;
      setHist(failed<Dept[]>(e)); reportRequestFailure(e?.status);
    }
  }, [claim]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    const onUser = () => {
      setSelDept(''); setSelUser(''); setHist(ok<Dept[]>([])); setErr(null); setFlash(null);
      load();
    };
    window.addEventListener('factory:acting-user-changed', onUser);
    return () => window.removeEventListener('factory:acting-user-changed', onUser);
  }, [load]);

  const run = async (label: string, fn: () => Promise<unknown>, success: string) => {
    setBusy(label); setErr(null); setFlash(null);
    try {
      await fn(); reportRequestSuccess(); setFlash(success);
      await load();
      if (selDept) await loadHistory(selDept);
      return true;
    } catch (e: any) {
      reportRequestFailure(e?.status); setErr({ msg: e?.message || String(e), status: e?.status });
      return false;
    } finally { setBusy(null); }
  };

  // ── 파생 ────────────────────────────────────────────────────────────────
  const deptRows = flat.value || [];
  const userRows = users.value || [];
  const scope = me.value;
  const canEdit = Boolean(scope?.can_edit_org || scope?.unrestricted);
  const selectedDept = deptRows.find((d) => d.dept_id === selDept) || null;
  const selectedUser = userRows.find((u) => u.user_id === selUser) || null;
  const unscoped = deptRows.filter((d) => !String(d.scope_node_id || '').trim());

  /** 내부 `scope_node_id` 는 값으로만 쓰고 화면에는 조직명을 표시한다. */
  const scopeLabel = useCallback((nodeId: string) => {
    if (!nodeId) return '미지정';
    return scopeNodes.find((n) => n.node_id === nodeId)?.label || '연결된 조직';
  }, [scopeNodes]);

  useEffect(() => { setScopeDraft(selectedDept?.scope_node_id || ''); }, [selDept, selectedDept]);

  /** 부서 검색. ⚠️ 종전에는 부서 탭에 **동작하지 않는 검색창**이 놓여 있었다(빈 `onSearch`).
   *  입력할 수 있게 생긴 칸이 아무 일도 하지 않으면 사용자는 자기가 잘못 쳤다고 생각한다. */
  const filteredDepts = useMemo(() => {
    const q = deptSearch.trim().toLowerCase();
    if (!q) return deptRows;
    return deptRows.filter((d) => `${d.name_ko} ${scopeLabel(d.scope_node_id || '')}`
      .toLowerCase().includes(q));
  }, [deptRows, deptSearch, scopeLabel]);

  const filteredUsers = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return userRows;
    return userRows.filter((u) => `${u.display_name} ${u.user_id} ${deptRows.find((d) => d.dept_id === u.primary_dept_id)?.name_ko || ''}`
      .toLowerCase().includes(q));
  }, [userRows, search, deptRows]);

  const railItems: RailItem[] = [
    { id: 'chart', label: '조직도', hint: '부서와 조직 범위', icon: 'orgtree',
      // 범위 미지정은 **처리해야 할 일**이다 — 이 배지는 대기 건수의 뜻과 맞다.
      count: flat.status === 'ok' && unscoped.length ? unscoped.length : undefined,
      countLabel: `조직 범위 미지정 부서 ${unscoped.length}개` },
    { id: 'graph', label: '의미 그래프', hint: '소유·운영·공유·연결', icon: 'flow' },
    { id: 'users', label: '사용자', hint: '권한과 부서 역할', icon: 'people' },
    { id: 'history', label: '개편 이력', hint: '구판은 보존된다', icon: 'revise' },
    { id: 'myscope', label: '내 권한', hint: '왜 안 보이는가', icon: 'shield' },
  ];

  // ★★ 완료 조건 ②: 권한이 있는 사람에게만 행동을 안내한다.
  const jarvisActions = canEdit
    ? ['부서 추가', '조직 범위 지정', '권한 표식 변경', '부서 역할 지정']
    : [];
  const jarvisContext = {
    current_module: `org/${view}`,
    selected_object_type: view === 'users' ? 'org_user' : 'org_department',
    selected_object_id: view === 'users' ? (selectedUser?.user_id || '') : (selectedDept?.dept_id || ''),
    object_snapshot: view === 'users'
      ? (selectedUser ? { user_id: selectedUser.user_id, dept: selectedUser.primary_dept_id }
        : { load_status: users.status, total: userRows.length })
      : (selectedDept ? { dept_id: selectedDept.dept_id, scope_node_id: selectedDept.scope_node_id,
        version: selectedDept.version }
        : { load_status: flat.status, total: deptRows.length, unscoped: unscoped.length }),
    available_actions: jarvisActions,
    evidence_refs: [],
  };
  const jarvisTitle = view === 'users'
    ? (selectedUser ? selectedUser.display_name
      : users.status === 'ok' ? '사용자' : '조회 불가')
    : (selectedDept ? selectedDept.name_ko
      : flat.status === 'ok' ? MODULE[view].title : '조회 불가');
  const jarvisDesc = view === 'users'
    ? (selectedUser
      ? `${selectedUser.user_id} · ${deptRows.find((d) => d.dept_id === selectedUser.primary_dept_id)?.name_ko || '부서 미배정'}`
      : users.status === 'ok' ? '왼쪽 목록에서 사람을 고르면 그 계정을 문맥으로 씁니다.'
        : '사용자 명부를 가져오지 못했습니다 — «없다»가 아닙니다.')
    : (selectedDept
      ? `v${selectedDept.version} · ${scopeLabel(selectedDept.scope_node_id || '')}`
      : flat.status === 'ok'
        ? (unscoped.length
          ? `조직 범위가 없는 부서가 ${unscoped.length}개 있습니다 — 그 부서에는 자료가 보이지 않습니다.`
          : '부서를 고르면 그 부서를 문맥으로 씁니다.')
        : '조직도를 가져오지 못했습니다 — «없다»가 아닙니다.');

  const deptListRows: FoundationRow[] = filteredDepts.map((d) => ({
    id: d.dept_id,
    // ⚠️ 제목을 공백으로 들여쓰지 않는다 — 목록 아바타가 제목 앞 두 글자를 쓰므로 **빈 원**이
    //   된다(실제로 본사만 글자가 있었고 나머지는 다 빈 원이었다).
    //   더 나쁜 것은 그때 넣은 들여쓰기가 일반 공백이 아니라 NBSP 였다는 점이다 — 눈에도
    //   안 보이고 `trim()` 으로도 안 잡히는 문자가 화면 결함의 원인이었다.
    //   계층은 메타에 «상위» 로 적는다.
    title: d.name_ko,
    meta: `v${d.version} · ${orgStatusKo(d.status)}`
      + (d.parent_id
        ? ` · 상위 ${deptRows.find((x) => x.dept_id === d.parent_id)?.name_ko || '확인 불가'}`
        : ' · 최상위'),
    chip: String(d.scope_node_id || '').trim()
      ? { label: scopeLabel(d.scope_node_id), tone: 'success' }
      // ⚠️ 미지정을 조용히 두지 않는다. 이 값이 비면 그 부서에는 자료가 하나도 안 보인다.
      : { label: '범위 미지정', tone: 'warn' },
  }));

  const userListRows: FoundationRow[] = filteredUsers.map((u) => {
    const marks = FLAGS.filter((f) => u[f.key]).map((f) => f.label);
    return {
      id: u.user_id,
      title: u.display_name || u.user_id,
      meta: `${u.user_id} · ${deptRows.find((d) => d.dept_id === u.primary_dept_id)?.name_ko || '부서 미배정'}`
        + (marks.length ? ` · ${marks.join('·')}` : ''),
      chip: u.status && u.status !== 'active'
        ? { label: orgStatusKo(u.status), tone: 'danger' }
        : marks.length ? { label: marks[0], tone: 'data' }
          : { label: `역할 ${Object.keys(u.roles || {}).length}개`, tone: 'muted' },
    };
  });

  return (
    <HubDialog label="조직·권한 — 부서와 계정, 그리고 무엇이 보이는지" onClose={onClose} page={page}>
      {!page && <div className="afs-dialog-bar">
        <b>조직·권한</b>
        <span>부서의 조직 범위가 자료 노출을 정합니다</span>
        <div className="bar-actions">
          {busy && <span className="busy">{busy} 중…</span>}
          <button className="secondary-button" onClick={onClose}>
            닫기 <span aria-hidden="true" style={{ opacity: .7 }}>(Esc)</span>
          </button>
        </div>
      </div>}

      <div className="afs-dialog-body">
        <HubShell layoutClassName={page ? 'product-page-shell' : ''}
          kicker={MODULE[view].kicker} title={MODULE[view].title} subtitle={MODULE[view].subtitle}
          items={railItems} activeId={view} onSelect={(id) => setView(id as View)}
          footer={
            <div className="inheritance-card">
              <span>SCOPE</span>
              <b>범위가 비면 아무것도 보이지 않습니다</b>
              <p>부서에 조직 범위가 없으면 그 부서 사람들에게 조직 소유 자료가 하나도 보이지 않습니다.</p>
            </div>
          }
          jarvis={<JarvisRail contextTitle={jarvisTitle} contextDescription={jarvisDesc}
            context={jarvisContext}
            evidence={selectedDept && view !== 'users' ? [
              { label: '버전', value: `v${selectedDept.version}` },
              { label: '조직 범위', value: scopeLabel(selectedDept.scope_node_id || '') },
            ] : selectedUser && view === 'users' ? [
              { label: '계정', value: selectedUser.user_id },
              { label: '소속', value: deptRows.find((d) => d.dept_id === selectedUser.primary_dept_id)?.name_ko || '미배정' },
              { label: '상태', value: orgStatusKo(selectedUser.status || 'active') },
            ] : []}
            quickQuestions={[
              '이 부서 사람들에게는 무엇이 보입니까?',
              '조직 범위를 비워 두면 어떻게 됩니까?',
              '이 권한 표식은 무엇을 넓힙니까?',
            ]} />}
        >
          {err && <Banner tone="error" title={errorTitle(err.status)}>{err.msg}</Banner>}
          {flash && <Banner tone="info">{flash}</Banner>}
          {/* 서버가 만든 안내문 — «왜 안 보이는가»의 답이므로 화면 위쪽에 그대로 세운다. */}
          {scope?.access_note && (() => {
            // ⚠️ 서버의 안내문은 `**강조**` 마크다운을 쓴다. 그대로 그리면 화면에 별표가
            //   보인다(실측). 렌더러를 들이지 않고 **첫 강조를 제목으로** 올린다 —
            //   그 강조가 실제로 «무슨 일인지»를 말하는 문장이기 때문이다.
            const m = scope.access_note.match(/^\s*\*\*(.+?)\*\*\s*(.*)$/s);
            const plain = (s: string) => s.replace(/\*\*/g, '').trim();
            return m
              ? <Banner tone="warn" title={plain(m[1])}>{plain(m[2])}</Banner>
              : <Banner tone="warn">{plain(scope.access_note)}</Banner>;
          })()}
          {hidden.present && view === 'users' && (
            <Banner tone="warn">
              {hidden.count === null
                ? '읽을 수 있는 부서 밖의 인원은 표시하지 않았습니다 — 현재 조직 범위 인원만 표시 중입니다.'
                : `읽을 수 있는 부서 밖의 인원 ${hidden.count}명은 표시하지 않았습니다.`}
            </Banner>
          )}

          <ScreenHead kicker={MODULE[view].kicker} title={MODULE[view].title}
            description={MODULE[view].desc}
            chip={flat.status !== 'ok'
              ? flat.status === 'loading'
                ? { label: '확인 중', tone: 'muted' }
                : { label: flat.status === 'forbidden' ? '접근 불가' : '조회 불가', tone: 'danger' }
              : unscoped.length
                ? { label: `범위 미지정 ${unscoped.length}개`, tone: 'warn' }
                : { label: `부서 ${deptRows.length}개`, tone: 'data' }} />

          <div className="metric-row">
            <Metric label="부서" state={flat.status}
              value={flat.status === 'ok' ? deptRows.length : null} hint="운영 중인 부서" />
            {/* ⚠️ 여기서 0 은 «좋다»는 뜻이다(전부 지정됨). 그래서 0 을 숨기지 않는다. */}
            <Metric label="조직 범위 미지정" state={flat.status}
              value={flat.status === 'ok' ? unscoped.length : null}
              hint={unscoped.length ? '이 부서에는 자료가 보이지 않습니다' : '모든 부서에 범위가 있습니다'} />
            <Metric label="사용자" state={users.status}
              value={users.status === 'ok' ? userRows.length : null}
              notes={{ empty: '표시할 인원 없음' }}
              hint={hidden.present ? '범위 밖 인원은 제외' : '전체'} />
            <Metric label="내 읽기 부서" state={me.status}
              value={scope ? (scope.unrestricted ? '전체' : scope.readable_dept_ids.length) : null}
              notes={{ loading: '권한 조회 중', error: '권한 조회 불가',
                forbidden: '권한 조회 불가', empty: '배정된 부서 없음' }} />
          </div>

          {view === 'chart' && (
            <>
              <FoundationToolbar search={deptSearch} onSearch={setDeptSearch}
                placeholder="부서명·조직 범위로 찾기"
                actions={canEdit ? (
                  <button className="secondary-button" disabled={!!busy}
                    onClick={() => seed.ask('all')}>부서 시드</button>
                ) : undefined}
                hint={flat.status !== 'ok' ? undefined
                  : canEdit
                    ? '개편은 새 버전이 되고 구판은 이력으로 남습니다. 폐지는 물리 삭제가 아닙니다.'
                    : '조직 편집 권한이 없어 조회만 가능합니다 — 변경은 관리자에게 요청하십시오.'} />

              <ConfirmInline open={seed.open}
                title="코드에 하드코딩된 부서를 기준정보로 적재합니다"
                body={<>멱등 동작이며 <b>기존 부서는 건드리지 않습니다.</b> 조직 범위는 부서별로
                  따로 지정해야 합니다 — 시드만으로는 자료가 보이지 않습니다.</>}
                confirmLabel="시드 실행" danger={false}
                onConfirm={() => seed.run(() => run('부서 시드', orgApi.seedDepartments,
                  '부서를 적재했습니다. 조직 범위는 부서별로 지정하십시오.'))}
                onCancel={seed.cancel} />

              {/* ★ [설계 §6.5] 삭제는 확인 Sheet 대상이다. */}
              <ConfirmInline open={retire.open}
                title={`'${retire.target?.name_ko || ''}' 부서를 폐지합니다`}
                changes={<>물리 삭제가 아니라 <b>폐지 표시</b>입니다 — 구판은 이력으로 남고
                  과거 산출물의 소유 부서 해석은 유지됩니다.</>}
                affects={<>이 부서에 배정된 사람들은 <b>읽을 수 있는 범위를 잃습니다.</b>
                  {users.status === 'ok'
                    ? ` 이 부서 소속 ${userRows.filter((u) => u.primary_dept_id === retire.target?.dept_id).length}명.`
                    : ' 소속 인원을 확인하지 못했습니다(0명이 아닙니다).'}</>}
                reversible={<>구판이 남으므로 같은 부서를 다시 만들 수 있지만, 그 사이 범위를
                  잃은 사람들의 조회 실패는 되돌아오지 않습니다.</>}
                approval="조직 편집 권한이 필요합니다."
                confirmLabel="폐지"
                onConfirm={() => retire.run((d) => run('폐지', () => orgApi.retireDept(d.dept_id),
                  `'${d.name_ko}' 를 폐지했습니다. 구판은 이력으로 남습니다.`))}
                onCancel={retire.cancel} />

              <div className="inbox-layout">
                <FoundationList state={flat} rows={deptListRows} selectedId={selDept}
                  onSelect={(id) => { setSelDept(id); loadHistory(id); }} onRetry={load}
                  kicker="DEPARTMENTS" title="부서"
                  emptyText={<>등록된 부서가 없습니다. 부서가 없으면 조직 범위 필터가 전부
                    무효이며 기존과 같이 동작합니다.</>} />

                <Panel kicker="DEPARTMENT" title={selectedDept ? selectedDept.name_ko : '부서 상세'}>
                  {!selDept ? (
                    <div className="empty-note">왼쪽에서 부서를 선택하십시오.</div>
                  ) : !selectedDept ? (
                    <div className="empty-note">이 부서를 목록에서 찾지 못했습니다.</div>
                  ) : (
                    <div style={{ padding: '0 14px 14px' }}>
                      <EvidenceStrip items={[
                        { label: '버전', value: `v${selectedDept.version}` },
                        { label: '상태', value: orgStatusKo(selectedDept.status) },
                      ]} note="개편은 구판을 지우지 않습니다 — 과거 산출물의 소유 부서가 유지됩니다." />

                      {!String(selectedDept.scope_node_id || '').trim() && (
                        <Banner tone="warn" title="조직 범위가 지정되지 않았습니다">
                          이 부서에 배정된 사람들에게는 조직 소유 자료가 <b>하나도 보이지 않습니다.</b>
                          비어 있는 것이 «전사 공개»를 뜻하지 않습니다.
                        </Banner>
                      )}

                      {/* ★ 상단의 회사 문맥 버튼은 이 화면을 연다. 따라서 여기서 조직을
                          고른 뒤 실제 실행 문맥으로 전환할 행동이 반드시 있어야 한다.
                          조직 정본을 편집하는 «적용»과 사용자의 조회 문맥을 바꾸는 이 행동은
                          서로 다른 일이다. 범위가 비면 D-014에 따라 전환하지 않는다. */}
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8,
                        margin: '10px 0 14px', flexWrap: 'wrap' }}>
                        <button className="secondary-button"
                          disabled={!String(selectedDept.scope_node_id || '').trim()}
                          onClick={() => {
                            const scopeNodeId = String(selectedDept.scope_node_id || '').trim();
                            if (!scopeNodeId) return;
                            setEnterpriseContext({ scopeNodeId });
                            onClose();
                            window.location.reload();
                          }}>
                          이 조직으로 전환
                        </button>
                        <span className="hint-line" style={{ margin: 0 }}>
                          선택하면 모든 화면이 이 조직 범위의 자료를 다시 조회합니다.
                        </span>
                      </div>

                      {canEdit ? (
                        <FormField label="조직 범위"
                          hint="회사 구성에 등록된 조직에서 고릅니다. 개정이므로 새 버전이 됩니다.">
                          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                            <select className="afs-select" style={{ maxWidth: 220 }}
                              value={scopeDraft}
                              onChange={(e) => setScopeDraft(e.target.value)}>
                              <option value="">미지정</option>
                              {scopeNodes.map((n) => <option key={n.node_id} value={n.node_id}>
                                {'　'.repeat(n.depth)}{n.label}
                              </option>)}
                            </select>
                            <button className="primary-button" disabled={!!busy
                              || scopeDraft.trim() === (selectedDept.scope_node_id || '')}
                              onClick={() => run('조직 범위 지정',
                                () => orgApi.updateDept(selectedDept.dept_id,
                                  { scope_node_id: scopeDraft.trim() }),
                                scopeDraft.trim()
                                  ? `'${selectedDept.name_ko}' 의 조직 범위를 «${scopeLabel(scopeDraft.trim())}» 로 지정했습니다.`
                                  : `'${selectedDept.name_ko}' 의 조직 범위를 비웠습니다 — 이 부서에는 자료가 보이지 않습니다.`)}>
                              적용
                            </button>
                          </div>
                        </FormField>
                      ) : (
                        <p className="hint-line">
                          조직 범위: <b>{scopeLabel(selectedDept.scope_node_id || '')}</b>
                        </p>
                      )}

                      {canEdit && (
                        <div style={{ display: 'flex', gap: 7, marginTop: 12, flexWrap: 'wrap' }}>
                          <button className="danger-ghost" disabled={!!busy}
                            onClick={() => retire.ask(selectedDept)}>부서 폐지</button>
                        </div>
                      )}
                    </div>
                  )}
                </Panel>
              </div>

              {canEdit && (
                <Panel kicker="NEW" title="부서 추가" className="afs-mt">
                  <div style={{ padding: 14, display: 'grid', gap: 10 }}>
                    <FormField label="부서명" required>
                      <input className="afs-input" value={deptForm.name}
                        onChange={(e) => setDeptForm({ ...deptForm, name: e.target.value })}
                        placeholder="예: 품질보증" />
                    </FormField>
                    <FormField label="상위 부서" hint="비우면 최상위가 됩니다.">
                      <select className="afs-select" value={deptForm.parent}
                        onChange={(e) => setDeptForm({ ...deptForm, parent: e.target.value })}>
                        <option value="">(최상위)</option>
                        {deptRows.map((d) => (
                          <option key={d.dept_id} value={d.dept_id}>{d.name_ko}</option>
                        ))}
                      </select>
                    </FormField>
                    <div>
                      <button className="primary-button"
                        disabled={!!busy || !deptForm.name.trim()}
                        onClick={async () => {
                          const okDone = await run('부서 추가', () => orgApi.createDept({
                            name_ko: deptForm.name.trim(),
                            parent_id: deptForm.parent,
                          }), `'${deptForm.name.trim()}' 부서를 만들었습니다. 조직 범위를 지정해야 자료가 보입니다.`);
                          if (okDone) setDeptForm({ name: '', parent: '' });
                        }}>부서 만들기</button>
                    </div>
                  </div>
                </Panel>
              )}
            </>
          )}

          {view === 'graph' && <StructureGraph scopeNodes={scopeNodes} />}

          {view === 'users' && (
            <>
              <FoundationToolbar search={search} onSearch={setSearch}
                placeholder="이름·계정·부서로 찾기"
                hint={users.status !== 'ok' ? undefined
                  : canEdit
                    ? '권한 표식은 전사 범위를 넓힙니다. 부서 역할은 그 부서와 하위에서만 유효합니다.'
                    : '조직 편집 권한이 없어 조회만 가능합니다 — 변경은 관리자에게 요청하십시오.'} />

              <div className="inbox-layout">
                <FoundationList state={users} rows={userListRows} selectedId={selUser}
                  onSelect={setSelUser} onRetry={load}
                  kicker="PEOPLE" title="사용자"
                  emptyText={search
                    ? <>«{search}» 와 일치하는 사람이 없습니다.</>
                    : <>표시할 인원이 없습니다. 사용자가 0명이면 권한을 강제하지 않습니다 —
                      첫 관리자를 만들 수 있도록 하기 위함입니다.</>} />

                <Panel kicker="ACCOUNT"
                  title={selectedUser ? (selectedUser.display_name || selectedUser.user_id) : '계정 상세'}>
                  {!selUser ? (
                    <div className="empty-note">왼쪽에서 사람을 선택하십시오.</div>
                  ) : !selectedUser ? (
                    <div className="empty-note">이 계정을 목록에서 찾지 못했습니다.</div>
                  ) : (
                    <div style={{ padding: '0 14px 14px' }}>
                      <EvidenceStrip items={[
                        { label: '계정', value: selectedUser.user_id },
                        { label: '소속', value: deptRows.find((d) => d.dept_id === selectedUser.primary_dept_id)?.name_ko || '미배정' },
                        { label: '상태', value: orgStatusKo(selectedUser.status || 'active') },
                      ]} />

                      <div className="section-grid" style={{ marginTop: 12 }}>
                        <section>
                          <h4>권한 표식</h4>
                          {FLAGS.map((f) => (
                            <div key={f.key} style={{ display: 'flex', alignItems: 'center',
                              gap: 9, padding: '6px 0' }}>
                              <button className={selectedUser[f.key] ? 'primary-button' : 'secondary-button'}
                                disabled={!canEdit || !!busy}
                                aria-pressed={selectedUser[f.key]}
                                onClick={() => run(`${f.label} 변경`,
                                  () => orgApi.upsertUser({ ...selectedUser, [f.key]: !selectedUser[f.key] }),
                                  `${selectedUser.display_name} 의 «${f.label}» 표식을 `
                                  + `${selectedUser[f.key] ? '해제' : '부여'}했습니다.`)}>
                                {f.label} {selectedUser[f.key] ? '있음' : '없음'}
                              </button>
                              {/* 표식 이름만으로는 결과를 알 수 없다 — 무엇이 넓어지는지 함께 쓴다. */}
                              <small style={{ color: 'var(--muted)' }}>{f.what}</small>
                            </div>
                          ))}
                        </section>
                      </div>

                      <div className="section-grid" style={{ marginTop: 12 }}>
                        <section>
                          <h4>부서 역할<em>상위 부서 역할은 하위로 상속됩니다</em></h4>
                          {flat.status !== 'ok' ? (
                            <p className="section-missing">
                              부서 목록을 가져오지 못해 역할을 표시할 수 없습니다.
                            </p>
                          ) : deptRows.length === 0 ? (
                            <p className="section-missing">등록된 부서가 없습니다.</p>
                          ) : (
                            <div style={{ display: 'grid', gap: 6 }}>
                              {deptRows.map((d) => {
                                const cur = selectedUser.roles?.[d.dept_id] || '';
                                return (
                                  <div key={d.dept_id} style={{ display: 'grid',
                                    gridTemplateColumns: 'minmax(0,1fr) 150px', gap: 9,
                                    alignItems: 'center' }}>
                                    <span className="section-text" style={{ margin: 0 }}>
                                      {d.name_ko}
                                      {/* 역할이 있어도 부서에 범위가 없으면 아무것도 안 보인다. */}
                                      {!String(d.scope_node_id || '').trim() && cur
                                        ? ' — 이 부서는 조직 범위가 없어 자료가 보이지 않습니다'
                                        : ''}
                                    </span>
                                    <select className="afs-select" value={cur} disabled={!canEdit || !!busy}
                                      aria-label={`${d.name_ko} 부서 역할`}
                                      onChange={(e) => {
                                        const roles = { ...(selectedUser.roles || {}) };
                                        if (e.target.value) roles[d.dept_id] = e.target.value;
                                        else delete roles[d.dept_id];
                                        run('역할 지정',
                                          () => orgApi.setRoles(selectedUser.user_id, roles),
                                          `${selectedUser.display_name} 의 «${d.name_ko}» 역할을 `
                                          + `${e.target.value ? deptRoleKo(e.target.value) : '해제'}로 바꿨습니다.`);
                                      }}>
                                      <option value="">역할 없음</option>
                                      {Object.keys(DEPT_ROLE_KO).map((r) => (
                                        <option key={r} value={r}>{deptRoleKo(r)}</option>
                                      ))}
                                    </select>
                                  </div>
                                );
                              })}
                            </div>
                          )}
                        </section>
                      </div>
                    </div>
                  )}
                </Panel>
              </div>

              {canEdit && (
                <Panel kicker="NEW" title="사용자 추가">
                  <div style={{ padding: 14, display: 'grid', gap: 10 }}>
                    {/* ⚠️ 임의 계정을 만들면 실제 인원과 충돌한다. 화면이 그 사실을 먼저 말한다. */}
                    <Banner tone="warn" title="실제 사내 계정과 같은 값을 쓰십시오">
                      임의로 만든 계정은 나중에 실제 인원과 충돌합니다. 확인되지 않은 주소로
                      계정을 만들지 마십시오.
                    </Banner>
                    <FormField label="계정" required hint="사내 메일 주소를 그대로 씁니다.">
                      <input className="afs-input" value={userForm.id}
                        onChange={(e) => setUserForm({ ...userForm, id: e.target.value })}
                        placeholder="예: hikwon@lsmnm.com" />
                    </FormField>
                    <FormField label="표시 이름" required>
                      <input className="afs-input" value={userForm.name}
                        onChange={(e) => setUserForm({ ...userForm, name: e.target.value })} />
                    </FormField>
                    <div>
                      <button className="primary-button"
                        disabled={!!busy || !userForm.id.trim() || !userForm.name.trim()}
                        onClick={async () => {
                          const okDone = await run('사용자 추가', () => orgApi.upsertUser({
                            user_id: userForm.id.trim(), display_name: userForm.name.trim(),
                          }), `'${userForm.name.trim()}' 계정을 등록했습니다. 부서 역할을 지정해야 자료가 보입니다.`);
                          if (okDone) setUserForm({ id: '', name: '' });
                        }}>계정 등록</button>
                    </div>
                  </div>
                </Panel>
              )}
            </>
          )}

          {view === 'history' && (
            <Panel kicker="LINEAGE"
              title={selectedDept ? `${selectedDept.name_ko} 개편 이력` : '개편 이력'}>
              {!selDept ? (
                <div className="empty-note">
                  «조직도» 에서 부서를 먼저 선택하십시오 — 이력은 부서별로 봅니다.
                </div>
              ) : hist.status !== 'ok' ? (
                <EmptyOrError state={hist.status} error={hist.error}
                  emptyText="이 부서의 개편 이력을 가져오지 못했습니다."
                  onRetry={() => loadHistory(selDept)} />
              ) : (
                <div style={{ padding: 12 }}>
                  <VersionHistory
                    rows={(hist.value || []).map((h) => ({
                      id: `v${h.version}`,
                      version: `v${h.version}`,
                      at: (h.valid_from || '').slice(0, 10) || '시행일 미기재',
                      actor: scopeLabel(h.scope_node_id || ''),
                      summary: `${h.name_ko} · ${orgStatusKo(h.status)}`,
                    }))}
                    emptyText="개편 이력이 없습니다 — 아직 한 번도 개정되지 않았습니다." />
                </div>
              )}
            </Panel>
          )}

          {view === 'myscope' && (
            <Panel kicker="MY ACCESS" title="내 권한">
              {me.status !== 'ok' || !scope ? (
                <EmptyOrError state={me.status} error={me.error}
                  emptyText="권한 정보를 가져오지 못했습니다." onRetry={load} />
              ) : (
                <div style={{ padding: 14 }}>
                  <EvidenceStrip items={[
                    { label: '계정', value: scope.user_id || '(익명)' },
                    { label: '소속', value: deptRows.find((d) => d.dept_id === scope.primary_dept_id)?.name_ko || '미배정' },
                    { label: '권한 강제', value: scope.org_enforced ? '켜짐' : '꺼짐' },
                  ]} note={scope.org_enforced
                    ? '조직 범위·등급 통제가 작동 중입니다.'
                    : '통제가 꺼져 있어 지금은 모든 사용자가 전체를 봅니다.'} />

                  <div className="section-grid" style={{ marginTop: 12 }}>
                    <section>
                      <h4>내가 가진 권한 표식</h4>
                      {(() => {
                        const mine = FLAGS.filter((f) => (scope as any)[f.key]);
                        if (!mine.length) {
                          return <p className="section-missing">
                            특별 권한 표식이 없습니다 — 부서 역할로만 자료를 봅니다.
                          </p>;
                        }
                        return <ul className="section-list">
                          {mine.map((f) => <li key={f.key}><b>{f.label}</b> — {f.what}</li>)}
                        </ul>;
                      })()}
                    </section>
                  </div>

                  <div className="section-grid" style={{ marginTop: 12 }}>
                    <section className={scope.unrestricted || scope.readable_dept_ids.length
                      ? '' : 'missing'}>
                      <h4>읽을 수 있는 부서</h4>
                      {scope.unrestricted ? (
                        <p className="section-text">
                          무제한 권한이므로 모든 부서를 봅니다. 조직 미도입·부트스트랩·강제 해제
                          상태에서 이렇게 됩니다.
                        </p>
                      ) : scope.readable_dept_ids.length ? (
                        <ul className="section-list">
                          {scope.readable_dept_ids.map((id) => {
                            const d = deptRows.find((x) => x.dept_id === id);
                            return <li key={id}>
                              <b>{d?.name_ko || '확인할 수 없는 부서'}</b>
                              {d && !String(d.scope_node_id || '').trim()
                                && <span> — 조직 범위가 없어 자료가 보이지 않습니다</span>}
                            </li>;
                          })}
                        </ul>
                      ) : (
                        <p className="section-missing">
                          배정된 부서가 없습니다 — 관리자에게 부서 배정을 요청하십시오.
                        </p>
                      )}
                    </section>
                  </div>

                  <div className="section-grid" style={{ marginTop: 12 }}>
                    <section className={scope.unrestricted || scope.readable_scope_nodes.length
                      ? '' : 'missing'}>
                      <h4>내 조직 범위<em>자료가 보이는 범위</em></h4>
                      {scope.unrestricted ? (
                        <p className="section-text">전체 범위입니다.</p>
                      ) : scope.readable_scope_nodes.length ? (
                        <ul className="section-list">
                          {scope.readable_scope_nodes.map((n) => <li key={n}>
                            <b>{scopeLabel(n)}</b>
                          </li>)}
                        </ul>
                      ) : (
                        <p className="section-missing">
                          조직 범위가 없습니다. 부서에 범위가 지정되지 않았거나 배정된 부서가
                          없는 경우입니다 — 이 상태에서는 조직 소유 자료가 보이지 않습니다.
                        </p>
                      )}
                    </section>
                  </div>
                </div>
              )}
            </Panel>
          )}
        </HubShell>
      </div>
    </HubDialog>
  );
}

/** [UI 설계서 §5.8 Enterprise Structure] 의미 그래프 — 소유·운영·공유·연결.
 *
 * ## 설계가 못박은 것
 *
 * 「기본 트리와 의미 그래프를 **탭으로 구분**한다. 트리는 탐색, 그래프는 소유/운영/공유/연결
 * 관계 편집에 사용한다. **권한 상속 관계는 OPERATING_PARENT 만 별도 강조**한다.」
 *
 * ## ⚠️ 왜 강조가 중요한가
 *
 * 관계는 네 종류인데 **권한을 물려주는 것은 하나뿐**이다. 넷을 같은 무게로 그리면 관리자는
 * 「법인이 소유하니까 그 자료도 보이겠지」로 읽고, 실제로는 보이지 않아 시스템이 고장 난
 * 것으로 결론짓는다. 판정(`grants_authority`)은 **서버가 붙여 준 값**을 쓴다 — 여기서 관계
 * 이름으로 추측하면 관계 종류가 늘어날 때 조용히 틀린다.
 */
function StructureGraph({ scopeNodes }: { scopeNodes: FlatNode[] }) {
  const [rows, setRows] = useState<Loaded<OrgEdge[]>>(loading<OrgEdge[]>());

  const load = useCallback(async () => {
    setRows(loading<OrgEdge[]>());
    try {
      const r = await orgApi.edges();
      setRows(ok((r.rows || []) as OrgEdge[]));
    } catch (e) {
      setRows(failed<OrgEdge[]>(e));
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  const all = rows.value || [];
  const authority = all.filter((e) => e.grants_authority);
  const others = all.filter((e) => !e.grants_authority);
  const nodeName = (id: string) => scopeNodes.find((n) => n.node_id === id)?.label || '연결된 조직';
  const relationName = (value: string) => ({
    OPERATING_PARENT: '운영 상위', LEGAL_OWNERSHIP: '법적 소유',
    SHARED_SERVICE: '공유 서비스', CONSOLIDATION_SCOPE: '연결 범위',
  } as Record<string, string>)[value] || '조직 관계';

  const group = (title: string, list: OrgEdge[], note: string, strong: boolean) => (
    <Panel kicker={strong ? 'AUTHORITY' : 'OTHER'} title={title}
      action={<span className={`state-chip ${strong ? 'success' : 'muted'}`}>{list.length}건</span>}>
      <div style={{ padding: 15 }}>
        <p className="hint-line" style={{ margin: '0 0 10px' }}>{note}</p>
        {list.length === 0 ? (
          <p className="afs-muted" style={{ fontSize: 13, margin: 0 }}>해당 관계가 없습니다.</p>
        ) : (
          <div className="afs-table-wrap">
            <table className="afs-table">
              <thead>
                <tr><th>상위</th><th>관계</th><th>하위</th><th>권한 상속</th></tr>
              </thead>
              <tbody>
                {list.map((e, i) => (
                  <tr key={e.edge_id || `${e.from_node_id}-${e.to_node_id}-${i}`}>
                    <td>{nodeName(e.from_node_id)}</td>
                    <td>{relationName(e.relation_type)}</td>
                    <td>{nodeName(e.to_node_id)}</td>
                    <td className={e.grants_authority ? 'afs-success-fg' : 'afs-muted'}>
                      {e.grants_authority ? '예 — 권한이 내려갑니다' : '아니오'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </Panel>
  );

  return (
    <>
      <ScreenHead kicker="STRUCTURE" title="의미 그래프"
        description="조직 사이의 관계입니다. 트리는 탐색에, 이 화면은 관계 확인에 씁니다."
        chip={rows.status !== 'ok' ? { label: '조회 불가', tone: 'danger' }
          : { label: `관계 ${all.length}건 · 권한 상속 ${authority.length}건`, tone: 'data' }} />

      {/* ★★ 상시 배너 — 네 관계 중 권한을 물려주는 것은 하나뿐이다. */}
      <Banner tone="info" title="권한 상속은 OPERATING_PARENT 하나뿐입니다">
        소유(LEGAL_OWNERSHIP)·공유(SHARED_SERVICE)·연결(CONSOLIDATION_SCOPE)은 관계를 기록할
        뿐 <b>권한을 물려주지 않습니다.</b> 법인이 소유한다고 그 자료가 보이지는 않습니다 —
        자료가 보이려면 <b>운영 상위</b>로 이어져 있어야 합니다.
      </Banner>

      {rows.status !== 'ok' ? (
        <EmptyOrError state={rows.status} error={rows.error} onRetry={load}
          emptyText="등록된 관계가 없습니다." />
      ) : (
        <>
          {group('권한을 물려주는 관계 — 운영 상위', authority,
            '이 관계를 따라 상위 조직의 권한이 하위로 내려갑니다.', true)}
          <div style={{ marginTop: 14 }}>
            {group('권한과 무관한 관계 — 소유 · 공유 · 연결', others,
              '기록되지만 자료 노출 범위를 넓히지 않습니다.', false)}
          </div>
        </>
      )}

      {/* ★ [사용자 승인 2026-08-09] 이 화면은 **조회 전용**으로 둔다.
          ⚠️ 서버에 관계를 **잇는** 경로(`POST /edges`)는 있으나 **끊는** 경로가 없다. 편집
            버튼을 지금 붙이면 「이을 수는 있는데 끊을 수 없는 화면」이 된다 — 관계 하나가
            권한 전개 범위를 바꾸므로, 잘못 이으면 그 조직이 보면 안 될 자료를 보게 되고
            되돌릴 방법이 화면에 없다. 조직 관계는 개편 때만 바뀌는 값이라, 쓰지 않을 화면
            때문에 되돌릴 수 없는 위험을 열지 않는다.
          편집이 필요해지면 순서는 **끊기 경로 → 영향 확인 대화 → 편집 UI** 다. 그때의 핵심은
          버튼이 아니라 「이 관계를 끊으면 어느 조직이 무엇을 못 보게 되는가」를 누르기 전에
          보여 주는 것이다. */}
      <p className="hint-line" style={{ marginTop: 12 }}>
        이 화면은 <b>조회 전용</b>입니다. 조직 관계는 <b>조직 개편 시 별도 절차로 반영</b>하며,
        화면에서 직접 잇거나 끊지 않습니다 — 관계 하나가 권한이 미치는 범위를 바꾸기
        때문입니다.
      </p>
    </>
  );
}
