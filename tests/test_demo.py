import io
import json
from pathlib import Path
import sys
import time
import wave

import pytest
from fastapi.testclient import TestClient
from lecture_transcriber.app import create_app, markdown
from lecture_transcriber.models import REQUIRED

ORIGIN = "http://127.0.0.1:8765"


def wav():
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1); audio.setsampwidth(2); audio.setframerate(16000)
        audio.writeframes(b"\0\0" * 16000)
    return output.getvalue()


def fake_models(root):
    for name in ("base", "small", "large-v3-turbo"):
        folder = root / name
        folder.mkdir(parents=True)
        for file in REQUIRED: (folder / file).write_bytes(b"test")
        (folder / "manifest.json").write_text(json.dumps({"files":{file:{"bytes":4} for file in REQUIRED}}))


def command(source, model, result, hint_file):
    code = "import json,sys,time;from pathlib import Path;time.sleep(0.2);Path(sys.argv[1]).write_text(json.dumps({'text':sys.argv[2]+' 한글 결과 *별표*','error':None},ensure_ascii=False),encoding='utf-8')"
    return [sys.executable,"-c",code,str(result),model.name]


@pytest.fixture
def connected(tmp_path):
    models = tmp_path / "models"; fake_models(models)
    app = create_app(tmp_path / "data", ORIGIN, model_root=models, worker_command=command)
    with TestClient(app, base_url=ORIGIN) as client:
        client.headers["Origin"] = ORIGIN
        token = app.state.launch_token
        response = client.post("/api/v1/session",json={"launch_token":token})
        client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
        yield app, client


def submit(client, model="base", content=None):
    return client.post("/api/v1/transcriptions",files={"file":("음성.wav",wav() if content is None else content,"audio/wav")},data={"model_id":model})


def wait(client, job_id):
    deadline=time.monotonic()+10
    while time.monotonic()<deadline:
        result=client.get(f"/api/v1/transcriptions/{job_id}").json()
        if result["state"]!="running": return result
        time.sleep(.05)
    pytest.fail("worker timeout")


def test_selection_result_download_and_cleanup(connected):
    app,client=connected
    previous=None
    for model in ("base","small","large-v3-turbo"):
        response=submit(client,model)
        assert response.status_code==202,response.text
        job=response.json()["job_id"]
        result=wait(client,job)
        assert result["state"]=="completed"
        assert result["text"].startswith(model)
        download=client.get(f"/api/v1/transcriptions/{job}/download")
        assert download.status_code==200
        assert download.content.decode("utf-8")==markdown(result["text"])
        assert list(app.state.jobs.root.iterdir())==[]
        if previous: assert client.get(f"/api/v1/transcriptions/{previous}").status_code==404
        previous=job


def test_busy_and_download_before_complete(connected):
    app,client=connected
    def slow(source,model,result,hint_file):
        return [sys.executable,"-c","import time;time.sleep(5)"]
    app.state.jobs.command=slow
    job=submit(client).json()["job_id"]
    assert submit(client).status_code==409
    assert client.get(f"/api/v1/transcriptions/{job}/download").status_code==409
    process=app.state.jobs.process
    app.state.jobs.close()
    assert process.poll() is not None
    assert list(app.state.jobs.root.iterdir())==[]


@pytest.mark.parametrize("payload",[b"",b"invalid",b"#EXTM3U\nhttps://example.com/audio.mp3"])
def test_invalid_media(connected,payload):
    app,client=connected
    assert submit(client,content=payload).status_code==415
    assert list(app.state.jobs.root.iterdir())==[]


def test_invalid_and_missing_model(connected):
    app,client=connected
    assert submit(client,model="../../escape").status_code==422
    (app.state.jobs.models/"small"/"model.bin").unlink()
    assert submit(client,model="small").status_code==409
    models=client.get("/api/v1/models").json()
    assert models[1]["available"] is False


def test_expired_and_empty_result(connected):
    app,client=connected
    job=submit(client).json()["job_id"];wait(client,job)
    app.state.jobs.job["text"]=""
    assert client.get(f"/api/v1/transcriptions/{job}/download").status_code==409
    app.state.jobs.job["completed"]=time.monotonic()-1801
    assert client.get(f"/api/v1/transcriptions/{job}").status_code==404


def test_failed_process_then_retry(connected):
    app,client=connected
    app.state.jobs.command=lambda *args:[sys.executable,"-c","raise SystemExit(2)"]
    job=submit(client).json()["job_id"]
    assert wait(client,job)["state"]=="failed"
    app.state.jobs.command=command
    assert wait(client,submit(client).json()["job_id"])["state"]=="completed"


def test_auth_and_boundaries(tmp_path):
    app=create_app(tmp_path,ORIGIN)
    with TestClient(app,base_url=ORIGIN) as client:
        assert client.get("/api/v1/models").status_code==401
        token=app.state.launch_token
        assert client.post("/api/v1/session",json={"launch_token":token}).status_code==403
        client.headers["Origin"]=ORIGIN
        assert client.post("/api/v1/session",json={"launch_token":token}).status_code==200
        assert client.post("/api/v1/session",json={"launch_token":token}).status_code==401
        assert submit(client).status_code==403
        assert client.get("/api/v1/models",headers={"Origin":"https://evil.test"}).status_code==403
        assert client.get("/api/v1/health",headers={"Host":"evil.test"}).status_code==403
        assert client.get("/api/v1/courses").status_code==404


def test_space_and_limit(connected,monkeypatch):
    from collections import namedtuple
    import lecture_transcriber.app as module
    _,client=connected
    Usage=namedtuple("Usage","total used free")
    monkeypatch.setattr(module.shutil,"disk_usage",lambda path:Usage(100,99,1))
    assert submit(client).status_code==507
    assert client.post("/api/v1/transcriptions",content=b"",headers={"Content-Length":str(202*1024**2)}).status_code==413


def test_token_expiry(tmp_path):
    app=create_app(tmp_path,ORIGIN);app.state.token_created-=61
    with TestClient(app,base_url=ORIGIN) as client:
        assert client.post("/api/v1/session",json={"launch_token":app.state.launch_token},headers={"Origin":ORIGIN}).status_code==401


def test_hint_request_validation_and_worker_delivery(connected):
    app,client=connected
    seen=[]
    def capture(source,model,result,hint_file):
        seen.append((model.name,json.loads(hint_file.read_text(encoding='utf-8'))))
        return command(source,model,result,hint_file)
    app.state.jobs.command=capture
    for hint in ('클라우드컴퓨팅',''):
        response=client.post('/api/v1/transcriptions',files={'file':('test.wav',wav())},data={'model_id':'large-v3-turbo','hint':hint})
        assert response.status_code==202
        assert wait(client,response.json()['job_id'])['state']=='completed'
        assert seen[-1]==('large-v3-turbo',hint)
    assert client.post('/api/v1/transcriptions',files={'file':('test.wav',wav())},data={'model_id':'small','hint':'가'*101}).status_code==422
    assert len(seen)==2


def test_worker_passes_hint_to_asr(monkeypatch,tmp_path):
    from types import SimpleNamespace
    from lecture_transcriber.worker import run
    import lecture_transcriber.probe as probe_module
    monkeypatch.setattr(probe_module,'probe',lambda path:None)
    calls=[]
    class Model:
        def __init__(self,*args,**kwargs): pass
        def transcribe(self,path,**kwargs):
            calls.append(kwargs)
            return [SimpleNamespace(text=' 실제 '), SimpleNamespace(text='결과입니다. 다음입니다.')],None
    monkeypatch.setitem(sys.modules,'faster_whisper',SimpleNamespace(WhisperModel=Model))
    assert run(tmp_path/'source',tmp_path/'model','클라우드컴퓨팅')=='실제 결과입니다.\n\n다음입니다.'
    assert calls[-1]['initial_prompt']=='클라우드컴퓨팅'
    run(tmp_path/'source',tmp_path/'model')
    assert calls[-1]['initial_prompt'] is None

def test_recovery_downloads_are_session_and_job_scoped(connected):
    app,client=connected
    job=submit(client).json()['job_id']
    wait(client,job)
    app.state.jobs.recovery.mkdir(exist_ok=True)
    payload={'original_text':'원래 *전사문*.','attempts':[{'retry_text':'재시도 결과.'}]}
    (app.state.jobs.recovery/(job+'.json')).write_text(json.dumps(payload),encoding='utf-8')
    assert client.get('/api/v1/transcriptions/'+job+'/original').content.decode('utf-8')==markdown(payload['original_text'])
    assert client.get('/api/v1/transcriptions/'+job+'/recovery').json()==payload
    assert client.get('/api/v1/transcriptions/unknown/recovery').status_code==404
