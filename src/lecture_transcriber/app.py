from contextlib import asynccontextmanager
from pathlib import Path
import secrets
import json
import shutil
import subprocess
import threading
import time

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict

from .jobs import Jobs, JobError, MAX_UPLOAD
from .models import CATALOG, MODEL_ROOT, ready


class Session(BaseModel):
    model_config = ConfigDict(extra="forbid")
    launch_token: str


def error(status, code, message):
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


def markdown(text):
    special = set("\\\x60*_{}[]<>()#+-.!|~>")
    return "".join("\\" + c if c in special else c for c in text) + "\n"


def create_app(data_dir: Path, origin="http://127.0.0.1:8765", *, model_root=MODEL_ROOT, worker_command=None, note_provider=None, key_store=None, note_timeout=180):
    jobs = Jobs(data_dir, model_root, worker_command)

    from .notes import Notes
    from .note_routes import register
    notes = Notes(jobs, note_provider, key_store, note_timeout)

    @asynccontextmanager
    async def lifespan(app):
        yield
        await notes.close()
        jobs.close()

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.jobs = jobs
    app.state.notes = notes
    register(app, notes)
    app.state.launch_token = secrets.token_urlsafe(32)
    app.state.token_created = time.monotonic()
    app.state.sessions = {}
    app.state.session_lock = threading.Lock()
    app.state.shutdown = None
    static = Path(__file__).parent / "static"

    @app.exception_handler(JobError)
    async def job_error(request, exc):
        return error(exc.status, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def validation(request, exc):
        return error(422, "INVALID_INPUT", "입력 내용과 길이를 확인해 주세요.")

    @app.exception_handler(OSError)
    async def storage_error(request, exc):
        return error(507, "STORAGE_ERROR", "저장 공간과 접근 권한을 확인해 주세요.")

    @app.exception_handler(subprocess.TimeoutExpired)
    async def probe_timeout(request, exc):
        return error(415, "UNSUPPORTED_MEDIA", "음성 파일을 읽을 수 없습니다.")

    @app.middleware("http")
    async def protect(request: Request, call_next):
        if request.headers.get("host") != origin.removeprefix("http://"):
            return error(403, "INVALID_HOST", "허용하지 않는 주소입니다.")
        if request.headers.get("origin") not in (None, origin):
            return error(403, "INVALID_ORIGIN", "외부 화면의 요청은 허용하지 않습니다.")
        public = request.url.path in ("/", "/api/v1/health") or request.url.path.startswith("/static/")
        exchange = request.url.path == "/api/v1/session" and request.method == "POST"
        csrf = app.state.sessions.get(request.cookies.get("session"))
        if not public and not exchange and not csrf:
            return error(401, "SESSION_REQUIRED", "start.cmd로 앱을 다시 열어 주세요.")
        if request.method not in ("GET", "HEAD"):
            if request.headers.get("origin") != origin:
                return error(403, "INVALID_ORIGIN", "앱 화면에서 다시 시도해 주세요.")
            if not exchange and (not csrf or not secrets.compare_digest(request.headers.get("x-csrf-token", ""), csrf)):
                return error(403, "CSRF_FAILED", "앱 화면을 새로 고쳐 주세요.")
        if request.url.path == "/api/v1/transcriptions" and request.method == "POST":
            try:
                size = int(request.headers.get("content-length", "-1"))
            except ValueError:
                size = -1
            if size < 0 or size > MAX_UPLOAD + 1024**2:
                return error(413, "FILE_TOO_LARGE", "파일은 200MiB 이하로 선택해 주세요.")
            if shutil.disk_usage(jobs.root).free < size * 2 + 128 * 1024**2:
                return error(507, "DISK_FULL", "파일 처리에 필요한 공간이 부족합니다.")
        response = await call_next(request)
        response.headers.update({"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer",
                                 "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"})
        return response

    @app.get("/")
    def index():
        return FileResponse(static / "index.html")

    app.mount("/static", StaticFiles(directory=static), name="static")

    @app.get("/api/v1/health")
    def health():
        return {"status": "ok", "api_version": 1}

    @app.post("/api/v1/session")
    def session(body: Session):
        with app.state.session_lock:
            if not app.state.launch_token or time.monotonic() - app.state.token_created > 60 or not secrets.compare_digest(body.launch_token, app.state.launch_token):
                raise JobError(401, "TOKEN_EXPIRED", "앱을 종료한 뒤 start.cmd로 다시 실행해 주세요.")
            app.state.launch_token = None
            cookie, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            app.state.sessions[cookie] = csrf
        response = JSONResponse({"csrf_token": csrf})
        response.set_cookie("session", cookie, httponly=True, samesite="strict", path="/")
        return response

    @app.get("/api/v1/session")
    def session_current(request: Request):
        return {"csrf_token": app.state.sessions[request.cookies["session"]]}

    @app.get("/api/v1/models")
    def models():
        return [{"id": key, "label": label, "available": ready(key, model_root)} for key, label in CATALOG.items()]

    @app.post("/api/v1/transcriptions", status_code=202)
    def transcribe(file: UploadFile = File(), model_id: str = Form(), hint: str = Form(default="", max_length=100)):
        try:
            return jobs.start(file.file, model_id, file.filename or "녹음", hint)
        finally:
            file.file.close()

    @app.get("/api/v1/transcriptions/{job_id}")
    def result(job_id: str):
        job = jobs.get(job_id)
        return {key: job[key] for key in ("job_id", "state", "model_id", "text", "error", "diagnostics_status", "recovery")}

    @app.get("/api/v1/transcriptions/{job_id}/download")
    def download(job_id: str):
        job = jobs.get(job_id)
        if job["state"] != "completed" or not job["text"]:
            raise JobError(409, "NOT_READY", "다운로드할 전사문이 없습니다.")
        return Response(markdown(job["text"]).encode("utf-8"), media_type="text/markdown; charset=utf-8",
                        headers={"Content-Disposition": 'attachment; filename="transcript.md"'})

    @app.get("/api/v1/transcriptions/{job_id}/recovery")
    def recovery_record(job_id: str):
        job = jobs.get(job_id)
        path = jobs.recovery / (job["job_id"] + ".json")
        if job["state"] != "completed" or not path.is_file():
            raise JobError(404, "NOT_FOUND", "보존된 복구 기록이 없습니다.")
        return FileResponse(path, media_type="application/json", filename="recovery.json")

    @app.get("/api/v1/transcriptions/{job_id}/original")
    def original_transcript(job_id: str):
        job = jobs.get(job_id)
        path = jobs.recovery / (job["job_id"] + ".json")
        if job["state"] != "completed" or not path.is_file():
            raise JobError(404, "NOT_FOUND", "보존된 원래 전사문이 없습니다.")
        payload = json.loads(path.read_text(encoding="utf-8"))
        return Response(markdown(payload["original_text"]).encode("utf-8"), media_type="text/markdown; charset=utf-8",
                        headers={"Content-Disposition": 'attachment; filename="original.md"'})

    @app.post("/api/v1/shutdown", status_code=202)
    def shutdown(body: dict):
        if body != {"confirmed": True}:
            raise JobError(422, "CONFIRM_REQUIRED", "종료 여부를 확인해 주세요.")
        if app.state.shutdown:
            threading.Timer(0.2, app.state.shutdown).start()
        return {"status": "closing"}
    return app

