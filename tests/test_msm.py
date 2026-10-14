"""Synthetic fixtures only; never exported as observed market data."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock
from msm.core import VERSION, analyze, canonical, cluster, date, metrics, stamp
from msm.collect import record, rss, fetch, download
from msm.run import run
NOW=datetime(2026,1,10,12,tzinfo=timezone.utc)
CFG={'window_hours':24,'half_life_hours':6,'min_events':5,'min_sources':2}
SRC={'id':'test','name':'Test','kind':'rss','domains':['example.com'],'publish_titles':False,'enabled':True,'terms':'https://example.com/terms'}
def rec(title='US stocks rally after earnings beat',url='https://example.com/1',hours=1):
    return record({'title':title,'url':url,'published_at':stamp(NOW-timedelta(hours=hours))},SRC,NOW)
class CoreTests(unittest.TestCase):
    def test_canonical(self):
        self.assertEqual(canonical('http://EXAMPLE.com/a?utm_source=x&id=3#top'),'https://example.com/a?id=3')
        self.assertNotEqual(canonical('https://example.com/?id=1'),canonical('https://example.com/?id=2'))
    def test_unsafe_url(self):
        for url in ['javascript:alert(1)','file:///tmp/x','https://user:pass@example.com']:
            with self.assertRaises(ValueError): canonical(url)
    def test_direction(self):
        self.assertGreater(analyze('US stocks rally after earnings beat')['score'],0)
        self.assertLess(analyze('Nasdaq stocks plunge after earnings miss')['score'],0)
    def test_negation(self):
        self.assertIsNone(analyze('US stocks do not rise today')['score'])
        self.assertIsNone(analyze('Fed will not hike rates')['score'])
    def test_inflation(self):
        self.assertLess(analyze('US inflation rises again')['score'],0)
        self.assertGreater(analyze('US inflation falls again')['score'],0)
    def test_no_evidence(self):self.assertIsNone(analyze('Apple holds annual meeting')['score'])
    def test_conditional(self):
        self.assertLess(abs(analyze('US stocks could rally')['score']),abs(analyze('US stocks rally')['score']))
    def test_relevance(self):
        self.assertEqual(analyze('Local football stocks up on new jerseys')['segments'],[])
        self.assertEqual(set(analyze('Fed cuts rates')['segments']),{'nasdaq100','sp500'})
    def test_type(self):
        self.assertEqual(analyze('Opinion: Nasdaq stocks rally')['kind'],'commentary')
        self.assertEqual(analyze('Nasdaq stocks rally')['kind'],'unknown')
    def test_private_titles(self):
        r=rec();self.assertIsNone(r['title']);self.assertNotIn('summary',r)
    def test_bad_dates(self):
        with self.assertRaises(ValueError):rec(hours=-1)
        with self.assertRaises(ValueError):date('')
        with self.assertRaises(ValueError):date('2026-01-01')
    def test_dedup(self):self.assertEqual(len(cluster([rec(),rec(url='https://example.com/2')])),1)
    def test_opposite_news(self):
        self.assertEqual(len(cluster([rec('US stocks rally after Fed policy decision today'),rec('US stocks fall after Fed policy decision today','https://example.com/2')])),2)
    def test_old_event(self):self.assertEqual(len(cluster([rec(),rec(url='https://example.com/2',hours=23)])),2)
    def test_no_data(self):
        m=metrics([],NOW,[],CFG);self.assertIsNone(m['value']);self.assertEqual(m['extreme'],'unavailable')
    def test_unknown_excluded(self):
        m=metrics([rec('Apple holds annual meeting')],NOW,[],CFG)
        self.assertEqual(m['events'],1);self.assertEqual(m['scored_events'],0);self.assertIsNone(m['value'])
    def test_low_coverage(self):
        m=metrics([rec()],NOW,[],CFG)
        self.assertEqual(m['status'],'low_coverage');self.assertIsNone(m['momentum']);self.assertEqual(m['extreme'],'unavailable')
    def test_expiration(self):self.assertIsNone(metrics([rec(hours=25)],NOW,[],CFG)['value'])
    def test_duplicate_no_extra_weight(self):
        self.assertEqual(metrics([rec()],NOW,[],CFG)['value'],metrics([rec(),rec(url='https://example.com/2')],NOW,[],CFG)['value'])
    def test_equal_sources(self):
        b=rec('Nasdaq stocks plunge','https://example.com/2');b['source']='other.example'
        self.assertEqual(metrics([rec(),b],NOW,[],CFG)['value'],50)
    def test_momentum(self):
        c={**CFG,'min_events':1,'min_sources':1}
        h={'model':VERSION,'at':stamp(NOW-timedelta(hours=1)),'metrics':{'all':{'value':55,'status':'ok'}}}
        m=metrics([rec()],NOW,[h],c);self.assertEqual(m['momentum'],30);self.assertEqual(m['extreme'],'euphoria')
        h['at']=stamp(NOW-timedelta(hours=3));self.assertIsNone(metrics([rec()],NOW,[h],c)['momentum'])
    def test_segments(self):
        self.assertIsNone(metrics([rec('Nasdaq rises')],NOW,[],CFG,'sp500')['value'])
        self.assertIn('sp500',analyze('Nvidia shares rise')['segments'])
class AdapterTests(unittest.TestCase):
    def test_rss(self):
        a=rss(b'<rss><channel><item><title>US stocks rise</title><link>https://example.com/1</link><pubDate>Sat, 10 Jan 2026 10:00:00 GMT</pubDate></item></channel></rss>')
        self.assertEqual(a[0]['title'],'US stocks rise')
    def test_atom(self):
        a=rss(b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Test</title><link href="https://example.com/a"/><published>2026-01-10T10:00:00Z</published></entry></feed>')
        self.assertEqual(a[0]['url'],'https://example.com/a')
    def test_bad_xml(self):
        for data in [b'<!DOCTYPE rss><rss/>',b'<html/>',b'<rss']:
            with self.assertRaises(Exception):rss(data)
    def test_unapproved_domain(self):
        with self.assertRaises(ValueError):rec(url='https://example.com.attacker.org/a')
    def test_av_quota(self):
        with patch.dict('os.environ',{'ALPHAVANTAGE_API_KEY':'TEST-SECRET'}),patch('msm.collect.download',return_value=b'{"Information":"quota"}'):
            with self.assertRaisesRegex(ValueError,'quota'):fetch({'kind':'alphavantage'})
    def test_av_missing_key(self):
        with patch.dict('os.environ',{},clear=True):
            with self.assertRaises(ValueError):fetch({'kind':'alphavantage'})
    def test_av_parse(self):
        with patch.dict('os.environ',{'ALPHAVANTAGE_API_KEY':'TEST-SECRET'}),patch('msm.collect.download',return_value=b'{"feed":[{"title":"US stocks rally","url":"https://example.com/1","time_published":"20260110T100000"}]}'):
            self.assertIsNotNone(record(fetch({'kind':'alphavantage'})[0],SRC,NOW))
    def test_retry(self):
        import urllib.error
        response=MagicMock();response.__enter__.return_value.read.return_value=b'ok'
        with patch('urllib.request.urlopen',side_effect=[urllib.error.HTTPError('https://example.com',503,'error',{},None),response]) as request,patch('time.sleep'):
            self.assertEqual(download('https://example.com'),b'ok');self.assertEqual(request.call_count,2)
class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        (self.root/'config.json').write_text(json.dumps({**CFG,'sources':[SRC]}))
        self.rows=[{'title':'US stocks rally','url':'https://example.com/1','published_at':stamp(NOW-timedelta(hours=1))}]
    def tearDown(self):self.tmp.cleanup()
    def test_idempotence_history(self):
        a=run(self.root,now=NOW,fetcher=lambda s:self.rows)
        b=run(self.root,now=NOW+timedelta(minutes=15),fetcher=lambda s:self.rows)
        self.assertEqual(a['new_articles'],1);self.assertEqual(b['new_articles'],0);self.assertEqual(b['total_archived'],1)
        self.assertEqual(len(json.loads((self.root/'docs/data/history.json').read_text())),2)
        for p in [self.root/'state/store.json',self.root/'docs/data/articles.json']:self.assertNotIn('US stocks rally',p.read_text())
    def test_failure_preserves_and_redacts(self):
        run(self.root,now=NOW,fetcher=lambda s:self.rows)
        def fail(s):raise ValueError('https://api?apikey=TOPSECRET')
        d=run(self.root,now=NOW+timedelta(minutes=15),fetcher=fail)
        self.assertEqual(d['collection_status'],'degraded');self.assertEqual(d['total_archived'],1)
        self.assertNotIn('TOPSECRET',(self.root/'state/store.json').read_text());self.assertEqual(d['sources'][0]['last_success'],stamp(NOW))
    def test_bad_item(self):
        d=run(self.root,now=NOW,fetcher=lambda s:[{'title':'bad'},*self.rows])
        self.assertEqual(d['sources'][0]['rejected'],1);self.assertEqual(d['new_articles'],1)
    def test_corrupt_state(self):
        (self.root/'state').mkdir();p=self.root/'state/store.json';p.write_text('{bad')
        with self.assertRaises(ValueError):run(self.root,now=NOW,fetcher=lambda s:[])
        self.assertEqual(p.read_text(),'{bad')
    def test_archive_never_pruned(self):
        run(self.root,now=NOW,fetcher=lambda s:self.rows)
        d=run(self.root,now=NOW+timedelta(days=30),fetcher=lambda s:[])
        self.assertEqual(d['total_archived'],1);self.assertEqual(d['articles'],[]);self.assertIsNone(d['metrics']['all']['value'])
    def test_throttle(self):
        (self.root/'config.json').write_text(json.dumps({**CFG,'sources':[{**SRC,'min_interval_minutes':120}]}))
        run(self.root,now=NOW,fetcher=lambda s:self.rows)
        fetcher=MagicMock();d=run(self.root,now=NOW+timedelta(minutes=15),fetcher=fetcher)
        fetcher.assert_not_called();self.assertEqual(d['sources'][0]['status'],'throttled')
    def test_model_upgrade_preserves_revisions(self):
        run(self.root,now=NOW,fetcher=lambda s:self.rows)
        p=self.root/'state/store.json'; state=json.loads(p.read_text())
        item=next(iter(state['records'].values()));item['analysis']['model']='old-model'
        p.write_text(json.dumps(state))
        d=run(self.root,now=NOW+timedelta(minutes=15),fetcher=lambda s:self.rows)
        self.assertEqual(d['new_articles'],0)
        revised=json.loads((self.root/'docs/data/revisions.json').read_text())
        self.assertEqual(len(revised),1);self.assertEqual(revised[0]['analysis']['model'],'old-model')
        self.assertEqual(d['articles'][0]['first_seen'],stamp(NOW))
    def test_failed_throttle_stays_degraded(self):
        (self.root/'config.json').write_text(json.dumps({**CFG,'sources':[{**SRC,'min_interval_minutes':120}]}))
        def fail(s):raise ValueError('quota')
        run(self.root,now=NOW,fetcher=fail)
        fetcher=MagicMock(); d=run(self.root,now=NOW+timedelta(minutes=15),fetcher=fetcher)
        fetcher.assert_not_called();self.assertEqual(d['collection_status'],'degraded')
    def test_momentum_does_not_cross_models(self):
        h={'model':'old-model','at':stamp(NOW-timedelta(hours=1)),'metrics':{'all':{'status':'ok','value':50}}}
        self.assertIsNone(metrics([rec()],NOW,[h],{**CFG,'min_events':1,'min_sources':1})['momentum'])
if __name__=='__main__':unittest.main()


class InvestingTests(unittest.TestCase):
    def test_naive_feed_date_and_private_export(self):
        src={**SRC,'naive_date_timezone':'UTC'}
        rows=rss(b'<rss><channel><item><title>US stocks rally</title><link>https://example.com/1</link><pubDate>2026-01-10 10:00:00</pubDate></item></channel></rss>')
        item=record(rows[0],src,NOW)
        self.assertEqual(item['published_at'],'2026-01-10T10:00:00Z')
        self.assertIsNone(item['title'])
        self.assertGreater(item['analysis']['score'],0)
        with self.assertRaises(ValueError): record(rows[0],SRC,NOW)
    def test_explicit_zone_preserved(self):
        raw={'title':'US stocks rally','url':'https://example.com/1','published_at':'2026-01-10T10:00:00+02:00'}
        item=record(raw,{**SRC,'naive_date_timezone':'UTC'},NOW)
        self.assertEqual(item['published_at'],'2026-01-10T08:00:00Z')
    def test_future_rejected(self):
        raw={'title':'US stocks rally','url':'https://example.com/1','published_at':'2026-01-11 10:00:00'}
        with self.assertRaises(ValueError): record(raw,{**SRC,'naive_date_timezone':'UTC'},NOW)


class MeaningRegressionTests(unittest.TestCase):
    def test_labeled_headline_cases(self):
        # Synthetic, manually labelled contrasts; not a market benchmark.
        cases=[
            ('Why is Nvidia stock sliding today?', -1),
            ('Nvidia stock is rising today', 1),
            ('US stocks plunge after inflation data', -1),
            ('US stocks rally after inflation data', 1),
            ('US inflation rises again', -1),
            ('US inflation falls again', 1),
            ('Hot inflation leaves the Fed trapped', -1),
            ('Lower inflation gives the Fed room', 1),
            ('Treasury yields rise', -1),
            ('Treasury yields fall', 1),
            ('Nvidia stock does not fall', 0),
            ('Nvidia stock does not rise', 0),
            ('Apple holds a meeting', 0),
            ('US stocks await inflation data', 0),
            ('US stocks watch oil prices plunge', 0),
            ('US stocks watch oil prices surge', 0),
        ]
        for title, expected in cases:
            with self.subTest(title=title):
                score=analyze(title)['score']
                self.assertEqual(0 if score is None else (1 if score>0 else -1 if score<0 else 0),expected)
    def test_inflation_led_selloff_is_not_falling_inflation(self):
        a=analyze('US Treasury yields fall after reversing inflation-led selloff')
        self.assertEqual(a['rules'],['yields_down'])
        self.assertAlmostEqual(a['score'],.35)
    def test_inflation_led_rally_is_not_rising_inflation(self):
        self.assertNotIn('inflation_up',analyze('US stocks discuss inflation-led rally')['rules'])
