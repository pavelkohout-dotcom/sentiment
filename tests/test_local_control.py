import base64
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch
from http.server import ThreadingHTTPServer
from msm.local_control import Controller, Handler, SITE, merge_cache, publish


def cache(at='1', ratings=None):
    return dict(model='v', model_digest='d', prompt_hash='p', options={}, last_attempt=at, ratings=ratings or {})


class MergeTests(unittest.TestCase):
    def test_newer_ratings_and_metadata_survive(self):
        a=cache('2', {'a': {'rated_at':'2','rating':1}, 'b': {'rated_at':'1'}})
        b=cache('3', {'a': {'rated_at':'3','rating':-1}, 'c': {'rated_at':'1'}})
        result=merge_cache(a,b)
        self.assertEqual(set(result['ratings']), {'a','b','c'})
        self.assertEqual(result['ratings']['a']['rating'], -1)
        self.assertEqual(result['last_attempt'], '3')
        self.assertEqual(len(b['ratings']),2)

    def test_incompatible_model_rejected(self):
        a=cache();b=cache();b['prompt_hash']='different'
        with self.assertRaises(ValueError):merge_cache(a,b)

    def test_conflict_refetches_and_merges(self):
        initial=cache('1');concurrent=cache('3',{'foreign':{'rated_at':'3'}})
        blob=lambda c,sha:dict(sha=sha,content=base64.b64encode(json.dumps(c).encode()).decode())
        error=urllib.error.HTTPError('https://api.github.com',409,'Conflict',{},None)
        with patch('msm.local_control.request_json',side_effect=[blob(initial,'old'),error,blob(concurrent,'new'),{'commit':{'sha':'ok'}}]) as api:
            sha,result=publish(cache('2',{'local':{'rated_at':'2'}}),'fake-secret')
        self.assertEqual(sha,'ok')
        self.assertEqual(set(result['ratings']),{'foreign','local'})
        self.assertEqual(api.call_args_list[-1].args[2]['sha'],'new')
        self.assertTrue(api.call_args_list[-1].args[0].endswith('/contents/state/llama_scores.json'))


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.control=Controller(Path(self.temp.name)/'private')
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.server.controller=self.control
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url='http://127.0.0.1:'+str(self.server.server_port)

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.temp.cleanup()

    def call(self,path='/status',origin=SITE,method='GET',nonce=None,host=None):
        headers={'Origin':origin,'Content-Type':'application/json'}
        if nonce is not None:headers['X-MSM-Token']=nonce
        if host:headers['Host']=host
        request=urllib.request.Request(self.url+path,method=method,headers=headers,data=b'{}' if method=='POST' else None)
        try:return urllib.request.urlopen(request)
        except urllib.error.HTTPError as ex:return ex

    def test_status_does_not_expose_github_token(self):
        self.control.token_path.write_text('private-github-secret')
        response=self.call();body=response.read().decode()
        self.assertEqual(response.status,200)
        self.assertNotIn('private-github-secret',body)
        self.assertEqual(response.headers['Access-Control-Allow-Origin'],SITE)

    def test_other_origins_and_dns_rebinding_denied(self):
        self.assertEqual(self.call(origin='https://evil.test').status,403)
        self.assertEqual(self.call(host='evil.test').status,403)
        self.assertEqual(self.call(origin='null').status,403)

    def test_refresh_needs_nonce_and_configuration(self):
        self.assertEqual(self.call('/refresh',method='POST').status,403)
        self.assertEqual(self.call('/refresh',method='POST',nonce=self.control.secret).status,428)

    def test_public_site_cannot_change_credentials(self):
        self.assertEqual(self.call('/configure',method='POST',nonce=self.control.secret).status,403)

    def test_duplicate_run_rejected(self):
        self.control.token_path.write_text('fake')
        self.control.lock.acquire()
        try:self.assertEqual(self.control.start(),409)
        finally:self.control.lock.release()

    def test_configured_secret_is_private(self):
        with patch('msm.local_control.request_json',return_value={'permissions':{'push':True}}):
            self.control.configure('x'*30)
        self.assertEqual(self.control.token_path.stat().st_mode & 0o777,0o600)
        self.assertEqual(self.control.directory.stat().st_mode & 0o777,0o700)


if __name__=='__main__':unittest.main()

class RunnerTests(unittest.TestCase):
    def test_partial_rating_failure_still_publishes_valid_cache(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as tmp:
            control=Controller(Path(tmp)/'private');control.token_path.write_text('fake')
            control.lock.acquire()
            def run(args, **kwargs):
                if args[0]=='git':
                    root=Path(args[-1]);(root/'state').mkdir(parents=True)
                    (root/'state/llama_scores.json').write_text(json.dumps(cache()))
                    return SimpleNamespace(returncode=0)
                self.assertEqual(args[-2:],['-m','msm.rate_local'])
                result=cache('2',{'valid':{'rated_at':'2'}})
                result.update(last_success='2',errors=[{'headline_hash':'invalid'}])
                (kwargs['cwd']/'state/llama_scores.json').write_text(json.dumps(result))
                return SimpleNamespace(returncode=1)
            with patch('msm.local_control.subprocess.run',side_effect=run), patch('msm.local_control.time.sleep'), patch('msm.local_control.request_json',side_effect=[{}, {'generated_at':'9999','llama':{'last_refresh_at':'2'}}]), patch('msm.local_control.publish',side_effect=lambda c,t:('commit',c)) as pub:
                control.run()
            self.assertEqual(control.state['phase'],'done')
            self.assertEqual(pub.call_args.args[0]['errors'][0]['headline_hash'],'invalid')
            self.assertFalse(control.lock.locked())
            self.assertFalse((control.directory/'pending-scores.json').exists())

    def test_model_failure_never_publishes(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as tmp:
            control=Controller(Path(tmp)/'private');control.token_path.write_text('fake');control.lock.acquire()
            def run(args, **kwargs):
                if args[0]=='git':
                    root=Path(args[-1]);(root/'state').mkdir(parents=True)
                    (root/'state/llama_scores.json').write_text(json.dumps(cache()))
                return SimpleNamespace(returncode=1)
            with patch('msm.local_control.subprocess.run',side_effect=run),patch('msm.local_control.request_json',return_value={}),patch('msm.local_control.publish') as pub:
                control.run()
            pub.assert_not_called()
            self.assertEqual(control.state['phase'],'error')
            self.assertFalse(control.lock.locked())
