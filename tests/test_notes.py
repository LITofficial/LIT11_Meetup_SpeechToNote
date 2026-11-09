import asyncio,copy,json,time
from uuid import uuid4
from pathlib import Path
import pytest
import pymupdf as fitz
from fastapi.testclient import TestClient
from lecture_transcriber.app import create_app
from lecture_transcriber.jobs import JobError
from lecture_transcriber.note_sources import snapshot_segments
from lecture_transcriber.note_content import validate_content
from lecture_transcriber.gemini import payload
from lecture_transcriber.note_pdf import make_pdf

ORIGIN='http://127.0.0.1:8765'
def sample(kind='understand'):
    block=dict(type='paragraph',text='데이터 일관성은 복제된 값의 관계를 뜻합니다.',items=[],columns=[],rows=[],question='',answer='',basis='lecture',source_ids=['s1'],uncertain=False)
    doc=dict(sections=[dict(heading='핵심 개념',blocks=[block])],questions=[],answers=[],fewer_questions_reason='')
    if kind=='memorize':doc['sections'][0]['blocks'] += [dict(block,type='table',columns=['개념','설명'],rows=[['최종 일관성','시간이 지나면 같은 값']]),dict(block,type='qa',question='일관성이란?',answer='복제된 값의 관계')]
    if kind=='practice':
        doc['questions']=[dict(id='1',category='concept',format='short',prompt='일관성이란?',options=[],source_ids=['s1'],basis='lecture',uncertain=False)]
        doc['answers']=[dict(question_id='1',answer='복제 값의 관계',explanation='강의 정의에 근거합니다.',source_ids=['s1'],basis='lecture',uncertain=False)]
        doc['fewer_questions_reason']='짧은 강의이므로 한 문제만 제공합니다.'
    return doc
class Keys:
    value='synthetic-key'
    def get(self):return self.value
    def set(self,v):self.value=v
    def delete(self):self.value=None
class Provider:
    def __init__(self):self.calls=[];self.kind='understand';self.delay=0;self.fail=False;self.bad=False;self.ignore_cancel=False
    async def generate(self,key,body):
        self.calls.append(body)
        try:await asyncio.sleep(self.delay)
        except asyncio.CancelledError:
            if not self.ignore_cancel:raise
        if self.fail:raise JobError(429,'QUOTA_EXCEEDED','한도 초과')
        data=sample(self.kind)
        if self.bad:data['sections'][0]['blocks'][0]['source_ids']=['made-up']
        return data
@pytest.fixture
def connected(tmp_path):
    provider=Provider();keys=Keys();app=create_app(tmp_path,ORIGIN,note_provider=provider,key_store=keys)
    with TestClient(app,base_url=ORIGIN) as client:
        client.headers['Origin']=ORIGIN
        csrf=client.post('/api/v1/session',json={'launch_token':app.state.launch_token}).json()['csrf_token']
        client.headers['X-CSRF-Token']=csrf
        id=str(uuid4());now=time.monotonic()
        app.state.jobs.job=dict(job_id=id,state='completed',model_id='small',filename='합성 강의.wav',text='일관성 설명입니다.',segments=[dict(text='일관성 설명입니다.',start=0,end=10,source_duration=10,avg_logprob=-.2,compression_ratio=1)],completed=now,error=None,diagnostics_status='saved',recovery={'status':'not_needed'})
        yield app,client,provider,id

def submit(c,id,kind='understand',regenerate=False,request=None):
    return c.post(f'/api/v1/transcriptions/{id}/notes',json=dict(kind=kind,snapshot_id=id,request_id=request or str(uuid4()),regenerate=regenerate))
def wait(c,id):
    for _ in range(100):
        r=c.get('/api/v1/note-jobs/'+id).json()
        if r['state']!='running':return r
        time.sleep(.02)
    pytest.fail('note timeout')

def test_understand_to_pdf_without_extra_calls(connected):
    app,c,p,id=connected
    op=submit(c,id);assert op.status_code==202
    end=wait(c,op.json()['id']);assert end['state']=='completed',end
    n=c.get('/api/v1/notes/'+end['note_id']).json()
    assert n['content']['sections'][0]['blocks'][0]['evidence']=='강의 근거 00:00'
    c.patch(f'/api/v1/transcriptions/{id}/note-title',json={'title':'변경된 강의 제목'})
    for _ in range(2):
        pdf=c.get('/api/v1/notes/'+n['id']+'/pdf');assert pdf.status_code==200
        document=fitz.open(stream=pdf.content,filetype='pdf');text=''.join(page.get_text() for page in document)
        assert '변경된 강의 제목' in text and '일관성' in text
    assert len(p.calls)==1
    sent=json.dumps(p.calls,ensure_ascii=False)
    assert '합성 강의' not in sent and 'start_seconds' not in sent and 'synthetic-key' not in sent
    assert app.state.jobs.job['text']=='일관성 설명입니다.'

def test_all_kinds_retained_and_pdf_failure_keeps_note(connected,monkeypatch):
    app,c,p,id=connected
    for kind in ('understand','memorize','practice'):
        p.kind=kind;end=wait(c,submit(c,id,kind).json()['id']);assert end['state']=='completed'
    listing=c.get(f'/api/v1/transcriptions/{id}/notes').json();assert len(listing['notes'])==3
    n=listing['notes'][0]['id']
    import lecture_transcriber.note_routes as routes
    monkeypatch.setattr(routes,'make_pdf',lambda n:(_ for _ in ()).throw(RuntimeError()))
    assert c.get(f'/api/v1/notes/{n}/pdf').status_code==500
    assert c.get(f'/api/v1/notes/{n}').status_code==200 and len(p.calls)==3

def test_retry_failure_preserves_previous_and_minimal_log(connected):
    app,c,p,id=connected
    end=wait(c,submit(c,id).json()['id']);first=end['note_id'];p.fail=True
    failed=wait(c,submit(c,id,regenerate=True).json()['id'])
    assert failed['error']['code']=='QUOTA_EXCEEDED'
    assert c.get(f'/api/v1/notes/{first}').status_code==200
    log=(app.state.jobs.root.parent/'note-events/events.jsonl').read_text()
    assert 'synthetic-key' not in log and '일관성' not in log and len(p.calls)==2

def test_cancel_timeout_late_result_and_idempotency(connected):
    app,c,p,id=connected;p.delay=2;p.ignore_cancel=True
    request=str(uuid4());op=submit(c,id,request=request).json()
    assert submit(c,id,request=request).json()['id']==op['id']
    assert submit(c,id,'memorize').status_code==409
    assert c.put('/api/v1/notes/key',json={'key':'new'}).status_code==409
    c.post('/api/v1/note-jobs/'+op['id']+'/cancel')
    time.sleep(.05)
    assert c.get('/api/v1/note-jobs/'+op['id']).json()['state']=='cancelled'
    assert not app.state.notes.notes
    p.ignore_cancel=False;app.state.notes.timeout=.03
    end=wait(c,submit(c,id).json()['id']);assert end['state']=='timed_out'
    assert not app.state.notes.notes

def test_key_security_missing_source_and_oversize(connected):
    app,c,p,id=connected
    c.delete('/api/v1/notes/key');assert not c.get('/api/v1/notes/settings').json()['key_configured']
    assert submit(c,id).status_code==409
    assert c.put('/api/v1/notes/key',json={'key':'synthetic-key'}).status_code==200
    assert 'synthetic-key' not in c.get('/api/v1/notes/settings').text
    bad=c.post(f'/api/v1/transcriptions/{id}/notes',json=dict(kind='understand',snapshot_id=str(uuid4()),request_id=str(uuid4())))
    assert bad.status_code==409
    app.state.jobs.job['segments']=[]
    assert submit(c,id).status_code==409 and not p.calls

def test_invalid_output_and_references(connected):
    app,c,p,id=connected;p.bad=True
    end=wait(c,submit(c,id).json()['id']);assert end['state']=='failed' and not app.state.notes.notes
    with pytest.raises(JobError):payload('understand',[dict(source_id='s1',text='가'*200000,uncertainty_codes=[])])
    source={'s1':{'uncertainty_codes':['low_confidence']}}
    validated=validate_content(sample(),'understand',source)
    assert validated['sections'][0]['blocks'][0]['uncertain']
    doc=sample('practice');doc['answers'][0]['question_id']='wrong'
    with pytest.raises(JobError):validate_content(doc,'practice',source)

def test_source_boundaries_and_expiration(connected):
    app,c,p,id=connected
    rows=snapshot_segments(app.state.jobs.job);assert rows[0]['start_seconds']==0
    app.state.jobs.job['segments'][0]['end']=15
    rows=snapshot_segments(app.state.jobs.job);assert rows[0]['start_seconds'] is None
    app.state.jobs.job['completed']=time.monotonic()-1801
    assert c.get(f'/api/v1/transcriptions/{id}/notes').status_code==404
    assert app.state.notes.snapshot is None

def test_guarded_endpoints(connected):
    app,c,p,id=connected
    c.headers['X-CSRF-Token']='bad'
    assert submit(c,id).status_code==403
    assert c.put('/api/v1/notes/key',json={'key':'private'}).status_code==403
    assert not p.calls

def test_gemini_transport_rejects_truncated_and_quota_without_retry(monkeypatch):
    import httpx
    from lecture_transcriber.gemini import Gemini
    calls=[]
    status=[429];body=[{}]
    def handle(request):
        calls.append(request)
        assert request.url.host=='generativelanguage.googleapis.com'
        assert 'key=' not in str(request.url)
        return httpx.Response(status[0],json=body[0])
    original=httpx.AsyncClient
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(handle),**kw))
    async def check():
        with pytest.raises(JobError) as e:await Gemini().generate('test-key',{})
        assert e.value.code=='QUOTA_EXCEEDED' and len(calls)==1
        status[0]=200;body[0]={'candidates':[{'finishReason':'MAX_TOKENS','content':{'parts':[{'text':'{}'}]}}]}
        with pytest.raises(JobError) as e:await Gemini().generate('test-key',{})
        assert e.value.code=='OUTPUT_INCOMPLETE' and len(calls)==2
        body[0]={'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':json.dumps(sample())}]}}]}
        assert (await Gemini().generate('test-key',{}))['sections']
    asyncio.run(check())

def test_notes_block_transcription_and_current_source_only(connected):
    app,c,p,id=connected;p.delay=2
    op=submit(c,id).json()
    from io import BytesIO
    with pytest.raises(JobError) as error:app.state.jobs.start(BytesIO(b'a'),'base','test.wav')
    assert error.value.code=='BUSY'
    c.post('/api/v1/note-jobs/'+op['id']+'/cancel')
    app.state.jobs.on_reset()
    assert c.get('/api/v1/note-jobs/'+op['id']).status_code==404

def test_gemini_errors_distinguish_request_from_credentials():
    import httpx
    from lecture_transcriber.gemini import provider_error
    cases=[(400,{'status':'INVALID_ARGUMENT','message':'Request contains an invalid argument.'},'PROVIDER_INVALID_REQUEST'),
           (400,{'message':'too many states in schema'},'PROVIDER_SCHEMA'),
           (400,{'details':[{'reason':'API_KEY_INVALID'}]},'API_KEY_INVALID'),
           (403,{'message':'private project value'},'PROVIDER_PERMISSION'),
           (401,{},'API_KEY_INVALID')]
    for status,error,code in cases:
        exc=provider_error(httpx.Response(status,json={'error':error}))
        assert exc.code==code
        assert 'private project value' not in exc.message


def test_wire_schema_small_local_validation_still_strict():
    from lecture_transcriber.gemini import response_schema
    from lecture_transcriber.note_content import Content
    wire=json.dumps(response_schema())
    for keyword in ('$ref','$defs','maxItems','maxLength','additionalProperties'):assert keyword not in wire
    assert 'maxItems' in json.dumps(Content.model_json_schema())
    data=sample();data['sections'][0]['blocks'][0]['text']='x'*10001
    with pytest.raises(JobError):validate_content(data,'understand',{'s1':{'uncertainty_codes':[]}})

def test_validation_failure_diagnostics_are_specific_and_private(connected):
    from lecture_transcriber.note_content import validate_content
    sources={'s1':{'uncertainty_codes':[]}}
    tests=[]
    v=sample();v['sections'][0]['blocks'][0]['source_ids']=['private-source-text'];tests.append((v,'NOTE_SOURCE_UNKNOWN'))
    v=sample();v['sections'][0]['blocks'][0]['source_ids']=[];tests.append((v,'NOTE_SOURCE_MISSING'))
    v=sample();v['sections'][0]['blocks'][0]['text']='';tests.append((v,'NOTE_BLOCK_EMPTY'))
    v=sample();v['sections'][0]['blocks'][0]['private-secret']='private-value';tests.append((v,'NOTE_SCHEMA_INVALID'))
    for value,code in tests:
        with pytest.raises(JobError) as e:validate_content(value,'understand',sources)
        assert e.value.code==code
        assert 'private' not in json.dumps(e.value.validation)
    app,c,p,id=connected;p.bad=True
    outcome=wait(c,submit(c,id).json()['id'])
    assert outcome['error']['code']=='NOTE_SOURCE_UNKNOWN'
    log=(app.state.jobs.root.parent/'note-events/events.jsonl').read_text()
    assert 'unknown_source' in log and 'made-up' not in log

def test_application_without_sources_allowed_but_lecture_still_requires_sources():
    sources={'s1':{'uncertainty_codes':[]}}
    doc=sample('practice')
    doc['questions'][0].update(category='application',basis='supplement',source_ids=[])
    doc['answers'][0].update(basis='supplement',source_ids=[])
    assert validate_content(doc,'practice',sources)['questions'][0]['source_ids']==[]
    doc['questions'][0]['basis']='lecture'
    with pytest.raises(JobError) as e:validate_content(doc,'practice',sources)
    assert e.value.code=='NOTE_SOURCE_MISSING'


def test_pdf_omits_times_keeps_warnings_and_section_gap():
    doc=sample();doc['sections'][0]['blocks'][0]['uncertain']=True
    second=copy.deepcopy(doc['sections'][0]);second['heading']='다음 주제';second['blocks'][0]['basis']='supplement'
    doc['sections'].append(second)
    note=dict(title='가독성 검증',kind='understand',sources={'s1':dict(start_seconds=2540,uncertainty_codes=[])},content=doc)
    pdf=fitz.open(stream=make_pdf(note),filetype='pdf');text=pdf[0].get_text()
    assert '강의 근거' not in text and '42:20' not in text
    assert '확인 필요' in text and '보충 설명' in text and '다음 주제' in text
    blocks=pdf[0].get_text('blocks');heading=next(b for b in blocks if '다음 주제' in b[4])
    previous=max(b[3] for b in blocks if b[3]<heading[1] and '가독성 검증' not in b[4])
    assert heading[1]-previous>=16

def test_provider_status_logged_without_response_or_key(monkeypatch,connected):
    import httpx
    from lecture_transcriber.gemini import Gemini
    original=httpx.AsyncClient
    calls=[]
    def handle(request):
        calls.append(request)
        return httpx.Response(503,json={'error':{'status':'UNAVAILABLE','message':'private-response-secret','details':[{'key':'secret'}]}})
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(handle),**kw))
    app,c,p,id=connected;app.state.notes.provider=Gemini()
    result=wait(c,submit(c,id).json()['id'])
    assert result['error']['code']=='PROVIDER_SERVER_ERROR'
    assert 'HTTP 503' in result['error']['message'] and len(calls)==1
    log=(app.state.jobs.root.parent/'note-events/events.jsonl').read_text()
    assert '503' in log and 'UNAVAILABLE' in log
    assert 'private-response-secret' not in log and 'synthetic-key' not in log
    assert not app.state.notes.notes

def test_practice_excludes_intro_preserves_questions_and_answers():
    doc=sample('practice');doc['sections'][0]['heading']='삭제할 개념 설명'
    source={'s1':dict(start_seconds=0,uncertainty_codes=[])}
    result=validate_content(doc,'practice',source)
    assert not result['sections']
    assert result['questions']==doc['questions'] and result['answers']==doc['answers']
    assert doc['sections']  # Caller-owned input unchanged.
    # Old in-memory practice results are also rendered without introductions.
    pdf=fitz.open(stream=make_pdf(dict(title='연습',kind='practice',sources=source,content=doc)),filetype='pdf')
    text=''.join(p.get_text() for p in pdf)
    assert '삭제할 개념 설명' not in text and '일관성이란?' in text and '정답과 해설' in text
    understand=sample()
    assert validate_content(understand,'understand',source)['sections']
