# 데모 라이선스와 근거

> 최신 상태 (2026-11-09): 사용자 후속 요청으로 강의노트 구현이 승인되어 세 종류 생성·키 설정·취소·PDF 기능을 구현했다. 외부 API 실호출과 사용자 무료 프로젝트/노트 품질 검증은 아직 미실행이다. 기존 전사 기능은 유지한다. 아래의 설계만 승인/미구현 표현은 이전 단계 기록이며 현재 상태는 IMPLEMENTATION_STATUS.md의 마지막 항목을 따른다.


자체 코드의 MIT 공개 방향을 유지합니다. 실제 저작권자 표시와 배포 고지는 공개 전에 확정합니다. 현재 구현은 로컬이며 공개 게시를 포함하지 않습니다.

| 구성요소 | 근거와 확인 대상 |
| --- | --- |
| faster-whisper | [공식 문서](https://github.com/SYSTRAN/faster-whisper), CPU int8와 로컬 모델 사용, 실제 설치 버전 고정 |
| Whisper | [공식 저장소](https://github.com/openai/whisper), 다국어 모델과 코드·가중치 라이선스 |
| FastAPI | [공식 문서](https://fastapi.tiangolo.com/), 기존 로컬 화면 구조 재사용 |
| PyAV·FFmpeg | [PyAV 라이선스](https://github.com/PyAV-Org/PyAV/blob/master/LICENSE.txt), [FFmpeg 조건](https://ffmpeg.org/legal.html), 실제 포함 바이너리 확인 |

모델 파일의 출처·revision·해시·라이선스를 준비 단계에서 기록합니다. Gemini·Google API SDK·키 저장 의존성은 데모에 필요 없습니다. 기존 문서에 있던 API 조건과 학습노트 참고 자료는 현재 범위에서 제외합니다.

이 PC에 준비한 모델의 revision·SHA-256은 MODEL_MANIFEST.json에 기록했습니다. 실제 모델 파일은 Git에서 제외합니다.

## 강의노트 의존성·정책 확인 예정 (설계만 승인)

SDK·PDF 라이브러리·재배포 가능한 한글 글꼴은 아직 미선정이다. 구현 전 호환성과 폰트 임베딩/재배포 조건을 확인하고 버전을 고정한다. 이번 문서 작업에서 설치/다운로드는 하지 않았다. 정책 확인 경로: [Gemini 가격](https://ai.google.dev/gemini-api/docs/pricing), [한도](https://ai.google.dev/gemini-api/docs/rate-limits), [이용 조건](https://ai.google.dev/gemini-api/terms), [결제](https://ai.google.dev/gemini-api/docs/billing). 이전 논의의 선택 근거이며 이번 작업에서 최신 조건을 재검증한 것은 아니다.

## 강의노트에서 실제 선택한 의존성

- ReportLab 5.1.0: 로컬 PDF 생성. https://docs.reportlab.com/reportlab/userguide/ch3_fonts/ (TrueType Unicode 지원 확인).
- httpx 0.28.1: 기존 설치 버전의 비동기 HTTP, 공식 Gemini REST 호출.
- 나눔고딕 Regular: https://github.com/google/fonts/blob/main/ofl/nanumgothic/NanumGothic-Regular.ttf — NHN Corporation, SIL OFL 1.1. 원본 폰트와 OFL.txt를 src/lecture_transcriber/fonts에 동봉. SHA-256 76f45ef4a6bcff344c837c95a7dcc26e017e38b5846d5ae0cdcb5b86be2e2d31.
- 검증 도구 PyMuPDF 1.28.2(AGPL/상용 이중 라이선스), Playwright 1.64.1은 개발 테스트용이며 런타임 의존성에는 추가하지 않았다. requirements.lock은 개발 환경 전체를 잠근 파일이다. 배포 시 테스트 도구를 묶지 않고 라이선스를 검토한다.
- 모델 후보 문서: https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash (1M 입력·구조화 출력), https://ai.google.dev/gemini-api/docs/pricing.md (무료 등급). 확인일 2026-11-09, 계정 접근성과 품질은 미검증.
- Microsoft Windows 자격 증명 API: https://learn.microsoft.com/windows/win32/api/wincred/nf-wincred-credreadw .
