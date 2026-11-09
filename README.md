# Speech to Note

한국어 강의 녹음 파일을 내 컴퓨터에서 전사하고, 필요하면 Gemini로 학습 목적에 맞는 강의노트를 만드는 Windows 로컬 앱입니다.

**녹음 업로드 → 모델 선택 → 전사 → 전사문 다운로드 → 선택적으로 강의노트 생성·PDF 다운로드**

전사는 로컬 Whisper 모델을 사용하므로 API 키나 서비스 크레딧이 필요 없습니다. 강의노트 생성은 별도의 Gemini API를 사용하며 계정별 사용량 제한과 요금 정책이 적용됩니다.

## 주요 기능

- M4A·MP3·WAV 파일 한 개 업로드(최대 200MiB)
- Base·Small·Turbo(large-v3-turbo) 모델 선택
- 최대 100자의 선택 입력인 **용어**로 강의명·핵심 용어 전달
- 문장별 줄바꿈을 적용한 전사문 표시와 시간표시 없는 Markdown 다운로드
- 반복·힌트만 출력되는 구간·연속 저신뢰도 구간의 제한적 자동 재전사
- 이해용·암기용·문제풀이용 강의노트 생성과 한글 PDF 다운로드
- 좌측 상단 메뉴에서 Gemini API 키 설정

## 준비 사항

- Windows 10/11 64비트 PC와 Python 3.10 64비트(검증 환경: 3.10.5)
- Git 또는 GitHub의 ZIP 다운로드
- 최초 패키지·모델 설치를 위한 인터넷 연결과 수 GB 이상의 디스크 여유 공간
- 강의노트 기능을 사용할 경우 Gemini API 키와 인터넷 연결

현재 전사는 CPU에서 실행합니다. GPU는 필수가 아닙니다. 모델이 클수록 메모리와 처리 시간이 늘어나며, 긴 녹음은 상당한 시간이 걸릴 수 있습니다. 먼저 짧은 파일로 확인하세요.

## 처음 설치하기

아래 명령은 **PowerShell**에서 실행합니다. Python 설치 시 `Add Python to PATH`를 선택하세요.

```powershell
git clone https://github.com/redsnack12345/LIT11_Meetup_SpeechToNote.git
cd LIT11_Meetup_SpeechToNote
py -3.10 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e .
```

ZIP으로 받은 경우 압축을 푼 뒤 `start.cmd`가 있는 폴더에서 PowerShell을 열고, 위 명령 중 가상환경 생성부터 실행하면 됩니다. 가상환경 활성화 명령은 필요하지 않습니다.

### 모델 다운로드

세 모델을 모두 준비하려면 다음 명령을 실행하거나 `prepare-models.cmd`를 더블클릭합니다.

```powershell
.\prepare-models.cmd
```

모델 하나만 준비하려면 다음과 같이 실행합니다.

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m lecture_transcriber.setup_models --model large-v3-turbo
```

`--model`에는 `base`, `small`, `large-v3-turbo`를 사용할 수 있습니다. 모델은 저장소의 `models` 폴더에 저장됩니다. 준비가 끝난 모델만 앱에서 사용할 수 있으며, 파일과 검증 정보를 수동으로 이동하기보다 준비 명령을 사용하세요.

| 모델 | 선택 기준 |
| --- | --- |
| Base | 빠른 동작 확인, 상대적으로 가벼운 처리 |
| Small | 속도와 품질을 함께 비교할 때 |
| Turbo | 품질을 우선할 때. CPU에서는 오래 걸릴 수 있음 |

모델을 준비한 뒤에는 전사만 사용할 경우 인터넷이 필요 없습니다.

## 실행 및 전사

1. 저장소 폴더의 **start.cmd를 더블클릭**합니다. PowerShell에서는 `.\start.cmd`를 실행합니다.
2. 자동으로 열린 브라우저에서 녹음 파일을 선택합니다. 브라우저가 열리지 않으면 기본 브라우저 설정을 확인한 뒤 터미널에서 Ctrl+C로 종료하고 다시 실행합니다.
3. 준비된 모델을 선택합니다. 필요하면 용어에 `클라우드컴퓨팅`처럼 핵심 용어를 입력합니다. 비워 두어도 됩니다.
4. 전사를 시작하고 완료될 때까지 기다립니다.
5. 전사문을 확인하고 Markdown 파일을 다운로드합니다.
6. 사용을 마치면 화면의 **앱 종료** 버튼을 누릅니다.

브라우저 화면을 사용하지만 서버와 음성 인식은 본인 PC에서 실행됩니다. 터미널 창을 닫으면 앱이 종료될 수 있습니다. 실행 중 `start.cmd`를 다시 누르지 마세요.

## 강의노트 만들기 (선택)

1. [Google AI Studio](https://aistudio.google.com/apikey)에서 본인 계정의 Gemini API 키를 준비합니다.
2. 앱 좌측 상단 **☰ 메뉴**를 열고 API 키를 입력한 뒤 저장합니다. 키는 Windows 자격 증명 저장소에 보관되며 이후 실행에서도 사용할 수 있습니다. 메뉴에서 변경·삭제할 수 있습니다.
3. 전사가 끝나면 **강의노트** 탭으로 이동합니다.
4. **강의노트 제목**을 입력하고 제목을 적용합니다.
5. 학습 목적을 하나 선택하고 **강의노트 만들기**를 누릅니다.
6. 결과를 확인하고 **PDF 다운로드**를 누릅니다.

| 학습 목적 | 결과 |
| --- | --- |
| 이해용 | 개념과 설명·예시 중심 |
| 암기용 | 핵심 정의·비교·질문과 답 중심 |
| 문제풀이용 | 문제와 정답·해설 중심, 앞부분 개념 설명 생략 |

노트 생성 시 최종 전사문과 근거 정보가 Google Gemini로 전송됩니다. 녹음 파일은 전송하지 않습니다. 무료 서비스 입력·출력은 제품 개선이나 사람의 검토에 사용될 수 있으므로 전송할 수 있는 자료로 사용하세요. [Gemini 이용 조건](https://ai.google.dev/gemini-api/terms), [가격](https://ai.google.dev/gemini-api/docs/pricing), [사용량 제한](https://ai.google.dev/gemini-api/docs/rate-limits)을 확인하세요. 무료 사용량이나 모델 접근은 계정·프로젝트에 따라 달라지며 무제한을 보장하지 않습니다.

노트 생성 실패 시 기존 노트는 유지합니다. 자동 API 재시도나 유료 모델 전환은 하지 않습니다. PDF 생성·다운로드는 로컬에서 처리합니다.

## 결과 보관과 주의할 점

- 필요한 전사문과 PDF는 직접 다운로드하세요. 화면 결과는 영구 보관함이 아니며 새 녹음·재전사·앱 종료·30분 유휴 등으로 초기화됩니다.
- 원본 녹음 파일은 변경하지 않습니다. 처리용 임시 음성은 작업 후 정리합니다.
- 진단 기록과 복구 전·후 전사문은 `%LOCALAPPDATA%\LectureTranscriber` 아래 `diagnostics`, `recovery`에 남습니다. 전사 내용이 포함될 수 있으므로 이 폴더를 공개 저장소에 올리지 마세요.
- 자동 복구는 모든 누락·반복을 해결하지 않습니다. 전문 용어·수치·정답은 원본과 대조하세요. 노트 역시 AI가 생성한 자료입니다.
- 녹음·전송·공유할 권한이 있는 자료를 사용하세요.

## 자주 생기는 문제

| 증상 | 확인 방법 |
| --- | --- |
| start.cmd 실행 후 바로 종료 | PowerShell에서 실행해 오류를 확인하고 `.venv` 및 패키지 설치 여부 확인 |
| Python을 찾지 못함 | Python 3.10 64비트 설치 후 새 PowerShell에서 `py -3.10 --version` 확인 |
| 모델을 사용할 수 없음 | 해당 모델의 준비 명령을 다시 실행하고 네트워크·여유 공간 확인 |
| Turbo 전사가 오래 걸림 | CPU 처리와 자동 복구로 시간이 늘어날 수 있음. 짧은 파일이나 Base로 먼저 확인 |
| API 키·프로젝트 권한 오류 | AI Studio에서 키의 프로젝트·모델 접근 권한 확인 |
| 사용량 초과 또는 Gemini 요청 실패 | 해당 프로젝트 할당량·결제 설정·서비스 상태를 확인한 뒤 직접 재시도 |
| 노트 형식 또는 근거 오류 | 응답 검증 실패로 사용량 초과와는 다른 오류. 기존 결과를 보관하고 재시도 |

## 개발 및 검증

개발 환경 전체의 버전은 `requirements.lock`에 기록되어 있습니다. 일반 사용자는 위 설치 절차만 따르면 됩니다. 개발 테스트에는 다음을 사용합니다.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m pip install -e .
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m pytest -q
```

UI 검증 도구 `tools/verify_notes_ui.py`는 Microsoft Edge가 설치된 환경에서 실행하며 합성 데이터와 모의 API 응답을 사용합니다. 실제 API 품질·속도 검증과 구분합니다.

- [구현 현황](docs/IMPLEMENTATION_STATUS.md)
- [아키텍처](docs/ARCHITECTURE.md)
- [개인정보 및 로컬 보관 범위](docs/PRIVACY_SECURITY.md)
- [라이선스·출처](docs/LICENSES_AND_SOURCES.md)
- [팀 발표 대본](docs/TEAM_PRESENTATION.md)

개발 브랜치는 `feature/local-transcription`입니다. 기존 Streamlit 앱은 [archive/streamlit-demo 브랜치](https://github.com/redsnack12345/LIT11_Meetup_SpeechToNote/tree/archive/streamlit-demo/AI-Study-Note-Audio-AI-Correction1)에 보존하며 main의 실행 경로에는 포함하지 않습니다.

모델·음성·전사문·API 키·개인 진단 기록은 Git에 포함하지 않습니다. 한글 PDF용 나눔고딕은 SIL OFL 1.1이며 글꼴과 라이선스 전문을 동봉합니다. 프로젝트 코드 자체의 별도 LICENSE는 아직 제공하지 않으며, 각 의존성과 모델의 사용 조건은 별도로 확인해야 합니다.
