"""Whitespace-only sentence layout; never correct or insert transcript text."""
import re

# Conservative exceptions: ambiguous abbreviations stay with the next phrase.
ABBREVIATIONS = {'mr.', 'mrs.', 'ms.', 'dr.', 'prof.', 'sr.', 'jr.', 'vs.', 'etc.', 'e.g.', 'i.e.', 'no.', 'fig.'}
ENDING = re.compile(r'''[.!?。！？]+["'”’」』)\]]*(?=\s|[가-힣]|$)''')


def sentence_layout(text):
    text = re.sub(r'\s+', ' ', text).strip()
    pieces = []
    start = 0
    for match in ENDING.finditer(text):
        end = match.end()
        token = text[:end].rsplit(' ', 1)[-1].rstrip('"\'”’」』)]')
        if match.group().startswith('.'):
            if token.lower() in ABBREVIATIONS or re.fullmatch(r'(?:[A-Za-z]\.)+', token):
                continue
        pieces.append(text[start:end].strip())
        start = end
    if text[start:].strip():
        pieces.append(text[start:].strip())
    return '\n\n'.join(piece for piece in pieces if piece)
