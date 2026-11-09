import json
from types import SimpleNamespace
from lecture_transcriber.diagnostics import Recorder,repetition_count

def segment(text,start=0,end=1,avg=-.2,ratio=1):
 return SimpleNamespace(text=text,start=start,end=end,avg_logprob=avg,compression_ratio=ratio,no_speech_prob=.1,temperature=0)

def test_diagnostic_signals_and_privacy(tmp_path):
 p=tmp_path/'diagnostics'/'job.json';r=Recorder(p,10,'large-v3-turbo',True)
 r.add(segment('비밀용어 비밀용어 비밀용어 비밀용어',end=12,avg=-1.5))
 r.finish('completed');saved=json.loads(p.read_text(encoding='utf-8'))
 assert set(saved['segments'][0]['flags'])=={'repetition','low_confidence','invalid_time'}
 assert '비밀용어' not in p.read_text(encoding='utf-8')
 assert saved['state']=='completed' and saved['flagged_segments']==1
 assert not p.with_suffix('.partial').exists()

def test_cross_segment_repetition_and_tolerance(tmp_path):
 r=Recorder(tmp_path/'job.json',10,'small',False)
 for i in range(4):r.add(segment('반복',start=i,end=i+1))
 assert 'repetition' in r.data['segments'][-1]['flags']
 assert repetition_count('정상 반복 정상 반복')==2
 clean=Recorder(tmp_path/'clean.json',10,'small',False)
 clean.add(segment('강조 강조',end=10.5,avg=-1))
 assert clean.data['segments'][0]['flags']==[]

def test_diagnostic_write_failure_preserves_text_flow(tmp_path,monkeypatch):
 from pathlib import Path
 from lecture_transcriber.worker import run
 import lecture_transcriber.probe as probe
 import sys
 monkeypatch.setattr(probe,'probe',lambda p:None)
 class Model:
  def __init__(self,*a,**kw):pass
  def transcribe(self,*a,**kw):return iter([segment('원문입니다.')]),SimpleNamespace(duration=1)
 monkeypatch.setitem(sys.modules,'faster_whisper',SimpleNamespace(WhisperModel=Model))
 blocker=tmp_path/'file';blocker.write_text('file')
 status=[]
 assert run(tmp_path/'source',tmp_path/'model','힌트',blocker/'job.json',status)=='원문입니다.'
 assert status==['failed']
