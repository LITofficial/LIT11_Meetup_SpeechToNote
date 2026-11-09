"""Local numeric ASR diagnostics. Detection never edits transcript text."""
import json
import re
from datetime import datetime, timezone


def repetition_count(text):
    tokens = re.findall(r'\w+', text.lower())
    best = 1 if tokens else 0
    for size in range(1, 5):
        for start in range(len(tokens) - size):
            phrase = tokens[start:start + size]
            count = 1
            while tokens[start + count*size:start + (count+1)*size] == phrase:
                count += 1
            best = max(best, count)
    return best


class Recorder:
    def __init__(self, path, duration, model, hint_present):
        self.path = path
        self.tail = ''
        self.failed = False
        self.data = {'schema_version':1, 'created_utc':datetime.now(timezone.utc).isoformat(),
                     'state':'running', 'duration_seconds':duration, 'model_id':model,
                     'hint_present':hint_present, 'thresholds':{'avg_logprob_below':-1.0,
                     'compression_ratio_above':2.4, 'consecutive_repetitions_at_least':4,
                     'time_tolerance_seconds':1.0}, 'segments':[]}
        self.save()

    def add(self, segment):
        row = {k: getattr(segment,k,None) for k in ('start','end','avg_logprob','compression_ratio','no_speech_prob','temperature')}
        row['index'] = len(self.data['segments'])
        row['text_characters'] = len(segment.text)
        combined = self.tail + ' ' + segment.text
        row['consecutive_repetitions'] = repetition_count(combined)
        self.tail = ' '.join(re.findall(r'\w+', combined)[-24:])
        flags=[]
        if row['consecutive_repetitions'] >= 4 or (row['compression_ratio'] is not None and row['compression_ratio'] > 2.4): flags.append('repetition')
        if row['avg_logprob'] is not None and row['avg_logprob'] < -1.0: flags.append('low_confidence')
        if row['start'] is not None and row['end'] is not None:
            if row['start'] < 0 or row['end'] < row['start'] or row['end'] > self.data['duration_seconds'] + 1: flags.append('invalid_time')
        row['flags']=flags
        self.data['segments'].append(row)
        self.save()

    def save(self):
        try:
            self.path.parent.mkdir(parents=True,exist_ok=True)
            temporary=self.path.with_suffix('.partial')
            temporary.write_text(json.dumps(self.data,ensure_ascii=False,indent=2),encoding='utf-8')
            temporary.replace(self.path)
        except OSError:
            self.failed=True

    def finish(self,state):
        self.data['state']=state
        self.data['flagged_segments']=sum(bool(s['flags']) for s in self.data['segments'])
        self.save()
