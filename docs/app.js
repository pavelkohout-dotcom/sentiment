'use strict';
let latest, history, segment='all';
const $=id=>document.getElementById(id);
const fmt=d=>new Date(d).toLocaleString('cs-CZ',{timeZone:'Europe/Prague',day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});
const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
const status={ok:'DOSTATEČNÝ VZOREK',low_coverage:'SLABÉ POKRYTÍ',no_data:'BEZ HODNOCENÝCH DAT'};
function draw(){
 const m=latest.metrics[segment];
 $('value').textContent=m.value===null?'—':m.value.toFixed(1);
 $('quality').textContent=status[m.status];
 $('needle').setAttribute('visibility',m.value===null?'hidden':'visible');
 $('needle').setAttribute('transform',`rotate(${m.value*1.8} 200 200)`);
 $('dial-title').textContent=`Sentiment ${m.value===null?'není dostupný':m.value+' ze 100'}; ${status[m.status]}`;
 $('momentum').textContent=m.momentum===null?'—':`${m.momentum>0?'+':''}${m.momentum.toFixed(1)} b.`;
 $('momentum-note').textContent=m.momentum_baseline?`Změna proti ${fmt(m.momentum_baseline)} (Praha).`:'Zatím chybí dostatečné pokrytí nebo platný bod starý 45–90 minut.';
 $('extreme').textContent={normal:'Bez extrému',panic:'Panika',euphoria:'Euforie',unavailable:'Nehodnoceno'}[m.extreme];
 for(const [id,key] of [['events','scored_events'],['sources','sources'],['articles','articles']])$(id).textContent=m[key];
 $('archive').textContent=latest.total_archived;
 const age=(Date.now()-Date.parse(latest.generated_at))/60000;
 const labels=[];
 if(age>45)labels.push(`ZASTARALÁ DATA · poslední běh před ${Math.floor(age/60)} h ${Math.floor(age%60)} min`);
 if(latest.collection_status!=='ok')labels.push('Sběr je omezený nebo offline');
 if(m.status!=='ok')labels.push('Nedostatek důkazů pro spolehlivé momentum a detekci extrémů');
 $('notice').textContent=labels.join(' · ')||'Sběr proběhl. Experimentální odhad z titulků; podrobnosti a stav zdrojů níže.';
 $('updated').textContent=`POSLEDNÍ BĚH ${fmt(latest.generated_at)} · PRAHA`;
 renderChart();renderNews();
}
function renderNews(){
 const items=latest.articles.filter(r=>(segment==='all'||r.analysis.segments.includes(segment))&&($('kind').value==='all'||r.analysis.kind===$('kind').value)&&(!$('scored-only').checked||r.analysis.score!==null));
 const host=$('news');host.replaceChildren();
 if(!items.length){host.append(el('p','V tomto filtru zatím nejsou zaznamenané zprávy.','empty'));return;}
 for(const r of items){
  const row=el('article',undefined,'news-row');const time=el('time',fmt(r.published_at));time.dateTime=r.published_at;row.append(time);
  const body=el('div');const a=el('a',r.title||`Zpráva · ${r.source}`);
  try{const u=new URL(r.url);if(['http:','https:'].includes(u.protocol)){a.href=u.href;a.target='_blank';a.rel='noopener noreferrer';}}catch{}
  body.append(a,el('small',`${r.analysis.kind==='commentary'?'Komentář':'Typ neurčen'} · ${r.source}${r.title?'':' · Titulek se veřejně neexportuje'}`));
  body.append(el('small',r.analysis.rules.length?`Pravidla: ${r.analysis.rules.join(', ')}${r.analysis.uncertain?' · podmíněný výrok':''}`:'Bez rozpoznaného pravidla; do skóre nezahrnuto.'));
  row.append(body,el('span',r.analysis.score===null?'—':`${r.analysis.score>0?'+':''}${r.analysis.score.toFixed(2)}`,'impact'));host.append(row);
 }
}
function renderChart(){
 const hours=Number($('range').value),end=Date.parse(latest.generated_at);
 const points=history.filter(h=>!hours||end-Date.parse(h.at)<=hours*3600000);
 const target=$('chart');target.replaceChildren();
 if(!points.length){target.append(el('p','Historie zatím není dostupná.','empty'));return;}
 const ns='http://www.w3.org/2000/svg',s=document.createElementNS(ns,'svg');s.setAttribute('viewBox','0 0 1000 230');s.setAttribute('role','img');s.setAttribute('aria-label',`Historie sentimentu, ${points.length} zaznamenaných běhů`);
 const add=(tag,attrs,text)=>{const n=document.createElementNS(ns,tag);for(const [k,v]of Object.entries(attrs))n.setAttribute(k,v);if(text)n.textContent=text;s.append(n);return n;};
 for(const v of [0,20,50,80,100]){const y=190-v*1.6;add('line',{x1:40,x2:980,y1:y,y2:y,stroke:'#42504a','stroke-dasharray':v===50?'none':'3 6'});add('text',{x:0,y:y+4},String(v));}
 const start=Date.parse(points[0].at),span=Math.max(1,end-start);let previous=null;
 for(const p of points){const m=p.metrics[segment];if(m.value===null){previous=null;continue;}
  const t=Date.parse(p.at),x=40+(t-start)/span*940,y=190-m.value*1.6;
  if(previous&&previous.model===p.model&&t-previous.t<=45*60000)add('line',{x1:previous.x,y1:previous.y,x2:x,y2:y,stroke:'#c4a76d','stroke-width':2});
  const circle=add('circle',{cx:x,cy:y,r:3,fill:m.status==='ok'?'#c4a76d':'#101e21',stroke:'#c4a76d'});const title=document.createElementNS(ns,'title');title.textContent=`${fmt(p.at)}: ${m.value} (${status[m.status]})`;circle.append(title);previous={t,x,y,model:p.model};
 }
 add('text',{x:40,y:222},fmt(points[0].at));add('text',{x:980,y:222,'text-anchor':'end'},fmt(latest.generated_at));target.append(s);
}
async function load(){
 try{
  const responses=await Promise.all(['latest','history'].map(n=>fetch(`data/${n}.json`,{cache:'no-store'})));
  if(responses.some(r=>!r.ok))throw Error('Data nejsou dostupná');
  [latest,history]=await Promise.all(responses.map(r=>r.json()));
  $('source-list').replaceChildren();
  for(const source of latest.sources){const row=el('div',undefined,'source-row');row.append(el('strong',source.name),el('span',({ok:'Dostupný',error:'Chyba sběru',throttled:'Čeká na API interval',offline:'Offline'})[source.status]||source.status),el('span',source.last_success?`Úspěch ${fmt(source.last_success)}`:'Dosud bez úspěšného sběru'));$('source-list').append(row);}
  draw();
 }catch(e){$('notice').textContent='Data se nepodařilo načíst. Otevřete dashboard přes HTTP server; zkontrolujte JSON export a workflow. Zobrazené hodnoty mohou pocházet z předchozího načtení.';}
}
document.querySelectorAll('[data-segment]').forEach(b=>b.addEventListener('click',()=>{segment=b.dataset.segment;document.querySelectorAll('[data-segment]').forEach(x=>{x.classList.toggle('active',x===b);x.setAttribute('aria-pressed',String(x===b));});if(latest)draw();}));
$('range').addEventListener('change',()=>{if(latest)renderChart();});$('kind').addEventListener('change',()=>{if(latest)renderNews();});$('scored-only').addEventListener('change',()=>{if(latest)renderNews();});
load();setInterval(load,60000);
