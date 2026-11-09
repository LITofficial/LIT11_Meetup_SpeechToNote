"use strict";
let noteBusy=false,noteOperation=null,noteList=[],noteSnapshot=null,noteView=null,noteEpoch=0;
const noteLabels={understand:"이해용",memorize:"암기용",practice:"문제풀이용"};
function noteStatus(text){$("note-status").textContent=text;}
function allowDiscardNotes(){return !noteList.length||confirm("새 입력 또는 재전사를 시작하면 기존 강의노트가 사라집니다. 필요한 PDF를 다운로드했나요? 계속할까요?");}
function resetNotes(){noteEpoch++;noteList=[];noteSnapshot=null;noteView=null;$("note-content").replaceChildren();$("note-pdf").hidden=true;$("note-warning").hidden=true;$("note-title").value="";noteStatus("전사를 완료한 뒤 노트를 만들 수 있습니다.");}
function noteControls(){
 for(const id of ["generate-note","save-key","delete-key","api-key"])$(id).disabled=busy||noteBusy||!connected;
 $("generate-note").disabled||=!noteSnapshot;
 $("save-title").disabled=!noteSnapshot||!connected;
 $("note-title").disabled=!noteSnapshot;
 $("cancel-note").hidden=!noteBusy;
 $("generate-note").textContent=noteList.some(n=>n.kind===$("note-kind").value)?"다시 생성":"강의노트 만들기";
}
function selectPanel(notes){$("notes-panel").hidden=!notes;$("transcript-panel").hidden=notes;$("notes-tab").setAttribute("aria-pressed",String(notes));$("transcript-tab").setAttribute("aria-pressed",String(!notes));}
$("notes-tab").onclick=()=>selectPanel(true);$("transcript-tab").onclick=()=>selectPanel(false);
async function loadKeySettings(){try{const r=await api("/notes/settings");$("key-status").textContent=r.key_configured?"키가 Windows 자격 증명 저장소에 보관되어 있습니다.":"저장된 API 키가 없습니다.";}catch(e){$("key-status").textContent=e.message;}}
$("save-key").onclick=async()=>{try{const key=$("api-key").value.trim();$("api-key").value="";await api("/notes/key",{method:"PUT",body:{key}});await loadKeySettings();}catch(e){$("key-status").textContent=e.message;}};
$("delete-key").onclick=async()=>{try{await api("/notes/key",{method:"DELETE"});await loadKeySettings();}catch(e){$("key-status").textContent=e.message;}};
async function loadNotes(){
 if(!currentJob)return;
 const expected=currentJob,epoch=noteEpoch;
 try{const r=await api(`/transcriptions/${expected}/notes`);if(currentJob!==expected||epoch!==noteEpoch)return;
 noteSnapshot=r.snapshot_id;noteList=r.notes;$("note-title").value=r.title;$("note-warning").hidden=!r.has_uncertainty;await showNote();noteControls();
 }catch(e){noteStatus(e.message);}
}
function element(tag,text,parent){const el=document.createElement(tag);el.textContent=text;parent.append(el);return el;}
function renderNote(note){
 const host=$("note-content");host.replaceChildren();element("h2",note.title,host);element("p",noteLabels[note.kind]+" 강의노트",host);
 function evidence(u){element("p",u.evidence,host).className="note-evidence";}
 for(const section of (note.kind==="practice"?[]:note.content.sections)){element("h3",section.heading,host);for(const b of section.blocks){
 evidence(b);
 if(b.type==="paragraph")element("p",b.text,host);
 else if(b.type==="list"){const ul=element("ul","",host);b.items.forEach(x=>element("li",x,ul));}
 else if(b.type==="qa"){element("p","질문: "+b.question,host);element("p","답: "+b.answer,host);}
 else {const wrap=element("div","",host);wrap.className="table-scroll";const table=element("table","",wrap);let row=element("tr","",element("thead","",table));b.columns.forEach(c=>element("th",c,row));const tbody=element("tbody","",table);b.rows.forEach(r=>{row=element("tr","",tbody);r.forEach(c=>element("td",c,row));});}
 }}
 if(note.content.questions.length){element("h3","문제",host);if(note.content.fewer_questions_reason)element("p",note.content.fewer_questions_reason,host);
 for(const q of note.content.questions){element("h4",q.id+". "+q.prompt,host);evidence(q);q.options.forEach(o=>element("p",o,host));}
 element("h3","정답과 해설",host);for(const a of note.content.answers){element("h4",a.question_id+". "+a.answer,host);element("p",a.explanation,host);evidence(a);}}
}
async function showNote(){
 const epoch=noteEpoch,kind=$("note-kind").value;const found=noteList.find(n=>n.kind===kind);noteView=null;$("note-pdf").hidden=true;$("note-content").replaceChildren();
 if(!found){if(!noteBusy)noteStatus(noteSnapshot?"학습 목적을 선택하고 강의노트를 만들어 주세요.":"전사를 완료한 뒤 노트를 만들 수 있습니다.");return;}
 const r=await api(`/notes/${found.id}`);if(epoch!==noteEpoch||kind!==$("note-kind").value)return;
 noteView=r;renderNote(r);$("note-pdf").hidden=false;if(!noteBusy)noteStatus("노트가 준비되었습니다. 내용을 확인해 주세요.");
}
$("note-kind").onchange=()=>{showNote().catch(e=>noteStatus(e.message));noteControls();};
$("save-title").onclick=async()=>{try{await api(`/transcriptions/${currentJob}/note-title`,{method:"PATCH",body:{title:$("note-title").value}});await showNote();}catch(e){noteStatus(e.message);}};
$("generate-note").onclick=async()=>{
 if(noteBusy||busy||!noteSnapshot)return;noteBusy=true;controls();const epoch=noteEpoch,kind=$("note-kind").value;
 noteStatus(noteLabels[kind]+" 노트를 만들고 있습니다… 최대 3분 기다립니다.");
 try{const op=await api(`/transcriptions/${currentJob}/notes`,{method:"POST",body:{kind,snapshot_id:noteSnapshot,request_id:crypto.randomUUID(),regenerate:noteList.some(n=>n.kind===kind)}});noteOperation=op.id;
 while(epoch===noteEpoch){await new Promise(r=>setTimeout(r,700));const state=await api(`/note-jobs/${op.id}`);if(state.state==="running")continue;
 if(state.state==="completed"){await loadNotes();noteStatus("노트가 완성되었습니다. 내용을 확인해 주세요.");}
 else noteStatus(state.error?.message||(state.state==="cancelled"?"생성을 취소했습니다. 이미 전송된 요청의 사용량은 발생할 수 있습니다.":"생성하지 못했습니다."));break;}
 }catch(e){noteStatus(e.message);}finally{noteBusy=false;noteOperation=null;controls();}
};
$("cancel-note").onclick=async()=>{if(!noteOperation)return;try{await api(`/note-jobs/${noteOperation}/cancel`,{method:"POST"});}catch(e){noteStatus(e.message);}};
$("note-pdf").onclick=async()=>{
 if(!noteView)return;const id=noteView.id,kind=noteView.kind;$("note-pdf").disabled=true;
 try{const r=await fetch(`/api/v1/notes/${id}/pdf`);if(!r.ok){const err=await r.json();throw new Error(err.error?.message||"PDF 다운로드에 실패했습니다.");}
 const url=URL.createObjectURL(await r.blob()),a=document.createElement("a");a.href=url;a.download="강의노트-"+noteLabels[kind]+".pdf";a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
 }catch(e){noteStatus(e.message);}finally{$("note-pdf").disabled=false;}
};
noteControls();

// Native modal dialog supplies focus containment and Escape dismissal.
const settingsMenu=$("settings-menu");
$("menu-toggle").onclick=()=>{
 settingsMenu.showModal();$("menu-toggle").setAttribute("aria-expanded","true");
 $("menu-close").focus();loadKeySettings();
};
$("menu-close").onclick=()=>settingsMenu.close();
settingsMenu.addEventListener("close",()=>{
 $("api-key").value="";$("menu-toggle").setAttribute("aria-expanded","false");$("menu-toggle").focus();
});
settingsMenu.addEventListener("click",event=>{
 const r=settingsMenu.getBoundingClientRect();
 if(event.target===settingsMenu&&(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom))settingsMenu.close();
});
