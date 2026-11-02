"""휴대폰 녹음 파일을 전사하고 AI 교정 제안을 거쳐 학습 노트를 생성하는 앱."""

import tempfile
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from ai_generator import generate_notes, review_transcript

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

st.set_page_config(page_title="AI Study Note", page_icon="📚", layout="wide")
st.title("📚 AI Study Note")
st.caption("강의 녹음을 전사하고, AI 교정 제안을 검토한 뒤 나만의 학습 노트를 만들어 보세요.")

for key, default in {
    "transcript": "",
    "original_transcript": "",
    "notes": "",
    "correction_suggestions": [],
    "correction_source": "",
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

st.header("1. 강의 녹음 파일 전사")
audio_file = st.file_uploader(
    "MP3, M4A, WAV 등의 녹음 파일을 업로드하세요.",
    type=["mp3", "m4a", "wav", "aac", "flac", "ogg"],
)
model_size = st.selectbox(
    "Whisper 모델",
    options=["base", "small", "medium"],
    index=0,
    help="처음에는 base를 권장합니다. 모델은 최초 실행 시 다운로드되며, 큰 모델일수록 메모리와 시간이 더 필요합니다.",
)

if audio_file is not None:
    st.audio(audio_file)
    if st.button("🎙️ 한국어 전사 시작", type="primary"):
        try:
            from faster_whisper import WhisperModel

            suffix = Path(audio_file.name).suffix or ".audio"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(audio_file.getvalue())
                audio_path = tmp.name
            try:
                with st.spinner("Whisper 모델을 준비하고 음성을 텍스트로 변환하고 있습니다. 첫 실행은 모델 다운로드로 시간이 걸릴 수 있습니다."):
                    model = WhisperModel(model_size, device="cpu", compute_type="int8")
                    segments, info = model.transcribe(
                        audio_path, language="ko", vad_filter=True, beam_size=5
                    )
                    transcript = "\n".join(
                        segment.text.strip() for segment in segments if segment.text.strip()
                    )
                st.session_state.transcript = transcript
                st.session_state.original_transcript = transcript
                st.session_state.correction_suggestions = []
                st.session_state.correction_source = ""
                st.session_state.notes = ""
                st.success(f"전사 완료! 감지 언어: {info.language}, 길이: 약 {info.duration:.0f}초")
            finally:
                Path(audio_path).unlink(missing_ok=True)
        except Exception as exc:
            st.error(f"전사 중 오류가 발생했습니다: {exc}")
            st.info("faster-whisper 설치가 완료됐는지, 파일 형식이 지원되는지 확인해 주세요.")

if st.session_state.transcript:
    # 선택 수정 적용 후 rerun된 경우, 위젯이 생성되기 전에 편집기 값을 갱신합니다.
    if "pending_transcript" in st.session_state:
        st.session_state.transcript = st.session_state.pending_transcript
        st.session_state.transcript_editor = st.session_state.pending_transcript
        del st.session_state.pending_transcript

    st.header("2. 전사문 확인 및 AI 교정")
    st.info("원본 전사문은 별도로 보존됩니다. AI는 수정 후보만 제안하며, 실제 반영 여부는 사용자가 결정합니다.")

    # 새 전사 결과가 들어온 경우에만 편집기 상태를 초기화합니다.
    if st.session_state.get("editor_source") != st.session_state.original_transcript:
        st.session_state.transcript_editor = st.session_state.transcript
        st.session_state.editor_source = st.session_state.original_transcript

    subject = st.text_input("강의 분야 또는 과목", value="일반 강의", help="예: 선형대수학, 자료구조, 인공지능")
    glossary = st.text_input(
        "참고 전문 용어 (선택)",
        placeholder="예: 행렬식, 고유값, 고유벡터, 특이값 분해",
        help="쉼표로 구분해 입력하면 Gemini가 오인식 후보를 찾을 때 참고합니다.",
    )

    if st.button("🔎 AI로 오인식 의심 부분 찾기"):
        current_text = st.session_state.get("transcript_editor", st.session_state.transcript)
        try:
            with st.spinner("Gemini가 강의 문맥과 전문 용어를 바탕으로 전사문을 검토하고 있습니다..."):
                suggestions = review_transcript(current_text, subject, glossary)
            st.session_state.transcript = current_text
            st.session_state.correction_suggestions = suggestions
            st.session_state.correction_source = current_text
            if suggestions:
                st.success(f"검토 완료! 수정 후보 {len(suggestions)}개를 찾았습니다. 각 항목을 확인해 주세요.")
            else:
                st.success("검토 완료! 뚜렷한 오인식 의심 부분을 찾지 못했습니다.")
        except Exception as exc:
            st.error(f"AI 전사문 검토 중 오류가 발생했습니다: {exc}")

    st.text_area("전사문 (직접 수정 가능)", height=300, key="transcript_editor")

    if st.session_state.correction_suggestions:
        st.subheader("AI 수정 제안")
        st.caption("제안은 완벽하지 않을 수 있습니다. 강의 음성을 확인한 뒤 필요한 항목만 선택하세요.")
        for index, suggestion in enumerate(st.session_state.correction_suggestions):
            with st.expander(f"제안 {index + 1}: {suggestion['original_text']} → {suggestion['replacement']}", expanded=True):
                st.markdown(f"**원문:** `{suggestion['original_text']}`")
                st.markdown(f"**수정 후보:** `{suggestion['replacement']}`")
                st.write(f"**이유:** {suggestion['reason']}")
                st.write(f"**신뢰도:** {suggestion['confidence']}")
                if suggestion.get("context"):
                    st.caption(f"문맥: {suggestion['context']}")
                st.checkbox("이 수정 제안 적용", key=f"apply_correction_{index}")

        if st.button("선택한 수정 제안 적용", type="primary"):
            revised = st.session_state.transcript_editor
            applied = 0
            skipped = []
            for index, suggestion in enumerate(st.session_state.correction_suggestions):
                if not st.session_state.get(f"apply_correction_{index}", False):
                    continue
                original = suggestion["original_text"]
                replacement = suggestion["replacement"]
                occurrences = revised.count(original)
                if occurrences == 1:
                    revised = revised.replace(original, replacement, 1)
                    applied += 1
                elif occurrences == 0:
                    skipped.append(f"제안 {index + 1}: 원문을 찾을 수 없음 (전사문이 이미 수정되었을 수 있음)")
                else:
                    skipped.append(f"제안 {index + 1}: 같은 원문이 {occurrences}번 있어 자동 적용하지 않음")
            st.session_state.pending_transcript = revised
            st.session_state.correction_suggestions = []
            st.success(f"수정 제안 {applied}개를 적용했습니다.")
            for message in skipped:
                st.warning(message)
            st.rerun()

    st.header("3. 학습 스타일 선택 및 노트 생성")
    style = st.radio("어떤 방식으로 정리할까요?", ["이해 중심", "암기 중심", "문제풀이 중심"], horizontal=True)
    if st.button("✨ 학습 노트 생성", type="primary"):
        final_transcript = st.session_state.get("transcript_editor", st.session_state.transcript)
        if not final_transcript.strip():
            st.warning("전사문이 비어 있습니다. 먼저 전사하거나 내용을 입력해 주세요.")
        else:
            try:
                with st.spinner("Gemini가 학습 노트를 만들고 있습니다..."):
                    st.session_state.notes = generate_notes(final_transcript, style)
                st.session_state.transcript = final_transcript
            except Exception as exc:
                st.error(f"노트 생성 중 오류가 발생했습니다: {exc}")

if st.session_state.notes:
    st.header("4. 생성된 학습 노트")
    st.markdown(st.session_state.notes)
    st.download_button(
        "⬇️ Markdown으로 저장",
        data=st.session_state.notes,
        file_name="study_notes.md",
        mime="text/markdown",
    )

st.divider()
st.caption("음성 전사는 faster-whisper를 PC에서 실행합니다. 첫 실행 시 Whisper 모델 다운로드가 필요합니다. AI 전사문 검토와 노트 생성에는 Gemini API 사용량이 발생합니다.")
