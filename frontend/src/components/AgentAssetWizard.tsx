// [D-017 §9 P2-2 / 설계 §8.5] 자산 생성 마법사 — 8단계.
//
// ## 왜 마법사인가
//
// 자산 하나를 만드는 데 필요한 결정은 여덟 가지인데, 한 화면에 다 놓으면 사용자는 **무엇이
// 되돌릴 수 없는 결정인지** 구분하지 못한다. 공개 범위와 쓰기 영향은 나중에 바꾸기 어렵고
// (전사에 한번 나가면 남의 프로젝트가 물고 있다), 이름과 목적은 언제든 고칠 수 있다.
//
// ## ⚠️⚠️ 이 화면이 **지어내지 않는 것**
//
// 설계 §8.5 는 「AI 추천은 사용자가 허용받은 데이터·도구 범위 안에서만 후보를 만든다. 권한이
// 없는 기능을 «가능» 하다고 안내하지 않는다」고 못박았다. 그런데 서버에는 **허용 데이터 도메인
// ·도구 목록을 주는 조회 경로가 없다**(`core/agent_design_context` 는 추천 프롬프트를 만들 때만
// 쓰이고 라우트로 노출되지 않는다).
//
// 그래서 3·4단계는 **선택지를 만들지 않는다.** 그럴듯한 목록을 띄우면 사용자는 그것이 자기가
// 실제로 쓸 수 있는 범위라고 믿고, 실행 단계에서 권한 교집합(P3-3)에 걸려서야 아니라는 것을
// 안다. 그 시점은 이미 설계가 끝난 뒤다 — **모르면 «없음» 이라고 말하지 않는다**(P2-3 의 교훈).
//
// 마찬가지로 7단계 「테스트 실행」도 **실행하지 않는다.** 자산을 시험 실행하는 서버 경로가
// 없으므로, 있는 척하는 버튼 대신 무엇을 어디서 확인해야 하는지를 적는다.
import { useState } from 'react';

import { ConfirmInline, FormField } from '../design/DataFoundationShell';
import { Banner, Panel } from '../design/HubShell';
import { HubDialog } from '../design/HubDialog';
import { MODEL_TIER_KO } from '../design/terms';
import { getEnterpriseContext } from '../lib/api';
import {
  agentGovApi, type AssetKindPath, type GovAsset, type GovCapabilities,
} from '../lib/agentGovernanceApi';

type Step = {
  id: string;
  title: string;
  /** 이 단계가 무엇을 결정하는가. 제목만으로는 «왜 묻는지» 가 전달되지 않는다. */
  why: string;
};

//: 설계 §8.5 의 여덟 단계. **순서를 바꾸지 않는다** — 공개 범위(2)를 정하기 전에는 어떤
//: 데이터를 쓸 수 있는지(3)가 정해지지 않고, 도구와 쓰기 영향(4)을 모르면 승인 게이트(6)를
//: 어디에 둘지 판단할 수 없다.
const STEPS: Step[] = [
  { id: 'purpose', title: '업무 목적과 산출물',
    why: '무엇을 위해 만드는지와 무엇이 나오는지 — 이 둘이 없으면 승인자가 판단할 근거가 없습니다' },
  { id: 'scope', title: '소유 조직과 공개 범위',
    why: '누가 책임지고 누구까지 쓰는가 — 나중에 바꾸기 가장 어려운 결정입니다' },
  { id: 'data', title: '필요한 데이터 도메인',
    why: '어떤 자료를 근거로 판단하는가' },
  { id: 'tools', title: '허용 도구와 쓰기 영향',
    why: '바깥에 무엇을 남기는가 — 읽기만 하는 것과 쓰는 것은 승인 무게가 다릅니다' },
  { id: 'model', title: '모델 품질·비용 정책',
    why: '품질과 비용의 균형' },
  { id: 'gate', title: '사용자 승인 게이트',
    why: '사람이 끼어들 지점 — 자동으로 끝까지 가면 되돌릴 수 없는 산출물이 나옵니다' },
  { id: 'test', title: '테스트 실행',
    why: '승인 요청 전에 무엇을 확인해야 하는가' },
  { id: 'submit', title: '승인 요청',
    why: '초안으로 둘지, 지금 답을 요청할지' },
];

const KIND_KO: Record<AssetKindPath, string> = {
  agents: '에이전트', workflows: '워크플로우', skills: '스킬',
};

/** 이 종류에 해당하지 않는 단계. **숨기지 않고 «해당 없음» 으로 보여준다** — 단계가 사라지면
 *  사용자는 자기가 무엇을 건너뛰었는지 모르고, 나중에 「왜 도구를 못 정했나」를 묻는다. */
const NA_STEPS: Record<AssetKindPath, string[]> = {
  agents: [],
  workflows: ['tools', 'model'],
  skills: ['data', 'tools', 'model', 'gate'],
};

type Draft = {
  name_ko: string;
  purpose: string;
  deliverable: string;
  visibility: string;
  owner_scope_id: string;
  data_domains: string;
  tools: string;
  write_impact: 'read_only' | 'writes';
  model_tier: string;
  cost_note: string;
  hotl_after: boolean;
  submit_now: boolean;
};

const EMPTY: Draft = {
  name_ko: '', purpose: '', deliverable: '',
  //: ★ 기본값은 **가장 좁은 범위**다. 넓은 값을 기본으로 두면 아무 생각 없이 넘긴 사용자가
  //:   조직 자산을 만들게 되고, 그 자산은 남이 지울 수도 고칠 수도 없는 상태로 남는다.
  visibility: 'PERSONAL', owner_scope_id: '',
  data_domains: '', tools: '', write_impact: 'read_only',
  model_tier: 'pro', cost_note: '', hotl_after: false, submit_now: false,
};

export function AgentAssetWizard({ kind, caps, onClose, onCreated }: {
  kind: AssetKindPath;
  caps: GovCapabilities | null;
  onClose: () => void;
  onCreated: (a: GovAsset) => void;
}) {
  const ctx = getEnterpriseContext();
  const [d, setD] = useState<Draft>({ ...EMPTY, owner_scope_id: ctx.scopeNodeId || '' });
  const [i, setI] = useState(0);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [confirmOpen, setConfirmOpen] = useState(false);

  const set = <K extends keyof Draft>(k: K, v: Draft[K]) => setD((p) => ({ ...p, [k]: v }));
  const na = NA_STEPS[kind].includes(STEPS[i].id);
  const canPublishEnterprise = Boolean(caps?.can_publish_enterprise);

  /** 다음으로 갈 수 있는가. ⚠️ **막을 때는 이유를 함께 낸다** — 회색 버튼만 두면 사용자는
   *  화면이 고장난 것으로 읽는다(§8.6 과 같은 규칙). */
  const blocked = (): string => {
    const s = STEPS[i].id;
    if (s === 'purpose' && !d.name_ko.trim()) return '이름을 입력해야 넘어갑니다.';
    if (s === 'scope') {
      if (d.visibility !== 'PERSONAL' && !d.owner_scope_id.trim()) {
        return '개인 범위가 아니면 소유 조직이 필요합니다 — 소유가 없으면 나중에 '
          + '«이 자산은 누구 책임인가» 에 답할 수 없습니다.';
      }
      if (d.visibility === 'ENTERPRISE' && !canPublishEnterprise) {
        return '전사 공개는 AI 거버넌스 관리자만 만들 수 있습니다 — 조직 자산으로 만든 뒤 '
          + '전사 승격을 요청하십시오.';
      }
    }
    return '';
  };
  const block = blocked();

  const save = async () => {
    setBusy(true); setErr('');
    try {
      //: ⚠️ 서버 `AssetCreate` 는 `name_ko`·`purpose`·`visibility`·`owner_scope_id`·`body` 만
      //:   받는다. 나머지 결정은 **본문에 담는다** — 스키마에 없는 값을 최상위로 보내면
      //:   조용히 버려지고, 사용자는 자기가 정한 것이 저장됐다고 믿는다.
      const body: Record<string, unknown> = { deliverable: d.deliverable.trim() };
      const na1 = NA_STEPS[kind];
      if (!na1.includes('data')) {
        body.data_domains = d.data_domains.split(',').map((x) => x.trim()).filter(Boolean);
      }
      if (!na1.includes('tools')) {
        body.tools = d.tools.split(',').map((x) => x.trim()).filter(Boolean);
        body.write_impact = d.write_impact;
      }
      if (!na1.includes('model')) {
        body.model_tier = d.model_tier;
        body.cost_note = d.cost_note.trim();
      }
      if (!na1.includes('gate')) body.hotl_after = d.hotl_after;

      const a = await agentGovApi.create(kind, {
        name_ko: d.name_ko.trim(),
        purpose: d.purpose.trim(),
        visibility: d.visibility,
        owner_scope_id: d.visibility === 'PERSONAL' ? '' : d.owner_scope_id.trim(),
        body,
      });
      if (d.submit_now) {
        //: ⚠️ 승인 요청이 실패해도 **자산은 이미 만들어졌다.** 그 사실을 알려야 사용자가
        //:   같은 것을 또 만들지 않는다.
        try {
          await agentGovApi.submit(kind, a.asset_id);
        } catch (e: unknown) {
          onCreated(a);
          setErr(`초안은 저장됐지만 승인 요청이 거절됐습니다 — ${(e as Error)?.message || ''} `
            + '목록에서 «승인 요청» 을 다시 누르십시오.');
          setBusy(false);
          return;
        }
      }
      onCreated(a);
      onClose();
    } catch (e: unknown) {
      setErr((e as Error)?.message || '저장하지 못했습니다.');
    } finally {
      setBusy(false);
    }
  };

  const S = STEPS[i];
  return (
    <HubDialog label={`${KIND_KO[kind]} 만들기 — ${S.title}`} onClose={onClose}>
      <div className="afs-dialog-bar">
        <b>{KIND_KO[kind]} 만들기</b>
        <span>{i + 1} / {STEPS.length} · {S.title}</span>
        <div className="bar-actions">
          <button className="secondary-button" onClick={onClose}>
            닫기 <span aria-hidden="true" style={{ opacity: .7 }}>(Esc)</span>
          </button>
        </div>
      </div>

      <div className="afs-dialog-body" style={{ padding: 16 }}>
        {/* 단계 표시 — 어디까지 왔고 무엇이 남았는지. */}
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 14 }}>
          {STEPS.map((s, n) => (
            <span key={s.id}
              className={`state-chip ${n === i ? 'data' : n < i ? 'success' : 'muted'}`}
              style={{ fontSize: 11 }}>
              {n + 1}. {s.title}{NA_STEPS[kind].includes(s.id) ? ' (해당 없음)' : ''}
            </span>
          ))}
        </div>

        {err && (
          <div style={{ marginBottom: 12 }}>
            <Banner tone="error" title="진행하지 못했습니다">
              <span style={{ whiteSpace: 'pre-wrap' }}>{err}</span>
            </Banner>
          </div>
        )}

        <Panel kicker={`STEP ${i + 1}`} title={S.title}>
          <div className="panel-body">
            <p className="afs-muted" style={{ fontSize: 13, marginTop: 0 }}>{S.why}</p>

            {na ? (
              <Banner tone="info" title="이 종류에는 해당하지 않습니다">
                {KIND_KO[kind]} 자산은 이 항목을 갖지 않습니다 — 건너뛰어도 빠지는 것이 없습니다.
              </Banner>
            ) : S.id === 'purpose' ? (
              <>
                <FormField label="이름" required>
                  <input className="afs-input" value={d.name_ko}
                    onChange={(e) => set('name_ko', e.target.value)}
                    placeholder="예: 발주 요구사항 분석가" />
                </FormField>
                <FormField label="업무 목적"
                  hint="승인자가 «이것이 왜 필요한가» 를 읽는 곳입니다.">
                  <textarea className="afs-input" rows={3} value={d.purpose}
                    onChange={(e) => set('purpose', e.target.value)} />
                </FormField>
                <FormField label="산출물"
                  hint="무엇이 나오는지 — 「보고서」처럼 뭉뚱그리면 검수 기준이 서지 않습니다.">
                  <input className="afs-input" value={d.deliverable}
                    onChange={(e) => set('deliverable', e.target.value)}
                    placeholder="예: 요구사항 정의서(RFP) 초안" />
                </FormField>
              </>
            ) : S.id === 'scope' ? (
              <>
                <FormField label="공개 범위" required
                  hint="기본값은 가장 좁은 «개인» 입니다 — 넓히는 것은 결정이어야 합니다.">
                  <select className="afs-input" value={d.visibility}
                    onChange={(e) => set('visibility', e.target.value)}>
                    <option value="PERSONAL">개인 — 나만 봅니다</option>
                    <option value="SCOPE">조직 — 소유 조직만</option>
                    <option value="DESCENDANTS">조직과 하위 — 소유 조직과 그 아래</option>
                    <option value="ENTERPRISE">전사 — 모든 조직</option>
                  </select>
                </FormField>
                {d.visibility !== 'PERSONAL' && (
                  <FormField label="소유 조직" required
                    hint="지금 실행 문맥의 조직이 기본값입니다. ⚠️ 관리 범위 밖이면 서버가 거절하고 사유를 알려 줍니다 — 화면은 그 판정을 흉내 내지 않습니다.">
                    <input className="afs-input" value={d.owner_scope_id}
                      onChange={(e) => set('owner_scope_id', e.target.value)}
                      placeholder={ctx.scopeNodeId || '조직 노드 id'} />
                  </FormField>
                )}
                {d.visibility === 'ENTERPRISE' && !canPublishEnterprise && (
                  <Banner tone="warn" title="전사 공개는 여기서 만들 수 없습니다">
                    조직 자산으로 만들어 조직 승인을 받은 뒤 목록에서 «전사 승격 요청» 을
                    누르십시오. 요청은 <b>가시성을 바꾸지 않습니다</b> — AI 거버넌스 관리자가
                    확정할 때 전사에 공개됩니다.
                  </Banner>
                )}
              </>
            ) : S.id === 'data' ? (
              <>
                <FormField label="필요한 데이터 도메인"
                  hint="콤마로 구분합니다. 예: manufacturing, logistics">
                  <input className="afs-input" value={d.data_domains}
                    onChange={(e) => set('data_domains', e.target.value)} />
                </FormField>
                <Banner tone="warn" title="여기에 «고를 수 있는 목록» 을 띄우지 않습니다">
                  서버가 <b>내가 허용받은 데이터 도메인 목록을 주는 경로를 아직 제공하지
                  않습니다.</b> 그럴듯한 선택지를 만들어 두면 그것이 실제 허용 범위라고 믿게
                  되고, 실행 단계에서 권한에 걸려서야 아니라는 것을 알게 됩니다 — 그때는 이미
                  설계가 끝난 뒤입니다.
                </Banner>
              </>
            ) : S.id === 'tools' ? (
              <>
                <FormField label="허용 도구" hint="콤마로 구분합니다.">
                  <input className="afs-input" value={d.tools}
                    onChange={(e) => set('tools', e.target.value)} />
                </FormField>
                <FormField label="쓰기 영향" required
                  hint="바깥 시스템에 무엇을 남기는가 — 승인 무게가 달라집니다.">
                  <select className="afs-input" value={d.write_impact}
                    onChange={(e) => set('write_impact',
                      e.target.value as Draft['write_impact'])}>
                    <option value="read_only">읽기만 — 바깥에 아무것도 남기지 않습니다</option>
                    <option value="writes">쓰기 있음 — 외부 시스템에 기록이 남습니다</option>
                  </select>
                </FormField>
                {d.write_impact === 'writes' && (
                  <Banner tone="warn" title="쓰기는 되돌릴 수 없습니다">
                    실행 시점에 요청자와 이 정의의 권한 <b>교집합</b>만 허용됩니다 — 여기 적은
                    도구가 곧 쓸 수 있는 도구는 아닙니다.
                  </Banner>
                )}
              </>
            ) : S.id === 'model' ? (
              <>
                <FormField label="모델 등급">
                  <select className="afs-input" value={d.model_tier}
                    onChange={(e) => set('model_tier', e.target.value)}>
                    {Object.entries(MODEL_TIER_KO).map(([k, v]) => (
                      <option key={k} value={k}>{v}</option>
                    ))}
                  </select>
                </FormField>
                <FormField label="비용에 대한 메모"
                  hint="한도를 여기서 강제하지는 않습니다 — 승인자가 읽는 근거입니다.">
                  <input className="afs-input" value={d.cost_note}
                    onChange={(e) => set('cost_note', e.target.value)} />
                </FormField>
              </>
            ) : S.id === 'gate' ? (
              <>
                <label style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
                  <input type="checkbox" checked={d.hotl_after}
                    onChange={(e) => set('hotl_after', e.target.checked)} />
                  <span>
                    <b>이 단계 뒤에 사람의 확인을 받습니다</b>
                    <br />
                    <small className="afs-muted">
                      끄면 다음 단계로 자동으로 넘어갑니다 — 되돌리기 어려운 산출물이 나오는
                      자리라면 켜 두십시오.
                    </small>
                  </span>
                </label>
              </>
            ) : S.id === 'test' ? (
              <Banner tone="warn" title="여기서 시험 실행을 하지 않습니다">
                자산을 <b>단독으로 시험 실행하는 경로가 서버에 없습니다.</b> 있는 척하는 버튼을
                두면 «테스트를 통과했다» 는 잘못된 안심을 줍니다.
                <br /><br />
                초안을 저장한 뒤 <b>프로젝트를 하나 만들어 이 정의로 돌려 보고</b>, 산출물이
                위에서 적은 «산출물» 과 같은지 확인하십시오. 확인 뒤에 승인을 요청하면 승인자가
                무엇을 근거로 승인하는지가 분명해집니다.
              </Banner>
            ) : (
              <>
                <label style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
                  <input type="checkbox" checked={d.submit_now}
                    onChange={(e) => set('submit_now', e.target.checked)} />
                  <span>
                    <b>저장하면서 승인을 요청합니다</b>
                    <br />
                    <small className="afs-muted">
                      끄면 «내 초안» 에 남습니다. 승인 요청은 나중에 목록에서도 할 수 있습니다.
                    </small>
                  </span>
                </label>
                <div style={{ marginTop: 12 }}>
                  <Panel kicker="REVIEW" title="이대로 만듭니다">
                    <div className="panel-body">
                      <p style={{ fontSize: 13, margin: 0 }}>
                        <b>{d.name_ko || '(이름 없음)'}</b>
                        {' · '}{d.visibility === 'PERSONAL' ? '개인'
                          : d.visibility === 'ENTERPRISE' ? '전사' : '조직'}
                        {d.visibility !== 'PERSONAL' && ` (${d.owner_scope_id || '미지정'})`}
                      </p>
                      <p className="afs-muted" style={{ fontSize: 12, margin: '4px 0 0' }}>
                        산출물 {d.deliverable || '미기재'}
                        {!NA_STEPS[kind].includes('tools')
                          && ` · ${d.write_impact === 'writes' ? '쓰기 있음' : '읽기만'}`}
                        {!NA_STEPS[kind].includes('gate')
                          && ` · 승인 게이트 ${d.hotl_after ? '있음' : '없음'}`}
                      </p>
                    </div>
                  </Panel>
                </div>
              </>
            )}

            {block && (
              <p className="afs-warn-fg" style={{ fontSize: 12, marginTop: 10 }}>🔒 {block}</p>
            )}
          </div>
        </Panel>

        <div style={{ display: 'flex', gap: 8, marginTop: 14, justifyContent: 'flex-end' }}>
          <button className="secondary-button" disabled={i === 0 || busy}
            onClick={() => setI((n) => Math.max(0, n - 1))}>이전</button>
          {i < STEPS.length - 1 ? (
            <button className="primary-button" disabled={Boolean(block)}
              onClick={() => setI((n) => Math.min(STEPS.length - 1, n + 1))}>다음</button>
          ) : (
            <button className="primary-button" disabled={busy || !d.name_ko.trim()}
              onClick={() => setConfirmOpen(true)}>
              {busy ? '만드는 중…' : d.submit_now ? '만들고 승인 요청' : '초안으로 저장'}
            </button>
          )}
        </div>

        {confirmOpen && (
          <ConfirmInline open danger={false} title="이 정의를 만듭니다"
            body={<>
              {d.visibility === 'PERSONAL' ? (
                <>«{d.name_ko}» 를 <b>내 초안</b>으로 만듭니다 — 다른 사람에게는 보이지 않습니다.</>
              ) : (
                <>«{d.name_ko}» 를 <b>{d.owner_scope_id || '미지정'} 조직의 자산</b>으로 만듭니다.
                  승인되면 그 범위의 실행에 쓰입니다.</>
              )}
              {d.submit_now && <><br />저장과 동시에 <b>승인을 요청</b>합니다.</>}
            </>}
            confirmLabel={d.submit_now ? '만들고 승인 요청' : '초안으로 저장'}
            onCancel={() => setConfirmOpen(false)}
            onConfirm={() => { setConfirmOpen(false); void save(); }} />
        )}
      </div>
    </HubDialog>
  );
}
