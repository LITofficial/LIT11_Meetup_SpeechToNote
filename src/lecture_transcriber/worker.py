"""One offline inference per child process."""
import json
import os
from pathlib import Path
import sys
from .formatting import sentence_layout
from .diagnostics import Recorder
from .recovery import recover, pack


def run(source, model_dir, hint="", diagnostic_path=None, diagnostic_status=None, recovery_status=None, final_segments=None):
    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1")
    from .probe import probe
    probe(source)
    from faster_whisper import WhisperModel
    model = WhisperModel(str(model_dir), device="cpu", compute_type="int8", cpu_threads=4,
                         num_workers=1, local_files_only=True)
    segments, info = model.transcribe(str(source), language="ko", task="transcribe", beam_size=5,
                                   vad_filter=False, word_timestamps=False, initial_prompt=hint or None)
    recorder = Recorder(diagnostic_path, info.duration, Path(model_dir).name, bool(hint)) if diagnostic_path else None
    if recorder:
        from importlib.metadata import version
        recorder.data['engine_version'] = version('faster-whisper')
        recorder.data['settings'] = {'device':'cpu','compute_type':'int8','cpu_threads':4,
            'language':'ko','beam_size':5,'vad_filter':False,'condition_on_previous_text':True,
            'temperature_schedule':[0.0,0.2,0.4,0.6,0.8,1.0]}
    texts=[]
    rows=[]
    try:
        for segment in segments:
            texts.append(segment.text.strip())
            rows.append(pack(segment))
            if recorder: recorder.add(segment)
    except Exception:
        if recorder: recorder.finish("failed")
        raise
    if recorder:
        recorder.finish("completed")
        if diagnostic_status is not None: diagnostic_status.append("failed" if recorder.failed else "saved")
    recovery_path = diagnostic_path.parent.parent / 'recovery' / diagnostic_path.name if diagnostic_path else None
    final, summary = recover(model, source, rows, getattr(info, 'duration', 0), hint, recovery_path, final_segments)
    if final_segments is not None:
        for row in final_segments: row["source_duration"] = info.duration
    if recovery_status is not None: recovery_status.append(summary)
    return final


if __name__ == "__main__":
    source, model, destination = map(Path, sys.argv[1:4])
    hint = json.loads(Path(sys.argv[4]).read_text(encoding="utf-8")) if len(sys.argv) > 4 else ""
    diagnostic_path = Path(sys.argv[5]) if len(sys.argv)>5 else None
    diagnostic_status=[]
    recovery_status=[]
    final_segments=[]
    try:
        result = {"text": run(source, model, hint, diagnostic_path, diagnostic_status, recovery_status, final_segments), "segments": final_segments, "error": None, "diagnostics_status": diagnostic_status[0] if diagnostic_status else "not_requested", "recovery": recovery_status[0] if recovery_status else {"status":"unavailable"}}
    except Exception:
        result = {"text": None, "error": "TRANSCRIPTION_FAILED"}
    destination.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
