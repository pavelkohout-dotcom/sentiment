"""RSS/Atom and opt-in Alpha Vantage ingestion with bounded requests."""
import json
from datetime import datetime
from zoneinfo import ZoneInfo
import os
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from urllib.parse import urlencode, urlsplit
from .core import clean, date, stamp, canonical, digest, signature, analyze

MAX_BYTES=4_000_000

class SourceError(ValueError):
    def __init__(self, code):
        self.code=code
        super().__init__(code)


def download(url):
    for attempt in range(3):
        try:
            req=urllib.request.Request(url, headers={'User-Agent':'MarketSentimentMonitor/1.0 (RSS metadata reader)', 'Accept':'application/rss+xml, application/atom+xml, application/json, application/xml;q=0.9'})
            with urllib.request.urlopen(req, timeout=20) as response:
                data=response.read(MAX_BYTES+1)
                if len(data)>MAX_BYTES: raise ValueError('response too large')
                return data
        except urllib.error.HTTPError as e:
            if e.code not in (429,500,502,503,504) or attempt==2:
                raise ValueError(f'HTTP {e.code}') from None
            time.sleep(min(10, 2**attempt))
        except (urllib.error.URLError, TimeoutError):
            if attempt==2: raise ValueError('network timeout or unavailable') from None
            time.sleep(2**attempt)
    raise ValueError('request failed')

def rss(data):
    if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
        raise ValueError('DTD/entity declarations are not supported')
    root=ET.fromstring(data)
    def local(tag): return tag.rsplit('}',1)[-1]
    if local(root.tag) not in ('rss','feed','RDF'): raise ValueError('not an RSS/Atom feed')
    result=[]
    for item in root.iter():
        if local(item.tag) not in ('item','entry'): continue
        fields={local(c.tag): c.text or '' for c in item}
        link=fields.get('link','')
        for c in item:
            if local(c.tag)=='link' and c.get('rel','alternate')=='alternate' and c.get('href'):
                link=c.get('href')
        result.append(dict(title=fields.get('title',''), url=link,
                           published_at=fields.get('pubDate') or fields.get('published') or fields.get('date') or fields.get('updated')))
    return result

def fetch(source):
    if source['kind']=='rss': return rss(download(source['url']))
    if source['kind']!='alphavantage': raise ValueError('unsupported source')
    key=os.getenv('ALPHAVANTAGE_API_KEY')
    if not key: raise SourceError('missing_api_key')
    # One request per configured interval, not one request per ticker.
    url='https://www.alphavantage.co/query?'+urlencode(dict(function='NEWS_SENTIMENT', topics='financial_markets', limit=200, sort='LATEST', apikey=key))
    obj=json.loads(download(url))
    if not isinstance(obj.get('feed'),list):
        # Inspect provider message in memory only; never persist raw messages/URLs.
        message=' '.join(str(obj.get(k,'')) for k in ('Information','Note','Error Message')).lower()
        if 'premium' in message or 'subscription' in message:
            raise SourceError('api_entitlement_required')
        if 'limit' in message or 'frequency' in message or 'quota' in message:
            raise SourceError('api_quota_exceeded')
        if 'apikey' in message or 'api key' in message:
            raise SourceError('api_key_rejected')
        raise SourceError('api_unexpected_response')
    return [dict(title=r.get('title',''),url=r.get('url',''),published_at=r.get('time_published')) for r in obj['feed']]

def record(raw, source, now):
    title=clean(raw['title'])
    if not title: raise ValueError('empty title')
    url=canonical(raw['url']); host=urlsplit(url).hostname
    if not any(host==d or host.endswith('.'+d) for d in source['domains']):
        raise ValueError('publisher not allowed')
    publication=raw['published_at']
    if source.get('naive_date_timezone'):
        # Only the publisher's explicitly configured legacy format gets a zone.
        try:
            naive=datetime.strptime(publication, '%Y-%m-%d %H:%M:%S')
        except (ValueError, TypeError):
            pass
        else:
            publication=naive.replace(tzinfo=ZoneInfo(source['naive_date_timezone'])).isoformat()
    published=date(publication)
    if published>now: raise ValueError('future publication date')
    analysis=analyze(title)
    if not analysis['segments']: return None
    # Persist derived fingerprints, never feed summaries or article bodies.
    # An explicit source rights decision is needed before exporting a title.
    return dict(id=digest(url),url=url, source=host, provider=source['id'],
                title=title if source.get('publish_titles',False) else None,
                published_at=stamp(published),first_seen=stamp(now), analysis=analysis,
                signature=signature(title), headline_hash=digest(title))
