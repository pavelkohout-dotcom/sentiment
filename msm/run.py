"""Run: python -m msm.run [--root .] [--offline]."""
import argparse
import json
import os
from pathlib import Path
from datetime import datetime, timezone
from .core import VERSION, date, stamp, metrics, analyze, canonical, digest
from .llama import VERSION as LLAMA_VERSION, cached_analysis, analysis_from_rating, validate_cache
from .collect import fetch, record
from urllib.parse import urlsplit


def read(path, default):
    return json.loads(path.read_text()) if path.exists() else default

def atomic(path, obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    os.replace(temp,path)

def run(root, offline=False, now=None, fetcher=fetch):
    now=now or datetime.now(timezone.utc)
    config=read(root/'config.json',{})
    model=config.get('analysis_model',VERSION)
    if model not in (VERSION, LLAMA_VERSION): raise ValueError('unsupported model')
    cache=validate_cache(read(root/'state/llama_scores.json',{})) if model==LLAMA_VERSION else {}
    state=read(root/'state/store.json',{'schema':1,'records':{},'sources':{}})
    # Stop on damaged state/history; never silently overwrite history.
    if state.get('schema')!=1 or not isinstance(state['records'],dict): raise ValueError('invalid state')
    history=read(root/'docs/data/history.json',[])
    reports=[]; new=0
    for src in config['sources']:
        if not src['enabled']: continue
        prior=state['sources'].get(src['id'],{})
        report=dict(id=src['id'],name=src['name'],terms=src['terms'],last_success=prior.get('last_success'),received=0,accepted=0,rejected=0)
        if model==LLAMA_VERSION: report['pending_llama']=0
        def analyzer(title):
            if model!=LLAMA_VERSION: return analyze(title)
            result=cached_analysis(title,cache)
            if result is None:
                report['pending_llama']+=1
                return dict(segments=[])
            return result
        recent=prior.get('last_attempt') and (now-date(prior['last_attempt'])).total_seconds()<src.get('min_interval_minutes',0)*60
        if offline or recent:
            report['status']='offline' if offline else ('error' if prior.get('status')=='error' else 'throttled')
        else:
            report['last_attempt']=stamp(now)
            try:
                rows=fetcher(src); report['received']=len(rows)
                for raw in rows:
                    try: item=record(raw,src,now,analyzer)
                    except (ValueError,KeyError,TypeError):
                        report['rejected']+=1; continue
                    if item is None: continue
                    report['accepted']+=1
                    if item['id'] not in state['records']:
                        state['records'][item['id']]=item; new+=1
                    elif state['records'][item['id']]['analysis']['model'] != item['analysis']['model']:
                        item['first_seen']=state['records'][item['id']]['first_seen']
                        state.setdefault('model_revisions',[]).append(state['records'][item['id']])
                        state['records'][item['id']]=item
                    # Re-score on model change only; preserve prior derived record in revisions.
                report.update(status='ok',last_success=stamp(now))
            except Exception as e:
                # Do not persist exception text: libraries can include URLs containing API keys.
                report.update(status='error',error_type=type(e).__name__)
                safe_code=getattr(e,'code',None)
                if safe_code in ('missing_api_key','api_entitlement_required','api_quota_exceeded','api_key_rejected','api_unexpected_response'):
                    report['error_code']=safe_code
            state['sources'][src['id']]={**prior,**report}
        reports.append(report)
    if model==LLAMA_VERSION:
        # Restore locally observed RSS items even if they rotated out of a short feed.
        providers={s['id']:s for s in config['sources'] if s['enabled']}
        for headline_hash, rating in cache.get('ratings',{}).items():
            if 'signature' not in rating or rating.get('provider') not in providers: continue
            src=providers[rating['provider']];url=canonical(rating['url']);host=urlsplit(url).hostname
            if not any(host==d or host.endswith('.'+d) for d in src['domains']): raise ValueError('cached publisher not allowed')
            if date(rating['published_at'])>now: continue
            analysis=analysis_from_rating(rating,{'segments':rating.get('rule_segments',[]),'kind':rating.get('kind','unknown')})
            key=digest(url)
            if key not in state['records'] and analysis['segments']:
                state['records'][key]=dict(id=key,url=url,source=host,provider=src['id'],title=None,published_at=rating['published_at'],first_seen=rating['rated_at'],analysis=analysis,signature=rating['signature'],headline_hash=headline_hash)
                new+=1
        for key, old in list(state['records'].items()):
            rating=cache.get('ratings',{}).get(old.get('headline_hash'))
            if rating and old['analysis']['model']!=model:
                analysis=analysis_from_rating(rating,old['analysis'])
                state.setdefault('model_revisions',[]).append(old)
                state['records'][key]={**old,'analysis':analysis}
    records=list(state['records'].values())
    values={k:metrics(records,now,history,config,None if k=='all' else k) for k in ('all','nasdaq100','sp500')}
    status='offline' if offline else 'ok' if reports and all(r['status'] in ('ok','throttled') for r in reports) else 'degraded'
    # A scheduled attempt is a snapshot even when fetch fails; acquisition status is separate.
    snapshot=dict(at=stamp(now),model=model,collection_status=status,metrics=values)
    if not history or history[-1]['at']!=snapshot['at']: history.append(snapshot)
    active=[r for r in records if r['analysis']['model']==model and r['analysis']['segments'] and 0<=(now-date(r['published_at'])).total_seconds()<=config['window_hours']*3600]
    latest=dict(schema_version=1,generated_at=stamp(now),model=model,collection_status=status,
                window_hours=config['window_hours'],metrics=values,sources=reports,new_articles=new,
                total_archived=len(records),articles=[{k:v for k,v in r.items() if k not in ('signature','headline_hash')} for r in sorted(active,key=lambda r:r['published_at'],reverse=True)],
                methodology={'type':'local_llama_headline_impact' if model==LLAMA_VERSION else 'deterministic_headline_impact_proxy','half_life_hours':config['half_life_hours'],
                 'min_events':config['min_events'],'min_sources':config['min_sources'],
                 'scope':'Explicit index/macro references and a limited large-cap watchlist; not complete index constituents.',
                 'titles':'Hidden unless publisher rights explicitly configured. No article bodies collected.'})
    if model==LLAMA_VERSION:
        latest['llama']={'last_rated_at':cache.get('updated_at'),'last_refresh_at':cache.get('last_success'),'errors':len(cache.get('errors',[])),'pending':sum(r.get('pending_llama',0) for r in reports),'model_digest':cache.get('model_digest'),'scale':{'negative':-1,'mixed':0,'positive':1,'unclear':None},'execution':'Ollama on owner Mac; cached ratings published to GitHub'}
        latest['methodology']['scope']='Llama relevance and direction; existing index routing; additional US companies included only in US MARKET. Not complete index membership.'
    atomic(root/'state/store.json',state)
    atomic(root/'docs/data/history.json',history)
    atomic(root/'docs/data/latest.json',latest)
    # Complete machine-readable derived article archive, never automatically pruned.
    atomic(root/'docs/data/articles.json',[{k:v for k,v in r.items() if k not in ('signature','headline_hash')} for r in records])
    atomic(root/'docs/data/revisions.json',[{k:v for k,v in r.items() if k not in ('signature','headline_hash')} for r in state.get('model_revisions',[])])
    return latest

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--root',type=Path,default=Path('.')); p.add_argument('--offline',action='store_true'); a=p.parse_args()
    result=run(a.root,a.offline)
    print(json.dumps({k:result[k] for k in ('generated_at','collection_status','new_articles','total_archived','metrics')},indent=2))
