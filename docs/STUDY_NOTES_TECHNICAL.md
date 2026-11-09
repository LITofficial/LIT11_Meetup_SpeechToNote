# 강의노트 기술 설계 — 미구현

> 최신 상태 (2026-11-09): 사용자 후속 요청으로 강의노트 구현이 승인되어 세 종류 생성·키 설정·취소·PDF 기능을 구현했다. 외부 API 실호출과 사용자 무료 프로젝트/노트 품질 검증은 아직 미실행이다. 기존 전사 기능은 유지한다. 아래의 설계만 승인/미구현 표현은 이전 단계 기록이며 현재 상태는 IMPLEMENTATION_STATUS.md의 마지막 항목을 따른다.

사용자 결정은 [기능 명세](STUDY_NOTES_SPEC.md)가 우선한다. 아래 구조·경로·제한은 위임된 기술 기본값이며 구현 요청 후 검증한다. 모델 ID·의존성 버전·실측 값은 아직 확정하지 않는다.

## 구조

브라우저 → 기존 루프백 서버 → 노트 작업 관리자 → Gemini 어댑터 → 외부 Gemini.
노트 작업 관리자 → 검증된 구조화 결과 → 공통 문서 모델 → 화면 / 로컬 PDF 렌더러.
키 관리자는 Windows Credential Manager만 사용하며 ASR worker와 분리한다. 기존 ASR은 네트워크 없이 실행하며 AI 장애·키 미설정·할당량 초과가 ASR 및 전사문 다운로드를 막지 않는다.

화면은 API 키를 로컬 키 설정 요청으로 한 번 전달하고 값을 비운다. localStorage/cookie/URL/로그/명령줄/일반 설정 파일에 키를 넣지 않는다. GET은 설정 여부만 반환한다. 자격 증명 저장 실패 시 평문 파일로 대체하지 않는다. 키는 서버에서 Gemini 인증에만 사용하며 요청 본문이나 모델 지시문에 포함하지 않는다. 생성 중 키 변경/삭제는 잠근다.

## 전사 구간과 근거 연결: 구현 선행 조건

현재 worker.run은 최종 문자열을 반환하며 일반 diagnostics에는 전사문이 없다. recovery 기록은 복구 대상이 없으면 생성되지 않을 수 있다. 따라서 기존 진단/복구 JSON에만 의존해서 전체 강의의 근거를 만들 수 없다.

향후 worker에서 모든 작업의 최종 segment 목록을 메모리 결과로 전달한다. accepted 복구는 retry_segments의 원본 기준 절대 시간으로 교체하고, 거절/실패/미적용은 원래 구간을 유지한다. 합성된 최종 문자열과 이 목록의 문자열은 공백·문장 배치 외에는 동일해야 한다. ASR 출력이나 복구 채택 기준은 바꾸지 않는다.

각 구간에 snapshot 내 고유 source_id를 부여한다. Gemini에는 source_id, text, uncertainty만 보내고 숫자 시간은 보내지 않아도 된다. 응답은 근거 source_id만 참조한다. 서버가 해당 ID를 원본 시간으로 변환해 [42:10] 또는 시간 범위를 표시한다. 실제 음성 밖/역전/결측 시간은 정확한 시각을 발명하지 않고 근거 시각 확인 필요로 표시한다. ASR 시간 자체도 근사값이며 단어 단위 정밀성은 보장하지 않는다.

최초 진단의 flag를 복구 후 상태에 그대로 붙이지 않는다. 적용된 재시도와 미해결 후보를 연결하고, 미해결 low confidence/invalid time/반복 정보를 최종 구간에 매핑한다. applied/unresolved 수는 전체 오류 수가 아니다. 정상 점수가 의미 정확성을 보장하지 않으므로 노트에서도 불확실성 지시를 유지한다.

## 스냅샷·동시성·취소

전사 완료 snapshot_id에 job_id, final_text, final_segments를 고정한다. 외부 입력 파일명·경로·raw_text·전체 복구 기록은 전송하지 않는다. 사용자 제목은 로컬에서만 붙인다. 서버가 소유한 snapshot으로 전송하며 브라우저가 임의 전사문이나 URL을 지정하게 하지 않는다.

한 세션에 ASR 또는 노트 생성 하나만 실행한다. 생성 버튼 요청에는 request_id를 붙여 이중 클릭/재전송을 중복 API 호출로 만들지 않는다. kind별 기존 completed note는 새 note_job과 분리한다.

상태: idle → running → completed / failed / cancelled / timed_out. 최초 로컬 생성 요청부터 monotonic 180초가 상한이며 SDK/HTTP 개별 timeout도 이 안에 제한한다. SDK 기본 재시도는 끈다. 취소/시간 초과/새 snapshot은 generation 번호를 무효화한다. 늦게 오는 응답은 완료를 덮어쓰지 못한다. 락 안에서 상태 검사와 원자 교체를 수행한다. 가능하면 네트워크 요청도 중단하되 공급자 측 취소/사용량 반환은 보장하지 않는다. 사용자가 이미 앱을 종료한 뒤 요청이 완료돼도 저장하지 않는다.

## 모델·용량·응답 검사

Google AI Studio에서 해당 프로젝트의 무료 제공 모델/입출력 한도/실제 quota/결제 상태를 구현 단계에서 확인한다. 무료 지원 모델 하나를 고정하고 모델 ID·검증일·프롬프트 버전을 기록한다. 지금 유효한 모델 이름이나 고정 무료 횟수를 추측하지 않는다. 유료 전환은 별도 사용자 결정이며 결제된 프로젝트의 과금 여부를 앱만으로 무조건 보장하지 않는다.

전사 전체와 지시문, 출력 여유를 포함해 길이 검사를 한다. 신뢰할 수 있는 로컬 토큰 계산 방식과 모델 한도는 모델 확정 단계에서 선택한다. 입력이 한도를 넘거나 전체 수용 가능 여부를 확인할 수 없으면 안내하고 호출하지 않는다. 몰래 잘라내기, 선요약, 다중 호출 분할은 첫 버전에 없다. 출력 분량은 종류별 목표를 프롬프트로 조절하며 고정 페이지 수는 약속하지 않는다.

구조화 응답 스키마, 정상 종료 사유, 비어 있지 않음, 문제-정답 ID 대응, source_id 존재, 보충/강의 구분을 검증한다. 출력 토큰 한도 종료·차단·스키마 오류는 완료로 취급하지 않는다. 의미상 오류는 구조 검사만으로 해결되지 않으며 사람 평가가 필요하다. 오류 후 자동 보정용 API 호출도 하지 않는다.

## 내부 API 추가안 (모두 미구현)

기존 세션·Host·Origin·CSRF 검사를 그대로 적용하고 모든 ID 소유권/현재 snapshot을 검사한다. 클라이언트 경로·URL 입력 금지. GET은 외부 API를 호출하지 않는다.

| 호출 | 요청 | 응답/동작 |
| --- | --- | --- |
| GET /api/v1/notes/settings | 없음 | key_configured, provider=gemini, model_ready; 키 값 없음 |
| PUT /api/v1/notes/key | {key} | 로컬 자격 증명 저장, 외부 호출 없음 |
| DELETE /api/v1/notes/key | 없음 | 해당 앱 키만 삭제 |
| PATCH /api/v1/transcriptions/{id}/note-title | {title} | 공통 노트 제목 변경; API 미호출 |
| POST /api/v1/transcriptions/{id}/notes | {kind, snapshot_id, request_id, regenerate} | 202 {note_job_id,state:running}; 기존 결과 조회와 분리 |
| GET /api/v1/note-jobs/{id} | 없음 | 상태·오류 코드·완료 note_id; 부분 본문 없음 |
| POST /api/v1/note-jobs/{id}/cancel | 없음 | 멱등 취소, 늦은 완료 차단 |
| GET /api/v1/transcriptions/{id}/notes | 없음 | 현재 snapshot의 종류별 완료 결과 목록 |
| GET /api/v1/notes/{id} | 없음 | 검증 완료된 구조화 내용과 서버 계산 근거 시간 |
| GET /api/v1/notes/{id}/pdf | 없음 | 현재 제목으로 application/pdf 첨부; AI 미호출 |

기술 입력 제한 기본값: 제목 1~120자(확장자 제거 파일명 기본값, 빈 파일명은 강의노트), 키 1~4096자, kind=understand|memorize|practice, UUID 검증. 제목 파일명은 경로/제어 문자 정리, PDF 헤더 인젝션 방지. 의도치 않은 필드 거절.

오류: 409 BUSY/STALE_SNAPSHOT/NOT_READY, 404 NOT_FOUND, 422 INVALID_INPUT/INPUT_TOO_LONG, 409 KEY_MISSING, 502 PROVIDER_AUTH/PROVIDER_UNAVAILABLE/INVALID_OUTPUT/OUTPUT_INCOMPLETE, 429 QUOTA_EXCEEDED, 504 GENERATION_TIMEOUT, 500 PDF_FAILED/CREDENTIAL_STORE_FAILED. 사용자에게 과금 보장·기다리면 반드시 해결 등의 단정 없이 한국어 설명을 매핑한다. 공급자 원문/스택/키/개인 경로는 반환하지 않는다. 429와 5xx도 자동 재시도 없음.

## 데이터 계약 추가안

영구 DB 추가 없음. 기존 전사·복구 스키마 보존, 새 노트용 snapshot은 별도 메모리 객체.

| 객체 | 필드 |
| --- | --- |
| TranscriptSnapshot | snapshot_id, job_id, final_text, segments[], created_at |
| SourceSegment | source_id, start_seconds?, end_seconds?, text, origin(original/retry), uncertainty_codes[] |
| NoteJob | id, request_id, snapshot_id, kind, generation, state, started_at, deadline, error_code? |
| Note | id, snapshot_id, kind, title, content, model_id, prompt_version, created_at |
| NoteContent | sections[], questions[], answers[]; 종류에 맞는 필수 필드 검증 |
| Section | id, heading, blocks[] |
| Block | type(paragraph/list/table/qa), content, basis(lecture/supplement), source_ids[], uncertain |
| Question | id, category(concept/application), format, prompt, options?, source_ids[], basis, uncertain |
| Answer | question_id, answer, explanation, source_ids[], basis, uncertain |
| NoteEvent | timestamp, random operation_id, stage, kind?, model_id?, duration_ms, outcome, error_code? |

block.content는 type별 제한 구조를 사용한다(문단 문자열, 목록 문자열 배열, 표 columns/rows, qa의 question/answer). HTML·스크립트·원격 이미지·임의 링크를 실행하지 않는다. 강의 근거와 보충은 블록을 나눠 표시한다. 질문 ID는 유일하며 답과 정확히 1:1로 대응한다. 숫자 시간은 모델 출력으로 받지 않는다.

## PDF

공통 검증 문서 모델로 화면과 PDF를 만든다. 제목/노트 종류/본문/표/근거/보충·확인 필요/문제·해설이 동일하게 포함된다. 로컬 렌더러와 재배포 가능한 한글 폰트를 선택하고 라이선스/버전을 고정한다. 라이브러리는 아직 미선정이며 구현 단계에서 한글·영문·표·페이지 나눔 실험 후 결정한다. 폰트는 실행 중 외부에서 가져오지 않는다.

A4 세로, 흰 배경, 검은 본문, 초록 제목, 페이지 번호, 별도 표지 없음. 긴 표 머리 반복, 긴 셀 줄바꿈, 제목 고립/문제-보기 분리 최소화, 코드와 기호 처리, 한글 글꼴 임베딩을 검증한다. 렌더러 외부 리소스 접근 차단. 메모리 생성 우선, 임시 파일 필요 시 앱 관리 임시 폴더만 사용하고 정리한다. 노트 자동 영구 저장은 하지 않는다. 다운로드 실패 후 로컬 변환만 다시 수행한다.

## 구현된 계약과 기술값

- 모듈: credentials.py, gemini.py, note_content.py, note_sources.py, notes.py, note_routes.py, note_pdf.py. worker와 recovery는 선택적 final_segments 수집을 추가했으며 기존 문자열/복구 채택 기준은 유지한다.
- 노트 snapshot_id는 해당 전사 job UUID. 원래/accepted retry 구간을 최종 순서로 연결하고 문자열 일치를 검사한다. source_duration을 이용해 시간 유효성을 검사하며 불명확하면 시각 확인 필요로 표시한다. 기존 버전 작업은 근거 정보가 없어 새 전사가 필요하다.
- SDK 대신 httpx 0.28.1의 고정 Gemini REST endpoint를 사용한다. redirects/proxy 환경 자동 적용/자동 재시도 없음. 모델 후보 gemini-3.5-flash, prompt notes-v1, 출력 상한 16000 tokens, 요청 전체 UTF-8 JSON 200000 bytes의 보수적인 로컬 입력 상한. 이는 정밀 토큰 추정이나 무료 quota가 아니며 전체 입력을 잘라내지 않는다. 180초 작업 상한 안에 HTTP 175초/connect 15초를 적용한다.
- Windows CredReadW/CredWriteW/CredDeleteW, 사용자 Credential Manager target SpeechToNote/Gemini. 키는 ASCII 공백 없는 1~2560자. 일반 파일 fallback 없음. 별도 입력 필드를 비운다.
- POST notes와 GET note-jobs 실제 응답은 {id,state,kind,error,note_id,snapshot_id}. settings는 {key_configured,provider,model,quality_verified:false}; 계정 접근성과 품질 검증 완료를 뜻하지 않는다.
- Section은 heading,blocks. Block은 type,text,items,columns,rows,question,answer,basis,source_ids,uncertain의 고정 필드(미사용 필드는 빈 값). Content에는 sections,questions,answers,fewer_questions_reason. 상세 제약은 note_content.py의 Pydantic schema가 실행 계약이다. 화면 응답에 서버 생성 evidence를 추가하며 원본 source 텍스트 사전은 반환하지 않는다.
- note-events/events.jsonl에는 UTC 시각·무작위 작업 ID·stage·kind·model_id·duration_ms·outcome·error_code만 기록한다. 본문/키/경로/공급자 응답은 기록하지 않는다.
- ReportLab 5.1.0, 로컬 나눔고딕 TTF 임베딩, 메모리 PDF 생성. 렌더러는 HTML/URL을 해석하지 않으며 문자열 이스케이프. 키 저장 실패/미설정은 ASR에 영향 없음.
- 노트 목록/결과 조회·제목 변경/생성 완료는 last_activity를 갱신하고 진행 중 만료를 막는다. 전사만 사용하는 경우 기존 completed 기준 30분 만료를 유지한다. 새 전사 시작/앱 종료 시 노트 메모리 정리. 손실 확인은 UI에서만 수행하고 서버는 현재 작업 ID·락으로 교차 실행을 거절한다.

## Gemini 요청 형식 오류 수정 (2026-11-09)

사용자 최초 시험은 HTTP 400 INVALID_ARGUMENT로 실패했고 기존 앱이 400/401/403을 모두 PROVIDER_AUTH로 표시해 키 문제로 오인하게 했다. 저장된 키의 읽기 전용 모델 조회는 HTTP 200. 사용자 허용 1회 합성 요청으로 기존 형식의 400을 재현했다. 공급자 원문과 키는 기록하지 않았다.

전송 스키마에서 중첩 참조를 풀고 title/additionalProperties 및 길이·개수 제한을 제거했다. Pydantic 로컬 검증의 길이·개수·근거 검사는 유지했다. 정확히 어떤 스키마 필드가 서버 거절을 일으켰는지는 개별 실험하지 않았다. 사용자 추가 허용 1회 합성 요청에서 수정 형식의 실제 Gemini 생성 및 PDF 변환 성공(8.97초, 2개 섹션). 실제 강의 내용은 전송하지 않았다. 전체 자동 테스트 50개 통과. 400 요청 오류/스키마 오류, 401·키 만료, 403 권한·키 제한을 별도 안전한 오류 코드와 메시지로 구분한다. 자동 재시도·다른 모델 전환 없음.

## 노트 응답 검증 실패 진단 개선 (2026-11-09)

사용자 실행에서 22.2초 후 INVALID_OUTPUT 발생. 기존 기록은 상세 검증 항목을 보존하지 않아 해당 응답의 실패 원인은 확정 불가. 검증을 우회하지 않고 NOTE_SCHEMA_INVALID/SOURCE_UNKNOWN/SOURCE_MISSING/BLOCK_EMPTY/TABLE_INVALID/QUESTION_MISMATCH 등 세부 코드로 분리했다. 로그에는 허용된 필드 경로·수치 인덱스·검증 규칙만 추가하고 입력 본문·근거 문자열·Pydantic input/context·추가 필드명은 저장하지 않는다. notes-v2 지시문에 로컬 길이/개수 한도, 근거 ID 사용, 종류별 빈 배열, 표 열 대응 규칙을 명시했다. 관련 모의 테스트 13개 통과. 이번 수정의 실제 Gemini 호출은 미실행이며 사용자 사례 해결 여부는 아직 미확인이다.

## PDF 가독성·응용 문제 근거 수정 (2026-11-09)

사용자 요청으로 PDF에서는 강의 근거 시간 문자열을 표시하지 않는다. 근거 ID 검증/내부 매핑과 화면의 근거 표시는 유지한다. 보충 설명·응용 문제·확인 필요는 PDF에서도 유지한다. 초록색 소제목 앞 16pt 여백으로 이전 주제와 한 줄 정도 구분한다. 기존 다운로드 파일은 변경하지 않으며 새 PDF 변환에 적용한다.

문제풀이 실패 두 건은 NOTE_SCHEMA_INVALID/questions.6.source_ids/too_short로, HTTP 429가 아니라 7번째 문제의 빈 근거 목록을 거절한 로컬 검증이었다. 당시 basis 값은 기록하지 않아 해당 문제의 lecture/supplement 분류는 확정할 수 없다. Question/Answer의 무조건 min_length=1 제한을 없애고 공통 의미 검증에서 lecture는 여전히 근거 필수, supplement는 빈 근거 허용으로 정합성을 맞췄다. 존재하지 않는 ID는 어느 유형에서도 거절한다. notes-v3 지시문 반영. 관련 테스트 15개 통과. 실제 문제풀이 재생성은 하지 않았으며 사용자 사례 해결 여부는 다음 생성으로 확인한다.

## 공급자 서버 오류 진단 보완 (2026-11-09)

사용자의 start.cmd 기본 데이터 경로 기록에서 이해용 3719ms, 암기용 2640ms 뒤 PROVIDER_UNAVAILABLE 확인. 표시 문구는 HTTP 응답의 일반 오류 분기에 해당하지만 기존 로그에는 번호가 없어 실제 상태를 확정할 수 없다. QUOTA_EXCEEDED 기록은 아니다. HTTP 500/502/503/504는 PROVIDER_SERVER_ERROR와 실제 번호로 안내하고, 기타 오류도 번호를 표시한다. 로그에는 http_status 및 허용된 Google 표준 status만 추가한다. 공급자 본문·키·개인정보는 기록하지 않는다. 관련 모의 테스트 16개 통과, 실제 API 재호출 없음. 기존 실행 프로세스에는 코드가 자동 반영되지 않으며 다음 시작부터 적용된다. 일시적 오류 재시도는 현재 전사 결과를 유지한 채 사용자가 생성 버튼으로 수행할 수 있다.
