"""Pipeline workflow tests use explicit synthetic inference outputs; model checks are separate."""
import hashlib
import io
import json
import unittest
from unittest.mock import patch
import zipfile
import numpy as np
from tests import test_workflow as workflow
from server import store,monitor,vision

class AutomationTests(unittest.TestCase):
    setUp=workflow.WorkflowTests.setUp
    tearDown=workflow.WorkflowTests.tearDown
    update=workflow.WorkflowTests.update

    def sample(self,time=102):return {'videoId':'v10','timestamp':time,'path':store.DATA/'evidence/OBS-001.jpg'}
    def result(self,predictions=True):
        mask=np.zeros((108,192),bool);mask[85:88,60:170]=True
        prediction={'box':{'x':.27,'y':.71,'width':.72,'height':.23},'label':'cable','score':.6,'maskQuality':.8,'maskWidth':192,'maskHeight':108,'mask':vision.encode_mask(mask),'lowerImageFraction':1}
        return {'sourceSha256':hashlib.sha256(self.sample()['path'].read_bytes()).hexdigest(),'sourceWidth':1920,'sourceHeight':1080,'pipelineVersion':'test-only','models':{'detector':{'repo':'TEST FIXTURE','revision':'test'},'segmenter':{'repo':'TEST FIXTURE','revision':'test'}},'generatedAt':store.now(),'cacheHit':False,'predictions':[prediction] if predictions else []}

    def test_issues_exist_before_review_and_reruns_do_not_duplicate(self):
        result=self.result();self.assertEqual(monitor.persist(self.sample(),result),['FL-001'])
        project=self.client.get('/api/project').json();i=project['issues'][0];o=next(o for o in project['observations'] if o['id']==i['observationId'])
        self.assertEqual(i['status'],'needs_review');self.assertIsNone(i['observationReviewer'])
        self.assertEqual(o['highlight']['method'],'automatic-sam2');self.assertTrue(o['highlight']['mask']);self.assertIsNone(o['highlight']['reviewer'])
        self.assertEqual(monitor.persist(self.sample(),result),[])
        self.assertEqual(monitor.persist(self.sample(105),result),[])
        issues=self.client.get('/api/project').json()['issues'];self.assertEqual(len(issues),1);self.assertEqual(len(issues[0]['automation']['sightings']),2)
        self.assertEqual(self.update(issues[0],'open').status_code,422)
        self.assertEqual(self.update(issues[0],'assigned',assignee='Team',dueDate='2026-10-20').status_code,422)
        accepted=self.update(issues[0],'open',note='Confirmed visible cable; route use needs checking.');self.assertEqual(accepted.status_code,200,accepted.text)
        self.assertEqual(accepted.json()['observationReviewer'],'Test reviewer')
        self.assertEqual(monitor.persist(self.sample(),result),[])
        self.assertEqual(self.client.get('/api/project').json()['issues'][0]['status'],'open')

    def test_dismissal_is_retained_and_export_marks_pending_findings(self):
        monitor.persist(self.sample(),self.result());i=self.client.get('/api/project').json()['issues'][0]
        res=self.client.get('/api/exports/bundle');self.assertEqual(res.status_code,200)
        archive=zipfile.ZipFile(io.BytesIO(res.content));bcf=zipfile.ZipFile(io.BytesIO(archive.read('fieldlink-issues.bcfzip')))
        xml=bcf.read(i['guid']+'/markup.bcf');self.assertIn(b'Human review pending',xml);self.assertIn(b'needs_review',xml)
        self.assertNotIn(b'None at None',xml)
        result=self.update(i,'dismissed',note='Test false positive');self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(monitor.persist(self.sample(105),self.result()),[])
        self.assertEqual(self.client.get('/api/project').json()['issues'][0]['status'],'dismissed')
        self.assertEqual(self.update(result.json(),'closed',note='Invalid shortcut').status_code,409) # New sighting made revision stale.

    def test_no_detection_creates_no_issue_and_failure_is_explicit(self):
        self.assertEqual(monitor.persist(self.sample(),self.result(False)),[])
        self.assertEqual(self.client.get('/api/project').json()['issues'],[])
        with patch.object(vision,'ready',return_value=False):
            self.assertEqual(self.client.post('/api/analysis/run').status_code,503)

    def test_worker_failure_does_not_fabricate_findings(self):
        entries=[{**self.sample(n),'video':{'filename':'test.mp4'}} for n in range(3)]
        monitor._stop.clear()
        with patch.object(monitor,'samples',return_value=iter(entries)),patch.object(monitor,'source_frame',side_effect=RuntimeError('test model failure')):
            monitor._run()
        state=monitor.status();self.assertEqual(state['state'],'failed');self.assertEqual(len(state['errors']),3)
        self.assertEqual(self.client.get('/api/project').json()['issues'],[])
