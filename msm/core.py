"""Deterministic, versioned headline impact proxy. No article-body retrieval."""
import hashlib
import html
import math
import re
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

VERSION = 'impact-rules-1.0.2'
UTC = timezone.utc

def stamp(dt):
    return dt.astimezone(UTC).isoformat(timespec='seconds').replace('+00:00', 'Z')

def date(value):
    if not value:
        raise ValueError('missing publication date')
    if re.fullmatch(r'\d{8}T\d{6}',value):
        return datetime.strptime(value, '%Y%m%dT%H%M%S').replace(tzinfo=UTC)
    try:
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        try:
            dt = parsedate_to_datetime(value)
        except (ValueError, TypeError):
            dt = datetime.strptime(value, '%Y%m%dT%H%M%S').replace(tzinfo=UTC)
    if dt.tzinfo is None:
        raise ValueError('publication date has no timezone')
    return dt.astimezone(UTC)

def clean(text):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]*>', ' ', text or ''))).strip()

def canonical(url):
    p = urlsplit(url.strip())
    if p.scheme not in ('http', 'https') or not p.hostname or p.username or p.password:
        raise ValueError('unsafe article URL')
    query = [(k,v) for k,v in parse_qsl(p.query) if not k.lower().startswith(('utm_', 'mod', 'ref', 'fbclid', 'gclid', 'cmp'))]
    return urlunsplit(('https', p.netloc.lower(), p.path.rstrip('/') or '/', urlencode(sorted(query)), ''))

def digest(s):
    return hashlib.sha256(s.encode()).hexdigest()

# Only explicit US-market/macroeconomic references or a documented large-cap watchlist.
# No claim of complete, point-in-time constituent coverage.
NASDAQ = r'\b(nasdaq(?:-100)?|qqq|nvidia|nvda|apple|aapl|microsoft|msft|amazon|amzn|alphabet|google|googl|meta|tesla|tsla|broadcom|avgo|amd|intel|netflix|nflx|chip stocks|chipmakers|semiconductors)\b'
SP = r'\b(s&p\s*500|s and p 500|spx|spy|jpmorgan|jpm|goldman sachs|walmart|exxon|unitedhealth|berkshire)\b'
BROAD = r'\b(wall street|u\.?s\.? (stocks|equities|economy|inflation|jobs|markets)|american (stocks|equities)|fed|federal reserve|powell|treasury yields)\b'
POS = r'(?:rise[sn]?|rising|rall(?:y|ies|ied)|surge[sd]?|gain[sd]?|jump[sd]?|soar[sd]?|rebound[sd]?|climb[sd]?|higher|record high)'
NEG = r'(?:fall[sn]?|falling|fell|slid(?:e[sd]?|ing)|slump[sd]?|plunge[sd]?|drop[spd]*|tumble[sd]?|sink[sd]?|sank|lower|sell.?off|crash(?:es|ed)?)'
# Bind a movement to its subject; do not scan across unrelated clauses.
MOVE = r'\s+(?:(?:is|are|was|were|has|have|been|may|might|could|will|now|sharply|slightly|again|unexpectedly)\s+){0,3}'
EQUITY = r'\b(?:stocks?|shares?|equities|nasdaq(?:-100)?|s&p\s*500|wall street|futures)\b'
RULES = [
 ('equity_up', rf'{EQUITY}{MOVE}{POS}\b', .7),
 ('equity_down', rf'{EQUITY}{MOVE}{NEG}\b', -.7),
 ('earnings_beat', r'\b(?:beats?|tops?) (?:\w+ ){0,2}(?:expectations|estimates|forecasts)\b', .6),
 ('earnings_miss', r'\b(?:miss(?:es|ed)?|below) (?:\w+ ){0,2}(?:expectations|estimates|forecasts)\b', -.6),
 ('guidance_up', r'\b(?:raises?|raised|boosts?) (?:\w+ ){0,2}(?:guidance|outlook)\b', .65),
 ('guidance_down', r'\b(?:cuts?|lowers?|slashed) (?:\w+ ){0,2}(?:guidance|outlook)\b', -.65),
 ('inflation_up', rf'\binflation{MOVE}(?:{POS}|accelerates|sticky|hotter)\b|\b(?:sticky|hot|hotter|higher|rising) inflation\b', -.5),
 ('inflation_down', r'\binflation\s+(?:(?:is|was|has|been)\s+){0,2}(?:falls?|falling|fell|drops?|dropped|declines?|declined|cools?|cooled|eases?|eased)\b|\b(?:lower|cooler|falling) inflation\b', .5),
 ('yields_up', rf'\b(?:treasury |bond )?yields{MOVE}{POS}\b|\b(?:rising|higher) (?:treasury |bond )?yields\b', -.4),
 ('yields_down', rf'\b(?:treasury |bond )?yields{MOVE}{NEG}\b|\b(?:falling|lower) (?:treasury |bond )?yields\b', .35),
 ('rate_hike', r'\b(?:fed|federal reserve).{0,25}\b(?:raises|hikes) (?:interest )?rates\b', -.5),
 ('rate_cut', r'\b(?:fed|federal reserve).{0,25}\bcuts (?:interest )?rates\b', .4),
 ('recession', r'\b(recession|bankruptcy|defaults|bank failure)\b', -.6),
]

def analyze(title):
    t = clean(title).lower()
    segments = []
    if re.search(NASDAQ, t):
        segments.append('nasdaq100')
        # Shared large-cap themes can affect both indices; this is not a membership claim.
        if re.search(NASDAQ.replace('nasdaq(?:-100)?|qqq|', ''), t): segments.append('sp500')
    if re.search(SP, t) and 'sp500' not in segments: segments.append('sp500')
    if re.search(BROAD, t): segments = ['nasdaq100', 'sp500']
    hits = []
    uncertain = bool(re.search(r'\b(may|might|could|if|risk|risks|fears|forecast|predicts)\b|\?', t))
    for name, pattern, value in RULES:
        m = re.search(pattern, t)
        if not m: continue
        # Abstain on nearby negation instead of naively reversing a financial claim.
        context = t[max(0, m.start()-24):m.end()]
        if re.search(r"\b(no|not|never|without|unlikely|fails? to|doesn.t|didn.t)\b", context):
            continue
        hits.append((name, value))
    mixed = any(v>0 for _,v in hits) and any(v<0 for _,v in hits)
    score = max(-1., min(1., sum(v for _,v in hits))) if hits else None
    if score is not None and uncertain: score *= .5
    confidence = 0 if not hits else (.35 if uncertain or mixed else .65)
    # This is rule evidence strength, NOT calibrated probability.
    kind = 'commentary' if re.search(r'\b(opinion|commentary|column|editorial|my view)\b', t) else 'unknown'
    return dict(segments=segments, score=score, confidence=confidence,
                rules=[n for n,_ in hits], uncertain=uncertain, mixed=mixed, kind=kind, model=VERSION)

STOP = set('the a an and or to of in on for as with after before at by is are be it its from this that says said'.split())

def signature(title):
    return sorted({digest(t)[:16] for t in re.findall(r'[a-z0-9]+', clean(title).lower()) if t not in STOP})

def same_event(a, b):
    if a['url'] == b['url']: return True
    if abs((date(a['published_at'])-date(b['published_at'])).total_seconds()) > 18*3600: return False
    # Opposite-direction follow-up headlines are separate events.
    sa, sb = a['analysis']['score'], b['analysis']['score']
    if sa is not None and sb is not None and sa*sb<0: return False
    x,y = set(a['signature']),set(b['signature'])
    return len(x&y) >= 4 and len(x&y)/max(1,len(x|y)) >= .72

def cluster(records):
    groups=[]
    for r in sorted(records, key=lambda r:(r['published_at'],r['id'])):
        group = next((g for g in groups if same_event(r,g[0])), None)
        if group is None: groups.append([r])
        else: group.append(r)
    return groups

def metrics(records, now, history, config, segment=None):
    active=[r for r in records if r['analysis']['model']==VERSION and 0 <= (now-date(r['published_at'])).total_seconds() <= config['window_hours']*3600
            and (not segment or segment in r['analysis']['segments'])]
    groups=cluster(active)
    scored=[g for g in groups if any(r['analysis']['score'] is not None for r in g)]
    # Each event contributes once, irrespective of syndicated copy count.
    per_source={}
    for g in scored:
        r=next(r for r in g if r['analysis']['score'] is not None)
        a=r['analysis']; age=(now-date(r['published_at'])).total_seconds()/3600
        w=2**(-age/config['half_life_hours'])*a['confidence']*(.6 if a['kind']=='commentary' else 1)
        per_source.setdefault(r['source'],[]).append((a['score'],w))
    source_means=[sum(s*w for s,w in v)/sum(w for _,w in v) for v in per_source.values()]
    value=round(50+50*sum(source_means)/len(source_means),2) if source_means else None
    enough=len(scored)>=config['min_events'] and len(per_source)>=config['min_sources']
    key=segment or 'all'
    candidates=[h for h in history if h.get('model')==VERSION and 45*60 <= (now-date(h['at'])).total_seconds() <= 90*60
                and h['metrics'][key]['status']=='ok' and h['metrics'][key]['value'] is not None]
    previous=min(candidates,key=lambda h:abs((now-date(h['at'])).total_seconds()-3600)) if candidates else None
    momentum=round(value-previous['metrics'][key]['value'],2) if enough and previous else None
    return dict(value=value, status='no_data' if value is None else ('ok' if enough else 'low_coverage'),
                events=len(groups), scored_events=len(scored), articles=len(active), sources=len(per_source),
                momentum=momentum, momentum_baseline=previous['at'] if momentum is not None else None,
                extreme=('euphoria' if value>=80 else 'panic' if value<=20 else 'normal') if enough else 'unavailable')
