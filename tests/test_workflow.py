import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
import os
from fastapi.testclient import TestClient
from lxml import etree
import ifcopenshell
from server import store
from server.app import app

class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.old_autorun=os.environ.get('FIELDLINK_AUTORUN');os.environ['FIELDLINK_AUTORUN']='0'
        self.temp=tempfile.TemporaryDirectory();self.old_db=store.DB;store.DB=Path(self.temp.name)/'test.sqlite';self.client=TestClient(app);self.client.__enter__()
    def tearDown(self):
        self.client.__exit__(None,None,None);store.DB=self.old_db;self.temp.cleanup()
        if self.old_autorun is None:os.environ.pop('FIELDLINK_AUTORUN',None)
        else:os.environ['FIELDLINK_AUTORUN']=self.old_autorun
    def confirm(self):
        o=self.client.get('/api/project').json()['observations'][0]
        body={'revision':o['revision'],'reviewer':'Test reviewer','status':'confirmed','description':o['description'],'title':o['title'],'note':'Reviewed source image'}
        r=self.client.patch('/api/observations/'+o['id'],json=body);self.assertEqual(r.status_code,200,r.text);return r.json(),body
    def create(self):
        self.confirm();r=self.client.post('/api/issues',json={'observationId':'OBS-001','reviewer':'Test reviewer','discipline':'Site Safety','priority':'Medium'});self.assertEqual(r.status_code,201,r.text);return r.json()
    def update(self,issue,status,**changes):
        body={'revision':issue['revision'],'reviewer':'Test reviewer','status':status,'assignee':issue['assignee'],'dueDate':issue['dueDate'],'note':'','resolutionEvidence':issue['resolutionEvidence'],'priority':issue['priority'],'discipline':issue['discipline']};body.update(changes)
        return self.client.patch('/api/issues/'+issue['id'],json=body)
    def test_search_and_capture_provenance(self):
        project=self.client.get('/api/project').json();self.assertEqual(len(project['videos']),10);self.assertTrue(all(v['captured_at'] is None for v in project['videos']))
        for query,expected in [('cables on floor','OBS-001'),('storage racks','OBS-003'),('marked aisle','OBS-004')]:
            records=self.client.get('/api/search',params={'q':query}).json()['results'];self.assertIn(expected,[o['id'] for o in records])
        self.assertEqual(self.client.get('/api/search?q=cracked+concrete+beam').json()['results'],[])
    def test_confirmation_required_and_stale_review_rejected(self):
        body={'observationId':'OBS-001','reviewer':'Test reviewer','discipline':'Site Safety','priority':'Medium'}
        self.assertEqual(self.client.post('/api/issues',json=body).status_code,422)
        _,review=self.confirm();self.assertEqual(self.client.patch('/api/observations/OBS-001',json=review).status_code,409)
        self.assertEqual(self.client.post('/api/issues',json=body).status_code,201);self.assertEqual(self.client.post('/api/issues',json=body).status_code,409)
    def test_issue_lifecycle_requires_assignment_and_evidence(self):
        issue=self.create()
        self.assertEqual(self.update(issue,'closed').status_code,422)
        self.assertEqual(self.update(issue,'assigned').status_code,422)
        r=self.update(issue,'assigned',assignee='Demo contractor',dueDate='2026-10-20');self.assertEqual(r.status_code,200,r.text);issue=r.json()
        self.assertEqual(self.update(issue,'resolved',note='Done').status_code,422)
        r=self.update(issue,'resolved',note='Simulated resolution',resolutionEvidence='SIMULATED example record');self.assertEqual(r.status_code,200,r.text);issue=r.json()
        r=self.update(issue,'closed',note='Simulated verification');self.assertEqual(r.status_code,200,r.text);issue=r.json()
        self.assertEqual(self.update(issue,'open').status_code,422)
        r=self.update(issue,'open',note='Reopened for another inspection');self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(len(r.json()['history']),5)
        persisted=self.client.get('/api/project').json()['issues'][0];self.assertEqual(persisted['status'],'open')
    def test_exports_valid_and_references_match_ifc(self):
        issue=self.create();res=self.client.get('/api/exports/bundle');self.assertEqual(res.status_code,200,res.text[:200] if res.status_code!=200 else '')
        archive=zipfile.ZipFile(io.BytesIO(res.content));self.assertTrue(archive.read('fieldlink-punch-list.pdf').startswith(b'%PDF'))
        model=ifcopenshell.file.from_string(archive.read('representative.ifc').decode());bcf=zipfile.ZipFile(io.BytesIO(archive.read('fieldlink-issues.bcfzip')))
        for filename in bcf.namelist():
            schema='markup.xsd' if filename.endswith('markup.bcf') else 'visinfo.xsd' if filename.endswith('.bcfv') else 'version.xsd' if filename=='bcf.version' else None
            if schema:
                root=etree.fromstring(bcf.read(filename));etree.XMLSchema(etree.parse(str(store.DATA/'schemas'/schema))).assertValid(root)
                for component in root.findall('.//Component'):self.assertIsNotNone(model.by_guid(component.attrib['IfcGuid']))
        root=etree.fromstring(bcf.read(issue['guid']+'/markup.bcf'));self.assertIn('BV SAMPLE 10.mp4 @ 01:42',root.findtext('Topic/Description'))
        self.assertIn('Not yet independently verified',archive.read('manifest.json').decode())
        self.assertTrue(bcf.read(issue['guid']+'/snapshot.png').startswith(b'\x89PNG'))
    def test_media_range_and_unknown_files(self):
        res=self.client.get('/media/v08',headers={'Range':'bytes=0-1023'});self.assertEqual(res.status_code,206);self.assertEqual(len(res.content),1024)
        self.assertEqual(self.client.get('/media/unknown').status_code,404)
        self.assertEqual(self.client.get('/assets-data/fieldlink.sqlite').status_code,404)
    def test_cross_origin_mutation_rejected(self):
        res=self.client.post('/api/issues',headers={'Origin':'https://example.com'},json={});self.assertEqual(res.status_code,403)

if __name__=='__main__':unittest.main()
