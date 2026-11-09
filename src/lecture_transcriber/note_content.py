"""Validated note structure shared by UI and PDF; text is never executable."""
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field,ValidationError
from .jobs import JobError

KINDS={'understand':'이해용','memorize':'암기용','practice':'문제풀이용'}
class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
class Block(Strict):
    type: Literal['paragraph','list','table','qa']
    text: str=Field(max_length=10000)
    items: list[str]=Field(max_length=40)
    columns: list[str]=Field(max_length=6)
    rows: list[list[str]]=Field(max_length=60)
    question: str=Field(max_length=2000)
    answer: str=Field(max_length=4000)
    basis: Literal['lecture','supplement']
    source_ids: list[str]=Field(max_length=20)
    uncertain: bool
class Section(Strict):
    heading: str=Field(min_length=1,max_length=200)
    blocks: list[Block]=Field(min_length=1,max_length=40)
class Question(Strict):
    id: str=Field(min_length=1,max_length=30)
    category: Literal['concept','application']
    format: Literal['choice','short','essay','calculation']
    prompt: str=Field(min_length=1,max_length=4000)
    options: list[str]=Field(max_length=6)
    source_ids: list[str]=Field(max_length=20)
    basis: Literal['lecture','supplement']
    uncertain: bool
class Answer(Strict):
    question_id: str
    answer: str=Field(min_length=1,max_length=4000)
    explanation: str=Field(min_length=1,max_length=6000)
    source_ids: list[str]=Field(max_length=20)
    basis: Literal['lecture','supplement']
    uncertain: bool
class Content(Strict):
    sections: list[Section]=Field(max_length=30)
    questions: list[Question]=Field(max_length=10)
    answers: list[Answer]=Field(max_length=10)
    fewer_questions_reason: str=Field(max_length=500)

def invalid(code,message,path='',rule=''):
    error=JobError(502,code,message+' 기존 노트는 유지했습니다.')
    error.validation={'path':path,'rule':rule}
    return error


def validate_content(value,kind,sources):
    # Practice notes deliberately exclude introductory sections. Do not mutate input.
    if kind=='practice' and isinstance(value,dict):
        value=dict(value,sections=[])
    try:
        doc=Content.model_validate(value)
    except ValidationError as exc:
        # Do not record Pydantic input, context or untrusted extra-field names.
        e=exc.errors(include_input=False,include_context=False,include_url=False)[0]
        allowed={'sections','questions','answers','fewer_questions_reason','heading','blocks','type','text','items','columns','rows','question','answer','basis','source_ids','uncertain','id','category','format','prompt','options','question_id','explanation'}
        path='.'.join(str(v) if isinstance(v,int) or v in allowed else '?' for v in e['loc'])
        rules={'missing','too_long','too_short','string_too_long','string_too_short','string_type','list_type','literal_error','extra_forbidden','bool_parsing','model_type'}
        rule=e['type'] if e['type'] in rules else 'schema'
        raise invalid('NOTE_SCHEMA_INVALID','응답의 필수 항목·자료형·길이 제한을 확인하지 못했습니다.',path,rule) from None
    if kind=='practice':
        qs=doc.questions;ids=[q.id for q in qs]
        if not qs or len(ids)!=len(set(ids)) or sorted(ids)!=sorted(a.question_id for a in doc.answers):
            raise invalid('NOTE_QUESTION_MISMATCH','문제와 정답이 정확히 대응하지 않습니다.','questions','id_match')
        if len(qs)<10 and not doc.fewer_questions_reason:raise invalid('NOTE_QUESTION_COUNT','문제 수를 줄인 이유가 없습니다.','fewer_questions_reason','missing_reason')
        if len(qs)==10 and sum(q.category=='concept' for q in qs)!=6:raise invalid('NOTE_QUESTION_COUNT','개념·적용 문제 구성이 맞지 않습니다.','questions','category_count')
        if any(q.format=='choice' and len(q.options)<2 for q in qs):raise invalid('NOTE_OPTIONS_MISSING','객관식 보기가 부족합니다.','questions','options')
    elif not doc.sections or doc.questions or doc.answers:
        raise invalid('NOTE_KIND_MISMATCH','선택한 노트 종류와 응답 구성이 다릅니다.','sections','kind')
    units=[(f'sections.{i}.blocks.{j}',b) for i,section in enumerate(doc.sections) for j,b in enumerate(section.blocks)]
    units += [(f'questions.{i}',q) for i,q in enumerate(doc.questions)]+[(f'answers.{i}',a) for i,a in enumerate(doc.answers)]
    for path,unit in units:
        if any(i not in sources for i in unit.source_ids):
            raise invalid('NOTE_SOURCE_UNKNOWN','AI가 실제 전사 구간에 없는 근거를 참조했습니다.',path+'.source_ids','unknown_source')
        if unit.basis=='lecture' and not unit.source_ids:
            raise invalid('NOTE_SOURCE_MISSING','강의 내용으로 표시된 항목의 근거가 빠졌습니다.',path+'.source_ids','missing_source')
        if any(sources[i]['uncertainty_codes'] for i in unit.source_ids):unit.uncertain=True
        if isinstance(unit,Block):
            if (unit.type=='paragraph' and not unit.text) or (unit.type=='list' and not unit.items) or (unit.type=='qa' and (not unit.question or not unit.answer)):
                raise invalid('NOTE_BLOCK_EMPTY','노트 항목의 본문이 비어 있습니다.',path,'empty_content')
            if unit.type=='table' and (not unit.columns or not unit.rows or any(len(r)!=len(unit.columns) for r in unit.rows)):
                raise invalid('NOTE_TABLE_INVALID','표의 제목과 각 행의 열 개수가 맞지 않습니다.',path,'table_shape')
    return doc.model_dump()


def evidence(unit,sources):
    if unit['basis']=='supplement':label='응용 문제' if 'category' in unit else '보충 설명'
    else:
        stamps=[]
        for id in unit['source_ids']:
            s=sources[id];t=s.get('start_seconds')
            stamp='시각 확인 필요' if t is None else f'{int(t)//60:02}:{int(t)%60:02}'
            if stamp not in stamps:stamps.append(stamp)
        label='강의 근거 '+', '.join(stamps)
    if unit['uncertain']:label+=' · 확인 필요'
    return label
