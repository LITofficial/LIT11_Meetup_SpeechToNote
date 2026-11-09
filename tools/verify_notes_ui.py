"""Synthetic UI/PDF check only: no real credentials or Gemini requests."""
import sys,time,threading,socket,json,copy
from pathlib import Path
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
from test_notes import Provider,Keys,sample
from lecture_transcriber.app import create_app
from lecture_transcriber.note_pdf import make_pdf
from lecture_transcriber.note_content import validate_content
import uvicorn
import pymupdf as fitz
from playwright.sync_api import sync_playwright

out=Path('.local-data/notes-validation');out.mkdir(parents=True,exist_ok=True)
sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1];origin=f'http://127.0.0.1:{port}'
provider=Provider();app=create_app(out/'server',origin,note_provider=provider,key_store=Keys())
id=str(uuid4());app.state.jobs.job=dict(job_id=id,state='completed',model_id='small',filename='합성 강의.wav',text='일관성 설명입니다.',segments=[dict(text='일관성 설명입니다.',start=0,end=10,source_duration=10,avg_logprob=-.2,compression_ratio=1)],completed=time.monotonic(),error=None,diagnostics_status='saved',recovery={'status':'not_needed'})
server=uvicorn.Server(uvicorn.Config(app,log_level='error'));thread=threading.Thread(target=lambda:server.run(sockets=[sock]),daemon=True);thread.start()
while not server.started:time.sleep(.02)
errors=[]
try:
 with sync_playwright() as pw:
  browser=pw.chromium.launch(channel='msedge',headless=True)
  page=browser.new_page(viewport={'width':1100,'height':900});page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto(origin+'/#token='+app.state.launch_token)
  page.wait_for_function('()=>connected === true')
  assert not page.locator('#settings-menu').is_visible()
  assert page.locator('#notes-panel #api-key').count()==0
  page.locator('#menu-toggle').click()
  assert page.locator('#settings-menu').is_visible()
  page.locator('#api-key').fill('synthetic-menu-test')
  page.locator('#save-key').click()
  page.wait_for_function('()=>document.getElementById("api-key").value === ""')
  page.screenshot(path=str(out/'settings-menu.png'),full_page=True)
  page.keyboard.press('Escape')
  assert not page.locator('#settings-menu').is_visible()
  assert page.locator('#menu-toggle').get_attribute('aria-expanded')=='false'
  page.set_viewport_size({'width':390,'height':844})
  page.locator('#menu-toggle').click()
  assert page.locator('#api-key').is_visible()
  page.locator('#menu-close').click()
  page.set_viewport_size({'width':1100,'height':900})

  page.evaluate('(id)=>{currentJob=id;return loadNotes();}',id)
  page.locator('#notes-tab').click()
  for kind in ('understand','memorize','practice'):
   provider.kind=kind
   page.locator('#note-kind').select_option(kind)
   page.locator('#generate-note').click()
   page.wait_for_function('()=>noteBusy === false && noteView !== null')
   page.locator('#note-title').fill('클라우드컴퓨팅 — 합성 검증')
   page.locator('#save-title').click()
   with page.expect_download() as download:
    page.locator('#note-pdf').click()
   download.value.save_as(out/f'{kind}.pdf')
   page.screenshot(path=str(out/f'{kind}.png'),full_page=True)
  assert len(provider.calls)==3
  page.locator('#note-kind').select_option('understand')
  page.wait_for_function('()=>noteView?.kind === "understand"')
  assert len(provider.calls)==3
  browser.close()
finally:
 server.should_exit=True;thread.join(5)
assert not errors,errors
sources={'s1':dict(start_seconds=2540,end_seconds=2580,text='합성 설명',uncertainty_codes=[])}
long=sample('memorize');long['sections'][0]['blocks'][1]['rows']=[['항목 '+str(i),'긴 설명과 한국어 줄바꿈을 확인합니다. '*12] for i in range(35)]
note=dict(id='synthetic',title='긴 표와 페이지 검증',kind='memorize',sources=sources,content=validate_content(long,'memorize',sources))
(out/'long-table.pdf').write_bytes(make_pdf(note))
for path in out.glob('*.pdf'):
 doc=fitz.open(path)
 for i,page in enumerate(doc):
  page.get_pixmap(matrix=fitz.Matrix(1,1)).save(out/f'{path.stem}-page-{i+1}.png')
  assert page.get_text().strip()
 print(path.name,len(doc),'pages')
print('Browser all three kinds + PDF downloads PASS; external API calls: 0')
