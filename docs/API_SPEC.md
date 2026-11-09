# 데모 내부 호출 계약

> 최신 상태 (2026-11-09): 사용자 후속 요청으로 강의노트 구현이 승인되어 세 종류 생성·키 설정·취소·PDF 기능을 구현했다. 외부 API 실호출과 사용자 무료 프로젝트/노트 품질 검증은 아직 미실행이다. 기존 전사 기능은 유지한다. 아래의 설계만 승인/미구현 표현은 이전 단계 기록이며 현재 상태는 IMPLEMENTATION_STATUS.md의 마지막 항목을 따른다.


Gemini 등의 외부 API는 제거합니다. 아래는 로컬 브라우저 화면과 로컬 서버 사이의 구현용 계약이며 API 키가 필요한 외부 서비스가 아닙니다. 기존 보관함 API를 대체하는 현재 구현 계약입니다.

| 호출 | 입력 | 결과 |
| --- | --- | --- |
| GET /api/v1/models | 없음 | [{id,label,available}]의 허용 모델 목록 |
| POST /api/v1/transcriptions | multipart file, model_id, hint? (기본 빈 문자열, 최대 100자) | 202 {job_id,state:running,model_id} |
| GET /api/v1/transcriptions/{job_id} | 작업 ID | {job_id,state,model_id,text,error} |
| GET /api/v1/transcriptions/{job_id}/download | 작업 ID | UTF-8 .md 첨부 파일 |

GET /api/v1/health, POST /api/v1/session(launch_token), GET /api/v1/session, POST /api/v1/shutdown({confirmed:true})를 제공합니다. 최초 토큰 유효시간은 60초이며 쿠키·CSRF로 이후 요청을 보호합니다. 과목·용어·교정·노트 관련 경로는 데모에 제공하지 않습니다.

전사 중 새 요청은 409 BUSY, 허용되지 않은 모델은 422 INVALID_MODEL, 로컬 모델 없음은 409 MODEL_MISSING, 큰 파일은 413 FILE_TOO_LARGE, 미지원 파일은 415 UNSUPPORTED_MEDIA입니다. 완료 전 다운로드는 409 NOT_READY, 작업 없음·만료는 404입니다.

모델 ID·작업 ID를 서버 경로로 직접 조합하지 않습니다. API는 로컬 경로·URL 입력을 받지 않습니다. 오류는 한국어 안내를 반환하며 파일 경로·스택을 노출하지 않습니다.

클라이언트는 약 1초 간격으로 현재 작업을 조회합니다. completed에서만 결과를 표시합니다. 정확한 진행률이나 ETA 계약은 없습니다. 새 입력으로 이전 결과와 다운로드를 초기화합니다.

허용 모델: base, small, large-v3-turbo. hint는 앞뒤 공백 제거 후 initial_prompt로 전달하며 비어 있으면 None입니다. 100자 초과는 422입니다.

작업 조회에 diagnostics_status 추가: pending / saved / failed / unavailable (테스트 엔진 등 기록 없음). 진단 파일 내용은 HTTP로 제공하지 않습니다.

복구 추가: 작업 조회 recovery={status,attempted,applied,unresolved}. status는 pending/not_needed/applied/partial/needs_review/archive_failed/unavailable. GET /api/v1/transcriptions/{job_id}/original은 원래 Markdown, /recovery는 감사 JSON 첨부. 현재 세션·작업·완료 상태를 검증하며 요청 경로로 파일 시스템 경로를 받지 않습니다.

## 강의노트 내부 API 추가안 (설계만 승인)

신규 notes/settings·key·note-jobs·notes/pdf 등의 요청/응답·오류·CSRF 계약은 [기술 설계의 내부 API](STUDY_NOTES_TECHNICAL.md)에 정의했다. 모두 미구현이며 기존 전사 경로는 유지한다.

## 노트 API 구현 반영

STUDY_NOTES_TECHNICAL.md의 추가 경로를 구현했다. 실제 작업 응답 키는 note_job_id가 아닌 id이며 snapshot_id는 전사 UUID다. note content 응답은 서버 생성 evidence만 추가하고 sources 사전은 숨긴다. settings는 key_configured/provider/model/quality_verified를 반환한다. extra 필드는 거절한다. 오류 MODEL_UNAVAILABLE, SOURCE_MAPPING_MISSING, ALREADY_EXISTS, INVALID_REQUEST도 추가했다. 키 저장/삭제 중 active 노트 작업은 BUSY로 거절한다. 구체 스키마는 note_routes.py와 note_content.py가 기준이다.
