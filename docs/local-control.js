'use strict';
(() => {
 const endpoint='http://127.0.0.1:8766';
 const button=document.getElementById('local-refresh');
 const message=document.getElementById('local-refresh-status');
 const setup=document.getElementById('local-refresh-setup');
 let polling=false;
 const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
 async function call(path,options={}){
  const response=await fetch(endpoint+path,{...options,cache:'no-store',signal:AbortSignal.timeout(10000)});
  if(!response.ok&&response.status!==409&&response.status!==428)throw Error('local service');
  return {code:response.status,data:await response.json()};
 }
 function show(state){
  message.textContent=state.message;
  setup.hidden=state.configured;
  if(!state.configured)message.textContent='Nejdřív jednorázově připojte GitHub v nastavení tohoto Macu.';
 }
 button.addEventListener('click',async()=>{
  if(polling)return;
  polling=true;button.disabled=true;setup.hidden=true;
  message.textContent='Připojuji se k tomuto Macu… Případně povolte prohlížeči přístup k místní síti.';
  try{
   let {data:state}=await call('/status');show(state);
   if(!state.configured)return;
   if(!state.running){
    const result=await call('/refresh',{method:'POST',headers:{'Content-Type':'application/json','X-MSM-Token':state.nonce},body:'{}'});
    state=result.data;show(state);
   }
   while(state.running){
    await delay(3000);
    state=(await call('/status')).data;show(state);
   }
   if(state.phase==='done'&&typeof load==='function')await load();
  }catch{
   message.textContent='Místní pomocník není dostupný nebo prohlížeč nepovolil připojení. Tlačítko funguje jen na nastaveném Macu. Zkuste otevřít místní nastavení a aktualizaci spustit tam.';
   setup.hidden=false;
  }finally{polling=false;button.disabled=false;}
 });
})();
