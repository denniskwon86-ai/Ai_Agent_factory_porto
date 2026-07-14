import { useState } from 'react';
import { useFactoryStore } from '../store/useFactoryStore';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8080';

export default function HOTLInput() {
  const [feedback, setFeedback] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [supervisorReply, setSupervisorReply] = useState<string | null>(null);
  
  const state = useFactoryStore((store) => store.state);
  const currentProjectId = useFactoryStore((store) => store.currentProjectId);
  const hotlTaskId = useFactoryStore((store) => store.hotlTaskId);

  // HOTL 대기 판정을 단일화: needs_revision 또는 hotlTaskId 중 하나라도 켜져 있으면 '대기'(승인 가능)
  // → 좌측 상태 배너와 신호가 어긋나 '버튼은 비활성인데 실제론 멈춰 대기' 데드락 방지.
  const isWaitingForHuman = !!(state?.needs_revision || hotlTaskId);
  const currentTask = state?.current_sprint_task_id || hotlTaskId;

  // 지금 '무엇을' 승인하는지 + 어디서 검토하는지 안내 (HOTL 중단점 = 직전 산출 단계)
  const APPROVAL_MAP: Record<string, { what: string; where: string }> = {
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
    if (!currentTask) {
      alert("🚨 타겟 태스크(Task ID)를 찾을 수 없습니다.");
      return;
    }
    if (!currentProjectId) {
      alert("🚨 현재 프로젝트 ID를 찾을 수 없습니다.");
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
        // 🚀 원본 정상 경로 복구
        const response = await fetch(`${API_BASE_URL}/api/v1/factory/${currentProjectId}/hotl/resume`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            task_id: currentTask,
            feedback: feedback.trim()
          }),
        });

        if (!response.ok) {
          throw new Error(`서버 응답 오류 (상태 코드: ${response.status})`);
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
            task_id: currentTask,
            message: feedback.trim()
          }),
        });

        if (!response.ok) {
          throw new Error(`서버 응답 오류 (상태 코드: ${response.status})`);
        }

        const data = await response.json();
        setSupervisorReply(data.reply);
        setFeedback("");
      }
    } catch (error) {
      console.error("🚨 전송 실패:", error);
      alert("서버 통신에 실패했습니다. 백엔드 서버를 확인해주세요.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="p-4 border-t border-gray-700 bg-gray-800 shrink-0">
      <div className="flex flex-col gap-3">
        <div className="flex justify-between items-center">
          <span className={`text-sm font-semibold ${isWaitingForHuman ? 'text-yellow-400' : 'text-blue-400'}`}>
            {isWaitingForHuman ? "⏸️ HOTL (전문가 개입) 대기 중 - 설계 승인 또는 피드백 필요" : "▶️ AI 팩토리 자율 가동 중 (슈퍼바이저에게 질문 가능)"}
          </span>
          <span className="text-xs text-gray-400">Target Task: {currentTask || "알 수 없음"}</span>
        </div>

        {/* ✋ 실시간 채팅 응답 박스 */}
        {supervisorReply && (
          <div className="bg-gray-800 border border-purple-500 rounded p-3 mb-4 max-h-60 overflow-y-auto shrink-0 custom-scrollbar">
            <div className="font-bold flex items-center gap-1 mb-1 sticky top-0 bg-gray-800 pb-1">
              <span>🤖 슈퍼바이저 답변</span>
            </div>
            <div className="text-sm font-medium text-gray-300 mb-2">[{state?.project_name || "프로젝트"}] HOTL (전문가 개입) 리뷰 대기 중...</div>
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
                  <span>🤖 슈퍼바이저 개입 발생!</span>
                </div>
                <div className="mt-1 text-red-200/90 whitespace-pre-wrap">
                  {state.human_feedback_queue.filter((q: any) => q.feedback.includes("[SUPERVISOR]")).pop()?.feedback.replace("[SUPERVISOR] ", "")}
                </div>
              </div>
            )}
            
            <div className="rounded border border-yellow-700/50 bg-yellow-900/20 p-2.5 text-xs text-yellow-100 leading-relaxed">
              <div>✋ 승인 대상: <b className="text-yellow-300">{approval?.what || "직전 단계 산출물"}</b></div>
              <div className="mt-1 text-yellow-200/80">
                {approval ? `${approval.where}에서 내용을 검토한 뒤, ` : "산출물을 검토한 뒤, "}
                그대로 진행하려면 <b>빈칸으로 '설계 승인 및 진행'</b>, 수정이 필요하면 아래에 <b>피드백</b>을 적어 보내세요.
              </div>
            </div>
          </div>
        )}

        <textarea 
          disabled={isSubmitting}
          value={feedback}
          onChange={(e) => setFeedback(e.target.value)}
          placeholder={
            isWaitingForHuman 
              ? "승인하려면 빈칸으로 두고 전송하세요. 수정이 필요하면 요구사항을 입력하세요." 
              : "가동 중인 파이프라인에 대해 슈퍼바이저에게 지시하거나 질문하세요."
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
            : (isWaitingForHuman 
                ? (feedback.trim() ? "피드백 적용 후 재가동" : "설계 승인 및 진행") 
                : "슈퍼바이저에게 질문/지시")}
        </button>
      </div>
    </div>
  );
}