"""Final ASR segments mapped to bounded, auditable source references."""
import math,re
from .formatting import sentence_layout
from .recovery import repetition_spans
from .jobs import JobError

def snapshot_segments(job):
    rows=job.get('segments',[])
    if not rows or sentence_layout(' '.join(s['text'].strip() for s in rows))!=job['text']:
        raise JobError(409,'SOURCE_MAPPING_MISSING','근거 구간 정보가 없습니다. 새 버전에서 다시 전사해 주세요.')
    repeated={i for a,b in repetition_spans(rows) for i in range(a,b+1)}
    result=[]
    for i,row in enumerate(rows):
        flags=[]
        if row.get('avg_logprob') is not None and row['avg_logprob'] < -1:flags.append('low_confidence')
        if i in repeated or (row.get('compression_ratio') or 0)>2.4:flags.append('repetition')
        start,end=row.get('start'),row.get('end')
        if not all(isinstance(t,(int,float)) and math.isfinite(t) for t in (start,end)) or start<0 or end<start or end>row.get("source_duration",float("inf"))+1:
            start=end=None;flags.append('invalid_time')
        result.append(dict(source_id=f's{i+1}',text=row['text'].strip(),start_seconds=start,end_seconds=end,origin=row.get('origin','original'),uncertainty_codes=flags))
    return result
