import re
import pytest
from lecture_transcriber.formatting import sentence_layout

@pytest.mark.parametrize('source,expected',[
 ('앞부분\n\n그리고 뒷부분입니다.\n\n다음 문장입니다.', '앞부분 그리고 뒷부분입니다.\n\n다음 문장입니다.'),
 ('값은 3.14입니다. 버전 v1.2.3을 씁니다.', '값은 3.14입니다.\n\n버전 v1.2.3을 씁니다.'),
 ('Dr. Kim uses U.S. data. 끝입니다.', 'Dr. Kim uses U.S. data.\n\n끝입니다.'),
 ('example.com과 https://example.com/path를 봅니다. 끝.', 'example.com과 https://example.com/path를 봅니다.\n\n끝.'),
 ('“완료했나요?” 네! 다음입니다.끝입니다.', '“완료했나요?”\n\n네!\n\n다음입니다.\n\n끝입니다.'),
 ('끝맺음 없이\n\n이어지는 발언', '끝맺음 없이 이어지는 발언'),
 ('', ''),
])
def test_sentence_layout_preserves_content(source,expected):
 result=sentence_layout(source)
 assert result==expected
 assert re.sub(r'\s','',result)==re.sub(r'\s','',source)
 assert sentence_layout(result)==result
