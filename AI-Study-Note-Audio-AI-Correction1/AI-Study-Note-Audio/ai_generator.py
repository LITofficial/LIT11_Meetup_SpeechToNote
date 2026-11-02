"""Gemini API를 이용해 전사문을 검토하고 학습 노트로 변환하는 모듈."""

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai

load_dotenv(Path(__file__).resolve().parent / ".env")


def _get_client_and_model():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("API 키가 설정되지 않았습니다. 프로젝트 폴더의 .env 파일을 확인하세요.")
    model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    return genai.Client(api_key=api_key), model


def review_transcript(transcript: str, subject: str = "일반 강의", glossary: str = "") -> list[dict]:
    """전사문에서 오인식이 의심되는 구간을 찾아 수정 후보 목록을 반환한다.

    원문 전체를 다시 작성하지 않고, 사용자가 검토할 수 있는 정확한 부분 문자열만 제안한다.
    """
    if not transcript.strip():
        return []

    client, model = _get_client_and_model()
    prompt = f"""
당신은 강의 음성 전사문 검토 도우미입니다. 아래 전사문에서 음성 인식 오류일 가능성이 높은 부분만 찾아주세요.

강의 분야: {subject}
참고 전문 용어: {glossary or '제공되지 않음'}

엄격한 원칙:
- 문맥상 명백히 이상하거나 전문 용어 오인식 가능성이 높은 부분만 제안하세요.
- 문장을 더 매끄럽게 바꾸거나 말투를 교정하지 마세요.
- 원문에 없는 정보나 발언을 추측해 추가하지 마세요.
- 확신이 낮으면 제안하지 마세요.
- original_text는 전사문에 실제로 존재하는 짧고 연속된 문자열을 그대로 복사하세요. 띄어쓰기와 문장부호도 유지하세요.
- replacement는 original_text를 대체할 짧은 문자열이어야 합니다.
- 같은 원문 구간을 여러 번 제안하지 마세요.
- 제안이 없으면 suggestions를 빈 배열로 반환하세요.

반드시 아래 JSON 형식만 반환하세요.
{{
  "suggestions": [
    {{
      "original_text": "전사문에서 그대로 복사한 문자열",
      "replacement": "수정 후보",
      "reason": "오인식이 의심되는 이유",
      "confidence": "높음 또는 보통",
      "context": "해당 구간을 이해하는 데 필요한 짧은 문맥"
    }}
  ]
}}

[전사문]
{transcript}
"""
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config={"response_mime_type": "application/json"},
    )
    raw = response.text or "{}"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # 일부 모델 응답에 코드 펜스가 포함되는 경우를 대비
        cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        data = json.loads(cleaned)

    suggestions = data.get("suggestions", []) if isinstance(data, dict) else []
    valid = []
    for item in suggestions:
        if not isinstance(item, dict):
            continue
        original = str(item.get("original_text", "")).strip()
        replacement = str(item.get("replacement", "")).strip()
        if original and replacement and original != replacement and original in transcript:
            valid.append({
                "original_text": original,
                "replacement": replacement,
                "reason": str(item.get("reason", "문맥상 확인이 필요한 표현입니다.")),
                "confidence": str(item.get("confidence", "보통")),
                "context": str(item.get("context", "")),
            })
    return valid


def generate_notes(transcript: str, style: str) -> str:
    """전사문과 학습 스타일을 받아 Markdown 학습 노트를 생성한다."""
    client, model = _get_client_and_model()

    style_instructions = {
        "이해 중심": "개념을 쉬운 말로 설명하고, 개념 사이의 관계와 원리를 연결해 주세요. 필요하면 비유와 예시를 사용하세요.",
        "암기 중심": "핵심 용어와 정의를 표로 정리하고, 외워야 할 공식과 조건을 강조하세요. 마지막에 빈칸 문제와 정답을 만들어 주세요.",
        "문제풀이 중심": "공식과 풀이 절차를 정리하고, 예제는 단계별로 풀이하세요. 마지막에 유사 연습문제와 정답 및 풀이를 제시하세요.",
    }

    prompt = f"""
당신은 대학생을 돕는 학습 노트 작성 도우미입니다.
아래 강의 전사문을 바탕으로 정확하고 구조화된 한국어 Markdown 학습 노트를 작성하세요.

[학습 스타일: {style}]
{style_instructions.get(style, style_instructions['이해 중심'])}

작성 원칙:
- 전사문에 없는 사실이나 수치를 임의로 만들어내지 마세요.
- 전사 오류로 보이는 부분은 문맥상 확실한 경우에만 자연스럽게 다듬으세요.
- 불확실한 내용은 '원문 확인 필요'라고 표시하세요.
- 핵심 내용, 용어, 공식, 예시, 주의사항을 구분하세요.
- 읽기 쉬운 제목과 목록, 표를 활용하세요.

[강의 전사문]
{transcript}
"""
    response = client.models.generate_content(model=model, contents=prompt)
    return response.text or "노트를 생성하지 못했습니다. 전사문이나 모델 설정을 확인해 주세요."
