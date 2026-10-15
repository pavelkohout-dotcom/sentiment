import json, tempfile, unittest
from pathlib import Path
from datetime import datetime, timezone
from msm.core import digest, metrics, stamp, VERSION as RULES_VERSION
from msm.llama import VERSION, MODEL_DIGEST, PROMPT, validate, cached_analysis, cache_key
from msm.run import run
NOW=datetime(2026,10,15,12,tzinfo=timezone.utc)
SRC={'id':'test','name':'Test','kind':'rss','domains':['example.com'],'publish_titles':False,'enabled':True,'terms':'https://example.com/terms'}
CFG={'window_hours':24,'half_life_hours':6,'min_events':1,'min_sources':1,'analysis_model':VERSION,'sources':[SRC]}
def cache(title,scope='single_us_company',direction='negative',score=-1):
    return {'model':VERSION,'model_digest':MODEL_DIGEST,'prompt_hash':digest(PROMPT),'ratings':{cache_key(title):{'rating':dict(scope=scope,direction=direction,score=score,reason='Test explanation'),'rated_at':stamp(NOW)}}}

class LlamaTests(unittest.TestCase):
    def test_score_must_match_direction_and_scope(self):
        for score in (True,False,1,0,'-1',float('nan')):
            with self.assertRaises(ValueError):validate(dict(scope='single_us_company',direction='negative',score=score,reason='x'))
        with self.assertRaises(ValueError):validate(dict(scope='other',direction='negative',score=-1,reason='x'))
        self.assertIsNone(validate(dict(scope='other',direction='negative',score=None,reason='x'))['score'])

    def test_new_company_included_without_claiming_index_membership(self):
        title='CoreWeave AI bonds tumble'
        a=cached_analysis(title,cache(title))
        self.assertEqual(a['score'],-1);self.assertEqual(a['segments'],['us_equities'])
        r={'id':'a','source':'example.com','published_at':stamp(NOW),'signature':['unique'],'analysis':a}
        self.assertEqual(metrics([r],NOW,[],CFG)['value'],0)
        self.assertIsNone(metrics([r],NOW,[],CFG,'sp500')['value'])

    def test_missing_cache_never_falls_back_to_rules(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'config.json').write_text(json.dumps(CFG))
            result=run(root,now=NOW,fetcher=lambda s:[{'title':'US stocks rally','url':'https://example.com/1','published_at':stamp(NOW)}])
            self.assertEqual(result['llama']['pending'],1)
            self.assertIsNone(result['metrics']['all']['value'])

    def test_pipeline_numeric_score_history_boundary_and_privacy(self):
        title='CoreWeave AI bonds tumble'
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'state').mkdir();(root/'docs/data').mkdir(parents=True)
            (root/'config.json').write_text(json.dumps(CFG));(root/'state/llama_scores.json').write_text(json.dumps(cache(title)))
            old={'at':'2026-10-15T11:00:00Z','model':RULES_VERSION,'metrics':{'all':{'value':80,'status':'ok'}}}
            (root/'docs/data/history.json').write_text(json.dumps([old]))
            result=run(root,now=NOW,fetcher=lambda s:[{'title':title,'url':'https://example.com/1','published_at':stamp(NOW)}])
            self.assertEqual(result['metrics']['all']['value'],0)
            self.assertIsNone(result['metrics']['all']['momentum'])
            self.assertIsNone(result['articles'][0]['title'])
            self.assertEqual(result['articles'][0]['analysis']['score'],-1)
            self.assertEqual(json.loads((root/'docs/data/history.json').read_text())[0],old)

    def test_wrong_model_cache_rejected_before_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'state').mkdir();(root/'config.json').write_text(json.dumps(CFG))
            c=cache('US stocks rally');c['model_digest']='wrong';(root/'state/llama_scores.json').write_text(json.dumps(c))
            with self.assertRaises(ValueError):run(root,now=NOW,fetcher=lambda s:[])
            self.assertFalse((root/'state/store.json').exists())

    def test_cache_backfills_rotated_feed_item_and_excludes_expired(self):
        title='CoreWeave AI bonds tumble'
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'state').mkdir();(root/'config.json').write_text(json.dumps(CFG))
            c=cache(title);item=c['ratings'][cache_key(title)]
            item.update(url='https://example.com/seed',provider='test',published_at=stamp(NOW),signature=['coreweave','bonds','tumble'],rule_segments=[],kind='unknown')
            (root/'state/llama_scores.json').write_text(json.dumps(c))
            result=run(root,now=NOW,fetcher=lambda s:[])
            self.assertEqual(result['metrics']['all']['scored_events'],1)
            self.assertEqual(result['articles'][0]['analysis']['score'],-1)
            from datetime import timedelta
            later=run(root,now=NOW+timedelta(hours=25),fetcher=lambda s:[])
            self.assertEqual(later['metrics']['all']['scored_events'],0)
            self.assertEqual(later['total_archived'],1)

    def test_archived_rules_rating_migrates_with_revision(self):
        from msm.collect import record
        title='US stocks rally'
        old=record({'title':title,'url':'https://example.com/old','published_at':stamp(NOW)},SRC,NOW)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'state').mkdir();(root/'config.json').write_text(json.dumps(CFG))
            (root/'state/store.json').write_text(json.dumps({'schema':1,'records':{old['id']:old},'sources':{}}))
            (root/'state/llama_scores.json').write_text(json.dumps(cache(title,'broad_us','positive',1)))
            result=run(root,now=NOW,fetcher=lambda s:[])
            self.assertEqual(result['metrics']['all']['value'],100)
            saved=json.loads((root/'state/store.json').read_text())
            self.assertEqual(saved['model_revisions'][0],old)
            self.assertEqual(saved['records'][old['id']]['analysis']['model'],VERSION)
