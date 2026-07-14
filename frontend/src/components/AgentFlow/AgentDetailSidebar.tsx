import { X } from "lucide-react";
import { useState } from "react";
import { useFactoryStore, API_BASE_URL } from "../../store/useFactoryStore";

function Toggle({ on, onClick, label, title }: { on: boolean; onClick: () => void; label: string; title?: string }) {
  return (
    <button
      type="button"
      title={title}
      onClick={onClick}
      className={`px-2.5 py-1.5 rounded text-xs font-bold border transition-colors flex-1 ${
        on ? "bg-blue-600 border-blue-400 text-white" : "bg-gray-900 border-gray-700 text-gray-500 hover:text-gray-300"
      }`}
    >
      {on ? "● " : "○ "}{label}
    </button>
  );
}

export default function AgentDetailSidebar({
  agent,
  updateAgent,
  onClose,
}: {
  agent: any | null;
  updateAgent: (id: string, key: string, value: any) => void;
  onClose: () => void;
}) {
  const [isGeneratingSkill, setIsGeneratingSkill] = useState(false);

  if (!agent) return null;

  const handleGenerateSkill = async () => {
    if (!agent.role?.trim()) {
      alert("먼저 에이전트의 대략적인 역할을 입력해 주세요.");
      return;
    }
    setIsGeneratingSkill(true);
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/factory/ai-recommend/skill`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          agent_id: agent.id,
          agent_name_ko: agent.name_ko || "",
          role_description: agent.role
        })
      });
      const data = await res.json();
      if (res.ok && data.status === "success") {
        updateAgent(agent.id, "role", data.role);
        updateAgent(agent.id, "skill", data.skill);
        alert(`스킬 생성 완료! (파일명: ${data.skill}.md)`);
      } else {
        alert(`스킬 생성 실패: ${data.detail || "알 수 없는 오류"}`);
      }
    } catch (e: any) {
      alert(`스킬 생성 중 오류 발생: ${e.message}`);
    } finally {
      setIsGeneratingSkill(false);
    }
  };

  return (
    <div className="w-80 bg-gray-800 border-l border-gray-700 flex flex-col h-full shrink-0 shadow-xl overflow-y-auto">
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-700 bg-gray-850">
        <h2 className="text-sm font-bold text-white flex items-center gap-2">
          <span>🛠️</span> 에이전트 상세 편집
        </h2>
        <button onClick={onClose} className="text-gray-400 hover:text-white transition-colors">
          <X size={16} />
        </button>
      </div>

      <div className="p-4 flex flex-col gap-4">
        {/* ID & 활성 상태 */}
        <div className="flex items-center justify-between">
          <span className="text-xs font-mono text-gray-500 bg-gray-900 px-2 py-1 rounded border border-gray-700">
            {agent.id}
          </span>
          <Toggle
            on={!!agent.enabled}
            onClick={() => updateAgent(agent.id, "enabled", !agent.enabled)}
            label="활성 상태"
            title="비활성 시 파이프라인에서 제외됩니다."
          />
        </div>

        {/* 표시 이름 */}
        <div>
          <label className="block text-xs font-bold text-gray-400 mb-1">표시 이름</label>
          <input
            value={agent.name_ko || ""}
            onChange={(e) => updateAgent(agent.id, "name_ko", e.target.value)}
            className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm text-white focus:border-blue-500 outline-none"
          />
        </div>

        {/* 역할 설명 */}
        <div>
          <label className="block text-xs font-bold text-gray-400 mb-1">역할 설명</label>
          <textarea
            value={agent.role || ""}
            onChange={(e) => updateAgent(agent.id, "role", e.target.value)}
            rows={3}
            className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm text-gray-200 resize-y focus:border-blue-500 outline-none"
            placeholder="대략적인 역할을 적고 아래 AI 버튼을 누르면 자동 완성됩니다."
          />
          <button
            onClick={handleGenerateSkill}
            disabled={isGeneratingSkill || !agent.role?.trim()}
            className="w-full mt-2 text-xs font-bold text-white bg-purple-600 hover:bg-purple-500 disabled:bg-gray-700 disabled:text-gray-500 py-1.5 rounded transition-colors"
          >
            {isGeneratingSkill ? "⏳ AI가 스킬 문서 작성 중..." : "✨ AI로 역할 구체화 및 스킬 자동 생성"}
          </button>
        </div>

        {/* 스킬 & 단계 */}
        <div className="flex gap-3">
          <div className="flex-1">
            <label className="block text-xs font-bold text-gray-400 mb-1">호출 스킬 (Tools)</label>
            <input
              value={agent.skill || ""}
              onChange={(e) => updateAgent(agent.id, "skill", e.target.value)}
              placeholder="(없음)"
              className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm text-gray-200 font-mono focus:border-blue-500 outline-none"
            />
          </div>
          <div className="w-24">
            <label className="block text-xs font-bold text-gray-400 mb-1">실행 단계</label>
            <input
              value={agent.stage || ""}
              onChange={(e) => updateAgent(agent.id, "stage", e.target.value)}
              className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm text-gray-200 font-mono focus:border-blue-500 outline-none"
            />
          </div>
        </div>

        {/* 모델 티어 & 순서 */}
        <div className="flex gap-3">
          <div className="flex-1">
            <label className="block text-xs font-bold text-gray-400 mb-1">모델 티어</label>
            <select
              value={agent.model_tier || "pro"}
              onChange={(e) => updateAgent(agent.id, "model_tier", e.target.value)}
              className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm text-gray-200 focus:border-blue-500 outline-none"
            >
              <option value="pro">Pro (고성능)</option>
              <option value="flash">Flash (고속/경량)</option>
            </select>
          </div>
          <div className="w-24">
            <label className="block text-xs font-bold text-gray-400 mb-1">순서</label>
            <input
              type="number"
              value={agent.order ?? 0}
              onChange={(e) => updateAgent(agent.id, "order", parseInt(e.target.value) || 0)}
              className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm text-white outline-none focus:border-blue-500"
              title="원하는 순서대로 직접 입력하세요."
            />
          </div>
        </div>

        {/* 출력 포맷 */}
        <div>
          <label className="block text-xs font-bold text-gray-400 mb-1">
            출력 양식 (선택적 강제)
          </label>
          <select
            value={agent.output_format || ""}
            onChange={(e) => updateAgent(agent.id, "output_format", e.target.value)}
            className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm text-gray-200 focus:border-blue-500 outline-none"
          >
            <option value="">(없음 - 기본 스킬 프롬프트만 사용)</option>
            {useFactoryStore.getState().formats?.map((fmt: any) => (
              <option key={fmt.id} value={fmt.id}>
                {fmt.name}
              </option>
            ))}
          </select>
          <p className="text-[10px] text-gray-500 mt-1">
            * 포맷 마스터에 정의된 양식을 이 에이전트의 산출물에 강제로 적용합니다.
          </p>
        </div>

        {/* 시작/종료 지정 */}
        <div className="mt-2 border-t border-gray-700 pt-4">
          <label className="block text-xs font-bold text-gray-400 mb-2">시작 및 종료점 지정</label>
          <div className="flex gap-2">
            <Toggle
              on={!!agent.is_start}
              onClick={() => updateAgent(agent.id, "is_start", !agent.is_start)}
              label="시작점 (Start)"
              title="이 노드를 워크플로우의 시작점으로 지정합니다."
            />
            <Toggle
              on={!!agent.is_end}
              onClick={() => updateAgent(agent.id, "is_end", !agent.is_end)}
              label="종료점 (End)"
              title="이 노드를 워크플로우의 최종 종료점으로 지정합니다."
            />
          </div>
        </div>

        {/* 추가 옵션 */}
        <div className="mt-2 border-t border-gray-700 pt-4">
          <label className="block text-xs font-bold text-gray-400 mb-2">고급 실행 제어</label>
          <div className="flex gap-2">
            <Toggle
              on={!!agent.hotl_after}
              onClick={() => updateAgent(agent.id, "hotl_after", !agent.hotl_after)}
              label="HOTL (전문가 개입)"
              title="이 에이전트 실행 직후 HOTL (전문가 개입)을 위해 파이프라인이 일시 중지됩니다."
            />
            <Toggle
              on={!!agent.debate}
              onClick={() => updateAgent(agent.id, "debate", !agent.debate)}
              label="토론/합의 루프"
              title="결과 도출 전 다중 에이전트 토론 모드를 활성화합니다."
            />
          </div>
          {!agent.llm && (
            <div className="mt-3 text-xs text-amber-400/80 bg-amber-500/10 px-3 py-2 rounded border border-amber-500/20">
              ⚠️ 이 노드는 LLM 추론 없이 정적 스크립트 기반으로 동작합니다.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
