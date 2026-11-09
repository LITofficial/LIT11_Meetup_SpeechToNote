from types import SimpleNamespace
from pathlib import Path
import json
import numpy as np
from lecture_transcriber.recovery import recover,regions,pack

def row(start,end,text):
 return dict(start=start,end=end,text=text,avg_logprob=-.2,compression_ratio=1,temperature=0,no_speech_prob=.01)

class Model:
 def __init__(self,segments):self.segments=segments;self.calls=[]
 def transcribe(self,audio,**kwargs):
  self.calls.append(kwargs)
  return iter(SimpleNamespace(**s) for s in self.segments),None

def setup_audio(monkeypatch):
 import faster_whisper.audio
 monkeypatch.setattr(faster_whisper.audio,'decode_audio',lambda *a,**kw:np.zeros(100*16000,dtype=np.float32))

def test_detection_and_context_boundaries():
 rows=[row(0,30,'클라우드컴퓨팅'),row(30,60,'클라우드컴퓨팅'),row(60,67,'클라우드컴퓨팅'),row(67,76.6,'클라우드컴퓨팅'),row(76.6,79.4,'이어서 성능.'),row(79.4,90,'보존할 다음 문장.')]
 assert regions(rows,'클라우드컴퓨팅',90)==[(0,4)]
 assert regions([row(0,2,'클라우드컴퓨팅')],'클라우드컴퓨팅',2)==[]
 assert regions([row(0,30,'클라우드컴퓨팅 수업입니다.')],'클라우드컴퓨팅',30)==[]
 assert regions(rows,'',90)==[(0,4)]  # General repetition also works without a hint.

def test_retry_preserves_original_and_untouched_tail(tmp_path,monkeypatch):
 setup_audio(monkeypatch)
 rows=[row(0,30,'클라우드컴퓨팅'),row(30,40,'나머지는 유지합니다.')]
 model=Model([row(0,29,'데이터 형태를 설명합니다.')])
 path=tmp_path/'archive.json'
 text,summary=recover(model,'source',rows,40,'클라우드컴퓨팅',path)
 assert text=='데이터 형태를 설명합니다.\n\n나머지는 유지합니다.'
 assert summary['status']=='applied' and summary['applied']==1
 assert model.calls[0]['initial_prompt'] is None and model.calls[0]['condition_on_previous_text'] is False
 saved=json.loads(path.read_text(encoding='utf-8'))
 assert saved['original_segments']==rows and '클라우드컴퓨팅' in saved['original_text']
 assert saved['attempts'][0]['retry_text']=='데이터 형태를 설명합니다.'
 assert saved['final_text']==text


def test_suspicious_retry_keeps_original(tmp_path,monkeypatch):
 setup_audio(monkeypatch)
 rows=[row(0,30,'힌트')]
 for name,segments in [('empty',[]),('echo',[row(0,30,'힌트')]),('overtime',[row(0,33,'내용입니다.')]),('low',[dict(row(0,29,'내용입니다.'),avg_logprob=-2)])]:
  text,summary=recover(Model(segments),'source',rows,30,'힌트',tmp_path/f'{name}.json')
  assert text=='힌트' and summary['status']=='needs_review'


def test_archive_failure_does_not_replace_original(tmp_path,monkeypatch):
 setup_audio(monkeypatch)
 blocker=tmp_path/'file';blocker.write_text('not a folder')
 model=Model([row(0,29,'내용입니다.')])
 text,summary=recover(model,'source',[row(0,30,'힌트')],30,'힌트',blocker/'archive.json')
 assert text=='힌트' and summary['status']=='archive_failed' and not model.calls


def test_failed_retry_preserves_partial_and_original(tmp_path,monkeypatch):
 setup_audio(monkeypatch)
 class Failed:
  def transcribe(self,*a,**kw):
   def generate():
    yield SimpleNamespace(**row(0,10,'부분 결과'))
    raise RuntimeError('engine failure')
   return generate(),None
 path=tmp_path/'archive.json'
 text,summary=recover(Failed(),'source',[row(0,30,'힌트')],30,'힌트',path)
 saved=json.loads(path.read_text(encoding='utf-8'))
 assert text=='힌트' and summary['status']=='needs_review'
 assert saved['attempts'][0]['state']=='retry_failed'
 assert saved['attempts'][0]['retry_text']=='부분 결과'


def test_retry_length_limit(tmp_path):
 model=Model([])
 text,summary=recover(model,'source',[row(0,181,'힌트')],181,'힌트',tmp_path/'archive.json')
 assert text=='힌트' and summary['attempted']==0 and not model.calls

def test_general_word_phrase_and_segment_repetition():
 from lecture_transcriber.recovery import repetition_spans
 assert repetition_spans([row(0,8,'VectorDB, VectorDB, VectorDB, VectorDB')])==[(0,0)]
 assert repetition_spans([row(i,i+1,'구글') for i in range(46)])==[(0,45)]
 rows=[row(i,i+1,'이벤추얼 컨시스턴트') for i in range(9)]
 assert (0,8) in repetition_spans(rows)
 assert repetition_spans([row(0,5,'구글 구글 서비스 설명입니다.')])==[]
 assert repetition_spans([row(0,5,'구글 설명 구글 질문 구글 답변 구글 요약')])==[]


def test_every_region_processed_beyond_three(tmp_path,monkeypatch):
 setup_audio(monkeypatch)
 rows=[]
 for i in range(4):
  rows.extend([row(i*25,i*25+5,'구글 구글 구글 구글'),row(i*25+5,(i+1)*25,f'별도 정상 문장 {i}입니다.')])
 model=Model([row(0,4,'구글 서비스를 설명합니다.')])
 text,summary=recover(model,'source',rows,100,'',tmp_path/'archive.json')
 assert summary['applied']==4 and summary['unresolved']==0 and len(model.calls)==4
 assert all(f'별도 정상 문장 {i}입니다.' in text for i in range(4))


def test_long_repetition_is_partitioned():
 rows=[row(i,i+1,'구글') for i in range(200)]
 assert regions(rows,'',200)==[(0,179),(180,199)]


def test_unresolved_general_repeat_keeps_original(tmp_path,monkeypatch):
 setup_audio(monkeypatch)
 rows=[row(0,10,'구글 구글 구글 구글')]
 model=Model([row(0,9,'구글 구글 구글 구글')])
 text,summary=recover(model,'source',rows,10,'',tmp_path/'archive.json')
 assert text==rows[0]['text'] and summary['status']=='needs_review'
 assert json.loads((tmp_path/'archive.json').read_text(encoding='utf-8'))['attempts'][0]['reasons']==['repetition']


def test_sustained_low_confidence_boundaries():
 from lecture_transcriber.recovery import low_confidence_spans
 def low(a,b):return dict(row(a,b,'불확실한 설명'),avg_logprob=-2)
 assert low_confidence_spans([low(0,5),low(5,10)])==[(0,1)]
 assert low_confidence_spans([low(0,30)])==[]
 assert low_confidence_spans([low(0,4),low(4,9)])==[]
 assert low_confidence_spans([low(0,6),low(8,14)])==[]
 assert low_confidence_spans([low(0,6),row(6,7,'정상'),low(7,13)])==[]
 assert low_confidence_spans([dict(low(0,6),avg_logprob=float('nan')),low(6,12)])==[]
 assert regions([low(0,5),low(5,10),row(10,20,'보존')],'',20)==[(0,1)]


def test_low_confidence_recovery_audit_and_rejection(tmp_path,monkeypatch):
 setup_audio(monkeypatch)
 rows=[dict(row(0,6,'깨진 설명'),avg_logprob=-2),dict(row(6,12,'다른 설명'),avg_logprob=-2),row(12,30,'유지할 문장.')]
 for accepted in (True,False):
  path=tmp_path/f'low-{accepted}.json'
  retry=dict(row(0,11,'동기화를 설명합니다.'),avg_logprob=-.3 if accepted else -2)
  text,summary=recover(Model([retry]),'source',rows,30,'힌트',path)
  saved=json.loads(path.read_text(encoding='utf-8'))
  assert saved['original_segments']==rows
  assert saved['attempts'][0]['reasons']==['low_confidence']
  assert summary['applied']==int(accepted)
  assert text.endswith('유지할 문장.')
  assert ('깨진 설명' in text) is not accepted


def test_overlapping_low_confidence_and_repeat_retried_once(tmp_path,monkeypatch):
 setup_audio(monkeypatch)
 rows=[dict(row(0,6,'구글 구글 구글 구글'),avg_logprob=-2),dict(row(6,12,'설명'),avg_logprob=-2)]
 model=Model([row(0,11,'서비스 설명입니다.')])
 path=tmp_path/'merged.json'
 recover(model,'source',rows,12,'',path)
 assert len(model.calls)==1
 assert json.loads(path.read_text(encoding='utf-8'))['attempts'][0]['reasons']==['repetition','low_confidence']

def test_final_segment_collector_matches_accepted_and_rejected(tmp_path,monkeypatch):
 setup_audio(monkeypatch)
 rows=[row(0,30,'힌트'),row(30,40,'보존 문장.')]
 for accepted in (True,False):
  segments=[]
  retry=dict(row(0,29,'데이터 설명.'),avg_logprob=-.2 if accepted else -2)
  text,summary=recover(Model([retry]),'source',rows,40,'힌트',tmp_path/f'collector-{accepted}.json',segments)
  from lecture_transcriber.formatting import sentence_layout
  assert sentence_layout(' '.join(s['text'].strip() for s in segments))==text
  assert segments[0]['origin']==('retry' if accepted else 'original')
  assert segments[-1]['origin']=='original'
  assert rows[0]['text']=='힌트'
