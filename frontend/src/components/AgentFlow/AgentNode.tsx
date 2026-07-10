import { Handle, Position } from "@xyflow/react";

const CATEGORY_META: Record<string, { label: string; color: string; border: string }> = {
  planning: { label: "기획", color: "bg-sky-500/10 text-sky-400", border: "border-sky-500/40" },
  execution: { label: "실행", color: "bg-emerald-500/10 text-emerald-400", border: "border-emerald-500/40" },
  review: { label: "검수", color: "bg-amber-500/10 text-amber-400", border: "border-amber-500/40" },
  system: { label: "시스템", color: "bg-gray-500/10 text-gray-400", border: "border-gray-500/40" },
};

export default function AgentNode({ data, selected }: { data: any; selected: boolean }) {
  const cat = CATEGORY_META[data.category] || CATEGORY_META.system;

  return (
    <div
      className={`min-w-[180px] bg-gray-800/90 backdrop-blur-md rounded-xl p-4 transition-all duration-200 cursor-pointer ${
        selected ? `ring-2 ring-blue-500 shadow-lg shadow-blue-500/20 ${cat.border}` : `border ${cat.border} hover:border-gray-500`
      } ${!data.enabled ? "opacity-50 grayscale" : ""}`}
    >
      <Handle type="target" position={Position.Left} className="w-2 h-2 bg-gray-400 border-none" />
      
      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between gap-2">
          <div className="flex gap-1 items-center">
            <span className={`text-[10px] font-bold px-2 py-0.5 rounded border ${cat.color} ${cat.border}`}>
              {cat.label}
            </span>
            {data.is_start && <span className="text-[10px] font-bold bg-green-500/20 text-green-300 px-1.5 py-0.5 rounded" title="Start Point">▶ 시작</span>}
            {data.is_end && <span className="text-[10px] font-bold bg-red-500/20 text-red-300 px-1.5 py-0.5 rounded" title="End Point">■ 종료</span>}
          </div>
          <div className="flex gap-1">
            {data.hotl_after && <span className="text-[10px] font-bold bg-rose-500/20 text-rose-300 px-1.5 py-0.5 rounded" title="HOTL">✋</span>}
            {data.debate && <span className="text-[10px] font-bold bg-purple-500/20 text-purple-300 px-1.5 py-0.5 rounded" title="Debate">💬</span>}
          </div>
        </div>
        
        <div>
          <h3 className="text-sm font-bold text-white truncate" title={data.name_ko}>
            {data.name_ko || "Unnamed Agent"}
          </h3>
          <p className="text-[11px] font-mono text-gray-500 truncate" title={data.id}>
            {data.id}
          </p>
        </div>
      </div>

      <Handle type="source" position={Position.Right} className="w-2 h-2 bg-gray-400 border-none" />
    </div>
  );
}
