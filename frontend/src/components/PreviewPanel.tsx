import { useState, useEffect } from 'react';
import { useFactoryStore } from '../store/useFactoryStore';
// @ts-ignore
import * as Babel from '@babel/standalone';

type SubTabId = 'prd' | 'architecture' | 'tech_spec' | 'frontend' | 'backend' | 'review' | 'qa';

interface TabConfig {
  id: SubTabId;
  label: string;
  data: string | undefined;
}

export default function PreviewPanel() {
  const [activeMainTab, setActiveMainTab] = useState<'preview' | 'code'>('preview');
  const [activeSubTab, setActiveSubTab] = useState<SubTabId | null>(null);
  const [iframeHtml, setIframeHtml] = useState<string>('');
  
  const state = useFactoryStore((s) => s.state);

  const allTabs: TabConfig[] = [
    { id: 'prd', label: '🎯 PRD', data: state?.prd_summary },
    { id: 'architecture', label: '📐 Architecture', data: state?.architecture_summary },
    { id: 'tech_spec', label: '🛠️ Tech Spec', data: state?.tech_spec_summary },
    { id: 'frontend', label: '🎨 Frontend', data: state?.frontend_code_summary },
    { id: 'backend', label: '⚙️ Backend', data: state?.backend_code_summary },
    { id: 'review', label: '📝 Review', data: state?.code_review_report_summary },
    { id: 'qa', label: '🧪 QA', data: state?.qa_report_summary },
  ];

  const availableTabs = allTabs.filter((t) => !!t.data);

  useEffect(() => {
    if (availableTabs.length > 0) {
      const latestTab = availableTabs[availableTabs.length - 1];
      if (!activeSubTab || !availableTabs.find(t => t.id === activeSubTab)) {
        setActiveSubTab(latestTab.id);
      }
    } else {
      setActiveSubTab(null);
    }
  }, [state]);

  useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      if (event.data?.type === 'BUILD_ERROR') {
        const errorMessage = event.data.payload;
        useFactoryStore.getState().triggerSelfHealing(errorMessage);
      }
    };
    window.addEventListener('message', handleMessage);
    return () => window.removeEventListener('message', handleMessage);
  }, []);

  // 🚀 WSOD 방어 및 샌드박스 컴파일러 주입 완료
  useEffect(() => {
    if (!state?.frontend_code_summary) {
      setIframeHtml('');
      return;
    }

    try {
      const rawCode = state.frontend_code_summary;
      let targetCode = rawCode;

      if (rawCode.includes('<file path=')) {
        const fileBlocks = Array.from(rawCode.matchAll(/<file path="([^"]+)">(.*?)<\/file>/gs));
        const reactBlock = fileBlocks.find(block => 
          block[1].includes('App') || block[1].includes('index.js') || block[1].includes('.tsx')
        );
        if (reactBlock) targetCode = reactBlock[2];
        else {
          const fallbackBlock = fileBlocks.find(block => block[1].endsWith('.js') || block[1].endsWith('.tsx'));
          if (fallbackBlock) targetCode = fallbackBlock[2];
        }
      }

      let safeCode = targetCode.replace(/import\s+[a-zA-Z0-9_\{\}\s\,\*]*\s+from\s+['"][^'"]+['"];?/g, '');
      safeCode = safeCode.replace(/import\s+['"][^'"]+['"];?/g, ''); 

      if (!safeCode.includes('ReactDOM.createRoot') && !safeCode.includes('root.render')) {
        const exportMatch = safeCode.match(/export\s+default\s+(?:function\s+|class\s+)?([a-zA-Z0-9_]+)/);
        let componentName = "App"; 
        if (exportMatch && exportMatch[1]) {
          componentName = exportMatch[1];
        } else {
          const funcMatch = [...safeCode.matchAll(/(?:const|function|class)\s+([A-Z][a-zA-Z0-9_]*)/g)];
          if (funcMatch.length > 0) componentName = funcMatch[funcMatch.length - 1][1];
        }

        safeCode = safeCode.replace(/export\s+default\s+(?:function\s+|class\s+)?([a-zA-Z0-9_]+);?/g, 'function $1');
        safeCode = safeCode.replace(/export\s+const\s/g, 'const ');
        safeCode = safeCode.replace(/export\s+/g, '');

        safeCode += `\n
        if (typeof ${componentName} !== 'undefined') {
          const rootElement = document.getElementById('root');
          if (rootElement) {
            const root = ReactDOM.createRoot(rootElement);
            root.render(React.createElement(${componentName}));
          }
        }`;
      }

      const transformed = Babel.transform(safeCode, { 
          presets: ['react', 'env', ['typescript', { isTSX: true, allExtensions: true }]],
          filename: 'app.tsx' 
      }).code;

      const html = `
        <!DOCTYPE html>
        <html lang="ko">
        <head>
          <meta charset="UTF-8">
          <meta name="viewport" content="width=device-width, initial-scale=1.0">
          <script src="https://cdn.tailwindcss.com"></script>
          <script crossorigin src="https://unpkg.com/react@18/umd/react.development.js"></script>
          <script crossorigin src="https://unpkg.com/react-dom@18/umd/react-dom.development.js"></script>
          <style>body { margin: 0; padding: 1.5rem; background-color: #ffffff; color: #1f2937; height: 100vh; overflow: auto; }</style>
        </head>
        <body>
          <div id="root"></div>
          <script>
            window.onerror = function(message) {
              window.parent.postMessage({ type: 'BUILD_ERROR', payload: message }, '*');
            };
            try {
              ${transformed}
            } catch (err) {
              document.getElementById('root').innerHTML = '<div style="color:#ef4444; padding:20px; background:#fee2e2; border:1px solid #f87171; border-radius:8px;"><b>🚨 런타임 에러:</b><br/>' + err.message + '</div>';
              window.parent.postMessage({ type: 'BUILD_ERROR', payload: err.message }, '*');
            }
          </script>
        </body>
        </html>
      `;
      setIframeHtml(html);
    } catch (err: any) {
      setIframeHtml(`
        <div style="color:#ef4444; padding:20px; font-family:sans-serif; background:#fee2e2; height:100vh;">
          <b>🚨 빌드 파싱 에러 (WSOD 방어됨):</b><br/><pre style="margin-top:10px;">${err.toString()}</pre>
        </div>
      `);
    }
  }, [state?.frontend_code_summary]);

  const activeContent = availableTabs.find(t => t.id === activeSubTab)?.data || "";

  return (
    <div className="flex flex-col h-full bg-gray-900 overflow-hidden relative">
      <div className="flex bg-gray-800 border-b border-gray-700 shrink-0 px-2 pt-2">
        <button 
          onClick={() => setActiveMainTab('preview')}
          className={`px-4 py-2 text-sm font-semibold rounded-t-md transition-colors ${
            activeMainTab === 'preview' ? 'bg-gray-900 text-blue-400 border-t border-x border-gray-700' : 'text-gray-400 hover:text-gray-200 hover:bg-gray-700/50'
          }`}
        >
          👁️ Live Preview
        </button>
        <button 
          onClick={() => setActiveMainTab('code')}
          className={`px-4 py-2 text-sm font-semibold rounded-t-md transition-colors ${
            activeMainTab === 'code' ? 'bg-gray-900 text-blue-400 border-t border-x border-gray-700' : 'text-gray-400 hover:text-gray-200 hover:bg-gray-700/50'
          }`}
        >
          💻 Generated Docs & Code
        </button>
      </div>

      {activeMainTab === 'code' && availableTabs.length > 0 && (
        <div className="flex bg-gray-900 border-b border-gray-800 shrink-0 px-2 py-2 gap-2 overflow-x-auto custom-scrollbar">
          {availableTabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveSubTab(tab.id)}
              className={`px-3 py-1.5 text-xs font-bold rounded transition-colors whitespace-nowrap ${
                activeSubTab === tab.id
                  ? 'bg-blue-900/40 text-blue-300 border border-blue-700'
                  : 'bg-gray-800 text-gray-400 border border-gray-700 hover:bg-gray-700'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      )}

      <div className="flex-1 overflow-auto bg-gray-900 p-4">
        {activeMainTab === 'preview' ? (
          <div className="w-full h-full bg-white rounded-lg shadow-inner border-2 border-gray-700 overflow-hidden relative">
            {iframeHtml ? (
              <iframe srcDoc={iframeHtml} className="w-full h-full border-none" title="Live Preview Sandbox" sandbox="allow-scripts allow-same-origin" />
            ) : (
              <div className="flex flex-col items-center justify-center w-full h-full text-center bg-gray-50">
                <span className="text-5xl mb-4 animate-pulse">⚙️</span>
                <p className="text-gray-500 font-bold text-lg">에이전트 산출물 대기 중...</p>
              </div>
            )}
          </div>
        ) : (
          <div className="w-full h-full bg-[#0d1117] rounded-lg border border-gray-700 p-6 overflow-auto shadow-inner">
            {availableTabs.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full text-gray-500">
                <p>아직 생성된 문서나 코드가 없습니다.</p>
              </div>
            ) : (
              <pre className="text-gray-300 font-mono text-[13px] leading-[1.8] whitespace-pre-wrap break-words">
                {activeContent}
              </pre>
            )}
          </div>
        )}
      </div>
    </div>
  );
}