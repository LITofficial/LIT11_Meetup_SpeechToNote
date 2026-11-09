import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
from uuid import uuid4, UUID
from .models import MODEL_ROOT, model_path, ready

MAX_UPLOAD = 200 * 1024**2


class JobError(Exception):
    def __init__(self, status, code, message):
        self.status, self.code, self.message = status, code, message


class Jobs:
    def __init__(self, data_dir, model_root=MODEL_ROOT, command=None):
        self.root = (Path(data_dir) / "demo-temp").resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.diagnostics = self.root.parent / "diagnostics"
        self.recovery = self.root.parent / "recovery"
        self.models, self.command = model_root, command
        self.lock = threading.RLock()
        self.job = self.process = self.thread = None
        self.closed = False
        self.external_busy = lambda: False
        self.on_reset = lambda: None
        for path in self.root.iterdir():
            try:
                UUID(path.name)
                self.clean(path)
            except (ValueError, OSError):
                pass

    def clean(self, folder):
        if folder.resolve().parent != self.root or folder.is_symlink():
            raise ValueError("unsafe temporary path")
        if folder.exists():
            shutil.rmtree(folder)

    def start(self, file, model_id, filename, hint=""):
        if not isinstance(hint, str) or len(hint) > 100:
            raise JobError(422, "INVALID_HINT", "힌트는 100자 이하로 입력해 주세요.")
        hint = hint.strip()
        with self.lock:
            if self.closed:
                raise JobError(503, "CLOSING", "앱이 종료 중입니다.")
            if self.external_busy() or (self.job and self.job["state"] == "running"):
                raise JobError(409, "BUSY", "현재 전사가 끝난 뒤 다시 시작해 주세요.")
            try:
                model = model_path(model_id, self.models)
            except ValueError:
                raise JobError(422, "INVALID_MODEL", "모델을 다시 선택해 주세요.")
            if not ready(model_id, self.models):
                raise JobError(409, "MODEL_MISSING", "prepare-models.cmd로 모델을 준비해 주세요.")
            self.on_reset()
            self.job = None
            job_id = str(uuid4())
            folder = self.root / job_id
            folder.mkdir()
            try:
                size = 0
                source = folder / "source.audio"
                with source.open("xb") as out:
                    while block := file.read(1024**2):
                        size += len(block)
                        if size > MAX_UPLOAD:
                            raise JobError(413, "FILE_TOO_LARGE", "파일은 200MiB 이하로 선택해 주세요.")
                        if shutil.disk_usage(self.root).free < len(block) + 128 * 1024**2:
                            raise JobError(507, "DISK_FULL", "저장 공간이 부족합니다.")
                        out.write(block)
                if not size:
                    raise JobError(415, "UNSUPPORTED_MEDIA", "빈 파일은 전사할 수 없습니다.")
                probe = subprocess.run([sys.executable, "-m", "lecture_transcriber.probe", str(source)], capture_output=True, timeout=15,
                                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                if probe.returncode:
                    raise JobError(415, "UNSUPPORTED_MEDIA", "지원하는 M4A·MP3·WAV 음성인지 확인해 주세요.")
                result = folder / "result.json"
                hint_file = folder / "hint.json"
                hint_file.write_text(json.dumps(hint, ensure_ascii=False), encoding="utf-8")
                cmd = self.command(source, model, result, hint_file) if self.command else [sys.executable, "-m", "lecture_transcriber.worker", str(source), str(model), str(result), str(hint_file), str(self.diagnostics / (job_id + ".json"))]
                env = os.environ.copy()
                env.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1")
                self.process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env,
                                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                self.job = {"job_id":job_id, "state":"running", "model_id":model_id, "text":None,
                            "error":None, "diagnostics_status":"pending", "recovery":{"status":"pending"}, "filename":filename, "started":time.monotonic(), "completed":None}
                self.thread = threading.Thread(target=self.finish, args=(self.process, folder, result, job_id), daemon=True)
                self.thread.start()
                return {"job_id":job_id, "state":"running", "model_id":model_id}
            except Exception:
                self.clean(folder)
                raise

    def finish(self, process, folder, result, job_id):
        segments=[]
        diagnostics_status = "unavailable"
        recovery = {"status":"unavailable"}
        text, error = None, "전사에 실패했습니다. 음성 파일과 모델 준비 상태를 확인해 주세요."
        try:
            process.wait()
            if process.returncode == 0 and result.is_file():
                payload = json.loads(result.read_text(encoding="utf-8"))
                diagnostics_status = payload.get("diagnostics_status", "unavailable")
                recovery = payload.get("recovery", {"status":"unavailable"})
                if payload.get("error") is None and isinstance(payload.get("text"), str):
                    text, error = payload["text"], None
                    segments = payload.get("segments", [])
        except (OSError, ValueError):
            pass
        finally:
            try:
                self.clean(folder)
            except (OSError, ValueError):
                error = "임시 파일 정리에 실패했습니다. 앱을 다시 실행해 주세요."
            with self.lock:
                if self.job and self.job["job_id"] == job_id and not self.closed:
                    self.job.update(state="failed" if error else "completed", text=text if not error else None,
                                    error=error, segments=segments, diagnostics_status=diagnostics_status, recovery=recovery, completed=time.monotonic())

    def get(self, job_id):
        with self.lock:
            if self.job and self.job["completed"] and not self.external_busy() and time.monotonic() - self.job.get("last_activity", self.job["completed"]) >= 1800:
                self.job = None
                self.on_reset()
            if not self.job or self.job["job_id"] != job_id:
                raise JobError(404, "NOT_FOUND", "결과가 없거나 만료되었습니다. 다시 전사해 주세요.")
            return dict(self.job)

    def close(self):
        with self.lock:
            self.closed = True
            process, thread = self.process, self.thread
            self.job = None
            if process and process.poll() is None:
                process.terminate()
        if process:
            process.wait(timeout=10)
        if thread:
            thread.join(timeout=10)
