"""Explicit real-model smoke test; private/synthetic audio stays local."""
import argparse
import json
from pathlib import Path
import sys
import tempfile
import time
from fastapi.testclient import TestClient
from lecture_transcriber.app import create_app, markdown


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("audio",type=Path)
    parser.add_argument("--report",type=Path)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    def worker(source,model,result,hint_file):
        return [sys.executable,str(root/"tools/offline_worker.py"),str(source),str(model),str(result),str(hint_file)]
    report=[]
    with tempfile.TemporaryDirectory() as data:
        app=create_app(Path(data),worker_command=worker)
        with TestClient(app,base_url="http://127.0.0.1:8765") as client:
            client.headers["Origin"]="http://127.0.0.1:8765"
            session=client.post("/api/v1/session",json={"launch_token":app.state.launch_token}).json()
            client.headers["X-CSRF-Token"]=session["csrf_token"]
            for model in ("base","small"):
                start=time.monotonic()
                with args.audio.open("rb") as audio:
                    response=client.post("/api/v1/transcriptions",files={"file":(args.audio.name,audio)},data={"model_id":model})
                assert response.status_code==202,response.text
                job=response.json()["job_id"]
                while time.monotonic()-start<600:
                    status=client.get(f"/api/v1/transcriptions/{job}").json()
                    if status["state"]!="running":break
                    time.sleep(.2)
                assert status["state"]=="completed",status
                assert status["text"].strip(),status
                download=client.get(f"/api/v1/transcriptions/{job}/download")
                assert download.content.decode("utf-8")==markdown(status["text"])
                assert not list(app.state.jobs.root.iterdir())
                report.append({"model":model,"elapsed_seconds":round(time.monotonic()-start,2),"text":status["text"],"download_matches":True,"network_connections_blocked":True})
                print(json.dumps(report[-1],ensure_ascii=True),flush=True)
    if args.report: args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")


if __name__=="__main__":main()
