## 1. 전체 아키텍처 개요

본 시스템은 로컬 파일 기반 복구 세션 관리를 위한 데스크톱 애플리케이션으로 설계됩니다. 사용자 인터페이스는 직관적이고 사용하기 쉬워야 하며, 백엔드 로직은 파일 시스템과의 상호작용, 세션 정보 관리, 압축 및 암호화 기능을 담당합니다. 데이터베이스는 세션 메타데이터를 저장하여 효율적인 검색 및 관리를 지원합니다. 확장성은 로컬 파일 시스템에 국한되므로, 주요 고려사항은 **성능 (특히 파일 탐색 및 복구 속도)**과 **유지보수 용이성 (코드의 모듈화 및 명확성)**입니다.

## 2. 기술 스택 (Front, Back, DB)

*   **Front-end (Desktop Application UI)**:
    *   **기술**: Electron (Node.js 기반 크로스 플랫폼 데스크톱 앱 프레임워크)
    *   **언어**: JavaScript / TypeScript
    *   **UI 라이브러리**: React 또는 Vue.js (선택 사항, 개발 생산성 및 UI 복잡성에 따라 결정)
    *   **역할**: 사용자 인터페이스 제공, 사용자 입력 처리, 백엔드 API 호출, 결과 시각화.

*   **Back-end (Core Logic & File System Interaction)**:
    *   **기술**: Node.js (Electron의 런타임 환경 활용)
    *   **언어**: JavaScript / TypeScript
    *   **라이브러리**:
        *   `fs-extra`: 파일 시스템 작업 (복사, 이동, 삭제, 디렉토리 생성 등)
        *   `archiver`: ZIP, TAR.GZ 압축 생성
        *   `crypto`: 암호화 (AES 등)
        *   `glob` 또는 `fast-glob`: 파일/폴더 패턴 매칭 및 탐색
        *   `uuid`: 고유 ID 생성
    *   **역할**: 세션 자동 탐지, 파일/폴더 선택 처리, 세션 생성/구성 로직, 압축 및 암호화, 실행/복원 로직, 진행 상황 표시, 오류 처리.

*   **Database (Session Metadata Storage)**:
    *   **기술**: SQLite (로컬 파일 기반, 별도 서버 불필요)
    *   **ORM/라이브러리**: `Sequelize` 또는 `TypeORM` (TypeScript 사용 시) 또는 `Knex.js`
    *   **역할**: 복구 세션의 메타데이터 (이름, 생성일, 저장 경로, 압축/암호화 설정, 대상 파일 목록 등) 저장 및 관리.

## 3. 데이터베이스 스키마 (주요 테이블 구조)

```sql
-- 세션 정보를 저장하는 테이블
CREATE TABLE sessions (
    id TEXT PRIMARY KEY, -- 고유 세션 ID (UUID)
    name TEXT NOT NULL, -- 사용자 지정 세션 이름
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP, -- 세션 생성 일시
    storage_path TEXT NOT NULL, -- 세션 파일이 저장될 기본 경로 (압축 파일 경로)
    compression_type TEXT, -- 압축 방식 (e.g., 'zip', 'tar.gz', NULL)
    encryption_key TEXT, -- 암호화 키 (실제로는 안전하게 관리되어야 함, 여기서는 개념적 표현)
    is_encrypted BOOLEAN DEFAULT FALSE, -- 암호화 여부
    description TEXT -- 세션에 대한 추가 설명 (선택 사항)
);

-- 각 세션에 포함된 파일/폴더 정보를 저장하는 테이블
CREATE TABLE session_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL, -- sessions 테이블의 id와 연결
    item_path TEXT NOT NULL, -- 원본 파일 또는 폴더의 절대 경로
    item_type TEXT NOT NULL, -- 'file' 또는 'directory'
    FOREIGN KEY (session_id) REFERENCES sessions (id) ON DELETE CASCADE
);

-- 복구 작업 기록을 저장하는 테이블 (선택 사항, 감사 및 디버깅 용이)
CREATE TABLE recovery_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    operation_type TEXT NOT NULL, -- 'restore', 'create' 등
    status TEXT NOT NULL, -- 'success', 'failed', 'in_progress'
    start_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    end_time DATETIME,
    error_details TEXT, -- 오류 발생 시 상세 정보
    FOREIGN KEY (session_id) REFERENCES sessions (id) ON DELETE CASCADE
);
