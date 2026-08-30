import { useState, useEffect } from 'react';
// ★ [2026-08-06] 답변 직렬화·기본선택·토글을 `factory/clarifyAnswers.ts` 로 옮겼다. 그 문자열
//   형식은 **백엔드(`RFP_Analyst`)가 파싱하는 계약**이고, 신규 Studio 의 Decision Dock 도 같은
//   제출을 한다. 복사하면 두 벌이 되고 반드시 갈라진다 — 동작은 종전과 동일하다.
import {
  defaultSelections, serializeClarifyAnswers, toggleSelection,
} from '../factory/clarifyAnswers';
import { useFactoryStore } from '../store/useFactoryStore';
import { API_BASE_URL } from '../lib/api';

/** 실패한 응답을 **사람이 할 일이 보이는** 오류로 바꾼다.
 *
 * ## ⚠️⚠️ [2026-08-26 실측] 왜 생겼는가
 *
 * 종전에는 상태 코드와 무관하게 「서버 통신에 실패했습니다. 백엔드 서버를 확인해주세요」
 * 하나였다. 그런데 실제로 난 것은 **세션이 끊긴 401** 이었고, 사용자는 그 문구를 보고
 * **서버를 확인하러 갔다.** 서버는 멀쩡했다.
 *
 * ★ 오류 문구의 값어치는 「무엇이 잘못됐나」가 아니라 **「내가 무엇을 하면 되나」**다.
 *   401 은 다시 로그인하는 것이고, 503 은 기다리는 것이며, 통신 실패는 서버를 보는 것이다.
 * ⚠️ 서버가 준 사유(`detail`)가 있으면 그것을 싣는다 — 화면이 다시 지어내지 않는다.
 */
async function requestError(res: Response): Promise<Error> {
  let detail = '';
  try {
    detail = ((await res.json()) as { detail?: string })?.detail || '';
  } catch {
    /* JSON 이 아닐 수 있다 — 그때는 상태 코드만으로 말한다 */
  }
  if (res.status === 401) {
    return new Error('로그인이 필요합니다 — 세션이 만료되었을 수 있습니다. '
      + '다시 로그인한 뒤 이어서 진행해 주십시오.');
  }
  if (res.status === 403) {
    return new Error('이 작업을 할 권한이 없습니다' + (detail ? ` — ${detail}` : '')
      + '. 담당자에게 요청해 주십시오.');
  }
  if (res.status === 409) {
    return new Error(detail || '지금은 그 작업을 할 수 있는 상태가 아닙니다.');
  }
  if (res.status >= 500) {
    return new Error(`서버가 처리하지 못했습니다(${res.status})`
      + (detail ? ` — ${detail}` : '') + '. 잠시 후 다시 시도해 주십시오.');
  }
  return new Error(detail || `요청이 거절되었습니다(상태 코드 ${res.status}).`);
}



export default function HOTLInput() {
  const [feedback, setFeedback] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [supervisorReply, setSupervisorReply] = useState<string | null>(null);
  // 요구 확인 인터뷰 답변: 질문 id → 선택된 옵션 label 목록
  const [selections, setSelections] = useState<Record<string, string[]>>({});

  const state = useFactoryStore((store) => store.state);
  const currentProjectId = useFactoryStore((store) => store.currentProjectId);
  const hotlTaskId = useFactoryStore((store) => store.hotlTaskId);

  // HOTL 대기 판정을 단일화: needs_revision 또는 hotlTaskId 중 하나라도 켜져 있으면 '대기'(승인 가능)
  // → 좌측 상태 배너와 신호가 어긋나 '버튼은 비활성인데 실제론 멈춰 대기' 데드락 방지.
  const isWaitingForHuman = !!(state?.needs_revision || hotlTaskId);
  const currentTask = state?.current_sprint_task_id || hotlTaskId;

  // 요구 확인 인터뷰(선택형 질문) 게이트 여부
  const clarQuestions = (((state as any)?.clarification_questions || []) as any[]);
  const isClarification =
    isWaitingForHuman &&
    (state as any)?.current_stage === 'CLARIFICATION' &&
    clarQuestions.length > 0 &&
    !String((state as any)?.clarification_summary || '').trim();

  // 질문이 도착하면 각 질문의 추천안을 기본 선택값으로 세팅
  // 지문(fingerprint)에 옵션 라벨까지 포함 - id 만 보면 같은 id 로 재생성된 질문의 옛 선택(stale 라벨)이
  // 남아 직렬화 시 어떤 옵션과도 매칭되지 않아 '선택 없음'으로 전송되는 불일치가 생긴다
  const questionsFingerprint = JSON.stringify(
    clarQuestions.map((q: any) => [q.id, (q.options || []).map((o: any) => o.label)])
  );
  useEffect(() => {
    if (!isClarification) return;
    setSelections((prev) => defaultSelections(clarQuestions, prev));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isClarification, questionsFingerprint]);

  const toggleOption = (q: any, label: string) => {
    setSelections((prev) => toggleSelection(prev, q, label));
  };

  // 선택 결과를 백엔드(RFP_Analyst)가 소비할 수 있는 텍스트로 직렬화 — 형식은 공용 모듈에 있다.
  const serializeAnswers = () => serializeClarifyAnswers(clarQuestions, selections, feedback);

  // 지금 '무엇을' 승인하는지 + 어디서 검토하는지 안내 (HOTL 중단점 = 직전 산출 단계)
  const APPROVAL_MAP: Record<string, { what: string; where: string }> = {
    CLARIFICATION: { what: "요구사항 확인 질문", where: "아래 질문 카드" },
    RFP: { what: "요구사항 정의서 (RFP)", where: "우측 '요구정의(RFP)' 탭" },
    PLANNING: { what: "기획서 (PRD)", where: "우측 '기획서' 탭" },
    PMO: { what: "작업 분해 계획 (WBS)", where: "좌측 통제실의 태스크 목록" },
    UI_DESIGN: { what: "UI/UX 목업 디자인", where: "우측 'UI 디자인' 탭" },
    ARCHITECTURE: { what: "아키텍처 설계", where: "우측 '아키텍처' 탭" },
    TECH_SPEC: { what: "기술 설계 명세", where: "우측 '기술사양' 탭" },
    CODE_REVIEW: { what: "코드 리뷰 결과", where: "우측 '리뷰' 탭" },
  };
  const approval = APPROVAL_MAP[(state as any)?.current_stage] || null;

  const handleSubmit = async () => {
    // 승인/재개(resume)에만 태스크가 필요 - 슈퍼바이저 대화(자비스)는 태스크·가동 여부와 무관하게 가능
    if (isWaitingForHuman && !currentTask) {
      alert("🚨 재개할 작업을 찾을 수 없습니다. 작업 목록을 새로 확인해 주십시오.");
      return;
    }
    if (!currentProjectId) {
      alert("🚨 현재 프로젝트를 확인할 수 없습니다. 프로젝트를 다시 선택해 주십시오.");
      return;
    }
    if (!isWaitingForHuman && !feedback.trim()) {
      alert("메시지를 입력해주세요.");
      return;
    }
    
    setIsSubmitting(true);
    setSupervisorReply(null);
    try {
      if (isWaitingForHuman) {
        // 요구 확인 인터뷰 게이트면 선택 결과를 직렬화해 전송(그 외 게이트는 자유 피드백 그대로)
        const payloadFeedback = isClarification ? serializeAnswers() : feedback.trim();
        const response = await fetch(`${API_BASE_URL}/api/v1/factory/${currentProjectId}/hotl/resume`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            task_id: currentTask,
            feedback: payloadFeedback
          }),
        });

        if (!response.ok) {
          throw await requestError(response);
        }

        setFeedback("");

        // 승인/재가동 직후 상태를 '가동 중'으로 일관되게 전환
        useFactoryStore.setState((prev) => ({
          state: prev.state ? { ...prev.state, needs_revision: false } : null,
          hotlTaskId: null,
          activeSprintId: currentTask,
        }));
      } else {
        // 🚀 슈퍼바이저와 실시간 채팅
        const response = await fetch(`${API_BASE_URL}/api/v1/factory/${currentProjectId}/supervisor/chat`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            task_id: currentTask || "",  // 자비스 모드: 태스크 없이도 시스템 전체 질문 가능
            message: feedback.trim()
          }),
        });

        if (!response.ok) {
          throw await requestError(response);
        }

        const data = await response.json();
        setSupervisorReply(data.reply);
        setFeedback("");
      }
    } catch (error) {
      console.error("🚨 전송 실패:", error);
      // ⚠️⚠️ [2026-08-26 실측] 종전에는 무엇이 실패하든 「서버 통신에 실패했습니다.
      //   백엔드 서버를 확인해주세요」였다. 실제로는 **세션이 끊겨 401** 이었는데,
      //   사용자는 그 문구를 보고 **서버를 보러 갔다**(실제로 그렇게 됐다).
      //   할 일이 다른 두 가지를 같은 문장으로 말하면, 사람은 매번 틀린 쪽을 고친다.
      alert(error instanceof Error && error.message
        ? error.message
        : "서버에 닿지 못했습니다. 네트워크와 백엔드 서버를 확인해 주십시오.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="p-4 border-t border-gray-700 bg-gray-800 shrink-0">
      <div className="flex flex-col gap-3">
        <div className="flex justify-between items-center">
          <span className={`text-sm font-semibold ${isWaitingForHuman ? 'text-yellow-400' : 'text-blue-400'}`}>
            {isWaitingForHuman ? "⏸️ 전문가 확인 대기 · 승인 또는 수정 의견이 필요합니다" : "▶️ AI 제작 진행 중 · 자비스에게 질문할 수 있습니다"}
          </span>
          <span className="text-xs text-gray-400">현재 작업 · {currentTask || "확인 중"}</span>
        </div>

        {/* ✋ 실시간 채팅 응답 박스 */}
        {supervisorReply && (
          <div className="bg-gray-800 border border-purple-500 rounded p-3 mb-4 max-h-60 overflow-y-auto shrink-0 custom-scrollbar">
            <div className="font-bold flex items-center gap-1 mb-1 sticky top-0 bg-gray-800 pb-1">
              <span>🤖 자비스 답변</span>
            </div>
            <div className="text-sm font-medium text-gray-300 mb-2">[{state?.project_name || "프로젝트"}] 전문가 검토 대기 중...</div>
            <div className="whitespace-pre-wrap text-sm">{supervisorReply}</div>
          </div>
        )}

        {/* ✋ 무엇을 승인하는지 명확히 안내 및 슈퍼바이저 메시지 표시 */}
        {isWaitingForHuman && (
          <div className="flex flex-col gap-2">
            {/* 슈퍼바이저 인터럽트 감지 */}
            {state?.human_feedback_queue && state.human_feedback_queue.filter((q: any) => q.feedback.includes("[SUPERVISOR]")).length > 0 && (
              <div className="rounded border border-red-700/50 bg-red-900/20 p-2.5 text-xs text-red-100 leading-relaxed">
                <div className="font-bold flex items-center gap-1">
                  <span>🤖 자비스 확인 요청</span>
                </div>
                <div className="mt-1 text-red-200/90 whitespace-pre-wrap">
                  {state.human_feedback_queue.filter((q: any) => q.feedback.includes("[SUPERVISOR]")).pop()?.feedback.replace("[SUPERVISOR] ", "")}
                </div>
              </div>
            )}
            
            {isClarification ? (
              <div className="rounded border border-cyan-700/50 bg-cyan-900/20 p-2.5 text-xs text-cyan-100 leading-relaxed">
                <div>💬 <b className="text-cyan-300">요구사항 확인</b> — AI가 RFP 작성 전에 방향을 확인합니다.</div>
                <div className="mt-1 text-cyan-200/80">
                  각 질문에서 원하는 선택지를 클릭하세요. <b>추천안이 기본 선택</b>되어 있어 그대로 전송해도 됩니다.
                  선택지에 없는 의견은 아래 입력창에 적으면 함께 반영됩니다.
                </div>
              </div>
            ) : (
              <div className="rounded border border-yellow-700/50 bg-yellow-900/20 p-2.5 text-xs text-yellow-100 leading-relaxed">
                <div>✋ 승인 대상: <b className="text-yellow-300">{approval?.what || "직전 단계 산출물"}</b></div>
                <div className="mt-1 text-yellow-200/80">
                  {approval ? `${approval.where}에서 내용을 검토한 뒤, ` : "산출물을 검토한 뒤, "}
                  그대로 진행하려면 <b>빈칸으로 '설계 승인 및 진행'</b>, 수정이 필요하면 아래에 <b>피드백</b>을 적어 보내세요.
                </div>
              </div>
            )}

            {/* 💬 요구 확인 인터뷰 — 선택형 질문 카드 */}
            {isClarification && (
              <div className="flex flex-col gap-2 max-h-72 overflow-y-auto custom-scrollbar pr-1">
                {clarQuestions.map((q: any, i: number) => (
                  <div key={q.id} className="rounded border border-gray-600 bg-gray-900/60 p-2.5">
                    <div className="text-xs font-semibold text-gray-100">Q{i + 1}. {q.question}</div>
                    {q.why && <div className="mt-0.5 text-[11px] text-gray-400">{q.why}</div>}
                    <div className="mt-2 flex flex-col gap-1.5">
                      {(q.options || []).map((o: any) => {
                        const selected = (selections[q.id] || []).includes(o.label);
                        return (
                          <button
                            key={o.label}
                            type="button"
                            disabled={isSubmitting}
                            onClick={() => toggleOption(q, o.label)}
                            className={`text-left rounded border px-2.5 py-1.5 text-xs transition-colors ${
                              selected
                                ? 'border-cyan-500 bg-cyan-900/40 text-cyan-100'
                                : 'border-gray-600 bg-gray-800 text-gray-300 hover:border-gray-400'
                            }`}
                          >
                            <span className="font-semibold">{selected ? '●' : '○'} {o.label}</span>
                            {o.recommended && <span className="ml-1.5 rounded bg-emerald-800/70 px-1 py-px text-[10px] text-emerald-200">추천</span>}
                            {o.description && <span className="block mt-0.5 text-[11px] text-gray-400">{o.description}</span>}
                          </button>
                        );
                      })}
                    </div>
                    {q.multi && <div className="mt-1 text-[10px] text-gray-500">복수 선택 가능</div>}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        <textarea 
          disabled={isSubmitting}
          value={feedback}
          onChange={(e) => setFeedback(e.target.value)}
          placeholder={
            isClarification
              ? "(선택) 선택지에 없는 추가 의견이 있으면 여기에 적으세요. 위 선택과 함께 반영됩니다."
              : isWaitingForHuman
                ? "승인하려면 빈칸으로 두고 전송하세요. 수정이 필요하면 요구사항을 입력하세요."
                : "진행 중인 제작 작업에 대해 자비스에게 지시하거나 질문하세요."
          }
          className="w-full h-24 bg-gray-900 border border-gray-600 rounded p-3 text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:border-blue-500 resize-none disabled:opacity-50"
        />
        
        <button 
          disabled={isSubmitting} 
          onClick={handleSubmit}
          className="w-full bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 disabled:text-gray-500 text-white font-semibold py-2.5 rounded shadow-lg"
        >
          {isSubmitting
            ? "전송 중..."
            : (isClarification
                ? "선택 완료 — 답변 반영하여 RFP 작성"
                : isWaitingForHuman
                  ? (feedback.trim() ? "피드백 적용 후 재가동" : "설계 승인 및 진행")
                  : "자비스에게 질문·지시")}
        </button>
      </div>
    </div>
  );
}
