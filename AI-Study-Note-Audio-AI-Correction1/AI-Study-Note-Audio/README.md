# AI Study Note

휴대폰 강의 녹음 파일을 Whisper로 로컬 전사하고, Gemini의 교정 제안을 사용자가 검토한 뒤 개인 맞춤형 학습 노트를 생성하는 Streamlit 앱입니다.

## 주요 기능

1. MP3, M4A, WAV, AAC, FLAC, OGG 파일 업로드
2. faster-whisper를 이용한 한국어 로컬 음성 전사
3. Gemini를 이용한 오인식 의심 구간 탐색
4. 원문과 수정 후보를 비교하고 사용자가 선택적으로 적용
5. 이해 중심 / 암기 중심 / 문제풀이 중심 학습 노트 생성
6. Markdown 다운로드

## 실행 환경

- Python 3.12 64-bit 권장
- Windows PowerShell 기준

## 설치

```powershell
py -3.12 -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install --only-binary=:all: av==15.1.0
```

## Gemini API 설정

1. `.env.example`을 복사해 `.env`로 이름을 바꿉니다.
2. `.env`에 API 키와 사용할 수 있는 Gemini 모델명을 입력합니다.

```env
GEMINI_API_KEY=여기에_API_키_입력
GEMINI_MODEL=gemini-3.8-flash
```

모델명은 계정과 API 제공 상황에 따라 다를 수 있으므로, 오류가 발생하면 Google AI Studio에서 사용 가능한 모델을 확인하세요. API 키는 공개 저장소에 올리지 마세요.

## 실행

```powershell
streamlit run app.py
```

## 교정 기능 사용 방법

1. 녹음 파일을 업로드하고 한국어 전사를 실행합니다.
2. 강의 과목과 선택적 전문 용어 목록을 입력합니다.
3. `AI로 오인식 의심 부분 찾기`를 누릅니다.
4. 각 제안의 원문, 수정 후보, 이유를 확인합니다.
5. 실제로 맞다고 판단한 제안만 선택해 적용합니다.
6. 전사문을 최종 확인한 뒤 학습 노트를 생성합니다.

AI 제안은 오류일 수 있습니다. 원본 전사문을 보존하고, 사용자가 선택한 수정만 반영하도록 설계했습니다. 같은 원문이 전사문에 여러 번 등장하는 경우에는 잘못된 위치를 바꾸지 않도록 자동 적용을 건너뜁니다.

## 참고

- Whisper 모델은 최초 실행 시 다운로드됩니다.
- 음성 전사는 PC에서 수행하지만 Gemini 검토와 노트 생성에는 인터넷 연결 및 API 사용량이 필요합니다.
- 강의 녹음은 강의자 및 학교의 녹음·이용 정책을 확인하고 사용하세요.
