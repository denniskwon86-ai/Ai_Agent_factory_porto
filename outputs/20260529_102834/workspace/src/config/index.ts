// 이 파일은 Electron 메인 프로세스에서 환경 변수를 로드하거나,
// 복잡한 전역 설정을 관리할 때 사용될 수 있습니다.
// 현재 프론트엔드 React 앱은 .env 파일을 직접 사용하므로,
// 이 파일은 API URL을 노출하는 용도로만 사용합니다.

export const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:3001/api';

// Electron 환경에서 IPC 통신을 위한 타입 정의 (예시)
declare global {
  interface Window {
    electron?: {
      invoke: (channel: string, ...args: any[]) => Promise<any>;
      on: (channel: string, listener: (...args: any[]) => void) => () => void;
    };
  }
}