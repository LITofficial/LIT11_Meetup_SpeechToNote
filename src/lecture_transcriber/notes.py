"""Session-only note jobs. Cancellation never replaces a completed note."""
import asyncio,copy,json,time
from datetime import datetime,timezone
from pathlib import Path
from uuid import uuid4
from .jobs import JobError
from .credentials import KeyStore
from .gemini import Gemini,MODEL,PROMPT_VERSION,payload
from .note_content import validate_content,evidence
from .note_sources import snapshot_segments

class Notes:
    def __init__(self,jobs,provider=None,keys=None,timeout=180):
        self.jobs=jobs;self.provider=provider or Gemini();self.keys=keys or KeyStore();self.timeout=timeout
        self.snapshot=None;self.title='강의노트';self.notes={};self.operations={};self.requests={};self.task=None;self.active=None
        jobs.external_busy=lambda:self.active is not None
        jobs.on_reset=self.reset
    def reset(self):
        self.snapshot=None;self.notes.clear();self.operations.clear();self.requests.clear()
    def idle(self):
        if self.active:raise JobError(409,'BUSY','노트 생성이 끝나거나 취소한 뒤 다시 시도해 주세요.')
    def bind(self,id):
        job=self.jobs.get(id)
        if job['state']!='completed' or not job['text']:raise JobError(409,'NOT_READY','전사를 완료한 뒤 노트를 만들어 주세요.')
        if self.snapshot!=id:
            self.reset();self.snapshot=id
            self.title=(Path(job['filename'].replace('\\','/')).stem or '강의노트')[:120]
        job['segments']=snapshot_segments(job)
        self.jobs.job['last_activity']=time.monotonic()
        return job
    def log(self,operation,outcome,code=None,stage='generation'):
        data={'timestamp':datetime.now(timezone.utc).isoformat(),'operation_id':operation['id'],'stage':stage,'kind':operation['kind'],'model_id':MODEL,'duration_ms':round((time.monotonic()-operation['started'])*1000),'outcome':outcome,'error_code':code}
        if operation.get('provider'):
            data['provider']=operation['provider']
        if operation.get('validation'):
            data['validation']=operation['validation']
        try:
            folder=self.jobs.root.parent/'note-events';folder.mkdir(exist_ok=True)
            with (folder/'events.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(data)+'\n')
        except OSError:pass
    def start(self,id,body):
        with self.jobs.lock:
            job=self.bind(id)
            if str(body.snapshot_id)!=id:raise JobError(409,'STALE_SNAPSHOT','전사 결과가 변경되었습니다.')
            request=str(body.request_id)
            if request in self.requests:
                old=self.operations[self.requests[request]]
                if old['kind']!=body.kind:raise JobError(409,'INVALID_REQUEST','이미 다른 요청에 사용한 식별자입니다.')
                return self.public(old)
            self.idle()
            if body.kind in self.notes and not body.regenerate:raise JobError(409,'ALREADY_EXISTS','기존 결과를 보거나 다시 생성을 눌러 주세요.')
            key=self.keys.get()
            if not key:raise JobError(409,'KEY_MISSING','설정에서 Gemini API 키를 먼저 저장해 주세요.')
            prepared=payload(body.kind,job['segments'])
            op={'id':str(uuid4()),'state':'running','kind':body.kind,'started':time.monotonic(),'error':None,'note_id':None,'snapshot_id':id}
            self.operations[op['id']]=op;self.requests[request]=op['id'];self.active=op['id']
            self.task=asyncio.create_task(self.generate(op,key,prepared,job['segments']))
            return self.public(op)
    def public(self,op):return {k:op[k] for k in ('id','state','kind','error','note_id','snapshot_id')}
    async def generate(self,op,key,prepared,segments):
        try:
            value=await asyncio.wait_for(self.provider.generate(key,prepared),timeout=max(.001,self.timeout-(time.monotonic()-op['started'])))
            sources={s['source_id']:s for s in segments}
            content=validate_content(value,op['kind'],sources)
            with self.jobs.lock:
                if self.active!=op['id'] or op['state']!='running' or self.snapshot!=op['snapshot_id']:return
                note={'id':str(uuid4()),'snapshot_id':self.snapshot,'kind':op['kind'],'title':self.title,'content':content,'sources':sources,'model_id':MODEL,'prompt_version':PROMPT_VERSION}
                self.notes[op['kind']]=note;op.update(state='completed',note_id=note['id'])
        except asyncio.CancelledError:
            if op['state']=='running':op['state']='cancelled'
        except (asyncio.TimeoutError,TimeoutError):
            op.update(state='timed_out',error={'code':'GENERATION_TIMEOUT','message':'3분 대기 시간이 초과되었습니다. 기존 노트는 유지했습니다.'})
        except JobError as e:
            op.update(state='failed',error={'code':e.code,'message':e.message})
            if hasattr(e,'validation'):op['validation']=e.validation
            if hasattr(e,'provider'):op['provider']=e.provider
        except Exception:op.update(state='failed',error={'code':'GENERATION_FAILED','message':'노트 생성에 실패했습니다. 기존 결과는 유지했습니다.'})
        finally:
            with self.jobs.lock:
                if self.active==op['id']:
                    self.active=None
                    if self.jobs.job:self.jobs.job['last_activity']=time.monotonic()
                self.log(op,op['state'],op['error']['code'] if op['error'] else None)
    def operation(self,id):
        with self.jobs.lock:
            if id not in self.operations:raise JobError(404,'NOT_FOUND','노트 요청이 없거나 만료되었습니다.')
            op=self.operations[id];self.jobs.get(op['snapshot_id'])
            return self.public(op)
    def cancel(self,id):
        with self.jobs.lock:
            self.operation(id);op=self.operations[id]
            if op['state']=='running':
                op['state']='cancelled';self.active=None
                if self.task:self.task.cancel()
                if self.jobs.job:self.jobs.job['last_activity']=time.monotonic()
            return self.public(op)
    def find(self,id):
        with self.jobs.lock:
            if not self.snapshot:raise JobError(404,'NOT_FOUND','노트가 없습니다.')
            self.jobs.get(self.snapshot)
            for note in self.notes.values():
                if note['id']==id:
                    self.jobs.job['last_activity']=time.monotonic()
                    return copy.deepcopy(dict(note,title=self.title))
            raise JobError(404,'NOT_FOUND','노트가 없거나 새 결과로 교체되었습니다.')
    def display(self,note):
        result=copy.deepcopy(note);result.pop('sources',None)
        units=[b for s in result['content']['sections'] for b in s['blocks']]+result['content']['questions']+result['content']['answers']
        for unit in units:unit['evidence']=evidence(unit,note['sources'])
        return result
    async def close(self):
        if self.active:self.cancel(self.active)
        if self.task:
            try:await asyncio.wait_for(self.task,timeout=2)
            except (asyncio.CancelledError,asyncio.TimeoutError):pass
        self.reset()
