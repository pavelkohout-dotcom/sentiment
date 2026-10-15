"""python -m msm.rate_local --root . [--seed /private/results.json]
Only local Ollama. Writes derived cache, never titles or bodies. No model pulls.
"""
import argparse, json, time, urllib.request
from pathlib import Path
from datetime import datetime, timezone
from .core import digest, stamp, clean, analyze
from .collect import fetch, record
from .llama import VERSION, MODEL, MODEL_DIGEST, PROMPT, OPTIONS, SCHEMA, validate, cache_key
from .run import read, atomic

def api(path,data=None):
    req=urllib.request.Request('http://127.0.0.1:11434/api/'+path,data=None if data is None else json.dumps(data).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=180) as r:return json.load(r)

def rate(root,seed=None):
    tags=api('tags');model=next((m for m in tags['models'] if m['name']==MODEL),None)
    if not model or model['digest']!=MODEL_DIGEST:raise ValueError('Expected installed llama3 digest unavailable; no download attempted')
    path=root/'state/llama_scores.json';cache=read(path,{})
    if cache and (cache.get('model')!=VERSION or cache.get('model_digest')!=MODEL_DIGEST or cache.get('prompt_hash')!=digest(PROMPT)):raise ValueError('Cache version mismatch; preserve and migrate explicitly')
    cache.update(model=VERSION,model_digest=MODEL_DIGEST,prompt_hash=digest(PROMPT),options=OPTIONS)
    cache.setdefault('ratings',{});now=datetime.now(timezone.utc)
    config=read(root/'config.json',{});sources={s['id']:s for s in config['sources'] if s['enabled'] and s['kind']=='rss'}
    cases=[];errors=[]
    if seed:
        previous=read(seed,{})
        for r in previous.get('results',[]):
            if r.get('source') in sources and r.get('kind')!='synthetic': cases.append((r,sources[r['source']]))
    for src in sources.values():
        try:cases.extend((r,src) for r in fetch(src))
        except Exception as ex:errors.append({'source':src['id'],'error':type(ex).__name__})
    added=0;seen=set()
    for raw,src in cases:
        # Reuse production URL/date validation before sending any headline to Ollama.
        try:item=record(raw,src,now,lambda title:{'segments':['validation']})
        except (ValueError,TypeError,KeyError):continue
        key=cache_key(raw['title'])
        if key in seen: continue
        seen.add(key)
        metadata={'url':item['url'],'provider':src['id'],'published_at':item['published_at'],'signature':item['signature'],'rule_segments':analyze(raw['title'])['segments'],'kind':analyze(raw['title'])['kind']}
        if key in cache['ratings']:
            cache['ratings'][key].update(metadata)
            continue
        try:
            messages=[{'role':'system','content':PROMPT},{'role':'user','content':json.dumps({'headline':clean(raw['title'])})}]
            for attempt in range(2):
                response=api('chat',{'model':MODEL,'messages':messages,'stream':False,'format':SCHEMA,'options':OPTIONS,'keep_alive':'5m'})
                try:
                    answer=validate(json.loads(response['message']['content']));break
                except (ValueError,KeyError,TypeError):
                    if attempt: raise
                    messages.extend([{'role':'assistant','content':response['message']['content']},{'role':'user','content':'Correct the JSON only: score must be null when scope is other or unclear or direction is unclear. Otherwise positive=1, negative=-1, mixed=0. Keep your original scope and direction.'}])
            cache['ratings'][key]={'rating':answer,'rated_at':stamp(datetime.now(timezone.utc)),**metadata}
            cache['updated_at']=stamp(datetime.now(timezone.utc));atomic(path,cache);added+=1
            print(json.dumps({'added':added,'score':answer['score'],'scope':answer['scope']}),flush=True)
        except Exception as ex:errors.append({'headline_hash':key,'error':type(ex).__name__})
    cache['last_attempt']=stamp(datetime.now(timezone.utc));cache['errors']=errors
    if not any('source' in e for e in errors): cache['last_success']=cache['last_attempt']
    atomic(path,cache)
    print(json.dumps({'added':added,'cached':len(cache['ratings']),'errors':errors}),flush=True)
    return cache

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path('.'));p.add_argument('--seed',type=Path);a=p.parse_args();result=rate(a.root,a.seed)
    if result['errors']:raise SystemExit(1)
