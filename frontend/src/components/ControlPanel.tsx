import React, { useState, useEffect } from 'react';
import { useFactoryStore } from '../store/useFactoryStore';
// [트랙 E 7단계 전제] Sprint 명령의 조립·호출은 **한 곳**에서 한다. 새 Studio 와 같은
//   함수를 부른다 — 각자 조립하면 두 화면이 서로 다른 payload 를 보내게 된다.
import { downloadProjectArchive, newPlanningTaskId, pauseSprint, replanWbs, resumeAfterQuota,
  startPlanning } from '../factory/sprintActions';
import { API_BASE_URL } from '../lib/api';
//: ★ [2026-09-19 §1] «미확정» 판정과 원요청 조회 UI 는 **이미 있는 것을 그대로 쓴다.**
//:   여기서 잠금 엔진을 새로 만들면 두 화면의 규칙이 갈리고, 한쪽만 고쳐지는 날이 온다.
import { StudioExecutionRequests, useExecutionPending }
  from '../factory/StudioExecutionRequests';

/** 명령 결과를 «완료 시점의 화면» 에만, **세 갈래로** 말한다.
 *
 *  ⚠️⚠️ [2026-09-19 실측] 이 화면의 여덟 명령 자리가 각자 `res.ok`/`r.ok` 하나로 갈랐고,
 *    몇 곳은 결과를 아예 버렸다. 그러면 **UNKNOWN 이 REJECTED 와 같은 말**이 된다 —
 *    이 명령들의 UNKNOWN 은 「안 됐다」가 아니라 **「됐는지 모른다」**(응답 유실·5xx·문맥
 *    변경)이고, 실패라고 들으면 사용자는 다시 누를 수 있다.
 *  ★ [2026-09-20 정정] 실행 명령의 재전송은 **공용 계층이 이미 막는다**
 *    (`executeStudioCommand` 가 PAUSE/STOP 외 새 명령을 거절). 따라서 「유료 LLM 재실행」·
 *    「스냅샷 두 벌」은 **실측된 사건이 아니라 위험 가능성**이다 — 이 파일은 LLM 을
 *    한 번도 실행하지 않았다. 위험과 관찰을 섞지 않는다.
 *  ⚠️ `alert` 는 **전역**이다. 완료 시점의 열린 프로젝트가 아니면 **아무 말도 하지 않는다**
 *    — 남의 화면 위에 뜨면 그 사람은 자기 작업이 실패한 줄 안다.
 *  ★ 반환이 `'ok'` 일 때만 호출부가 후속 상태를 갱신한다. 나머지는 **상태를 건드리지 않는다**
 *    — 특히 미확정에서 진행 중 손잡이(`activeSprintId`)를 버리면 사용자가 진행을 보지도,
 *    멈추지도 못한다.
 */
type CommandVerdict = 'ok' | 'stale' | 'unknown' | 'failed';
function tellCommandResult(
  label: string, r: { ok: boolean; outcome?: string; message?: string }, requested: string,
): CommandVerdict {
  if (useFactoryStore.getState().currentProjectId !== requested) return 'stale';
  if (r.ok) return 'ok';
  const detail = r.message ? `\n\n${r.message}` : '';
  if (r.outcome === 'UNKNOWN') {
    alert(`⚠️ ${label} 요청의 결과를 확인하지 못했습니다. 다시 누르지 마십시오 — 같은 작업이 두 번 실행될 수 있습니다. 현재 상태를 먼저 확인하십시오.${detail}`);
    return 'unknown';
  }
  alert(`❌ ${label} 요청이 받아들여지지 않았습니다.${detail}`);
  return 'failed';
}


// 기본 실행 스프린트 전체 파이프라인 정의 (노드 id ↔ 라벨 ↔ 배정 에이전트명)
const DEFAULT_EXEC_PIPELINE = [
  { id: 'architect', label: 'Architect', agent: 'Architect' },
  { id: 'tech_lead', label: 'Tech Lead', agent: 'Tech_Lead' },
  { id: 'backend', label: 'Backend', agent: 'Backend' },
  { id: 'frontend', label: 'Frontend', agent: 'Frontend' },
  { id: 'codebuilder', label: 'Builder', agent: null as string | null },
  { id: 'reviewer', label: 'Supervisor', agent: null as string | null },
  { id: 'qa', label: 'QA', agent: 'QA' },
  { id: 'manualwriter', label: 'Manual', agent: null as string | null },
];

const DEFAULT_MACRO_STAGES: [string, string][] = [
  ["CLARIFICATION", "요구확인"], ["RFP", "요구정의"], ["PLANNING", "기획"], ["ARCHITECTURE", "아키텍처"], ["PMO", "작업분해"],
  ["TECH_SPEC", "기술설계"], ["EXECUTION", "구현"], ["BUILD", "빌드"], ["CODE_REVIEW", "검수"],
  ["QA", "QA"], ["MANUAL", "매뉴얼"],
];
const DEFAULT_NODE_MACRO: Record<string, number> = {
  Requirement_Interviewer: 0, RFP_Analyst: 1, Master_PM: 2, Architect: 3, Master_PMO: 4, Tech_Lead: 5,
  Backend: 6, Frontend: 6, CodeBuilder: 7, Reviewer: 8, QA: 9, ManualWriter: 10,
};
const DEFAULT_STAGE_MACRO: Record<string, number> = {
  CLARIFICATION: 0, RFP: 1, PLANNING: 2, ARCHITECTURE: 3, PMO: 4, TECH_SPEC: 5,
  EXECUTION: 6, BUILD: 7, CODE_REVIEW: 8, QA: 9, MANUAL: 10,
};

// 노드 id → Supervisor 채점 단계 키 (배지 표시용)
const STAGE_BY_NODE: Record<string, string> = {
  architect: 'ARCHITECTURE',
  tech_lead: 'TECH_SPEC',
  reviewer: 'CODE_REVIEW',
};

const getDynamicPipelineData = (templateData: any) => {
  if (!templateData || !templateData.agents || templateData.id === 'default') {
    return {
      execPipeline: DEFAULT_EXEC_PIPELINE,
      macroStages: DEFAULT_MACRO_STAGES,
      nodeMacro: DEFAULT_NODE_MACRO,
      stageMacro: DEFAULT_STAGE_MACRO,
    };
  }
  const agents = [...templateData.agents].sort((a: any, b: any) => a.order - b.order);
  const execPipeline = agents.map((a: any) => ({
    id: a.id.toLowerCase(),
    label: a.name_ko || a.id,
    agent: a.id,
  }));
  const macroStages: [string, string][] = agents.map((a: any) => [
    a.stage || a.id.toUpperCase(),
    a.name_ko || a.id
  ]);
  const nodeMacro: Record<string, number> = {};
  const stageMacro: Record<string, number> = {};
  agents.forEach((a: any, idx: number) => {
    nodeMacro[a.id] = idx;
    stageMacro[a.stage || a.id.toUpperCase()] = idx;
  });
  return { execPipeline, macroStages, nodeMacro, stageMacro };
};

const buildTaskPipeline = (requiredAgents: string[], execPipeline: any[], templateData: any, isFinalTask: boolean = false) => {
  const ra = (requiredAgents || []).map((a) => a.toLowerCase());
  const has = (agent: string) => ra.some((r) => r.includes(agent.toLowerCase()));
  
  if (!templateData || templateData.id === 'default') {
    const hasCode = has('Backend') || has('Frontend');
    return execPipeline.filter((n) => {
      if (n.id === 'codebuilder') return hasCode;
      if (n.id === 'reviewer') return true;
      if (n.id === 'manualwriter') return isFinalTask;
      if (n.id === 'qa') return has('QA') || isFinalTask;
      return n.agent ? has(n.agent) : false;
    });
  }
  
  if (ra.length === 0) return execPipeline;
  return execPipeline.filter(n => n.agent && has(n.agent));
};

// 토론·채점 단계(phase) → 표시 아이콘 (LIVE 배너용)
const PHASE_ICON: Record<string, string> = {
  draft: '✍️', critique: '🔍', revise: '♻️', scoring: '📊', scored: '✅',
};

const GUIDE_TEXT = "이 화면의 수정 요청 접수는 더 이상 쓰이지 않습니다.\n\n위쪽 「🏗 새 제작 화면」을 열고 「추가 작업 · 수정 요청」에서 어느 산출물을 고칠지 고른 뒤 제출하십시오.\n\n입력하신 내용은 이 화면에 그대로 두었습니다 — 자동으로 옮기지 않으니 **복사해서** 새 화면에 붙여 넣으십시오.";

export default function ControlPanel() {
  const [idea, setIdea] = useState("");
  const [masterData, setMasterData] = useState("");
  const [feedback, setFeedback] = useState("");
  const [resimParams, setResimParams] = useState("");
  const [isStarting, setIsStarting] = useState(false);

  
  const state = useFactoryStore((s) => s.state);
  const wbsData = useFactoryStore((s) => s.wbsData);
  const isWbsError = useFactoryStore((s) => s.isWbsError);
  const fetchWBS = useFactoryStore((s) => s.fetchWBS);
  const currentProjectId = useFactoryStore((s) => s.currentProjectId);
  //: ★★ [§1] 결과가 «미확정» 인 요청이 있으면 새 쓰기를 내보내지 않는다.
  //:   ⚠️ 공용 명령(`executeStudioCommand`)은 이미 첫 POST 전에 UNKNOWN 을 기록하고,
  //:     PAUSE/STOP 외의 새 명령을 **거절**한다. 그러니 버튼이 열려 있다고 해서 서버로
  //:     재전송되는 것은 아니다 — 문제는 사용자가 **왜 막혔는지 모르고, 원요청을 조회할
  //:     입구도 이 화면에 없다**는 것이었다. 그래서 잠금이 아니라 «보이게» 하는 일이다.
  //:   ⚠️ 일시정지·중단은 여기서 막지 않는다. 미확정 때야말로 멈출 수 있어야 한다
  //:     (공용 계층도 그 둘만 예외로 둔다).
  const executionPending = useExecutionPending(currentProjectId || '');
  const pendingReason = executionPending
    ? '결과가 미확정인 요청이 있습니다. 아래 «실행 요청 기록»에서 원래 요청을 조회한 뒤 진행하세요.'
    : '';

  const saveRelease = useFactoryStore((s) => s.saveRelease);
  const stopSprint = useFactoryStore((s) => s.stopSprint);
  
  const completedAgents = useFactoryStore((s) => s.completed_agents);
  const currentActivity = useFactoryStore((s) => s.currentActivity);
  const isWaitingForHuman = useFactoryStore((s) => s.state?.needs_revision);
  const clearSprintData = useFactoryStore((s) => s.clearSprintData);
  const activeSprintId = useFactoryStore((s) => s.activeSprintId);
  const setActiveSprintId = useFactoryStore((s) => s.setActiveSprintId);
  const hotlTaskId = useFactoryStore((s) => s.hotlTaskId);
  const isConnected = useFactoryStore((s) => s.isConnected);
  const isSuspendedQuota = useFactoryStore((s) => s.isSuspendedQuota);
  const suspendedTaskId = useFactoryStore((s) => s.suspendedTaskId);
  const clearSuspendedQuota = useFactoryStore((s) => s.clearSuspendedQuota);
  const currentTemplateData = useFactoryStore((s) => s.currentTemplateData);
  const lastSprintFailure = useFactoryStore((s) => s.lastSprintFailure);
  const clearSprintFailure = useFactoryStore((s) => s.clearSprintFailure);
  const fileInputRef = React.useRef<HTMLInputElement>(null);

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (event) => {
      const content = event.target?.result;
      if (typeof content === "string") {
        setMasterData(prev => prev ? prev + "\n\n" + content : content);
      }
    };
    reader.readAsText(file);
    // Reset input so the same file can be uploaded again if needed
    e.target.value = '';
  };
  
  const { execPipeline, macroStages: MACRO_STAGES, nodeMacro: NODE_MACRO, stageMacro: STAGE_MACRO } = getDynamicPipelineData(currentTemplateData);

  // 사용자가 접수시킨 요구사항(즉시 표시용 — 백엔드 state.initial_idea 가 도착하기 전 폴백)
  const [submittedIdea, setSubmittedIdea] = useState("");
  // "마지막 활동 N초 전" 상대시간 갱신용 틱
  const [nowTs, setNowTs] = useState(() => Date.now());

  useEffect(() => {
    if (currentProjectId) fetchWBS();
  }, [fetchWBS, currentProjectId]);

  useEffect(() => {
    // '경과 시간' 표시용 tick 은 실제 가동 중일 때만 - 유휴 상태에서 3초마다 패널 전체 재렌더 방지
    if (!activeSprintId && !currentActivity) return;
    const id = setInterval(() => setNowTs(Date.now()), 3000);
    return () => clearInterval(id);
  }, [activeSprintId, currentActivity]);

  const isDynamic = currentTemplateData && currentTemplateData.agents && currentTemplateData.id !== 'default' && currentTemplateData.pipeline_name !== '소프트웨어 개발 팩토리';

  const coreTasks = wbsData?.tasks?.filter((t: any) => !t.task_id?.startsWith('TASK_REV_')) || [];
  let totalTasks = coreTasks.length;
  let doneTasks = coreTasks.filter((t: any) => t.status === 'DONE').length;
  let progressPercent = totalTasks === 0 ? 0 : Math.round((doneTasks / totalTasks) * 100);

  if (!isDynamic && totalTasks === 0) {
    totalTasks = 5;
    const legacyStages = ["RFP", "PLANNING", "TECH_SPEC", "CODE_REVIEW", "QA", "END"];
    const curIdx = legacyStages.indexOf(state?.current_stage || "RFP");
    doneTasks = Math.max(0, curIdx);
    progressPercent = curIdx >= 0 ? Math.round((curIdx / (legacyStages.length - 1)) * 100) : 0;
    if (state?.supervisor_verdict) {
      progressPercent = 100;
      doneTasks = totalTasks;
    }
  }
  // ── 파이프라인 상태 표시(가동/대기/오류/완료) + 접수된 요구사항 ──
  const acceptedIdea = ((state as any)?.initial_idea || submittedIdea || "").trim();
  const supFb = (state?.supervisor_feedback || "").trim();
  const errorLike = /할당량|소진|LIMIT|UNKNOWN ERROR|중단/i.test(supFb);
  const lastActTs = currentActivity?.ts ? new Date(currentActivity.ts).getTime() : 0;
  const secsSinceAct = lastActTs ? Math.max(0, Math.round((nowTs - lastActTs) / 1000)) : null;

  let pipeStatus: { key: string; icon: string; label: string; cls: string; detail?: string };
  if (!isConnected) {
    pipeStatus = { key: "disconnected", icon: "🔌", label: "서버 연결 끊김 — 재연결 시도 중", cls: "bg-red-900/40 border-red-600 text-red-200" };
  } else if (errorLike && !activeSprintId) {
    // 할당량 소진/LLM 오류 등은 needs_revision 도 세팅되지만, '대기'가 아니라 '오류 정지'로 명확히 구분
    pipeStatus = { key: "error", icon: "🚨", label: "오류로 정지 — 재가동이 필요합니다", cls: "bg-red-900/40 border-red-600 text-red-200", detail: supFb };
  } else if (lastSprintFailure && !activeSprintId) {
    // 빌드 자가복구(3회) 소진 등 스프린트 최종 실패 - '완료' 위장 없이 실패로 표시 + 재시도 선택지 제공
    pipeStatus = {
      key: "failed", icon: "❌",
      label: `[${lastSprintFailure.taskId}] ${lastSprintFailure.error}`,
      cls: "bg-red-900/40 border-red-600 text-red-200",
      detail: (lastSprintFailure.detail || "").slice(0, 400) || undefined
    };
  } else if (hotlTaskId || (isWaitingForHuman && !activeSprintId)) {
    pipeStatus = { key: "hotl", icon: "⏸️", label: "HOTL (전문가 개입) 대기 중 — 승인 또는 피드백이 필요합니다", cls: "bg-amber-900/40 border-amber-500 text-amber-200" };
  } else if (activeSprintId) {
    const act = currentActivity?.detail
      || (currentActivity?.stage_label ? `${currentActivity.stage_label} ${currentActivity.phase || ""}`.trim() : "에이전트 작업 중");
    pipeStatus = { key: "running", icon: "⚙️", label: "가동 중", cls: "bg-emerald-900/40 border-emerald-500 text-emerald-200", detail: act };
  } else if (totalTasks > 0 && doneTasks === totalTasks) {
    pipeStatus = { key: "done", icon: "✅", label: "모든 단계 완료", cls: "bg-blue-900/40 border-blue-500 text-blue-200" };
  } else {
    pipeStatus = { key: "idle", icon: "💤", label: "대기 (가동 안 함)", cls: "bg-gray-800 border-gray-600 text-gray-400" };
  }

  // ── 라이브 진행 카드용 계산: 매크로 파이프라인 위치(%) + 단계 내 미니 국면(초안→비평→개정→채점) ──
  const completedIdx = (completedAgents || []).reduce((m: number, n: string) => Math.max(m, NODE_MACRO[n] ?? -1), -1);
  const activeStageIdx = currentActivity?.stage != null ? (STAGE_MACRO[currentActivity.stage] ?? -1) : -1;
  const curMacroIdx = Math.max(completedIdx, activeStageIdx);
  const macroPct = curMacroIdx >= 0 ? Math.round(((curMacroIdx + 1) / MACRO_STAGES.length) * 100) : 0;
  const curMacroLabel = curMacroIdx >= 0 ? MACRO_STAGES[Math.min(curMacroIdx, MACRO_STAGES.length - 1)][1] : "";

  const PHASE_STEPS = ["초안", "비평", "개정", "채점"];
  const phaseIdx = (() => {
    const p: string = currentActivity?.phase || "";
    if (p.startsWith("draft")) return 0;
    if (p.startsWith("critique")) return 1;
    if (p.startsWith("revise")) return 2;
    if (p.startsWith("scoring") || p.startsWith("scored")) return 3;
    return -1;
  })();
  // progressPercent calculated above

  const handleStartPlanning = async () => {
    if (!idea.trim()) return alert("💡 기획 아이디어를 입력해주세요.");
    if (!currentProjectId) return alert("프로젝트가 선택되지 않았습니다.");
    
    setIsStarting(true);
    const requested = currentProjectId;
    const uniquePlanningId = newPlanningTaskId();
    setActiveSprintId(uniquePlanningId);
    
    try {
      // ★ payload 조립은 `sprintActions.buildPlanningPayload` 하나가 담당한다.
      //   여기서 다시 적으면 새 Studio 와 스키마가 갈라진다.
      const r = await startPlanning(requested, idea, masterData, uniquePlanningId);
      // ⚠️ 예전에는 실패해도 «가동한 것처럼» 입력창을 비웠다. 실패를 말하고 입력을 남긴다.
      const verdict = tellCommandResult('기획 가동', r, requested);
      if (verdict !== 'ok') {
        //: ⚠️⚠️ 미확정에서는 `activeSprintId` 를 **버리지 않는다.** 접수됐을 수도 있고,
        //:   그 손잡이를 잃으면 사용자가 진행을 보지도 멈추지도 못한 채 다시 누르게 된다.
        if (verdict === 'failed') setActiveSprintId(null);
        return;
      }
      // 입력창은 비우되, 접수된 요구사항은 별도 보존하여 WBS 생성 전까지 화면에 유지한다.
      setSubmittedIdea(idea);
      setIdea("");
      setMasterData("");
    } catch (error) {
      //: ⚠️ 종전에는 console 에만 남겨 «눌렀는데 아무 일도 없는» 화면이 됐다.
      console.error("기획 가동 실패:", error);
      tellCommandResult('기획 가동',
        { ok: false, outcome: 'UNKNOWN', message: '연결을 확인하지 못했습니다.' }, requested);
    } finally {
      setIsStarting(false);
    }
  };

  // 📋 전체 WBS 를 새 창에 표 형태로 표시 (현재 wbsData 스냅샷)
  const openWbsWindow = () => {
    const tasks: any[] = wbsData?.tasks || [];
    if (!tasks.length) { alert("아직 WBS 가 없습니다. 기획(WBS 분할)을 먼저 가동하세요."); return; }
    const esc = (s: any) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c] || c));
    const rows = tasks.map((t, i) => {
      const st = String(t.status || "");
      const stCls = st === "DONE" ? "done" : st === "IN_PROGRESS" ? "prog" : "";
      return `<tr><td>${i + 1}</td><td>${esc(t.title || t.name || t.description || `작업 ${i + 1}`)}</td>`
        + `<td class="${stCls}">${esc(st)}</td><td>${esc((t.required_agents || []).join(", "))}</td><td>${esc(t.sprint_day ?? "")}</td></tr>`;
    }).join("");
    const projectLabel = wbsData?.project_name || '현재 프로젝트';
    const html = `<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>WBS · ${esc(projectLabel)}</title>`
      + `<style>body{font-family:system-ui,-apple-system,sans-serif;background:#0f172a;color:#e2e8f0;margin:0;padding:20px}`
      + `h1{font-size:17px;margin:0 0 14px}table{border-collapse:collapse;width:100%;font-size:13px}`
      + `th,td{border:1px solid #334155;padding:8px 10px;text-align:left;vertical-align:top}`
      + `th{background:#1e293b;position:sticky;top:0}tr:nth-child(even) td{background:#15213330}`
      + `.done{color:#4ade80;font-weight:700}.prog{color:#fbbf24;font-weight:700}</style></head><body>`
      + `<h1>📋 전체 WBS — ${esc(projectLabel)} <span style="color:#64748b;font-weight:400">(${tasks.length}개 태스크)</span></h1>`
      + `<table><thead><tr><th>#</th><th>태스크</th><th>상태</th><th>배정 에이전트</th><th>Sprint Day</th></tr></thead>`
      + `<tbody>${rows}</tbody></table></body></html>`;
    const w = window.open("", "omega_wbs", "width=920,height=720,resizable=yes,scrollbars=yes");
    if (!w) { alert("팝업이 차단되었습니다. 브라우저에서 이 사이트의 팝업을 허용해 주세요."); return; }
    w.document.open(); w.document.write(html); w.document.close(); w.focus();
  };

  // 빌드 자가복구(3회) 소진 실패 태스크의 재시도 - 직전 빌드 오류(build_error_log)는 상태에 남아 있어
  // 개발자 노드가 자동으로 프롬프트에 반영한다. withFeedback 이면 사용자의 추가 지시를 재작업 지시로 주입.
  const handleRetryFailedTask = async (withFeedback: boolean) => {
    if (!lastSprintFailure || !currentProjectId) return;
    const taskId = lastSprintFailure.taskId;
    let fb = "";
    if (withFeedback) {
      fb = window.prompt("재시도 시 에이전트에게 전달할 추가 지시를 입력하세요\n(예: 'X 라이브러리 대신 표준 API 사용', '해당 기능은 단순화해도 됨')") || "";
      if (!fb.trim()) return;
    }
    setIsStarting(true);
    const requested = currentProjectId;
    clearSprintData(); // lastSprintFailure 포함 초기화
    setActiveSprintId(taskId);
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/factory/${currentProjectId}/sprint/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          task_id: taskId,
          project_state_payload: {
            ...(state || {}),
            // ⚠️ schema_version 은 싣지 않는다 — 상태 스키마는 서버가 정한다.
            //   옛 화면이 옛 버전을 되돌려 보내면 서버 상태가 조용히 다운그레이드된다.
            schema_version: undefined,
            project_name: wbsData?.project_name || currentProjectId,
            current_sprint_task_id: taskId,
            factory_mode: taskId.startsWith('TASK_REV_') ? "REVISION" : "EXECUTION",
            ...(fb.trim() ? {
              // 기존 재작업 경로(Tech_Lead/개발자 노드가 reviewer_feedback 을 주입받음)를 그대로 활용
              reviewer_decision: "REWORK_DEV",
              reviewer_feedback: `[사용자 재시도 지시]\n${fb.trim()}`,
              human_feedback_queue: [{ task_id: taskId, feedback: fb.trim() }],
            } : {}),
          }
        })
      });
      if (useFactoryStore.getState().currentProjectId !== requested) return;
      //: ⚠️ 종전에는 거절당해도 **아무 말이 없었다** — 화면만 조용히 「가동 중 아님」으로
      //:   돌아가고, 사용자는 재시도가 왜 안 되는지 알 길이 없었다.
      if (!res.ok) {
        setActiveSprintId(null);
        alert(`❌ 재시도를 시작하지 못했습니다(서버 응답 ${res.status}).`);
      }
    } catch (error) {
      console.error("실패 태스크 재시도 실패:", error);
      if (useFactoryStore.getState().currentProjectId !== requested) return;
      //: ⚠️ 여기서는 손잡이를 비운다 — 접수 자체를 확인하지 못했고, 이 옛 경로에는
      //:   되찾을 원키가 없다. 대신 **다시 보내지 않는다**는 것을 말한다.
      setActiveSprintId(null);
      alert("⚠️ 재시도 요청의 결과를 확인하지 못했습니다. 자동으로 다시 보내지 않습니다. 현재 상태를 먼저 확인하십시오.");
    } finally {
      setIsStarting(false);
    }
  };

  const handleStartSprint = async (targetTask: any) => {
    if (!confirm(`${targetTask.title || '선택한 작업'}\n해당 스프린트를 가동/재가동하시겠습니까?`)) return;
    if (!currentProjectId) return;
    
    setIsStarting(true);
    const requested = currentProjectId;
    clearSprintData();
    setActiveSprintId(targetTask.task_id);

    try {
      //: ⚠️⚠️ 종전에는 `await fetch(...)` 로 **응답을 통째로 버렸다.** 서버가 409·403 을
      //:   줘도 화면은 이미 `activeSprintId` 를 세워 「가동 중」으로 보였다.
      const res = await fetch(`${API_BASE_URL}/api/v1/factory/${requested}/sprint/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          task_id: targetTask.task_id,
          project_state_payload: {
            ...(state || {}),
            // ⚠️ schema_version 은 싣지 않는다(위와 같은 이유) — 서버가 정한다.
            schema_version: undefined,
            project_name: wbsData.project_name || currentProjectId,
            current_sprint_task_id: targetTask.task_id,
            factory_mode: targetTask.task_id.startsWith('TASK_REV_') ? "REVISION" : "EXECUTION",
          }
        })
      });
      if (useFactoryStore.getState().currentProjectId !== requested) return;
      if (!res.ok) {
        setActiveSprintId(null);
        alert(`❌ 작업을 가동하지 못했습니다(서버 응답 ${res.status}).`);
      }
    } catch (error) {
      console.error("스프린트 가동 실패:", error);
      if (useFactoryStore.getState().currentProjectId !== requested) return;
      setActiveSprintId(null);
      alert("⚠️ 가동 요청의 결과를 확인하지 못했습니다. 자동으로 다시 보내지 않습니다. 현재 상태를 먼저 확인하십시오.");
    } finally {
      setIsStarting(false);
    }
  };

  const handlePauseSprint = async (targetTask: any) => {
    if (!currentProjectId) return;
    const requested = currentProjectId;
    //: ★ 새 Studio 와 **같은 공용 명령**을 쓴다. 종전에는 이 화면만 `/sprint/pause` 로 직접
    //:   POST 하고 **응답을 보지 않았다** — 실행 중 작업이 없어 409 가 와도 아래에서
    //:   `activeSprintId` 를 비워 화면은 「멈췄다」로 보였다(2026-09-19 실측 409).
    let r;
    try {
      r = await pauseSprint(requested, targetTask.task_id);
    } catch (error) {
      console.error("스프린트 일시정지 실패:", error);
      r = { ok: false, outcome: 'UNKNOWN', message: '연결을 확인하지 못했습니다.' };
    }
    if (tellCommandResult('일시정지', r, requested) !== 'ok') return;
    setActiveSprintId(null);
  };

  // [R2] 쿼터 회복 후 SUSPENDED 지점부터 재개(처음부터 재실행이 아님)
  const handleResumeQuota = async () => {
    if (!currentProjectId) return;
    if (!suspendedTaskId) return alert("재가동할 보류 태스크 정보가 없습니다. 페이지를 새로고침해 주세요.");
    const requested = currentProjectId;
    setIsStarting(true);
    try {
      const r = await resumeAfterQuota(requested, suspendedTaskId);
      //: ⚠️ 미확정이면 `clearSuspendedQuota()` 를 **부르지 않는다** — 보류 지점을 지우면
      //:   다음 재개가 「처음부터」로 떨어지고, 이미 쓴 LLM 비용을 다시 쓴다.
      if (tellCommandResult('재가동', r, requested) !== 'ok') return;
      setActiveSprintId(suspendedTaskId);
      clearSuspendedQuota();
    } catch (error) {
      console.error("쿼터 재가동 실패:", error);
      tellCommandResult('재가동',
        { ok: false, outcome: 'UNKNOWN', message: '연결을 확인하지 못했습니다.' }, requested);
    } finally {
      setIsStarting(false);
    }
  };

  /** ★★ [§10.1 「수정 요구」 · 2026-09-19] **여기서는 아무 데도 보내지 않는다.**
   *
   *  ⚠️⚠️ 종전에는 `/sprint/revision` 에 POST 했다. 그런데 서버는 기준 산출물·저장
   *    초안·원키 없이 새 작업을 만드는 그 접수를 **닫았고**, 언제나 409 를 돌려준다
   *    (격리 서버 실측). 화면은 그걸 삼켜서 «눌러도 아무 일도 안 일어나는» 상태였다.
   *  ★ 안내를 보이려고 **실패할 요청을 보내지 않는다.** 닫힌 줄 아는 곳으로
   *    두드리는 것은 서버에도 감사 로그에도 쓸데없는 자관을 남긴다.
   *  ★ 새 편집기·새 계약을 이 화면에 **다시 구현하지 않는다.** 새 제작 화면의
   *    수정 요청이 기준 산출물 선택·권한·원키까지 이미 다룬다 — 두 벌이 되면 그중
   *    하나만 고쳐지는 날이 온다.
   *  ⚠️ 입력을 **지우지 않는다.** 자동으로 옮기지도 않는다 — 기준 산출물을
   *    사람이 골라야 하고, 새 화면의 기존 초안을 덮어쓰면 안 된다. */
  const handleSubmitFeedback = () => {
    if (!feedback.trim()) return alert("수정 사항을 입력해주세요.");
    if (!currentProjectId) return;
    alert("ℹ️ " + GUIDE_TEXT);
  };

  const renderPipelineTracker = (isPaused: boolean, task: any) => {
    const isFinalTask = coreTasks.length > 0 && task.task_id === coreTasks[coreTasks.length - 1].task_id;
    // 이 태스크에 배정된 에이전트만으로 파이프라인 구성 (PMO Task별 매핑 반영)
    const pipeline = buildTaskPipeline(task?.required_agents || [], execPipeline, currentTemplateData, isFinalTask);
    const currentAgentIdx = pipeline.findIndex(a => !completedAgents.map((ca: string) => ca.toLowerCase()).includes(a.id));

    // 단계별 최신 Supervisor 판정 맵 (criteria_log에서 추출)
    const verdictByStage: Record<string, string> = {};
    ((state?.criteria_log as any[]) || []).forEach((e) => { if (e?.stage) verdictByStage[e.stage] = e.verdict; });
    const supFb = state?.supervisor_feedback || '';
    const assigned = (task?.required_agents || []).join(', ') || '—';

    return (
      <div className={`mt-3 pt-3 border-t ${isPaused ? 'border-orange-900/50' : 'border-blue-900/50'}`}>
        <div className={`text-[10px] mb-1 font-bold tracking-wider ${isPaused ? 'text-orange-300' : 'text-blue-300'}`}>
          🤖 AGENT PIPELINE STATUS
        </div>
        <div className="text-[9px] text-gray-500 mb-3">배정 에이전트: <span className="text-gray-300">{assigned}</span></div>
        <div className="flex justify-between items-center relative px-2 mb-2">
          <div className="absolute top-2.5 left-3 right-3 h-[2px] bg-gray-700 -z-10"></div>
          {pipeline.map((agent, idx) => {
            const isCompleted = completedAgents.map((ca: string) => ca.toLowerCase()).includes(agent.id);
            const isCurrent = currentAgentIdx === idx || (currentAgentIdx === -1 && idx === pipeline.length - 1 && !isCompleted);
            const isBottleneck = isCurrent && isWaitingForHuman && !isPaused;

            let circleClass = "bg-gray-800 border-gray-600";
            let textClass = "text-gray-500";

            if (isCompleted) {
              circleClass = "bg-green-500 border-green-400 opacity-50"; textClass = "text-green-500 opacity-50";
            } else if (isPaused && isCurrent) {
              circleClass = "bg-orange-500 border-orange-400"; textClass = "text-orange-400 font-bold";
            } else if (isBottleneck) {
              circleClass = "bg-red-500 border-red-400 animate-pulse"; textClass = "text-red-400 font-bold";
            } else if (isCurrent) {
              circleClass = "bg-blue-500 border-blue-400 animate-pulse"; textClass = "text-blue-300 font-bold";
            }

            // Supervisor 채점 배지 (점수 + 판정색 + 토론 라운드)
            const stageKey = STAGE_BY_NODE[agent.id];
            const score = stageKey ? state?.stage_scores?.[stageKey] : undefined;
            const verdict = stageKey ? verdictByStage[stageKey] : undefined;
            const rounds = stageKey ? state?.debate_rounds_used?.[stageKey] : undefined;
            let badgeColor = 'text-gray-400';
            if (verdict === 'PASS') badgeColor = 'text-green-400';
            else if (verdict === 'REWORK') badgeColor = 'text-amber-400';
            else if (verdict === 'ROLLBACK') badgeColor = 'text-red-400';
            const hasBadge = stageKey && typeof score === 'number';

            return (
              <div key={agent.id} className="flex flex-col items-center gap-1 z-10 relative bg-gray-800">
                <div className={`w-5 h-5 rounded-full border-2 ${circleClass}`}></div>
                <span className={`text-[9px] absolute top-6 whitespace-nowrap ${textClass}`}>{agent.label}</span>
                {hasBadge && (
                  <span
                    className={`text-[8px] absolute top-11 whitespace-nowrap font-bold ${badgeColor}`}
                    title={verdict ? `${stageKey} 채점: ${(score as number).toFixed(2)} / ${verdict}${rounds ? ` · 토론 ${rounds}R` : ''}${verdict !== 'PASS' && supFb ? ` · ${supFb}` : ''}` : ''}
                  >
                    {(score as number).toFixed(1)}{rounds ? ` ×${rounds}` : ''} {verdict === 'PASS' ? '✓' : verdict ? '!' : ''}
                  </span>
                )}
              </div>
            );
          })}
        </div>
        <div className="h-12"></div>
      </div>
    );
  };

  const handleStopSprint = async () => {
    if (!currentProjectId || !activeSprintId) return;
    if (!confirm("실행 중인 에이전트를 강제로 정지하시겠습니까? (이전 체크포인트까지만 저장됩니다)")) return;
    //: ⚠️⚠️ 종전에는 **결과를 통째로 버리고** 무조건 「정지했습니다」라고 말했다.
    //:   실행 중 작업이 없으면 서버는 409 를 준다(실측) — 그런데 사용자는 멈춘 줄 안다.
    //:   가동이 계속 도는 동안 멈췄다고 믿는 것이 이 화면에서 가장 위험한 거짓이다.
    const requested = currentProjectId;
    const r = await stopSprint(requested, activeSprintId);
    if (tellCommandResult('가동 정지', r, requested) !== 'ok') return;
    alert(`✅ 가동 정지를 접수했습니다.\n\n${r.message}`);
  };

  return (
    <div className="flex flex-col h-full bg-gray-800 text-gray-200">
      <div className="p-4 border-b border-gray-700 bg-gray-900 shrink-0">
        <h2 className="text-lg font-bold text-gray-100 flex items-center gap-2">
          ⚙️ 작업 실행
          {currentTemplateData && currentTemplateData.id !== 'default' && (
            <span className="text-[10px] bg-purple-900/60 text-purple-300 border border-purple-700 px-2 py-0.5 rounded-full shadow-sm ml-2">
              🛠️ {currentTemplateData.name || currentTemplateData.id} 템플릿
            </span>
          )}
        </h2>
      </div>

      {/* ★★ [§1-2] 미확정이면 **기존** 원요청 조회·복구 UI 를 그대로 띄운다.
          ⚠️ 새 패널·새 조회를 만들지 않는다. 자동 재전송도, 새 원키 발급도 하지 않는다 —
            사용자가 할 일은 «원래 요청의 결과를 확정하는 것» 하나다.
          ⚠️ 미확정일 때만 렌더한다. 새 제작 화면이 함께 떠 있으면 같은 컴포넌트가 둘이
            되는데, 이 컴포넌트는 주기 조회를 하지 않으므로 마운트당 GET 한 번이다. */}
      {currentProjectId && pendingReason && (
        <div className="p-4 border-b border-amber-700/40 bg-amber-950/30 shrink-0">
          <p className="text-xs font-bold text-amber-200 mb-2" role="status">⚠️ {pendingReason}</p>
          <p className="text-[11px] text-amber-100/80 mb-2">
            접수 여부가 확정될 때까지 새 작업 요청은 잠급니다. <b>일시정지·중단은 그대로 쓸 수
            있습니다.</b> 같은 요청을 자동으로 다시 보내지 않습니다.
          </p>
          <StudioExecutionRequests projectId={currentProjectId} />
        </div>
      )}

      {currentActivity && (
        <div className="px-4 py-2 bg-blue-950/60 border-b border-blue-800 flex items-center gap-2 shrink-0">
          <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse shrink-0"></span>
          <span className="text-[10px] text-red-300 font-bold tracking-widest shrink-0">LIVE</span>
          <span className="text-xs text-gray-100 truncate">
            {(PHASE_ICON[currentActivity.phase] || '⚙️')} {currentActivity.detail}
          </span>
        </div>
      )}

      <div className="flex-1 overflow-y-auto p-4">
        {isWbsError && (
          <div className="mb-4 p-3 bg-red-900/50 border border-red-500 rounded text-sm text-red-200">
            🚨 서버 통신 단절. 새로고침 해주세요.
          </div>
        )}

        {isSuspendedQuota && (
          <div className="mb-4 p-4 bg-orange-900/50 border border-orange-500 rounded text-sm text-orange-200 shadow-lg">
            <h3 className="font-bold text-base mb-2">🚨 AI 사용 한도를 모두 사용했습니다</h3>
            <p className="mb-3 text-xs leading-relaxed opacity-90">
              현재 연결된 AI 모델의 호출 한도를 모두 사용했습니다. <br/>
              가동 중이던 제작 작업은 현재 상태 그대로 안전하게 <strong>일시 정지</strong>되었습니다.
              내일 할당량이 갱신된 후 보류된 태스크를 재가동하거나, 새로운 API 키를 등록해 주세요.
            </p>
            <div className="flex gap-2">
              <button
                onClick={handleResumeQuota}
                disabled={isStarting || !suspendedTaskId || !!pendingReason}
                title={pendingReason || "쿼터 회복 후, 처음부터가 아니라 중단된 지점부터 이어서 재가동합니다."}
                className="px-3 py-1.5 bg-orange-600 hover:bg-orange-500 disabled:opacity-50 disabled:cursor-not-allowed rounded text-xs font-bold text-white transition-colors"
              >▶️ 중단 지점부터 재가동</button>
              <button onClick={clearSuspendedQuota} className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 rounded text-xs font-bold text-gray-100 transition-colors">⏸️ 알림 닫기</button>
            </div>
          </div>
        )}

        {/* 🚦 파이프라인 상태 배너 — 가동/대기/오류 명확 표시 + 접수된 요구사항(WBS 생성 전까지 유지) */}
        <div className={`mb-4 rounded border p-3 ${pipeStatus.cls}`}>
          <div className="flex flex-wrap items-center gap-2 text-sm font-bold">
            <span className={`shrink-0 ${pipeStatus.key === "running" ? "animate-pulse" : ""}`}>{pipeStatus.icon}</span>
            <span className="break-words w-full sm:w-auto flex-1">{pipeStatus.label}</span>
            {pipeStatus.key === "running" && secsSinceAct !== null && (
              <span className="ml-auto text-[11px] font-normal opacity-80 break-words mt-1 w-full sm:w-auto sm:mt-0 flex items-center gap-2">
                <span>마지막 활동 {secsSinceAct}초 전{secsSinceAct > 60 ? " · 응답 지연(할당량/점검 확인)" : ""}</span>
                <button 
                  onClick={handleStopSprint}
                  className="px-2 py-1 bg-red-600 hover:bg-red-500 text-white rounded text-[10px] font-bold"
                  title="서버 오류 또는 지연 시 강제로 실행을 중단합니다."
                >
                  🛑 강제 정지
                </button>
              </span>
            )}
          </div>
          {pipeStatus.detail && (
            <div className="mt-1 text-xs opacity-90 break-words">현재: {pipeStatus.detail}</div>
          )}
          {/* ❌ 자가복구 소진 실패 - 후속 처리 선택지 */}
          {pipeStatus.key === "failed" && (
            <div className="mt-2 pt-2 border-t border-white/10 flex flex-wrap gap-2">
              <button
                disabled={isStarting || !!pendingReason}
                onClick={() => handleRetryFailedTask(false)}
                className="px-2.5 py-1.5 bg-red-600 hover:bg-red-500 disabled:bg-gray-700 text-white rounded text-[11px] font-bold"
                title={pendingReason || "직전 빌드 오류 내용을 에이전트에게 전달하며 태스크를 재가동합니다."}
              >
                🔁 오류 반영 재시도
              </button>
              <button
                disabled={isStarting || !!pendingReason}
                onClick={() => handleRetryFailedTask(true)}
                className="px-2.5 py-1.5 bg-amber-600 hover:bg-amber-500 disabled:bg-gray-700 text-white rounded text-[11px] font-bold"
                title={pendingReason || "추가 지시(우회 방법, 범위 축소 등)를 입력해 함께 전달합니다."}
              >
                💬 지시 추가 후 재시도
              </button>
              <button
                disabled={isStarting}
                onClick={clearSprintFailure}
                className="px-2.5 py-1.5 bg-gray-700 hover:bg-gray-600 text-gray-200 rounded text-[11px] font-bold"
                title="태스크를 FAILED 상태로 보류합니다. 태스크 목록에서 언제든 재가동할 수 있습니다."
              >
                ⏸ 보류(닫기)
              </button>
            </div>
          )}
          {acceptedIdea && totalTasks === 0 && (
            <div className="mt-2 pt-2 border-t border-white/10 text-xs">
              <span className="opacity-70">📨 접수된 요구사항 (작업 분해 전까지 표시)</span>
              <div className="mt-1 text-gray-100 whitespace-pre-wrap break-words leading-relaxed">{acceptedIdea}</div>
            </div>
          )}
        </div>

        {/* ⚡ 라이브 진행 카드 — 가동 중 '지금 무엇을 하는지' 애니메이션 + 진행률 시각화 */}
        {pipeStatus.key === "running" && (
          <div className="mb-4 rounded-lg border border-emerald-700/60 bg-gray-900/80 p-4">
            <style>{`@keyframes omega-indet{0%{left:-42%}100%{left:100%}}`}</style>

            {/* 헤더: 회전 스피너 + 현재 단계 + 마지막 활동 경과 */}
            <div className="flex items-center gap-2 mb-3">
              <span className="inline-block w-4 h-4 border-2 border-emerald-400 border-t-transparent rounded-full animate-spin"></span>
              <span className="text-sm font-bold text-emerald-300">{curMacroLabel || "에이전트 작업"} 진행 중</span>
              {secsSinceAct !== null && (
                <span className="ml-auto text-[11px] text-gray-400">마지막 활동 {secsSinceAct}s 전{secsSinceAct > 60 ? " ⚠️" : ""}</span>
              )}
            </div>

            {/* 매크로 파이프라인 진행률 (수치 %) */}
            <div className="flex justify-between text-[11px] text-gray-400 mb-1">
              <span>파이프라인 {Math.min(curMacroIdx + 1, MACRO_STAGES.length)}/{MACRO_STAGES.length} · {curMacroLabel || "—"}</span>
              <span className="font-bold text-emerald-300">{macroPct}%</span>
            </div>
            <div className="w-full h-2 bg-gray-950 rounded-full border border-gray-700 overflow-hidden mb-3">
              <div className="h-full bg-emerald-500 transition-all duration-700 ease-out" style={{ width: `${macroPct}%` }}></div>
            </div>

            {/* 단계 내 미니 국면: 초안 → 비평 → 개정 → 채점 (현재 pulse) */}
            {phaseIdx >= 0 && (
              <div className="flex items-center flex-wrap gap-1 mb-3">
                {PHASE_STEPS.map((label, i) => (
                  <div key={label} className="flex items-center gap-1">
                    <span className={`px-2 py-1 rounded text-[11px] font-bold border transition-colors ${
                      i < phaseIdx ? "border-emerald-700 text-emerald-400 bg-emerald-900/30"
                      : i === phaseIdx ? "border-emerald-400 text-emerald-100 bg-emerald-700/50 animate-pulse"
                      : "border-gray-700 text-gray-500"}`}>
                      {i < phaseIdx ? "✓" : i === phaseIdx ? "●" : "○"} {label}
                    </span>
                    {i < PHASE_STEPS.length - 1 && <span className="text-gray-600 text-xs px-0.5">→</span>}
                  </div>
                ))}
                {currentActivity?.round ? <span className="ml-1 text-[11px] text-gray-500">{currentActivity.round}R</span> : null}
              </div>
            )}

            {/* 살아있음 표시: 항상 흐르는 막대 (진행 상황과 무관하게 '작동 중'임을 보장) */}
            <div className="relative w-full h-1.5 bg-gray-800 rounded-full overflow-hidden mb-2">
              <div className="absolute top-0 h-full w-2/5 bg-emerald-400/70 rounded-full" style={{ animation: "omega-indet 1.3s linear infinite" }}></div>
            </div>

            {/* 실시간 내레이션 (최근 활동만 — 오래되면 숨김) */}
            {currentActivity?.detail && secsSinceAct !== null && secsSinceAct < 90 && (
              <div className="text-xs text-gray-300 leading-relaxed break-words">💬 {currentActivity.detail}</div>
            )}
          </div>
        )}

        {!wbsData && !state?.project_name ? (
          <div className="flex flex-col gap-2">
            <label className="text-sm font-semibold text-gray-400">💡 1. 신규 앱 기획</label>
            <textarea 
              value={idea} onChange={(e) => setIdea(e.target.value)} disabled={isStarting || activeSprintId !== null}
              placeholder="프로젝트 아이디어를 입력하세요..."
              className="w-full h-20 bg-gray-950 border border-gray-700 rounded p-3 text-sm focus:outline-none focus:border-blue-500 resize-none disabled:opacity-50"
            />
            <div className="mt-4 border border-gray-700 rounded-lg bg-gray-800/50 p-4">
              <div className="flex items-center justify-between mb-3">
                <label className="text-sm font-semibold text-gray-300 flex items-center gap-2">
                  <span>🔗 데이터 소스 및 외부 지식 연결</span>
                  <span className="text-[10px] bg-blue-900/50 text-blue-300 px-2 py-0.5 rounded border border-blue-800">외부 연동 준비 중</span>
                </label>
              </div>
              
              <div className="flex gap-2 mb-3">
                <input 
                  type="file" 
                  accept=".txt,.md,.json,.csv" 
                  ref={fileInputRef} 
                  onChange={handleFileUpload} 
                  className="hidden" 
                />
                <button 
                  onClick={() => fileInputRef.current?.click()}
                  disabled={isStarting || activeSprintId !== null}
                  className="flex-[2] bg-indigo-900/40 hover:bg-indigo-800/60 border border-indigo-700 rounded py-2 text-xs text-indigo-300 flex items-center justify-center gap-2 font-bold transition-colors" 
                  title="로컬 텍스트/마크다운 파일을 선택하여 시뮬레이션 환경에 주입합니다."
                >
                  <span>📁 로컬 문서 업로드 (MCP 연동)</span>
                </button>
                <button className="flex-1 bg-blue-900/20 border border-blue-800 rounded py-2 text-xs text-blue-400 flex items-center justify-center gap-2 font-bold cursor-default">
                  <span>📝 텍스트 직접 입력</span>
                </button>
              </div>

              <textarea 
                value={masterData} onChange={(e) => setMasterData(e.target.value)} disabled={isStarting || activeSprintId !== null}
                placeholder="시뮬레이션 전사 환경 변수(환율, 단가, 목표 KPI 등)나 레퍼런스 문서를 직접 입력하세요..."
                className="w-full h-24 bg-gray-950 border border-gray-700 rounded p-3 text-sm focus:outline-none focus:border-blue-500 resize-none disabled:opacity-50"
              />
            </div>
            <button 
              onClick={handleStartPlanning}
              disabled={isStarting || !idea.trim() || activeSprintId !== null || !!pendingReason}
              title={pendingReason || undefined}
              className="mt-2 w-full bg-purple-600 hover:bg-purple-500 disabled:bg-gray-700 font-bold py-3 rounded transition-colors"
            >
              {isStarting ? "기획 중..." : "🎯 기획 및 작업분해 시작"}
            </button>
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            <div className="flex flex-col mb-2 border-b border-gray-700 pb-3">
              <div className="flex justify-between items-end mb-1">
                <label className="text-sm font-semibold text-gray-400">📋 2. 작업 실행 현황</label>
                <span className="text-xs font-bold text-blue-400">진척률: {progressPercent}% ({doneTasks}/{totalTasks})</span>
              </div>
              <div className="w-full bg-gray-950 rounded-full h-2 mt-1 border border-gray-700">
                <div className="bg-blue-500 h-2 rounded-full transition-all duration-500 ease-out" style={{ width: `${progressPercent}%` }}></div>
              </div>
              <div className="mt-2 flex gap-2">
                <button
                  onClick={openWbsWindow}
                  className="text-[11px] font-bold text-gray-200 bg-gray-700 hover:bg-gray-600 px-2.5 py-1 rounded transition-colors"
                  title="전체 작업계획을 새 창에 표로 봅니다"
                >
                  ↗ 전체 작업계획 보기
                </button>
                {/* 🔁 WBS 재분할 - 기획 산출물(PRD/아키텍처)은 그대로 두고 태스크 분할만 다시 수행 */}
                {!!(state as any)?.prd_summary && !activeSprintId && (
                  <button
                    onClick={async () => {
                      if (!currentProjectId) return;
                      if (!confirm("기획 산출물(요구정의/기획서/화면설계/아키텍처)은 유지한 채 작업만 다시 나눕니다.\n(작업 분해가 실패했거나 구성이 적절하지 않을 때 사용)\n진행할까요?")) return;
                      try {
                        const requested = currentProjectId;
                        const r = await replanWbs(requested);
                        //: ⚠️ 미확정이면 `clearSprintData()` 를 부르지 않는다 — 접수됐을 수도
                        //:   있는 작업의 기록을 지우면 결과를 확인할 길이 사라진다.
                        if (tellCommandResult('작업 재분할', r, requested) !== 'ok') return;
                        clearSprintData();
                        if (r.taskId) setActiveSprintId(r.taskId);
                      } catch (e) {
                        console.error("WBS 재분할 실패:", e);
                        tellCommandResult('작업 재분할',
                          { ok: false, outcome: 'UNKNOWN', message: '연결을 확인하지 못했습니다.' },
                          currentProjectId);
                      }
                    }}
                    className="text-[11px] font-bold text-amber-200 bg-amber-900/50 hover:bg-amber-800/60 border border-amber-700/50 px-2.5 py-1 rounded transition-colors disabled:opacity-50"
                    disabled={!!pendingReason}
                    title={pendingReason || "기획은 유지하고 작업 분해만 다시 수행합니다."}
                  >
                    🔁 작업 다시 나누기
                  </button>
                )}
              </div>
            </div>

            {/* 🚀 모든 단계 완료 시 — 고객 수용검수(Supervisor) 연동 + 최종 결과물 저장(배포) */}
            {progressPercent === 100 && currentProjectId && (
              <div className="flex flex-col gap-2 mb-1">
                {/* QA(수행사 통합검수) 보조 표시 */}
                <div className="text-[11px] text-gray-400">
                  🧪 QA(통합검수): {state?.qa_verdict === "PASS" ? "✅ 통과" : state?.qa_verdict === "FAIL" ? "❌ 미통과" : "—"}
                </div>
                {/* Supervisor(고객사 수용검수) = 완료/배포 판단 기준 */}
                {state?.supervisor_verdict === "PASS" ? (
                  <div className="rounded border border-emerald-700/50 bg-emerald-900/20 p-2.5 text-xs text-emerald-200">
                    ✅ <b>고객 수용검수 통과</b> — RFP 요구가 충족되어 인도·배포 가능한 완료 상태입니다. (우측 '수용검수' 탭 참조)
                  </div>
                ) : state?.supervisor_verdict === "REJECT" ? (
                  <div className="rounded border border-red-600 bg-red-900/30 p-2.5 text-xs text-red-200 leading-relaxed">
                    🚨 <b>고객 수용검수 반려</b> — RFP 대비 요구 미충족/완성도 미달입니다. 인도·배포 부적합 — 보완을 권장합니다. (우측 '수용검수' 탭에서 사유 확인)
                  </div>
                ) : (
                  <div className="rounded border border-gray-600 bg-gray-800 p-2.5 text-xs text-gray-400">
                    ℹ️ 수용검수 정보 없음 — 고객사 최종 수용검수(Supervisor)가 아직 수행되지 않았을 수 있습니다.
                  </div>
                )}
                <button
                  onClick={async () => {
                    const accepted = state?.supervisor_verdict === "PASS";
                    //: ★ [§1-6] 라벨을 새 화면과 맞춘다. 이 명령은 **검토용 버전 저장**이고
                    //:   배포·운영 승격은 별도 절차다 — 「배포」라고 부르면 이것으로 끝난 줄 읽는다.
                    const msg = accepted
                      ? "이 프로젝트의 결과물을 검토용 버전으로 저장하시겠습니까?\n\n배포·운영 승격은 별도 절차입니다."
                      : "⚠️ 고객 수용검수를 통과하지 못한 상태입니다 — 요구가 모두 충족되지 않았습니다.\n그래도 검토용 버전으로 저장하시겠습니까?\n\n배포·운영 승격은 별도 절차입니다.";
                    if (!confirm(msg)) return;
                    // ⚠️ `saveRelease` 는 이제 **이유를 담은 객체**를 돌려준다. `if (r)` 로 검사하면
                    //   객체는 항상 truthy 라 실패해도 «저장되었습니다» 가 뜬다 — `tsc` 는 이것을
                    //   잡지 못한다(2026-08-07 실측). 반드시 `r.ok` 를 본다.
                    const requested = currentProjectId;
                    const r = await saveRelease(requested);
                    //: ⚠️ [검토 2026-09-19] `alert` 는 **전역**이다. 완료 «시점» 의 화면이 아직
                    //:   그 프로젝트인지 보고 나서 말한다 — 아니면 남의 화면 위에 뜼다.
                    if (useFactoryStore.getState().currentProjectId !== requested) return;
                    if (r.ok) {
                      //: 서버·공용 함수가 준 문구를 그대로 싣는다. 화면이 「저장되었습니다」로
                      //:   **지어내지 않는다** — 접수와 저장 완료는 다르고, 목록이 정본이다.
                      alert(`✅ 검토용 버전 저장을 접수했습니다.\n\n${r.message}`);
                    } else if (r.outcome === 'UNKNOWN') {
                      //: ⚠️⚠️ **미확정을 「실패」로 단정하지 않는다.** 이 명령의 UNKNOWN 은
                      //:   「안 됐다」가 아니라 「됐는지 모른다」다(응답 유실·5xx·문맥 변경).
                      //:   ★ [2026-09-19 Codex 정정] 미확정 «중» 의 재전송은 공용 계층이 이미
                      //:     막는다(`executeStudioCommand` 가 PAUSE/STOP 외 새 명령을 거절).
                      //:     그러니 「두 벌 저장된다」고 겁주지 않는다 — 사용자가 할 일은
                      //:     **원요청을 조회해 결과를 확정하는 것**이다.
                      alert(`⚠️ 저장 여부를 확인하지 못했습니다. 다시 누르지 말고 아래 «실행 요청 기록» 에서 원래 요청을 조회하십시오.\n\n${r.message}`);
                    } else {
                      alert(`❌ 결과물을 저장하지 못했습니다.\n\n${r.message}`);
                    }
                  }}
                  disabled={!!pendingReason}
                  title={pendingReason || undefined}
                  className={`w-full text-white font-bold py-3 rounded-lg shadow-lg transition-all border disabled:opacity-50 ${
                    state?.supervisor_verdict !== "PASS"
                      ? "bg-gradient-to-r from-orange-700 to-red-700 hover:from-orange-600 hover:to-red-600 border-red-400/30"
                      : "bg-gradient-to-r from-emerald-600 to-green-600 hover:from-emerald-500 hover:to-green-500 border-emerald-400/30"
                  }`}
                >
                  {state?.supervisor_verdict !== "PASS" ? "⚠️ 수용검수 미통과 — 그래도 검토용 버전 저장" : "💾 검토용 버전 저장"}
                </button>
                {/* 생성된 산출물(코드·문서)을 zip 으로 즉시 내려받기 — Content-Disposition 헤더가 파일명 지정.
                    ★★★ [2026-09-19 실측] 앵커 직접 이동은 **세션 헤더를 못 싣는다**(401).
                      새 Studio 와 **같은 공용 함수**를 부른다 — 각자 앵커를 만들면 또 갈라진다. */}
                <button
                  onClick={() => {
                    void (async () => {
                      const result = await downloadProjectArchive(currentProjectId);
                      //: ⚠️⚠️ [검토 2026-09-19] `currentProjectId` 는 **요청을 시작한 렌더**의
                      //:   값이라 결과와 늘 같다 — 화면 전환을 감지하지 못한다. 게다가
                      //:   `alert` 는 **전역**이라 다른 화면 위에도 뜬다.
                      //: ★ 완료 시점의 열린 프로젝트와 비교한다.
                      if (useFactoryStore.getState().currentProjectId !== result.projectId) return;
                      //: ⚠️⚠️ [2026-09-20 실측] 성공하면 **아무 말도 하지 않았다.**
                      //:   브라우저가 저장을 조용히 시작하면 사용자는 「눌렀는데 아무 일도
                      //:   없다」로 읽는다 — 새 Studio 는 「시작했습니다」라고 말한다.
                      //: ★ 공용 함수가 준 파일명을 그대로 싣는다. 저장 완료를 단정하지
                      //:   않고 「시작」까지만 말한다 — 디스크 저장은 브라우저가 한다.
                      if (result.ok) alert(`✅ 내려받기를 시작했습니다 — ${result.filename}`);
                      else alert(result.reason);
                    })();
                  }}
                  className="w-full mt-2 text-emerald-200 font-bold py-2.5 rounded-lg border border-emerald-700/50 bg-emerald-900/20 hover:bg-emerald-800/40 transition-all text-sm"
                >
                  ⬇ 산출물 코드 ZIP 다운로드
                </button>
              </div>
            )}
            
            {/* 시뮬레이션 반복 재실행 UI */}
            {progressPercent === 100 && currentTemplateData?.simulation_framework && currentProjectId && (
              <div className="flex flex-col gap-2 mb-3 mt-2 p-3 rounded-lg border border-purple-500/50 bg-purple-900/10">
                <label className="text-sm font-semibold text-purple-300">🔄 인자 변경 후 재실행 (What-if Analysis)</label>
                <p className="text-xs text-gray-400">변경할 인자와 값을 JSON 형식으로 입력하세요. (예: {`{"환율": 1450, "유가": 85}`})</p>
                <textarea 
                  value={resimParams} onChange={(e) => setResimParams(e.target.value)} disabled={isStarting || activeSprintId !== null}
                  placeholder='{"변수명": 변경값}'
                  className="w-full h-20 bg-gray-950 border border-gray-700 rounded p-2 text-sm focus:outline-none focus:border-purple-500 resize-none font-mono disabled:opacity-50 text-gray-300"
                />
                <button 
                  onClick={async () => {
                    try {
                      const params = JSON.parse(resimParams || "{}");
                      if (Object.keys(params).length === 0) return alert("변경할 인자를 입력해주세요.");
                      if (!confirm("현재 결과를 보존하고 새로운 인자로 시뮬레이션을 재실행하시겠습니까?")) return;
                      
                      setIsStarting(true);
                      const res = await fetch(`${API_BASE_URL}/api/v1/factory/${currentProjectId}/resimulate`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ modified_params: params, base_cycle: state?.sim_cycle_count || 1 })
                      });
                      const data = await res.json();
                      if (res.ok) {
                        alert(data.message);
                        setResimParams("");
                      } else {
                        alert(`재실행 오류: ${data.detail}`);
                      }
                    } catch (e) {
                      alert("유효한 JSON 형식이 아닙니다.");
                    } finally {
                      setIsStarting(false);
                    }
                  }} 
                  disabled={isStarting || !resimParams.trim() || activeSprintId !== null}
                  className="mt-1 w-full bg-purple-600 hover:bg-purple-500 disabled:bg-gray-700 font-bold py-2 rounded text-white text-sm"
                >
                  {isStarting ? "처리 중..." : "▶️ 시뮬레이션 재실행"}
                </button>
              </div>
            )}


            {wbsData?.tasks?.map((task: any, taskIndex: number) => {
              const isDone = task.status === 'DONE';
              const isInProgress = task.status === 'IN_PROGRESS';
              const isFailed = task.status === 'FAILED'; // 빌드 자가복구(3회) 소진 - 재가동 가능
              const isRunning = isInProgress && activeSprintId === task.task_id;
              const isPaused = isInProgress && activeSprintId !== task.task_id;
              const isIdle = !isDone && !isInProgress;
              const isHotl = task.task_id === hotlTaskId;

              return (
                <div key={task.task_id} className={`p-3 rounded border transition-colors ${
                  isDone ? 'bg-gray-900 border-green-900/50 opacity-60' :
                  isRunning ? 'bg-blue-900/20 border-blue-500 shadow-[0_0_10px_rgba(59,130,246,0.2)]' :
                  isHotl ? 'bg-amber-900/20 border-amber-400 shadow-[0_0_10px_rgba(251,191,36,0.2)]' :
                  isPaused ? 'bg-orange-900/20 border-orange-500' : 'bg-gray-800 border-gray-600'
                }`}>
                  <div className="flex justify-between items-center mb-2">
                    <span className={`text-xs font-bold ${isHotl ? 'text-amber-300' : isPaused ? 'text-orange-300' : 'text-blue-300'}`}>작업 {taskIndex + 1}</span>
                    <span className={`text-xs px-2 py-0.5 rounded font-bold ${
                      isDone ? 'bg-green-900 text-green-300' :
                      isRunning ? 'bg-blue-600 text-white animate-pulse' :
                      isHotl ? 'bg-amber-500 text-white animate-pulse' :
                      isPaused ? 'bg-orange-600 text-white' :
                      isFailed ? 'bg-red-700 text-white' : 'bg-gray-700 text-gray-300'
                    }`}>
                      {isDone ? "✅ 완료" : isRunning ? "⚙️ 진행 중" : isHotl ? "⚠️ 전문가 확인" : isPaused ? "⏸️ 일시 정지" : isFailed ? "❌ 실패" : "대기"}
                    </span>
                  </div>
                  <h4 className="text-sm font-bold text-gray-200 mb-1">{task.title}</h4>
                  <p className="text-xs text-gray-400 mb-3">{task.goal}</p>
                  
                  {isIdle && (
                    <button onClick={() => handleStartSprint(task)} disabled={isStarting || activeSprintId !== null || !!pendingReason} title={pendingReason || undefined} className="w-full text-xs font-bold py-2 rounded bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 text-white">▶️ 작업 시작</button>
                  )}
                  {isPaused && (
                    <button onClick={() => handleStartSprint(task)} disabled={isStarting || activeSprintId !== null || !!pendingReason} title={pendingReason || undefined} className="w-full text-xs font-bold py-2 rounded bg-orange-600 hover:bg-orange-500 disabled:bg-gray-700 text-white">▶️ 이어서 실행</button>
                  )}
                  {isRunning && (
                    <div className="flex flex-col gap-2">
                      <button onClick={() => handlePauseSprint(task)} className="w-full text-xs font-bold py-2 rounded bg-red-600 hover:bg-red-500 text-white">🛑 작업 일시 정지</button>
                      {renderPipelineTracker(false, task)}
                    </div>
                  )}
                  {isPaused && renderPipelineTracker(true, task)}
                </div>
              );
            })}

            {doneTasks > 0 && (
              <div className="mt-4 pt-4 border-t border-gray-700 flex flex-col gap-2">
                <label className="text-sm font-semibold text-yellow-500">🎯 3. 사용자 검토 및 수정 요청</label>
                {/* ★ [§2] 이 자리에서 접수하지 않는다는 것을 «누르기 전에» 말한다. */}
                <p className="text-[11px] text-yellow-200/80 leading-relaxed">
                  수정 요청 접수는 <b>「🏗 새 제작 화면」 → 「추가 작업 · 수정 요청」</b>에서 합니다.
                  어느 산출물을 고칠지 고른 뒤 제출해야 하기 때문입니다. 아래 입력은 메모로 남고
                  <b> 자동으로 옮겨가지 않습니다</b> — 복사해서 붙여 넣으십시오.
                </p>
                <textarea 
                  value={feedback} onChange={(e) => setFeedback(e.target.value)} disabled={isStarting || activeSprintId !== null}
                  placeholder="디자인이나 기능 수정 요구사항을 입력하세요..."
                  className="w-full h-24 bg-gray-950 border border-gray-700 rounded p-3 text-sm focus:outline-none focus:border-yellow-500 resize-none disabled:opacity-50"
                />
                <button 
                  onClick={handleSubmitFeedback} disabled={!feedback.trim()}
                  className="mt-1 w-full bg-yellow-600 hover:bg-yellow-500 disabled:bg-gray-700 font-bold py-3 rounded text-white"
                >
                  📍 수정 요청은 어디서 하나요?
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
