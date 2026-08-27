// [UI 설계서 §5.8 Settings & Administration Console] 환경설정·관리자.
//
// ## 설계가 못박은 골격
//
//   좌측 6도메인 · 중앙 설정 폼 · **우측 `Change Impact` 고정**
//   개인 설정에는 「나에게만 적용」, 전사 설정에는 대상·상속 범위·필요한 관리자 역할을 명시
//   저장 버튼은 **페이지 헤더와 영향 패널 하단에 반복** 배치
//   전사 설정에서는 문구를 `저장` 이 아니라 **`검토 요청`**
//   CI 색과 위험·성공 상태색이 충돌하면 **저장을 차단**
//   API Key·토큰은 **마스킹된 값도 재표시하지 않는다** — Vault 참조·연결 상태·마지막 교체일만
//   권한 변경 화면에는 404 은폐·미바인딩 거부·OPERATING_PARENT 정책 배너를 **상시** 표시
//   운영 변경은 **사전검토·승인·예약 적용·감사 기록·되돌림** 5단계 상태로 표시
//
// ## ⚠️ 없는 설정을 있는 것처럼 그리지 않는다
//
// 설계는 예산·쿼터·비용 하한까지 요구하지만 이 시스템에는 **그 값을 저장할 경로가 없다.**
// 폼을 그려 두면 사용자는 입력하고 저장한 줄 안다 — 저장되지 않는다. 그래서 그런 항목은
// 입력란 대신 «이 시스템에 아직 설정 경로가 없다» 고 적는다.
//
// ## ⚠️ 일반 업무 내비게이션과 섞지 않는다
//
// 설계 3항: 「상단 사용자 영역의 `환경설정·관리자` 에서 진입하며 일반 업무 내비게이션과
// 혼합하지 않는다」. 그래서 이 화면은 좌측 업무 레일에 항목을 만들지 않고 세션 바에서만 연다.
import { useCallback, useEffect, useMemo, useState } from 'react';

import { Banner, HubShell, Panel, ScreenHead, type RailItem } from '../design/HubShell';
import { type RailIconName } from '../design/RailIcon';
import { HubDialog } from '../design/HubDialog';
import { orgApi, type OrgUser } from '../lib/orgApi';
import { EmptyOrError, Refreshing, failed, loading, ok, refreshing, type Loaded } from '../design/DataState';
import { ConfirmInline, useConfirm } from '../design/DataFoundationShell';
import {
  adminApi, type AuditStats, type EnforcePreflight, type ModelRouting,
  type ScopePolicy,
} from '../lib/adminApi';

type Domain = 'me' | 'brand' | 'people' | 'ai' | 'data' | 'security';

//: ⚠️ `icon` 은 `RailIcon` 이 아는 이름이어야 한다 — 없는 이름을 넘겼다가 앱 전체가
//  죽었다(2026-08-09 실측). RailIcon 에 폴백을 넣었지만, 여기서도 실제 있는 것만 쓴다.
const DOMAINS: {
  id: Domain; label: string; hint: string; scope: 'me' | 'org'; icon: RailIconName;
}[] = [
  { id: 'me', label: '개인', hint: '나에게만 적용', scope: 'me', icon: 'people' },
  { id: 'brand', label: '회사 · 브랜드', hint: '상속과 CI', scope: 'org', icon: 'globe' },
  { id: 'people', label: '사용자 · 권한', hint: '범위와 상속 규칙', scope: 'org', icon: 'shield' },
  { id: 'ai', label: 'AI 모델 · 비용', hint: '역할·예산·품질', scope: 'org', icon: 'cost' },
  { id: 'data', label: '데이터 · 연계', hint: '연결과 자격증명', scope: 'org', icon: 'inject' },
  { id: 'security', label: '보안 · 감사 · 운영', hint: '강제·감사·되돌림', scope: 'org',
    icon: 'checklist' },
];

/** [설계 §5.8] 「운영 변경은 **사전검토·승인·예약 적용·감사 기록·되돌림**의 5단계 상태로
 *  표시한다」. 어느 단계까지 왔는지 보이지 않으면 사용자는 «눌렀는데 아무 일도 없다» 로 읽는다. */
const OPS_STAGES = ['사전검토', '승인', '예약 적용', '감사 기록', '되돌림'];

// ── 색 충돌 검사 ────────────────────────────────────────────────────────────
/** `#rrggbb` → [r,g,b]. 형식이 아니면 `null` — **추측하지 않는다.** */
function rgb(hex: string): [number, number, number] | null {
  const m = /^#?([0-9a-f]{6})$/i.exec((hex || '').trim());
  if (!m) return null;
  const n = parseInt(m[1], 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

/** 상대 휘도(WCAG). 대비비 계산의 근거다. */
function luminance([r, g, b]: [number, number, number]) {
  const f = (v: number) => {
    const s = v / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
}

function contrast(a: string, b: string): number | null {
  const x = rgb(a); const y = rgb(b);
  if (!x || !y) return null;
  const l1 = luminance(x); const l2 = luminance(y);
  return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
}

/** 두 색이 **구분되지 않는지**. 상태색과 CI 색이 닮으면 「위험」이 브랜드처럼 읽힌다. */
function tooSimilar(a: string, b: string): boolean {
  const x = rgb(a); const y = rgb(b);
  if (!x || !y) return false;
  const d = Math.sqrt(x.reduce((s, v, i) => s + (v - y[i]) ** 2, 0));
  return d < 60;   // 0~441 척도. 60 아래면 나란히 두었을 때 같은 색으로 읽힌다.
}

const STATE_COLORS = [
  { key: '위험(오류)', value: '#a3001c' },
  { key: '성공', value: '#0a6c3d' },
  { key: '주의', value: '#7a4a00' },
];

export function AdminConsolePanel({ onClose, onGoToOrg, me }: {
  onClose: () => void;
  /** ★ 「조직도 화면에서 합니다」라고 **말만** 하지 않는다 — 실제로 데려간다. */
  onGoToOrg: () => void;
  /** `/auth/me` 결과. 권한 표시와 「필요한 관리자 역할」 안내에 쓴다. */
  me: { user_id: string; is_admin?: boolean; is_data_admin?: boolean; display_name?: string } | null;
}) {
  const [domain, setDomain] = useState<Domain>('me');
  const [policy, setPolicy] = useState<Loaded<ScopePolicy>>(loading<ScopePolicy>());
  const [pre, setPre] = useState<Loaded<EnforcePreflight>>(loading<EnforcePreflight>());
  const [audit, setAudit] = useState<Loaded<AuditStats>>(loading<AuditStats>());
  //: ★ 계정 목록. 건수만으로는 「누가 있는가」에 답할 수 없다(2026-08-23 지적).
  const [users, setUsers] = useState<Loaded<OrgUser[]>>(loading<OrgUser[]>());
  const [msg, setMsg] = useState('');
  const [err, setErr] = useState('');

  // 개인 — 비밀번호
  const [pw, setPw] = useState({ current: '', next: '', confirm: '' });
  //: ⚠️ [2026-08-23 사용자 지적] 「로그인한 본인의 이름조차 바꿀 수 없게 되어 있다」.
  //:   종전에는 이름을 **읽기 전용 칩**으로만 그렸다. 바꾸는 경로는 조직 관리자 전용
  //:   `POST /org/users` 뿐이었다 — 오타를 냈거나 개명한 사람이 관리자를 찾아가야 했다.
  const [name, setName] = useState('');
  useEffect(() => { setName(me?.display_name || ''); }, [me?.display_name]);
  // 브랜드 — CI 색(미리보기 전용. 저장 경로는 아래 주석 참조)
  const [ci, setCi] = useState({ primary: '#0a1e5a', accent: '#fa002d' });
  // 보안 — 강제 전환
  const [reason, setReason] = useState('');
  const confirmEnforce = useConfirm<boolean>();

  //: ★★★ [2026-08-27] AI — 모델 라우팅. 사유는 **강제 전환과 별도 상태**로 둔다.
  //: ⚠️ 하나를 공유하면 한쪽 Sheet 에 적은 사유가 다른 쪽 감사 기록에 실린다.
  const [routing, setRouting] = useState<Loaded<ModelRouting>>(loading<ModelRouting>());
  const [routingReason, setRoutingReason] = useState('');
  const [routingNote, setRoutingNote] = useState('');
  const confirmRouting = useConfirm<boolean>();

  const loadRouting = useCallback(async () => {
    setRouting(refreshing);
    try { setRouting(ok(await adminApi.modelRouting())); }
    //: ⚠️ 실패를 「꺼짐」으로 그리지 않는다 — 관리자는 전용 모드가 꺼진 줄 알고
    //:   비용이 안 나간다고 판단한다. «못 읽었다» 와 «꺼졌다» 는 다른 사실이다.
    catch (e) { setRouting(failed<ModelRouting>(e)); }
  }, []);

  const loadUsers = useCallback(async () => {
    setUsers(refreshing);
    try {
      const { rows } = await orgApi.users();
      setUsers(ok(rows));
    } catch (e) {
      //: ⚠️ 목록이 «없다» 와 «못 읽었다» 를 가른다 — 읽기 실패를 빈 목록으로 그리면
      //:   관리자는 계정이 하나도 없다고 판단한다.
      setUsers(failed<OrgUser[]>(e));
    }
  }, []);

  const load = useCallback(async () => {
    // ★ [설계 §6.2] 재조회는 **값을 비우지 않는다.** 강제 전환 뒤 이력을 다시 읽을 때 표가
    //   사라졌다 돌아오면 «방금 무엇이 바뀌었는지» 를 비교할 수 없다.
    setPolicy(refreshing); setPre(refreshing); setAudit(refreshing);
    const [p, f, a] = await Promise.allSettled([
      adminApi.scopePolicy(), adminApi.enforcePreflight(), adminApi.auditStats(),
    ]);
    // ★ 셋을 **각각** 담는다 — 하나가 막혔다고 나머지를 «없음» 으로 그리지 않는다.
    setPolicy(p.status === 'fulfilled' ? ok(p.value) : failed<ScopePolicy>(p.reason));
    setPre(f.status === 'fulfilled' ? ok(f.value) : failed<EnforcePreflight>(f.reason));
    setAudit(a.status === 'fulfilled' ? ok(a.value) : failed<AuditStats>(a.reason));
    await loadUsers();
    await loadRouting();
  }, [loadRouting]);
  useEffect(() => { load(); }, [load]);

  const act = async (fn: () => Promise<unknown>, okMsg: string) => {
    setMsg(''); setErr('');
    try { await fn(); setMsg(okMsg); await load(); } catch (e: any) {
      setErr(e?.message || '요청이 거절됐습니다.');
    }
  };

  const cur = DOMAINS.find((d) => d.id === domain)!;
  const isOrg = cur.scope === 'org';

  /** [설계 §5.8] 「CI 색과 위험·성공 상태색이 충돌하면 **저장을 차단**한다」. */
  const ciConflicts = useMemo(() => {
    const out: string[] = [];
    for (const c of [ci.primary, ci.accent]) {
      if (!rgb(c)) { out.push(`«${c}» 는 #rrggbb 형식이 아닙니다.`); continue; }
      for (const s of STATE_COLORS) {
        if (tooSimilar(c, s.value)) {
          out.push(`${c} 가 «${s.key}» 상태색과 구분되지 않습니다 — `
            + '브랜드 색으로 칠한 요소를 사용자가 경고로 읽습니다.');
        }
      }
      const onWhite = contrast(c, '#ffffff');
      if (onWhite !== null && onWhite < 4.5) {
        out.push(`${c} 는 흰 배경 대비가 ${onWhite.toFixed(1)}:1 로 낮습니다 `
          + '(본문 기준 4.5:1) — 글자를 얹으면 읽히지 않습니다.');
      }
    }
    return out;
  }, [ci]);

  const items: RailItem[] = DOMAINS.map((d) => ({
    id: d.id, label: d.label, hint: d.hint, icon: d.icon,
  }));

  /** [설계 §5.8] 저장 버튼은 **헤더와 영향 패널 하단에 반복**. 전사면 문구가 «검토 요청». */
  const saveLabel = isOrg ? '검토 요청' : '저장';
  const saveDisabled = domain === 'brand' ? ciConflicts.length > 0 : true;
  const saveHint = domain === 'me'
    ? '개인 설정은 아래 각 항목에서 바로 적용합니다.'
    : domain === 'brand'
      ? (ciConflicts.length ? '색 충돌이 있어 요청할 수 없습니다.'
        : '브랜드 변경은 승인 전 전역 배포되지 않습니다.')
      //: ★★★ [2026-08-27] AI 도메인에는 **저장되는 항목이 생겼다**(모델 라우팅).
      //: ⚠️⚠️ 이 줄을 안 고쳤더니 화면 왼쪽은 스위치를 그리는데 오른쪽 레일은
      //:   「저장 가능한 설정 항목이 없습니다」라고 말했다 — 한 화면이 서로 반대로
      //:   말하면 사용자는 눌러도 안 될 거라고 읽는다(찍어 보고 잡았다).
      //: ★ 다만 여기 «검토 요청» 버튼으로 저장하지는 않는다. 모델 라우팅은 **그 자리의
      //:   확인 Sheet** 로만 바꾼다 — 사유와 영향 고지가 거기 붙어 있기 때문이다.
      : domain === 'ai'
        ? '모델 라우팅은 위 «모델 라우팅» 항목에서 사유와 함께 바꿉니다. 나머지 항목은 '
          + '아직 저장 경로가 없습니다.'
        : '이 도메인에는 아직 저장 가능한 설정 항목이 없습니다.';

  const saveButton = (
    <button className="primary-button" disabled={saveDisabled}
      title={saveHint}
      onClick={() => setMsg(saveHint)}>
      {saveLabel}
    </button>
  );

  return (
    <HubDialog label="환경설정 · 관리자" onClose={onClose}>
      <div className="afs-dialog-bar">
        <b>환경설정 · 관리자</b>
        <span>
          <Refreshing on={policy.refreshing || pre.refreshing || audit.refreshing} />
          {/* 설계: 개인/전사를 문구로 구분한다 — 같은 화면에서 영향 범위가 전혀 다르다. */}
          {isOrg
            ? '전사 설정입니다 — 바꾸면 이 회사의 모든 사용자에게 적용됩니다.'
            : '개인 설정입니다 — 나에게만 적용되며 다른 사용자에게 영향이 없습니다.'}
        </span>
        <div className="bar-actions">
          {saveButton}
          <button className="secondary-button" onClick={onClose}>
            닫기 <span aria-hidden="true" style={{ opacity: .7 }}>(Esc)</span>
          </button>
        </div>
      </div>

      <div className="afs-dialog-body">
        <HubShell
          kicker="SETTINGS" title="환경설정 · 관리자"
          subtitle="일반 업무 화면과 분리된 자리입니다."
          items={items} activeId={domain} onSelect={(id) => { setDomain(id as Domain); setMsg(''); setErr(''); }}
          jarvis={<ChangeImpact domain={domain} isOrg={isOrg} me={me} policy={policy.value}
            pre={pre.value} conflicts={ciConflicts} save={saveButton} hint={saveHint} />}>

          {err && <Banner tone="error" title="진행하지 못했습니다">{err}</Banner>}
          {msg && <Banner tone="info">{msg}</Banner>}

          {domain === 'me' && (
            <>
              <ScreenHead kicker="ME" title="개인 설정"
                description="여기서 바꾸는 것은 나에게만 적용됩니다. 다른 사용자나 조직 설정에는 영향이 없습니다."
                chip={{ label: me?.display_name || me?.user_id || '로그인 정보 없음', tone: 'data' }} />

              <Panel kicker="NAME" title="표시 이름">
                <div style={{ padding: 15, display: 'grid', gap: 10, maxWidth: 460 }}>
                  <p className="hint-line" style={{ margin: 0 }}>
                    화면과 이력에 표시되는 이름입니다. <b>계정 주소는 바꾸지 않습니다</b> —
                    계정은 산출물의 소유자로 기록돼 있어 바꾸면 과거 산출물의 주인이 사라집니다.
                  </p>
                  <label className="field-label" htmlFor="dn">표시 이름</label>
                  <input id="dn" className="afs-input" value={name} maxLength={60}
                    onChange={(e) => setName(e.target.value)} />
                  <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                    {/* ⚠️ 못 누르는 이유를 화면에 적는다(§8.6). */}
                    {(!name.trim() || name.trim() === (me?.display_name || '')) && (
                      <span style={{ fontSize: 12, color: 'var(--surface-text-muted)' }}>
                        {!name.trim() ? '이름을 입력하십시오.' : '지금 이름과 같습니다.'}
                      </span>
                    )}
                    <button className="primary-button" style={{ marginLeft: 'auto' }}
                      disabled={!name.trim() || name.trim() === (me?.display_name || '')}
                      onClick={() => act(
                        () => adminApi.changeMyDisplayName(name.trim()),
                        '표시 이름을 바꿨습니다. 다른 화면은 새로고침하면 반영됩니다.')}>
                      이름 바꾸기 (나에게만 적용)
                    </button>
                  </div>
                </div>
              </Panel>

              <Panel kicker="PASSWORD" title="비밀번호 변경">
                <div style={{ padding: 15, display: 'grid', gap: 10, maxWidth: 460 }}>
                  <p className="hint-line" style={{ margin: 0 }}>
                    ⚠️ 비밀번호를 바꾸면 <b>다른 기기의 로그인이 모두 끊깁니다</b> — 계정을 누가
                    쓰고 있는 것 같아 바꾸는 경우, 기존 세션이 살아 있으면 소용이 없기 때문입니다.
                  </p>
                  <label className="field-label" htmlFor="pw0">현재 비밀번호</label>
                  <input id="pw0" className="afs-input" type="password" value={pw.current}
                    onChange={(e) => setPw({ ...pw, current: e.target.value })} />
                  <label className="field-label" htmlFor="pw1">새 비밀번호 (5자 이상)</label>
                  <input id="pw1" className="afs-input" type="password" value={pw.next}
                    onChange={(e) => setPw({ ...pw, next: e.target.value })} />
                  <label className="field-label" htmlFor="pw2">새 비밀번호 확인</label>
                  <input id="pw2" className="afs-input" type="password" value={pw.confirm}
                    onChange={(e) => setPw({ ...pw, confirm: e.target.value })} />
                  {pw.next && pw.confirm && pw.next !== pw.confirm && (
                    <p className="afs-danger-fg" style={{ fontSize: 13, margin: 0 }}>
                      두 값이 다릅니다.
                    </p>
                  )}
                  <div>
                    <button className="primary-button"
                      disabled={!pw.current || pw.next.length < 5 || pw.next !== pw.confirm}
                      onClick={() => act(
                        () => adminApi.changePassword(pw.current, pw.next),
                        '비밀번호를 바꿨습니다. 다른 기기의 로그인은 끊겼습니다.')
                        .then(() => setPw({ current: '', next: '', confirm: '' }))}>
                      비밀번호 변경 (나에게만 적용)
                    </button>
                  </div>
                </div>
              </Panel>
            </>
          )}

          {domain === 'brand' && (
            <>
              <ScreenHead kicker="BRAND" title="회사 · 브랜드"
                //: ⚠️ 「하위 조직의 재정의」라고 적어 두었다가 규칙과 어긋났다 — 브랜드는
                //  상속만 하고 하위가 덮어쓰지 않는다(사용자 결정 2026-08-09). 3열 카드는
                //  고쳤는데 이 설명문을 함께 못 고쳐, 화면 위아래가 서로 다른 말을 했다.
                description="상속 원천과 현재 해석값, 하위에 그대로 적용될 값을 나란히 봅니다. 색은 저장 전에 상태색과 충돌하는지 검사합니다."
                chip={ciConflicts.length
                  ? { label: `충돌 ${ciConflicts.length}건`, tone: 'danger' }
                  : { label: '충돌 없음', tone: 'success' }} />

              {/* [설계 §5.8] 「상속 원천, 현재 해석값, 하위 override 를 **3열 diff** 로 표시」 */}
              <Panel kicker="INHERITANCE" title="상속 3열">
                <div style={{ padding: 15 }}>
                  <div className="brand-diff">
                    <section>
                      <h4>상속 원천</h4>
                      <p>회사 기본 프로필에서 내려옵니다.</p>
                      <ul>
                        <li>주색 <code>#0a1e5a</code></li>
                        <li>강조색 <code>#fa002d</code></li>
                      </ul>
                    </section>
                    <section className="on">
                      <h4>현재 해석값</h4>
                      <p>이 조직에 실제로 적용되는 값입니다.</p>
                      <ul>
                        <li>주색 <code>{ci.primary}</code></li>
                        <li>강조색 <code>{ci.accent}</code></li>
                      </ul>
                    </section>
                    {/* ★ [사용자 결정 2026-08-09] 「본사에서 브랜드 색을 바꾸면 그 하위 조직은
                        **모두 따라간다**」 — 하위 재정의(override)는 이 회사에 존재하지 않는다.
                        ⚠️ 설계서 §5.8 은 3열의 셋째를 «하위 override» 로 적었지만, 그것은
                          재정의를 허용하는 조직을 전제한 것이다. 여기서는 «없어서 못 보여
                          준다» 가 아니라 **애초에 생기지 않는다** 고 적는다 — 둘을 뭉치면
                          다음 사람이 「덮어쓸 수는 있는데 확인이 안 되는구나」로 읽는다. */}
                    <section>
                      <h4>하위 적용</h4>
                      <p>
                        브랜드는 <b>상속만 합니다.</b> 하위 조직이 이 값을 자기 색으로
                        덮어쓰는 경로는 없으며, 위에서 바꾸면 하위 전체가 그대로 따라갑니다.
                      </p>
                      <ul>
                        <li>주색 <code>{ci.primary}</code> — 하위 전체 동일</li>
                        <li>강조색 <code>{ci.accent}</code> — 하위 전체 동일</li>
                      </ul>
                    </section>
                  </div>
                </div>
              </Panel>

              <Panel kicker="CI" title="CI 미리보기와 충돌 검사">
                <div style={{ padding: 15 }}>
                  <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', marginBottom: 14 }}>
                    <label className="reg-filter">
                      <span>주색 (구조)</span>
                      <input className="afs-input" value={ci.primary}
                        onChange={(e) => setCi({ ...ci, primary: e.target.value })} />
                    </label>
                    <label className="reg-filter">
                      <span>강조색 (핵심 행동)</span>
                      <input className="afs-input" value={ci.accent}
                        onChange={(e) => setCi({ ...ci, accent: e.target.value })} />
                    </label>
                  </div>

                  {/* 설계: 「실제 Shell Preview 로 즉시 확인」 — Top Bar·주요 버튼·상태색 */}
                  <div className="shell-preview">
                    <div className="sp-bar" style={{ background: ci.primary }}>
                      <b>LS MnM</b><span>경영 홈 · 실행 문맥 REAL</span>
                    </div>
                    <div className="sp-body">
                      <button style={{ background: ci.primary, color: '#fff' }}>주 행동</button>
                      <button style={{ background: ci.accent, color: '#fff' }}>핵심 행동</button>
                      {STATE_COLORS.map((s) => (
                        <span key={s.key} style={{ color: s.value, borderColor: s.value }}>
                          {s.key}
                        </span>
                      ))}
                    </div>
                  </div>

                  {ciConflicts.length > 0 ? (
                    <div style={{ display: 'grid', gap: 8, marginTop: 12 }}>
                      {ciConflicts.map((c) => (
                        <Banner key={c} tone="error" title="이 색으로는 저장할 수 없습니다">{c}</Banner>
                      ))}
                    </div>
                  ) : (
                    <p className="hint-line" style={{ marginTop: 12 }}>
                      상태색과 충돌하지 않습니다. ⚠️ 브랜드 변경은 <b>승인 전 전역 사용자에게
                      배포되지 않습니다</b> — 이 화면의 미리보기는 나에게만 보입니다.
                    </p>
                  )}
                </div>
              </Panel>
            </>
          )}

          {domain === 'people' && (
            <>
              <ScreenHead kicker="PEOPLE" title="사용자 · 권한"
                description="권한은 조직 범위에서 파생합니다. 여기서 계정과 권한 표식을 확인하고, 바꾸는 것은 아래 버튼으로 조직·권한 화면에서 합니다."
                chip={pre.status !== 'ok' ? { label: '조회 불가', tone: 'danger' }
                  : { label: `사용자 ${pre.value?.users ?? 0}명`, tone: 'data' }} />

              {/* ★★ [설계 §5.8] 「권한 변경은 …404 은폐, 미바인딩 거부, OPERATING_PARENT
                  상속 규칙을 설명하는 정책 배너를 **상시** 표시한다」 — 조건부가 아니다.
                  이 셋을 모르면 관리자는 화면이 고장 난 것으로 읽고 우회로를 찾는다. */}
              <Banner tone="info" title="이 시스템의 권한 규칙 — 항상 적용됩니다">
                <ul style={{ margin: '4px 0 0', paddingLeft: 18, lineHeight: 1.7 }}>
                  <li>
                    <b>404 은폐</b> — 범위 밖 자원은 «권한 없음(403)» 이 아니라 «없음(404)» 으로
                    답합니다. 403 을 주면 그 자원이 <b>존재한다는 사실</b>이 새어 나갑니다.
                  </li>
                  <li>
                    <b>미바인딩 거부</b> — 조직에 묶이지 않은 사용자·자원은 조회를 거부합니다.
                    소속이 없으면 어느 범위로 판정할지 정할 수 없기 때문입니다.
                  </li>
                  <li>
                    <b>OPERATING_PARENT 상속</b> — 권한 상속은 <b>운영 상위</b>만 따릅니다.
                    소유·공유·연결 관계는 권한을 물려주지 않습니다.
                  </li>
                </ul>
              </Banner>

              <Panel kicker="STATE" title="현재 구성">
                <div style={{ padding: 15 }}>
                  {pre.status !== 'ok' ? (
                    <EmptyOrError state={pre.status} error={pre.error} onRetry={load}
                      emptyText="구성 정보를 받지 못했습니다." />
                  ) : (
                    <>
                      <div className="validation-facts">
                        <div><span>부서</span><b>{pre.value!.departments}</b>
                          <small>조직 트리의 노드 수</small></div>
                        <div><span>사용자</span><b>{pre.value!.users}</b>
                          <small>관리자 {pre.value!.admins}명 포함</small></div>
                        <div><span>범위 미배정</span>
                          <b className={pre.value!.unassigned ? 'afs-danger-fg' : ''}>
                            {pre.value!.unassigned}</b>
                          <small>{pre.value!.unassigned
                            ? '강제가 켜지면 이 사용자들은 아무 것도 볼 수 없습니다.'
                            : '모든 사용자가 조직에 묶여 있습니다.'}</small></div>
                      </div>
                      {pre.value!.warnings.map((w) => (
                        <Banner key={w} tone="warn" title="확인이 필요합니다">{w}</Banner>
                      ))}
                    </>
                  )}
                </div>
              </Panel>

              {/* ★★★ [2026-08-23 사용자 지적] 「관리자 페이지에 사용자 리스트가 나오지 않아요」.
                  종전에는 **건수만** 보여 주고 「개별 사용자 편집은 조직도 화면에서 합니다」라고
                  적어 두었다 — 그런데 **거기로 갈 방법을 주지 않았다.** 사용자는 이 창을 닫고,
                  ☰ 를 열고, 「조직·권한」을 찾아야 했다. 안내가 막다른 길이면 안내가 아니다.
                  ★ 목록을 여기서 **보여 주고**, 편집은 한 번 눌러 그 화면으로 간다. */}
              <Panel kicker="PEOPLE" title="계정 목록">
                <div style={{ padding: 15, display: 'grid', gap: 10 }}>
                  {users.status !== 'ok' ? (
                    <EmptyOrError state={users.status} error={users.error} onRetry={loadUsers}
                      emptyText="계정을 받지 못했습니다." />
                  ) : (users.value || []).length === 0 ? (
                    <p className="hint-line" style={{ margin: 0 }}>
                      내 권한 범위 안에 등록된 계정이 없습니다.
                    </p>
                  ) : (
                    <table className="afs-table">
                      <thead><tr><th>이름</th><th>계정</th><th>소속</th><th>권한 표식</th></tr></thead>
                      <tbody>
                        {(users.value || []).map((u) => (
                          <tr key={u.user_id}>
                            <td><b>{u.display_name || u.user_id}</b></td>
                            <td><code>{u.user_id}</code></td>
                            <td>{u.primary_dept_id || '—'}</td>
                            <td>{[u.is_admin && '관리자', u.is_data_admin && '데이터 관리자',
                                  u.is_ai_admin && 'AI 관리자', u.is_executive && '경영진']
                                  .filter(Boolean).join(' · ') || '없음'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                  <p className="hint-line" style={{ margin: 0 }}>
                    권한과 부서 역할은 <b>조직·권한</b> 화면에서 바꿉니다 — 권한은 조직 범위에서
                    파생하므로 조직도와 같은 자리에서 다뤄야 어긋나지 않습니다.
                  </p>
                  <div>
                    <button className="secondary-button" onClick={onGoToOrg}>
                      조직·권한 화면 열기 →
                    </button>
                  </div>
                </div>
              </Panel>
            </>
          )}

          {domain === 'ai' && (
            <>
              <ScreenHead kicker="AI" title="AI 모델 · 비용"
                description="어떤 모델로 도는지, 그리고 그 선택의 비용을 다룹니다."
                chip={routing.status !== 'ok'
                  ? { label: '조회 불가', tone: 'danger' }
                  : routing.value!.enabled
                    ? { label: 'OpenRouter 전용', tone: 'warn' }
                    : { label: '무료 폴백 체인', tone: 'data' }} />

              {/* ══════════════════════════════════════════════════════════════
                  ★★★ [2026-08-27] 모델 라우팅 — **화면에서 바꾼다.**

                  코드 상수로 두면 모드를 켜고 끄는 데 배포가 필요하고, 그러면 사람들은
                  아예 안 끄거나(비용이 계속 나감) 아예 안 켠다(쿼터가 계속 터짐).
                  `scope_policy` 가 한시 예외 만료일을 두고 내린 것과 같은 결론이다.
                 ══════════════════════════════════════════════════════════════ */}
              <Panel kicker="ROUTING" title="모델 라우팅"
                action={<button className="secondary-button" onClick={loadRouting}>다시 읽기</button>}>
                {routing.status !== 'ok' ? (
                  <div style={{ padding: 15 }}>
                    <EmptyOrError state={routing.status} error={routing.error}
                      emptyText="모델 라우팅 설정을 읽지 못했습니다." onRetry={loadRouting} />
                  </div>
                ) : (
                  <div style={{ padding: 15 }}>
                    {/* ⚠️⚠️ **적용되지 않고 있는 저장값**을 가장 먼저 말한다.
                        환경변수가 저장소를 이기는 구조라, 이 줄이 없으면 관리자는 스위치를
                        내리고 「껐다」고 믿는데 서버는 켜진 채로 돈다 — 그리고 화면만
                        보고는 알 수 없다. 그건 통제가 아니라 거짓 표시다. */}
                    {routing.value!.source === 'env' && (
                      <Banner tone="warn" title="지금은 환경변수가 이기고 있습니다">
                        서버가 <b>{routing.value!.env_key}={String(routing.value!.env_value)}</b>
                        {' '}로 기동돼 있어, 이 화면에서 바꾼 값은 <b>적용되지 않습니다.</b>
                        {routing.value!.stored_value !== null && (
                          <> 저장된 값은 <b>{routing.value!.stored_value ? '켬' : '끔'}</b>입니다.</>
                        )}
                        {' '}적용하려면 그 환경변수 없이 서버를 다시 띄우십시오.
                      </Banner>
                    )}

                    <div className="validation-facts">
                      <div><span>지금 적용 중</span>
                        <b>{routing.value!.enabled ? 'OpenRouter 유료' : '무료 폴백 체인'}</b>
                        <small>{routing.value!.enabled
                          ? 'Gemini·xAI·Groq·Cerebras 는 인스턴스도 만들지 않습니다.'
                          : 'Gemini 를 1순위로 하는 5개 제공사 체인입니다.'}</small></div>
                      <div><span>이 값을 정한 곳</span>
                        <b>{routing.value!.source === 'env' ? '환경변수'
                          : routing.value!.source === 'store' ? '이 화면' : '코드 기본값'}</b>
                        <small>{routing.value!.source === 'env'
                          ? `${routing.value!.env_key} — 화면 설정보다 셉니다.`
                          : routing.value!.source === 'store'
                            ? '관리자가 이 화면에서 저장한 값입니다.'
                            : '아직 아무도 바꾸지 않았습니다.'}</small></div>
                      <div><span>Pro 체인</span>
                        <b>{routing.value!.enabled
                          ? (routing.value!.chains?.pro.length ?? 0) : '—'}</b>
                        <small>{routing.value!.enabled
                          ? (routing.value!.chains?.pro.join(' → ') || '(비어 있음)')
                          : '전용 모드에서만 표시됩니다.'}</small></div>
                      <div><span>Flash 체인</span>
                        <b>{routing.value!.enabled
                          ? (routing.value!.chains?.flash.length ?? 0) : '—'}</b>
                        <small>{routing.value!.enabled
                          ? (routing.value!.chains?.flash.join(' → ') || '(비어 있음)')
                          : '전용 모드에서만 표시됩니다.'}</small></div>
                    </div>

                    <div style={{ marginTop: 12 }}>
                      <button className="primary-button"
                        onClick={() => confirmRouting.ask(!routing.value!.enabled)}>
                        {routing.value!.enabled
                          ? 'OpenRouter 전용 끄기 — 검토 요청'
                          : 'OpenRouter 전용 켜기 — 검토 요청'}
                      </button>
                    </div>

                    {/* ★ [설계 §6.5] 운영 변경 — 5요소를 전부 채운다.
                        ⚠️ 켜는 것도 끄는 것도 **결과가 있다.** 한쪽만 위험한 것처럼 그리면
                          사람은 반대쪽을 «안전한 기본» 으로 읽는다. */}
                    <ConfirmInline open={confirmRouting.open}
                      title={confirmRouting.target
                        ? 'OpenRouter 유료 모델만 쓰도록 바꿉니다'
                        : '무료 티어 폴백 체인으로 되돌립니다'}
                      changes={confirmRouting.target
                        ? 'Gemini·xAI·Groq·Cerebras 를 쓰지 않습니다. 인스턴스도 만들지 않습니다.'
                        : 'Gemini 를 1순위로 하는 종전 폴백 체인이 돌아옵니다.'}
                      affects={confirmRouting.target ? (
                        <><b>비용이 발생합니다.</b> 무료 쿼터를 쓰지 않으므로 호출마다 과금됩니다
                          (Pro 체인 기준 출력 100만 토큰당 $2.50). 대신 실측 폴백 실패 190건 중
                          <b> 429 쿼터 소진 130건</b>이 사라집니다.</>
                      ) : (
                        <><b>429 쿼터 소진이 돌아옵니다.</b> 실측에서 폴백 실패 190건 중 130건이
                          그것이었고, 무료 체인이 소진되면 남는 것이 출력 8k 짜리 모델뿐이라
                          <b> 코드 생성이 구조적으로 실패</b>합니다.</>
                      )}
                      reversible={<>반대 방향으로 다시 바꾸면 됩니다. 두 변경 모두 이력과 감사에
                        남습니다. <b>다만 이미 나간 호출의 비용은 되돌릴 수 없습니다.</b></>}
                      approval="전사 관리자 권한이 필요합니다. 감사 로그에 기록됩니다."
                      reason={{
                        value: routingReason, onChange: setRoutingReason, required: true,
                        placeholder: '예: 무료 쿼터 소진으로 완주가 반복 실패 — 한시 전환',
                        label: <>변경 사유 <b>(필수)</b> — 되돌릴 때 «왜 바꿨는가» 의 근거가 됩니다</>,
                      }}
                      confirmLabel="적용"
                      onCancel={confirmRouting.cancel}
                      onConfirm={() => confirmRouting.run((t) => act(
                        async () => {
                          const out = await adminApi.setModelRouting(t, routingReason.trim());
                          //: ★ 서버가 적어 준 결과 문장을 **그대로** 보여 준다. 화면이 다시
                          //:   쓰면 「저장은 됐는데 안 먹는다」 같은 사실이 빠진다.
                          setRoutingNote(out.note || '');
                          return out;
                        },
                        '모델 라우팅을 바꿨습니다.')
                        .then(() => { setRoutingReason(''); loadRouting(); }))} />

                    {routingNote && (
                      <Banner tone="info" title="이 변경의 결과">{routingNote}</Banner>
                    )}

                    {/* ★★★ **언제 적용되는지**를 말한다. 「눌렀는데 아무 일도 없다」로
                        읽히지 않게. */}
                    <p className="hint-line" style={{ marginTop: 10 }}>
                      ⚠️ 이 변경은 <b>다음 서버 기동부터</b> 적용됩니다. 지금 돌고 있는 작업이
                      도중에 다른 모델로 갈아타면 앞 태스크와 뒤 태스크의 산출물이 달라지고,
                      그 프로젝트는 «무엇이 만든 것인가» 에 답할 수 없게 됩니다.
                    </p>

                    {(routing.value!.history || []).length > 0 && (
                      <div className="afs-table-wrap" style={{ marginTop: 12 }}>
                        <table className="afs-table">
                          <thead>
                            <tr><th>이전</th><th>이후</th><th>변경자</th><th>사유</th><th>시각</th></tr>
                          </thead>
                          <tbody>
                            {(routing.value!.history || []).map((h, i) => (
                              <tr key={i}>
                                <td>{h.from ? '켬' : '끔'}</td>
                                <td><b>{h.to ? '켬' : '끔'}</b></td>
                                <td>{h.actor}</td>
                                <td>{h.reason || '—'}</td>
                                <td>{h.at || '—'}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                )}
              </Panel>

              {/* ⚠️ 설계가 요구하는 항목 중 **서버에 저장 경로가 없는 것**을 입력란으로 그리지
                  않는다. 그리면 사용자는 입력하고 저장된 줄 안다.
                  ★ [2026-08-27] 모델 라우팅에는 저장 경로가 생겼으므로 이 배너에서 뺐다 —
                    「전부 저장 안 됨」이라고 계속 말하면 위 스위치도 안 먹는다고 읽힌다. */}
              <Banner tone="warn" title="아직 저장할 수 없는 설정이 남아 있습니다">
                설계는 여기에서 <b>모델 역할·예상 품질·비용 하한·월 예산·쿼터</b>도 다루도록
                정했지만, 그 값들을 저장할 서버 경로는 아직 없습니다. 입력란을 만들어 두면
                저장되지 않는 값을 저장한 것으로 오해하게 되므로 두지 않았습니다.
              </Banner>

              <Panel kicker="QUALITY" title="Golden Benchmark">
                <div style={{ padding: 15 }}>
                  <p className="hint-line" style={{ margin: 0 }}>
                    품질 기준선은 <b>Golden Benchmark</b> 화면에서 시나리오별로 관리합니다 —
                    모델을 바꾸기 전에 같은 시나리오로 비교하고, 통과한 것만 기준으로 승격합니다.
                  </p>
                  <p className="hint-line" style={{ marginTop: 8 }}>
                    ⚠️ 정책은 <b>진행 중인 Sprint 에 소급하지 않습니다</b> — 실행 중인 작업이
                    도중에 다른 모델로 바뀌면 산출물의 앞뒤가 달라집니다.
                  </p>
                </div>
              </Panel>
            </>
          )}

          {domain === 'data' && (
            <>
              <ScreenHead kicker="DATA" title="데이터 · 연계"
                description="외부 시스템 연결과 자격증명을 다룹니다."
                chip={{ label: '자격증명 비표시', tone: 'data' }} />

              {/* ★★ [설계 §5.8] 「API Key·토큰은 **마스킹된 값도 재표시하지 않는다.** Vault
                  참조, 연결 상태, 마지막 교체일만 표시하고 `교체` 행동만 제공」.
                  ⚠️ `sk-••••1234` 같은 마스킹도 **뒷자리를 노출한다** — 로그·스크린샷·화면
                    공유로 새어 나가고, 뒷자리는 키를 특정하는 데 충분한 단서다. */}
              <Banner tone="info" title="자격증명은 이 화면에 표시되지 않습니다">
                API Key·토큰은 <b>마스킹된 형태로도 다시 보여 주지 않습니다.</b> 화면에는 Vault
                참조·연결 상태·마지막 교체일만 나오고, 할 수 있는 행동은 <b>교체</b>뿐입니다.
                값을 확인해야 한다면 그것은 <b>새 키를 발급받아야 한다는 뜻</b>입니다.
              </Banner>

              <Panel kicker="CONNECTIONS" title="연결 상태">
                <div style={{ padding: 15 }}>
                  <p className="hint-line" style={{ margin: 0 }}>
                    개별 시스템 연결·범위 지정은 <b>Crosswalk</b> 화면에서 관리합니다. 이 화면은
                    자격증명 취급 규칙을 고정하는 자리입니다.
                  </p>
                </div>
              </Panel>
            </>
          )}

          {domain === 'security' && (
            <>
              <ScreenHead kicker="SECURITY" title="보안 · 감사 · 운영"
                description="권한 강제 스위치와 감사 기록입니다. 여기서의 변경은 전사에 즉시 적용됩니다."
                chip={policy.status !== 'ok' ? { label: '조회 불가', tone: 'danger' }
                  : { label: policy.value!.org_enforce ? '강제 켜짐' : '강제 꺼짐',
                    tone: policy.value!.org_enforce ? 'success' : 'warn' }} />

              <Panel kicker="ENFORCE" title="조직 권한 강제">
                <div style={{ padding: 15 }}>
                  {policy.status !== 'ok' ? (
                    <EmptyOrError state={policy.status} error={policy.error} onRetry={load}
                      emptyText="정책을 받지 못했습니다." />
                  ) : (
                    <>
                      <div className="validation-facts">
                        <div><span>현재</span>
                          <b>{policy.value!.org_enforce ? '켜짐' : '꺼짐'}</b>
                          {/* ⚠️ 코드 기본값과 정책 파일이 갈리면 화면과 실제가 달라진다 —
                              어느 쪽이 이겼는지 적는다. */}
                          <small>판정 출처: {policy.value!.org_enforce_source === 'policy'
                            ? '정책 파일' : '코드 기본값'}</small></div>
                        <div><span>레거시 유예 기한</span>
                          <b>{policy.value!.legacy_grandfather_until}</b>
                          <small>{policy.value!.is_default
                            ? '기본값을 쓰고 있습니다.' : '관리자가 지정한 값입니다.'}</small></div>
                        <div><span>전환 준비</span>
                          <b className={pre.value?.ready ? 'afs-success-fg' : 'afs-warn-fg'}>
                            {pre.status !== 'ok' ? '확인 불가'
                              : pre.value!.ready ? '준비됨' : `차단 ${pre.value!.blockers.length}건`}
                          </b>
                          <small>미배정 사용자 {pre.value?.unassigned ?? '?'}명</small></div>
                      </div>

                      {(pre.value?.blockers || []).map((b) => (
                        <Banner key={b} tone="error" title="먼저 해결해야 합니다">{b}</Banner>
                      ))}

                      {/* ⚠️ 사유 입력란은 **확인 Sheet 안**으로 옮겼다(§6.5 ⑤). 여기에 그대로
                          두었더니 «사유가 없으면 버튼이 잠기고 → Sheet 가 안 열리고 → Sheet
                          안의 사유란에 닿을 수 없는» 모순이 생겼다(실측으로 잡았다). 사유는
                          한 곳에서만 받는다. */}
                      <div style={{ marginTop: 10 }}>
                        <button className="primary-button"
                          onClick={() => confirmEnforce.ask(!policy.value!.org_enforce)}>
                          {policy.value!.org_enforce ? '강제 끄기 — 검토 요청' : '강제 켜기 — 검토 요청'}
                        </button>
                      </div>

                      {/* ★ [설계 §6.5] 전사에 즉시 적용되는 운영 변경 — 5요소를 전부 채운다. */}
                      <ConfirmInline open={confirmEnforce.open}
                        title={confirmEnforce.target
                          ? '조직 권한 강제를 켭니다' : '조직 권한 강제를 끕니다'}
                        changes={confirmEnforce.target
                          ? '모든 조회가 요청자의 조직 범위로 걸러집니다.'
                          : '조직 범위 필터가 해제되고 전 조직 자료가 모두에게 열립니다.'}
                        affects={confirmEnforce.target ? (
                          <>범위가 없는 사용자는 <b>즉시 아무 것도 볼 수 없게 됩니다.</b>
                            {' '}지금 미배정 {pre.value?.unassigned ?? '확인 불가'}명 ·
                            {' '}전체 {pre.value?.users ?? '확인 불가'}명.</>
                        ) : (
                          <>끄면 <b>모든 사용자가 모든 조직의 자료를 봅니다.</b> 이 상태로 남겨
                            두면 이후의 모든 범위 통제가 무력해집니다.</>
                        )}
                        reversible={<>반대 방향으로 다시 바꾸면 됩니다 — <b>다만 그 사이 열려
                          있던 자료를 누가 봤는지는 되돌릴 수 없습니다.</b> 두 변경 모두 이력에
                          남습니다.</>}
                        approval="전사 관리자 권한이 필요합니다. 감사 로그에 기록됩니다."
                        reason={{
                          value: reason, onChange: setReason, required: true,
                          placeholder: '예: M2 권한 모델 가동 — 사전 점검 통과',
                          label: <>변경 사유 <b>(필수)</b> — 되돌릴 때 «왜 켰는가» 의 근거가 됩니다</>,
                        }}
                        confirmLabel="적용"
                        onCancel={confirmEnforce.cancel}
                        onConfirm={() => confirmEnforce.run((t) => act(
                          () => adminApi.setEnforcement(t, reason.trim()),
                          '정책을 바꿨습니다. 아래 이력에 기록됐습니다.')
                          .then(() => setReason('')))} />

                      {/* [설계 §5.8] 운영 변경 5단계 상태 */}
                      <div className="ops-stages" aria-label="운영 변경 단계">
                        {OPS_STAGES.map((s, i) => (
                          <span key={s} className={i < 2 ? 'done' : ''}>
                            <i aria-hidden="true">{i + 1}</i>{s}
                          </span>
                        ))}
                      </div>
                      <p className="hint-line" style={{ marginTop: 6 }}>
                        ⚠️ 이 시스템은 <b>사전검토·승인·감사 기록</b>까지 수행합니다. 예약 적용과
                        되돌림은 아직 자동 경로가 없어, 되돌리려면 반대 방향으로 다시 변경해야
                        합니다 — 그 변경도 이력에 남습니다.
                      </p>
                    </>
                  )}
                </div>
              </Panel>

              <Panel kicker="HISTORY" title="정책 변경 이력"
                action={audit.status === 'ok' && (
                  <span className="afs-muted" style={{ fontSize: 12 }}>
                    감사 이벤트 {audit.value!.total}건
                  </span>)}>
                <div style={{ padding: 15 }}>
                  {policy.status !== 'ok' ? (
                    <EmptyOrError state={policy.status} error={policy.error} onRetry={load}
                      emptyText="이력을 받지 못했습니다." />
                  ) : (policy.value!.history || []).length === 0 ? (
                    <p className="afs-muted" style={{ fontSize: 13 }}>기록된 정책 변경이 없습니다.</p>
                  ) : (
                    <div className="afs-table-wrap">
                      <table className="afs-table">
                        <thead>
                          <tr><th>항목</th><th>이전</th><th>이후</th><th>변경자</th><th>사유</th></tr>
                        </thead>
                        <tbody>
                          {policy.value!.history.map((h, i) => (
                            <tr key={`${h.field}-${i}`}>
                              <td>{h.field}</td>
                              <td>{String(h.from ?? '—')}</td>
                              <td><b>{String(h.to ?? '—')}</b></td>
                              <td>{h.actor || '미상'}</td>
                              <td>{h.reason || '기록 없음'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              </Panel>
            </>
          )}
        </HubShell>
      </div>
    </HubDialog>
  );
}

/** [설계 §5.8] 「우측은 `Change Impact` 로 **고정**한다」.
 *
 * 설정 화면에서 가장 잦은 사고는 「이게 누구한테까지 영향을 주는지 모르고 눌렀다」이다.
 * 그래서 도메인이 바뀌어도 이 자리는 사라지지 않는다 — 늘 같은 자리에서 같은 질문에 답한다. */
function ChangeImpact({ domain, isOrg, me, policy, pre, conflicts, save, hint }: {
  domain: Domain; isOrg: boolean;
  me: { user_id: string; is_admin?: boolean; is_data_admin?: boolean } | null;
  policy: ScopePolicy | null; pre: EnforcePreflight | null;
  conflicts: string[]; save: React.ReactNode; hint: string;
}) {
  const audience = isOrg
    ? `이 회사의 사용자 ${pre ? `${pre.users}명 전원` : '전원'}`
    : '나 한 사람';
  const role = domain === 'security' ? '전사 관리자'
    : domain === 'people' ? '조직 관리자'
      : domain === 'brand' ? '브랜드 관리자'
        : domain === 'data' ? '데이터 관리자'
          : domain === 'ai' ? 'AI 관리자' : '없음 (본인)';
  const hasRole = domain === 'me' ? true : !!(me?.is_admin || me?.is_data_admin);

  return (
    <div className="change-impact">
      <h3>Change Impact</h3>

      <dl>
        <div><dt>적용 대상</dt><dd>{audience}</dd></div>
        <div><dt>상속 범위</dt>
          <dd>{isOrg
            ? '이 조직과 운영 하위 조직 전체 (OPERATING_PARENT 만 상속)'
            : '없음 — 다른 사용자에게 전파되지 않습니다.'}</dd></div>
        <div><dt>필요한 역할</dt>
          <dd className={hasRole ? '' : 'afs-danger-fg'}>
            {role}{hasRole ? '' : ' — 현재 계정에는 없습니다'}
          </dd></div>
        <div><dt>되돌릴 수 있나</dt>
          <dd>{domain === 'security'
            ? '반대 방향으로 다시 변경해야 하며, 그 변경도 이력에 남습니다.'
            : domain === 'me' ? '다시 바꾸면 됩니다.'
              : '승인 전에는 적용되지 않으므로 요청을 취소하면 됩니다.'}</dd></div>
      </dl>

      {domain === 'security' && policy && (
        <p className="ci-note">
          지금 강제는 <b>{policy.org_enforce ? '켜져' : '꺼져'}</b> 있고, 판정 출처는{' '}
          <b>{policy.org_enforce_source === 'policy' ? '정책 파일' : '코드 기본값'}</b>입니다.
          {pre && pre.unassigned > 0 && (
            <> 범위 미배정 <b>{pre.unassigned}명</b>이 즉시 영향을 받습니다.</>
          )}
        </p>
      )}

      {domain === 'brand' && (
        <p className={conflicts.length ? 'ci-note danger' : 'ci-note'}>
          {conflicts.length
            ? `색 충돌 ${conflicts.length}건이 남아 있어 요청할 수 없습니다.`
            : '색 충돌이 없습니다. 승인 전에는 나에게만 보입니다.'}
        </p>
      )}

      {/* 설계: 저장 버튼은 헤더와 **영향 패널 하단**에 반복 배치한다. */}
      <div className="ci-save">
        {save}
        <small>{hint}</small>
      </div>
    </div>
  );
}
