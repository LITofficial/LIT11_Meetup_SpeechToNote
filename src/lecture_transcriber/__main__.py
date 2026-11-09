import argparse
import json
import os
from pathlib import Path
import socket
import threading
import time
import webbrowser

import uvicorn
from .app import create_app


def main():
    parser = argparse.ArgumentParser(description="한국어 강의 전사 데모")
    parser.add_argument("--data-dir", type=Path, default=Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "LectureTranscriber")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    args.data_dir.mkdir(parents=True, exist_ok=True)
    runtime = args.data_dir / "runtime"
    runtime.mkdir(exist_ok=True)
    lock = (runtime / "app.lock").open("a+b")
    lock.write(b"0")
    lock.flush()
    lock.seek(0)
    try:
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        lock.close()
        print("이미 실행 중입니다. 기존 창을 사용하거나 기존 앱을 종료해 주세요.")
        return
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    origin = f"http://127.0.0.1:{port}"
    app = create_app(args.data_dir, origin)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port,
                                          access_log=False, log_level="warning"))
    app.state.shutdown = lambda: setattr(server, "should_exit", True)
    url = origin + "/#token=" + app.state.launch_token
    def open_when_ready():
        for _ in range(200):
            if server.started:
                if not args.no_browser:
                    webbrowser.open(url)
                return
            if server.should_exit:
                return
            time.sleep(0.05)
    threading.Thread(target=open_when_ready, daemon=True).start()
    # State contains no token or personal data. Useful for health checks.
    state_path = runtime / "server.json"
    state_path.write_text(json.dumps({"origin": origin, "pid": os.getpid()}), encoding="utf-8")
    print("강의 전사 데모를 실행합니다. 종료하려면 화면의 앱 종료 또는 Ctrl+C를 누르세요.")
    try:
        server.run(sockets=[sock])
    finally:
        app.state.jobs.close()
        state_path.unlink(missing_ok=True)
        sock.close()
        lock.close()


if __name__ == "__main__":
    main()
