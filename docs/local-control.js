'use strict';
(() => {
 const endpoint='http://127.0.0.1:8766';
 const button=document.getElementById('local-refresh');
 const message=document.getElementById('local-refresh-status');
 const setup=document.getElementById('local-refresh-setup');
 let helper=null, watch=null, timer=null, handshake=false, terminal=false;
 function release(){button.disabled=false;clearInterval(watch);clearTimeout(timer);}
 window.addEventListener('message',event=>{
  if(event.origin!==endpoint||event.source!==helper||!event.data||event.data.type!=='msm-status'||terminal)return;
  clearTimeout(timer);
  const state=event.data;
  message.textContent=state.configured?state.message:'V místním okně nejdřív jednorázově připojte GitHub.';
  setup.hidden=state.configured;
  if(!handshake){handshake=true;helper.postMessage({type:'msm-refresh'},endpoint);return;}
  if(!state.running&&['done','published','error'].includes(state.phase)){
   terminal=true;release();
   if(state.phase==='done'&&typeof load==='function')load();
  }
 });
 button.addEventListener('click',()=>{
  release();handshake=false;terminal=false;
  helper=window.open(endpoint+'/#refresh','msm-local-refresh','popup,width=760,height=780');
  if(!helper){message.textContent='Povolte otevření místního ovládacího okna, nebo použijte odkaz na nastavení.';setup.hidden=false;return;}
  button.disabled=true;setup.hidden=true;
  message.textContent='Otevírám ovládání na tomto Macu…';
  timer=setTimeout(()=>{message.textContent='Místní pomocník neodpovídá. Spusťte jej na tomto Macu a zkuste tlačítko znovu.';setup.hidden=false;release();},10000);
  watch=setInterval(()=>{if(helper.closed){release();message.textContent='Místní okno bylo zavřeno. Pokud aktualizace už běží, dokončí se na pozadí. Průběh zobrazíte opětovným kliknutím.';}},1000);
 });
})();
