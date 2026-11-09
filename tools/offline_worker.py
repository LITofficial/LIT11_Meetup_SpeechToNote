"""Test harness: prohibit socket connections while running the real model."""
import json
from pathlib import Path
import socket
import sys

def denied(*args, **kwargs):
    raise AssertionError("Network connection attempted during offline transcription")

socket.socket.connect = denied
socket.socket.connect_ex = denied
from lecture_transcriber.worker import run
source,model,result=map(Path,sys.argv[1:4])
hint=json.loads(Path(sys.argv[4]).read_text(encoding="utf-8")) if len(sys.argv)>4 else ""
result.write_text(json.dumps({"text":run(source,model,hint),"error":None},ensure_ascii=False),encoding="utf-8")
