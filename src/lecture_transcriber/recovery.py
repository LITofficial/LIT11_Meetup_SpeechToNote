"""Bounded per-region retry of hint-only output and repeated phrases. Never delete originals."""
import json
import math
import re
from pathlib import Path
from .formatting import sentence_layout

MIN_HINT_SECONDS = 10.0
MAX_RETRY_SECONDS = 180.0
MAX_PHRASE_TOKENS = 8
MIN_REPEATS = 4
MIN_LOW_CONFIDENCE_SECONDS = 10.0


def low_confidence_spans(rows):
    """Require sustained low confidence, not an isolated uncertain word."""
    found=[]; left=None
    for i in range(len(rows)+1):
        s=rows[i] if i<len(rows) else {}
        values=[s.get(k) for k in ('start','end','avg_logprob')]
        valid=all(isinstance(v,(int,float)) and math.isfinite(v) for v in values)
        low=valid and s['start']>=0 and s['end']>s['start'] and s['avg_logprob'] < -1
        adjacent=left is None or (low and 0<=s['start']-rows[i-1]['end']<=1)
        if left is not None and (not low or not adjacent):
            if i-left>=2 and rows[i-1]['end']-rows[left]['start']>=MIN_LOW_CONFIDENCE_SECONDS:
                found.append((left,i-1))
            left=None
        if low and left is None:left=i
    return found


def normalized(text):
    return ''.join(c.lower() for c in text if c.isalnum())


def hint_only(text, hint):
    value, term = normalized(text), normalized(hint)
    return bool(term and value and len(value) % len(term) == 0 and value == term * (len(value)//len(term)))


def pack(segment):
    return {k:getattr(segment,k,None) for k in ('start','end','text','avg_logprob','compression_ratio','temperature','no_speech_prob')}


def repetition_spans(rows):
    # Token ownership locates the actual repeated run, not a rolling-window tail.
    tokens=[];owners=[]
    for i,row in enumerate(rows):
        words=re.findall(r'\w+',row['text'].lower())
        tokens.extend(words);owners.extend([i]*len(words))
    found=[]
    for size in range(1,MAX_PHRASE_TOKENS+1):
        i=0
        while i+size*MIN_REPEATS<=len(tokens):
            phrase=tokens[i:i+size];count=1
            while tokens[i+count*size:i+(count+1)*size]==phrase:count+=1
            if count>=MIN_REPEATS:
                found.append((owners[i],owners[i+count*size-1]));i+=count*size
            else:i+=1
    merged=[]
    for left,right in sorted(set(found)):
        if merged and left<=merged[-1][1]:merged[-1]=(merged[-1][0],max(right,merged[-1][1]))
        else:merged.append((left,right))
    return merged


def regions(rows, hint, duration):
    candidates=repetition_spans(rows)+low_confidence_spans(rows)
    for i,s in enumerate(rows):
        if s['start'] is None or s['end'] is None: continue
        if s['end']-s['start'] >= MIN_HINT_SECONDS and hint_only(s['text'],hint):
            right=i
            while right+1<len(rows) and hint_only(rows[right+1]['text'],hint):right+=1
            candidates.append((i,right))
    expanded=[]
    for left,right in candidates:
        if rows[left]['start'] is None or rows[right]['end'] is None:continue
        start,end=rows[left]['start'],rows[right]['end']
        while left>0 and start-rows[left-1]['start']<=5:left-=1
        while right+1<len(rows) and rows[right+1]['end']-end<=5:right+=1
        # Continue through immediately following low-confidence output after a loop.
        while right+1<len(rows) and rows[right+1].get('avg_logprob') is not None and rows[right+1]['avg_logprob'] < -1:
            right+=1
        expanded.append((left,right))
    merged=[]
    for left,right in sorted(expanded):
        if merged and left<=merged[-1][1]+1:merged[-1]=(merged[-1][0],max(right,merged[-1][1]))
        else:merged.append((left,right))
    # Process every detected region. Split long runs at existing segment boundaries.
    bounded=[]
    for left,right in merged:
        first=left
        for i in range(left+1,right+1):
            if rows[i]['end']-rows[first]['start']>MAX_RETRY_SECONDS:
                bounded.append((first,i-1));first=i
        bounded.append((first,right))
    return bounded


def retry_options():
    return dict(language='ko',task='transcribe',beam_size=5,vad_filter=False,
                word_timestamps=False,initial_prompt=None,condition_on_previous_text=False)


def suspicious_retry(retry,text,hint,start,end):
    return (not text or hint_only(text,hint) or bool(repetition_spans(retry)) or
        any(s['start']<start or s['end']>end+1 or s['end']<s['start'] or
            (s['avg_logprob'] is not None and s['avg_logprob'] < -1) or
            (s['compression_ratio'] is not None and s['compression_ratio']>2.4) for s in retry))


def atomic_save(path, value):
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix('.partial')
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    temporary.replace(path)


def recover(model, source, rows, duration, hint, archive_path, final_rows=None):
    if final_rows is not None:
        final_rows.extend(dict(s, origin="original") for s in rows)
    selected=regions(rows,hint,duration)
    original=sentence_layout(' '.join(s['text'].strip() for s in rows))
    summary={'status':'not_needed','attempted':0,'applied':0,'unresolved':0}
    if not selected:return original,summary
    summary.update(status='pending',unresolved=len(selected))
    archive={'schema_version':1,'original_text':original,'original_segments':rows,
             'attempts':[],'final_text':original,'summary':dict(summary)}
    if archive_path is None:
        summary['status']='archive_failed';return original,summary
    try:atomic_save(archive_path,archive)
    except OSError:
        summary['status']='archive_failed';return original,summary
    audio=None; replacements={}
    for left,right in selected:
        start=max(0,rows[left]['start']);end=min(duration,rows[right]['end'])
        attempt={'start':start,'end':end,'original_indices':[left,right],
                 'original_text':' '.join(s['text'].strip() for s in rows[left:right+1]),
                 'retry_segments':[],'retry_text':'','state':'pending',
                 'reasons':(['repetition'] if repetition_spans(rows[left:right+1]) else []) +
                 (['hint_only'] if any(hint_only(s['text'],hint) and s['end']-s['start']>=MIN_HINT_SECONDS for s in rows[left:right+1]) else []) +
                 (['low_confidence'] if low_confidence_spans(rows[left:right+1]) else [])}
        archive['attempts'].append(attempt)
        if end-start>MAX_RETRY_SECONDS or end<=start:
            attempt['state']='skipped_limit'
        else:
            summary['attempted']+=1
            try:
                if audio is None:
                    from faster_whisper.audio import decode_audio
                    audio=decode_audio(str(source),sampling_rate=16000)
                clip=audio[round(start*16000):round(end*16000)]
                segments,_=model.transcribe(clip,**retry_options())
                retry=[]
                for segment in segments:
                    item=pack(segment)
                    item['start']+=start;item['end']+=start;retry.append(item)
                    attempt['retry_segments']=retry
                    attempt['retry_text']=sentence_layout(' '.join(s['text'].strip() for s in retry))
                    atomic_save(archive_path,archive)
                text=attempt['retry_text']
                suspicious=suspicious_retry(retry,text,hint,start,end)
                attempt['state']='needs_review' if suspicious else 'accepted'
                if not suspicious:
                    replacements[left]=(right,text);summary['applied']+=1;summary['unresolved']-=1
            except OSError:
                summary['status']='archive_failed'
                # Keep the original result whenever durable audit storage fails.
                return original,dict(summary,applied=0,unresolved=len(selected))
            except Exception:
                attempt['state']='retry_failed'
        archive['summary']=dict(summary)
        try:atomic_save(archive_path,archive)
        except OSError:return original,dict(summary,status='archive_failed',applied=0,unresolved=len(selected))
    pieces=[];i=0
    while i<len(rows):
        if i in replacements:
            right,text=replacements[i];pieces.append(text);i=right+1
        else:pieces.append(rows[i]['text'].strip());i+=1
    final=sentence_layout(' '.join(pieces))
    summary['status']='applied' if not summary['unresolved'] else 'partial' if summary['applied'] else 'needs_review'
    archive.update(final_text=final,summary=dict(summary))
    try:atomic_save(archive_path,archive)
    except OSError:return original,dict(summary,status='archive_failed',applied=0,unresolved=len(selected))
    if final_rows is not None:
        accepted={a['original_indices'][0]:a for a in archive['attempts'] if a['state']=='accepted'}
        merged=[];i=0
        while i<len(rows):
            if i in accepted:
                a=accepted[i];merged.extend(dict(s,origin='retry') for s in a['retry_segments']);i=a['original_indices'][1]+1
            else:merged.append(dict(rows[i],origin='original'));i+=1
        final_rows[:]=merged
    return final,summary
