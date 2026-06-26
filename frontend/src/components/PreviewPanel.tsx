import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useFactoryStore } from '../store/useFactoryStore';

// 마크다운을 간단히 HTML로 변환하는 경량 렌더러 (외부 라이브러리 없음)
function ManualRenderer({ markdown }: { markdown: string }) {
  const lines = markdown.split('\n');
  const elements: React.ReactNode[] = [];
  let key = 0;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (line.startsWith('### ')) {
      elements.push(<h3 key={key++} className="text-base font-bold text-gray-800 mt-5 mb-1">{line.slice(4)}</h3>);
    } else if (line.startsWith('## ')) {
      elements.push(<h2 key={key++} className="text-lg font-bold text-gray-900 border-b border-gray-200 pb-1 mt-6 mb-2">{line.slice(3)}</h2>);
    } else if (line.startsWith('# ')) {
      elements.push(<h1 key={key++} className="text-xl font-extrabold text-blue-700 mb-4">{line.slice(2)}</h1>);
    } else if (/^(\d+)\. /.test(line)) {
      elements.push(<div key={key++} className="flex gap-2 text-sm text-gray-700 my-0.5 pl-2"><span className="font-bold text-blue-600 shrink-0">{line.match(/^(\d+)\. /)![1]}.</span><span>{line.replace(/^\d+\. /, '')}</span></div>);
    } else if (line.startsWith('- ') || line.startsWith('* ')) {
      elements.push(<div key={key++} className="flex gap-2 text-sm text-gray-700 my-0.5 pl-2"><span className="text-blue-500 shrink-0">•</span><span>{line.slice(2)}</span></div>);
    } else if (line.startsWith('**Q:') || line.startsWith('**Q :')) {
      elements.push(<p key={key++} className="text-sm font-bold text-gray-800 mt-3 mb-0.5">{line.replace(/\*\*/g, '')}</p>);
    } else if (line.startsWith('A:') || line.startsWith('A :')) {
      elements.push(<p key={key++} className="text-sm text-gray-600 mb-2 pl-3">{line}</p>);
    } else if (line.trim() === '') {
      elements.push(<div key={key++} className="h-2" />);
    } else {
      // 인라인 **bold** 처리
      const parts = line.split(/\*\*(.*?)\*\*/g);
      elements.push(
        <p key={key++} className="text-sm text-gray-700 leading-relaxed">
          {parts.map((p, idx) => idx % 2 === 1 ? <strong key={idx}>{p}</strong> : p)}
        </p>
      );
    }
  }
  return <>{elements}</>;
}

interface PreviewPanelProps {
  rawCode: string;
  isLoading?: boolean;
}

type TabType = 'PREVIEW' | 'RFP' | 'PRD' | 'ARCH' | 'TECH' | 'FRONTEND' | 'BACKEND' | 'REVIEW' | 'QA' | 'MANUAL';

interface CodeFile {
  file_path: string;
  code: string;
}

const PreviewPanel: React.FC<PreviewPanelProps> = ({ rawCode, isLoading }) => {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<TabType>('PREVIEW');

  const [isIframeReady, setIsIframeReady] = useState<boolean>(false);
  const isIframeReadyRef = useRef<boolean>(false);
  // pendingFilesRef: 멀티파일 배열 캐시 (IFRAME_READY 수신 시 즉시 전송)
  const pendingFilesRef = useRef<CodeFile[]>([]);

  const statePayload = useFactoryStore((s) => s.state);
  const isConnected = useFactoryStore((s) => s.isConnected);
  const triggerSelfHealing = useFactoryStore((s) => s.triggerSelfHealing);
  const isConnectedRef = useRef(isConnected);
  useEffect(() => { isConnectedRef.current = isConnected; }, [isConnected]);

  // ─────────────────────────────────────────────────────────────────────────
  // iframe HTML 템플릿
  // 가상 모듈 레지스트리: 여러 파일을 순서대로 컴파일·등록 후 App을 렌더링
  // ─────────────────────────────────────────────────────────────────────────
  const htmlTemplate = `
    <!DOCTYPE html>
    <html lang="ko">
      <head>
        <meta charset="UTF-8" />
        <title>AI Factory Preview</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <script src="https://unpkg.com/react@18/umd/react.development.js" crossorigin></script>
        <script src="https://unpkg.com/react-dom@18/umd/react-dom.development.js" crossorigin></script>
        <script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>
        <script src="https://unpkg.com/lucide@latest"></script>
        <style>
          body { margin: 0; padding: 0; font-family: sans-serif; background: #f8fafc; }
          #root { min-height: 100vh; display: flex; flex-direction: column; }
          .loader { padding: 20px; color: #64748b; font-weight: bold; text-align: center; }
        </style>
      </head>
      <body>
        <div id="root"><div class="loader">컴포넌트 렌더링 대기 중...</div></div>

        <script>
          window.onerror = function(msg) {
            window.parent.postMessage({ type: 'PREVIEW_ERROR', message: msg }, '*');
            return false;
          };

          function notifyReady() {
            if (typeof Babel === 'undefined' || typeof React === 'undefined' || typeof ReactDOM === 'undefined') {
              setTimeout(notifyReady, 50);
              return;
            }
            window.parent.postMessage({ type: 'IFRAME_READY' }, '*');
          }
          notifyReady();

          // ── 유틸 ──────────────────────────────────────────────────────────
          function isRenderable(v) {
            if (typeof v === 'function') return true;
            if (v && typeof v === 'object' && v.$$typeof) return true;
            return false;
          }

          function createModuleStub() {
            var stub = function Stub() { return null; };
            stub.__esModule = true;
            stub.default = function Stub() { return null; };
            if (typeof Proxy !== 'undefined') {
              return new Proxy(stub, {
                get: function(t, p) { return (p in t) ? t[p] : function Stub() { return null; }; }
              });
            }
            return stub;
          }

          // ── 가상 모듈 레지스트리 ──────────────────────────────────────────
          // key: 정규화된 경로(예: "pages/RawMaterialPage")
          // value: { default, [named exports] }
          var moduleRegistry = {};

          function normalizePath(p) {
            // src/ prefix 제거, 확장자 제거
            return p.replace(/^\\.\\//,'').replace(/^src\\//,'').replace(/\\.(tsx?|jsx?)$/,'');
          }

          function resolveRelative(from, to) {
            var fromParts = from.split('/');
            fromParts.pop();
            var toParts = to.replace(/^\\.\\//,'').split('/');
            for (var i = 0; i < toParts.length; i++) {
              var seg = toParts[i];
              if (seg === '..') fromParts.pop();
              else if (seg !== '.') fromParts.push(seg);
            }
            return fromParts.join('/');
          }

          function lookupRegistry(key) {
            var norm = normalizePath(key);
            // exact match
            if (moduleRegistry[norm]) return moduleRegistry[norm];
            // prefix match (src/ stripped)
            var keys = Object.keys(moduleRegistry);
            for (var i = 0; i < keys.length; i++) {
              if (normalizePath(keys[i]) === norm) return moduleRegistry[keys[i]];
            }
            return null;
          }

          function makeRequire(fromPath) {
            return function require(mod) {
              if (mod === 'react') return window.React;
              if (mod === 'react-dom' || mod === 'react-dom/client') return window.ReactDOM;
              if (mod === 'lucide-react' && typeof window.lucide !== 'undefined') return window.lucide;

              if (mod.startsWith('.')) {
                var resolved = resolveRelative(fromPath, mod);
                var found = lookupRegistry(resolved);
                if (found) return found;
              }
              return createModuleStub();
            };
          }

          function compileAndRegister(file) {
            try {
              var compiled = Babel.transform(file.code, {
                presets: [
                  ['env', { modules: 'commonjs' }],
                  ['react', { runtime: 'classic' }],
                  'typescript'
                ],
                filename: file.file_path
              }).code;

              var fileExports = {};
              var fileModule = { exports: fileExports };
              var fn = new Function('exports', 'module', 'require', 'React', compiled);
              fn(fileExports, fileModule, makeRequire(file.file_path), window.React);

              var result = fileModule.exports.__esModule ? fileModule.exports : fileExports;
              var key = normalizePath(file.file_path);
              moduleRegistry[key] = result;
            } catch (e) {
              console.warn('[VMR] 컴파일 실패:', file.file_path, e.message);
            }
          }

          function renderRoot(TargetComponent) {
            if (!window.__reactRoot) {
              window.__reactRoot = ReactDOM.createRoot(document.getElementById('root'));
            }
            window.__reactRoot.render(React.createElement(TargetComponent));
          }

          // ── 메인 실행 핸들러 ──────────────────────────────────────────────
          function executeFiles(files) {
            // main.tsx / index.tsx 는 DOM 마운트 코드라 제외
            var filtered = files.filter(function(f) {
              return !f.file_path.match(/[\\/](main|index)\\.(tsx?|jsx?)$/)
                  && !f.file_path.match(/^(main|index)\\.(tsx?|jsx?)$/);
            });

            // App.tsx 마지막에 컴파일되도록 정렬 (의존성 먼저)
            filtered.sort(function(a, b) {
              var aIsApp = /[\\/]App\\.(tsx?|jsx?)$/.test(a.file_path) || /^App\\.(tsx?|jsx?)$/.test(a.file_path);
              var bIsApp = /[\\/]App\\.(tsx?|jsx?)$/.test(b.file_path) || /^App\\.(tsx?|jsx?)$/.test(b.file_path);
              return (aIsApp ? 1 : 0) - (bIsApp ? 1 : 0);
            });

            // 가상 레지스트리 초기화 후 순서대로 등록
            moduleRegistry = {};
            filtered.forEach(compileAndRegister);

            // App 컴포넌트 탐색
            var TargetComponent = null;

            // 1순위: App.tsx
            var appKeys = Object.keys(moduleRegistry).filter(function(k) {
              return /[\\/]App$/.test(k) || k === 'App';
            });
            for (var i = 0; i < appKeys.length; i++) {
              var exp = moduleRegistry[appKeys[i]];
              var cand = exp.default || Object.values(exp).find(isRenderable);
              if (isRenderable(cand)) { TargetComponent = cand; break; }
            }

            // 2순위: 가장 많은 코드를 가진 컴포넌트 파일
            if (!TargetComponent) {
              var sortedBySize = filtered
                .filter(function(f) { return !/[\\/]App\\./.test(f.file_path) && !/^App\\./.test(f.file_path); })
                .sort(function(a, b) { return (b.code || '').length - (a.code || '').length; });
              for (var j = 0; j < sortedBySize.length; j++) {
                var key = normalizePath(sortedBySize[j].file_path);
                var exp2 = moduleRegistry[key];
                if (!exp2) continue;
                var cand2 = exp2.default || Object.values(exp2).find(isRenderable);
                if (isRenderable(cand2)) { TargetComponent = cand2; break; }
              }
            }

            // 3순위: 레지스트리 전체 탐색
            if (!TargetComponent) {
              var allKeys = Object.keys(moduleRegistry);
              for (var k = 0; k < allKeys.length; k++) {
                var exp3 = moduleRegistry[allKeys[k]];
                var cand3 = exp3.default || Object.values(exp3).find(isRenderable);
                if (isRenderable(cand3)) { TargetComponent = cand3; break; }
              }
            }

            if (TargetComponent) {
              renderRoot(TargetComponent);
            } else {
              throw new Error('렌더링 가능한 컴포넌트를 찾을 수 없습니다. (등록된 파일: ' + Object.keys(moduleRegistry).join(', ') + ')');
            }
          }

          window.addEventListener('message', function(event) {
            if (event.data.type === 'EXECUTE_FILES') {
              try {
                executeFiles(event.data.files || []);
              } catch (err) {
                document.getElementById('root').innerHTML =
                  '<div style="background:#fee2e2;color:#b91c1c;padding:20px;margin:10px;border-radius:8px;border:1px solid #f87171;">' +
                  '<h3 style="margin-top:0;">🚨 렌더링 에러</h3><pre style="white-space:pre-wrap;font-size:13px;">' + err.message + '</pre></div>';
                window.parent.postMessage({ type: 'PREVIEW_ERROR', message: err.message }, '*');
              }
            }
          });
        </script>
      </body>
    </html>
  `;

  // ── rawCode 에서 코드파일 배열 추출 ────────────────────────────────────────
  const extractCodeFiles = useCallback((raw: string): CodeFile[] => {
    if (!raw) return [];

    // 1차: JSON { files: [...] }
    try {
      let jsonStr = raw.trim();
      const mdMatch = jsonStr.match(/`{3}(?:json)?\s*(\{[\s\S]*\})\s*`{3}/);
      if (mdMatch) jsonStr = mdMatch[1];
      const parsed = JSON.parse(jsonStr);
      const files: any[] = parsed.files || [];
      const codeFiles = files.filter((f: any) =>
        f.code && f.file_path &&
        /\.(tsx?|jsx?)$/.test(f.file_path)
      );
      if (codeFiles.length > 0) return codeFiles as CodeFile[];
    } catch (_) {}

    // 2차: 단일 코드블록 → App.tsx 하나짜리 배열로 포장
    let codeToRender = '';
    const blockMatch = raw.match(/`{3}(?:tsx|jsx|ts|js|javascript|react)?\s*\n([\s\S]*?)`{3}/);
    codeToRender = blockMatch ? blockMatch[1] : '';
    if (!codeToRender && !raw.trim().startsWith('{')) codeToRender = raw;
    if (codeToRender && !codeToRender.trim().startsWith('{')) {
      const firstImport = codeToRender.indexOf('import ');
      if (firstImport > 0) codeToRender = codeToRender.substring(firstImport);
      return [{ file_path: 'App.tsx', code: codeToRender.trim() }];
    }

    return [];
  }, []);

  // iframe 에 EXECUTE_FILES 메시지 전송
  const sendExecuteFiles = useCallback((files: CodeFile[]) => {
    if (!files.length || !iframeRef.current?.contentWindow) return;
    iframeRef.current.contentWindow.postMessage({ type: 'EXECUTE_FILES', files }, '*');
  }, []);

  // PREVIEW 탭 진입 시 iframe 재초기화
  useEffect(() => {
    if (iframeRef.current && activeTab === 'PREVIEW') {
      isIframeReadyRef.current = false;
      setIsIframeReady(false);
      iframeRef.current.srcdoc = htmlTemplate;
    }
  }, [activeTab]);

  // rawCode 변경 → 파일 추출 → 캐시 저장 → 준비됐으면 즉시 전송
  useEffect(() => {
    if (!rawCode || isLoading || activeTab !== 'PREVIEW') return;
    const files = extractCodeFiles(rawCode);
    if (!files.length) return;

    pendingFilesRef.current = files;
    setError(null);

    if (isIframeReadyRef.current) sendExecuteFiles(files);
  }, [rawCode, isLoading, activeTab, isIframeReady, extractCodeFiles, sendExecuteFiles]);

  // IFRAME_READY 수신 → 즉시 전송 (타이밍 경쟁 해소)
  useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      if (event.data?.type === 'PREVIEW_ERROR') {
        setError(event.data.message);
        if (isConnectedRef.current && event.data.message) {
          triggerSelfHealing(event.data.message);
        }
      } else if (event.data?.type === 'IFRAME_READY') {
        isIframeReadyRef.current = true;
        setIsIframeReady(true);
        if (pendingFilesRef.current.length) sendExecuteFiles(pendingFilesRef.current);
      }
    };
    window.addEventListener('message', handleMessage);
    return () => window.removeEventListener('message', handleMessage);
  }, [sendExecuteFiles]);

  const getTabContent = () => {
    if (!statePayload) return "데이터 로딩 대기 중...";
    switch (activeTab) {
      case 'RFP': return statePayload.rfp_summary || "요구사항 정의서(RFP)가 아직 없습니다.";
      case 'PRD': return statePayload.prd_summary || "기획서가 없습니다.";
      case 'ARCH': return statePayload.architecture_summary || "아키텍처가 없습니다.";
      case 'TECH': return statePayload.tech_spec_summary || "기술 사양이 없습니다.";
      case 'FRONTEND': return statePayload.frontend_code_summary || "프론트엔드 코드가 없습니다.";
      case 'BACKEND': return statePayload.backend_code_summary || "백엔드 코드가 없습니다.";
      case 'REVIEW': return statePayload.code_review_report_summary || "리뷰 리포트가 없습니다.";
      case 'QA': return statePayload.qa_report_summary || "QA 리포트가 없습니다.";
      case 'MANUAL': return statePayload.user_manual_summary || "사용자 매뉴얼이 아직 생성되지 않았습니다.\nQA 승인 완료 후 자동으로 작성됩니다.";
      default: return "";
    }
  };

  const tabs: { id: TabType; label: string }[] = [
    { id: 'PREVIEW', label: '🖥️ 실시간 샌드박스' }, { id: 'RFP', label: '📋 요구정의(RFP)' }, { id: 'PRD', label: '📄 기획서' },
    { id: 'ARCH', label: '🏗️ 아키텍처' }, { id: 'TECH', label: '🛠️ 기술사양' },
    { id: 'FRONTEND', label: '🎨 프론트엔드' }, { id: 'BACKEND', label: '⚙️ 백엔드' },
    { id: 'REVIEW', label: '📝 리뷰' }, { id: 'QA', label: '🧪 QA' },
    { id: 'MANUAL', label: '📘 사용자 매뉴얼' }
  ];

  return (
    <div className="w-full h-full flex flex-col bg-gray-900 rounded-lg shadow-inner overflow-hidden relative">
      <div className="flex bg-gray-800 border-b border-gray-700 overflow-x-auto shrink-0 select-none">
        {tabs.map((tab) => (
          <button key={tab.id} onClick={() => setActiveTab(tab.id)} className={`px-4 py-2.5 text-xs font-bold border-r border-gray-700 whitespace-nowrap transition-colors ${activeTab === tab.id ? 'bg-gray-900 text-blue-400 border-b-2 border-b-blue-500' : 'text-gray-400 hover:bg-gray-750 hover:text-gray-200'}`}>
            {tab.label}
          </button>
        ))}
      </div>
      <div className="flex-1 min-h-0 relative bg-white">
        {activeTab === 'PREVIEW' ? (
          <>
            {isLoading && (<div className="absolute inset-0 bg-white/70 backdrop-blur-sm flex flex-col items-center justify-center z-20"><div className="w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full animate-spin mb-4"></div><span className="text-gray-600 font-medium animate-pulse text-sm">에이전트가 코드를 컴파일하는 중입니다...</span></div>)}
            {error && !isLoading && (<div className="absolute top-0 left-0 w-full p-3 bg-red-50 text-red-600 text-sm z-10 border-b border-red-200 shadow-sm flex items-start gap-2"><span>🚨</span><div className="flex-1 overflow-hidden overflow-ellipsis"><strong>렌더링 에러:</strong> {error}</div></div>)}
            <iframe ref={iframeRef} title="AI Factory Preview Sandbox" className="w-full h-full border-none flex-1 bg-transparent" sandbox="allow-scripts allow-same-origin" />
          </>
        ) : activeTab === 'MANUAL' ? (
          <div className="w-full h-full bg-white overflow-y-auto">
            <div className="max-w-3xl mx-auto p-8 prose prose-sm">
              {statePayload?.user_manual_summary
                ? <ManualRenderer markdown={statePayload.user_manual_summary} />
                : <p className="text-gray-400 text-sm mt-8 text-center">사용자 매뉴얼이 아직 생성되지 않았습니다.<br />QA 승인 완료 후 자동으로 작성됩니다.</p>
              }
            </div>
          </div>
        ) : (
          <div className="w-full h-full bg-gray-950 p-5 overflow-y-auto text-gray-300 font-mono text-xs whitespace-pre-wrap">{getTabContent()}</div>
        )}
      </div>
    </div>
  );
};

export default PreviewPanel;
