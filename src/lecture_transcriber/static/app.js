"use strict";
const $=id=>document.getElementById(id);
let csrf="",busy=false,currentJob=null,generation=0,connected=false;
function status(text,type=""){ $("status").textContent=text;$("status").className=type; }
function resetResult(){if(typeof resetNotes==="function")resetNotes();$("recovery-info").hidden=true;$("original-download").removeAttribute("href");$("recovery-download").removeAttribute("href");generation++;currentJob=null;$("result").textContent="";$("result").hidden=true;$("empty").hidden=false;$("download").hidden=true;$("download").removeAttribute("href");}
function controls(){const working=busy||(typeof noteBusy!=="undefined"&&noteBusy); $("file").disabled=working;$("hint").disabled=working||!connected;$("model").disabled=working||!connected;$("start").disabled=working||!connected||!$("model").value||!$("file").files.length;if(typeof noteControls==="function")noteControls(); }
async function api(path,options={}){
 const headers={...(options.headers||{})};
 if(options.method&&options.method!=="GET")headers["X-CSRF-Token"]=csrf;
 if(options.body&&!(options.body instanceof FormData)){headers["Content-Type"]="application/json";options.body=JSON.stringify(options.body);}
 const response=await fetch("/api/v1"+path,{...options,headers});
 const body=await response.json();
 if(!response.ok)throw new Error(body.error?.message||"요청을 처리하지 못했습니다.");
 return body;
}
let priorFile=null,priorHint="",priorModel="";
function rememberInputs(){priorFile=$("file").files;priorHint=$("hint").value;priorModel=$("model").value;}
$("hint").onchange=$("file").onchange=$("model").onchange=()=>{
 if(typeof allowDiscardNotes==="function"&&!allowDiscardNotes()){$("hint").value=priorHint;$("model").value=priorModel;if(priorFile)$("file").files=priorFile;return;}
 rememberInputs();resetResult();controls();status("준비되면 텍스트로 변환을 눌러 주세요.");
};
$("form").onsubmit=async event=>{
 event.preventDefault();if(busy||(typeof noteBusy!=="undefined"&&noteBusy))return;
 if(typeof allowDiscardNotes==="function"&&!allowDiscardNotes())return;
 resetResult();const version=generation;const file=$("file").files[0];
 if(!file)return;
 if(file.size>200*1024*1024){status("파일은 200MiB 이하로 선택해 주세요.","error");return;}
 busy=true;controls();status("녹음을 확인하고 있습니다.","busy");
 try{
  const form=new FormData();form.append("file",file);form.append("model_id",$("model").value);form.append("hint",$("hint").value);
  const job=await api("/transcriptions",{method:"POST",body:form});currentJob=job.job_id;
  status("텍스트로 변환 중입니다…","busy");
  while(currentJob===job.job_id&&generation===version){
   await new Promise(resolve=>setTimeout(resolve,1000));
   const result=await api("/transcriptions/"+job.job_id);
   if(generation!==version)return;
   if(result.state==="failed")throw new Error(result.error||"전사에 실패했습니다.");
   if(result.state==="completed"){
    const recovery=result.recovery||{};
    if(["applied","partial","needs_review","archive_failed"].includes(recovery.status)){
     $("recovery-info").hidden=false;
     $("recovery-status").textContent=recovery.status==="archive_failed"?"복구 기록을 저장하지 못해 원래 전사문을 유지했습니다.":recovery.status==="applied"?`의심 구간 ${recovery.applied}곳의 재전사를 반영했습니다. 전체 오류 해결을 뜻하지 않으므로 내용을 확인해 주세요.`:`재전사 ${recovery.applied||0}곳 반영 · ${recovery.unresolved||0}곳 확인 필요. 선택된 구간 기준이며 미해결 구간은 원래 내용을 유지했습니다.`;
     for(const [id,path] of [["original-download","original"],["recovery-download","recovery"]]){
      $(id).hidden=recovery.status==="archive_failed";
      $(id).href="/api/v1/transcriptions/"+job.job_id+"/"+path;
     }
    }
    if(result.text){
     $("result").textContent=result.text;$("result").hidden=false;$("empty").hidden=true;
     $("download").href="/api/v1/transcriptions/"+job.job_id+"/download";$("download").hidden=false;
     if(typeof loadNotes==="function")await loadNotes();
     status(result.diagnostics_status==="failed"?"변환이 완료되었습니다. 로컬 진단 기록 저장에 실패했습니다.":"변환이 완료되었습니다.");
    }else{status("인식된 발언이 없습니다. 음성이 있는 파일을 선택해 주세요.");}
    break;
   }
  }
 }catch(error){status(error.message||"연결이 끊겼습니다. 앱을 다시 열어 주세요.","error");}
 finally{busy=false;controls();}
};
$("shutdown").onclick=async()=>{
 if((busy||(typeof noteBusy!=="undefined"&&noteBusy))&&!confirm("진행 중인 전사를 멈추고 앱을 종료할까요?"))return;
 try{await api("/shutdown",{method:"POST",body:{confirmed:true}});generation++;currentJob=null;connected=false;controls();$("download").hidden=true;$("recovery-info").hidden=true;status("앱을 종료했습니다. 이 창을 닫으셔도 됩니다.");}catch(error){status(error.message,"error");}
};
window.addEventListener("beforeunload",event=>{if(busy||(typeof noteBusy!=="undefined"&&noteBusy)){event.preventDefault();event.returnValue="";}});
async function boot(){
 const token=new URLSearchParams(location.hash.slice(1)).get("token");history.replaceState(null,"",location.pathname);
 const session=token?await api("/session",{method:"POST",body:{launch_token:token}}):await api("/session");csrf=session.csrf_token;
 const models=await api("/models");$("model").replaceChildren();
 for(const model of models){const option=new Option(model.label+(model.available?"":" · 준비 필요"),model.id);option.disabled=!model.available;$("model").add(option);}
 const first=models.find(model=>model.available);
 if(first)$("model").value=first.id;else{$("model").value="";status("모델이 없습니다. 앱을 종료하고 prepare-models.cmd를 실행해 주세요.","error");}
 connected=true;rememberInputs();controls();if(typeof loadKeySettings==="function")loadKeySettings();if(first)status("녹음 파일과 모델을 선택해 주세요.");
}
boot().catch(error=>status(error.message,"error"));
