from typing import Literal
from uuid import UUID
from pydantic import BaseModel,ConfigDict,Field,field_validator
from fastapi.responses import Response
from .jobs import JobError
from .gemini import MODEL
from .note_pdf import make_pdf

class Input(BaseModel):
    model_config=ConfigDict(extra='forbid')
class KeyInput(Input):
    key:str=Field(min_length=1,max_length=2560)
    @field_validator('key')
    @classmethod
    def valid(cls,v):
        if not v.isascii() or any(c.isspace() for c in v):raise ValueError('invalid key')
        return v
class TitleInput(Input):
    title:str=Field(min_length=1,max_length=120)
    @field_validator('title')
    @classmethod
    def valid(cls,v):
        if not v.strip() or any(ord(c)<32 for c in v):raise ValueError('invalid title')
        return v.strip()
class GenerateInput(Input):
    kind:Literal['understand','memorize','practice']
    snapshot_id:UUID
    request_id:UUID
    regenerate:bool=False

def register(app,notes):
    @app.get('/api/v1/notes/settings')
    def settings():
        return {'key_configured':bool(notes.keys.get()),'provider':'gemini','model':MODEL,'quality_verified':False}
    @app.put('/api/v1/notes/key')
    def key_set(body:KeyInput):
        with notes.jobs.lock:notes.idle();notes.keys.set(body.key)
        return {'key_configured':True}
    @app.delete('/api/v1/notes/key')
    def key_delete():
        with notes.jobs.lock:notes.idle();notes.keys.delete()
        return {'key_configured':False}
    @app.patch('/api/v1/transcriptions/{id}/note-title')
    def title(id:str,body:TitleInput):
        with notes.jobs.lock:notes.bind(id);notes.title=body.title
        return {'title':notes.title}
    @app.get('/api/v1/transcriptions/{id}/notes')
    def listing(id:str):
        with notes.jobs.lock:
            job=notes.bind(id)
            return {'snapshot_id':id,'title':notes.title,'has_uncertainty':any(s['uncertainty_codes'] for s in job['segments']),
                    'notes':[{k:n[k] for k in ('id','kind')} for n in notes.notes.values()]}
    @app.post('/api/v1/transcriptions/{id}/notes',status_code=202)
    async def generate(id:str,body:GenerateInput):return notes.start(id,body)
    @app.get('/api/v1/note-jobs/{id}')
    def operation(id:str):return notes.operation(id)
    @app.post('/api/v1/note-jobs/{id}/cancel')
    async def cancel(id:str):return notes.cancel(id)
    @app.get('/api/v1/notes/{id}')
    def note(id:str):return notes.display(notes.find(id))
    @app.get('/api/v1/notes/{id}/pdf')
    def pdf(id:str):
        note=notes.find(id)
        import time
        op={'id':id,'kind':note['kind'],'started':time.monotonic()}
        try:
            data=make_pdf(note);notes.log(op,'completed',stage='pdf')
            return Response(data,media_type='application/pdf',headers={'Content-Disposition':f'attachment; filename="notes-{note["kind"]}.pdf"'})
        except Exception:
            notes.log(op,'failed','PDF_FAILED','pdf')
            raise JobError(500,'PDF_FAILED','PDF 변환에 실패했습니다. 노트는 유지됐습니다. 다운로드만 다시 시도해 주세요.') from None
