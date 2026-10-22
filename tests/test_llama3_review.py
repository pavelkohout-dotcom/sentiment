import tempfile
import unittest
from pathlib import Path
from experiments.llama3_review import validate, report

class ReviewTests(unittest.TestCase):
    def test_invalid_model_output_rejected(self):
        for obj in ({}, {'scope':'broad_us','direction':'neutral','reason':'x'}, {'scope':'broad_us','direction':'positive','reason':''}):
            with self.assertRaises(ValueError): validate(obj)

    def test_report_escapes_untrusted_headline(self):
        data={'baseline':{'metrics':{},'generated_at':'snapshot','model':'rules'},'results':[{'cohort':'fresh_rss','source':'feed','title':'<script>alert(1)</script>','url':'https://example.com/story','llm':{'scope':'other','direction':'unclear','reason':'<unsafe>'},'rule':{'score':None,'segments':[],'rules':[]}}]}
        with tempfile.TemporaryDirectory() as tmp:
            report(data,Path(tmp));page=(Path(tmp)/'review.html').read_text()
            self.assertNotIn('<script>alert(1)</script>',page)
            self.assertIn('&lt;script&gt;',page)
            self.assertTrue((Path(tmp)/'ratings.csv').exists())
