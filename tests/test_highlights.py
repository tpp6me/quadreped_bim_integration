import base64
import hashlib
import io
import json
import zipfile
import unittest
import numpy as np
from PIL import Image
from tests import test_workflow as workflow
from server import store

class HighlightTests(unittest.TestCase):
    setUp=workflow.WorkflowTests.setUp
    tearDown=workflow.WorkflowTests.tearDown
    confirm=workflow.WorkflowTests.confirm
    create=workflow.WorkflowTests.create
    def selection(self):
        return json.loads((store.ROOT/'scripts/demo-highlight-selection.json').read_text())

    def test_segmentation_review_persistence_and_export(self):
        issue=self.create();selection=self.selection()
        before=(store.DATA/'evidence/OBS-001.jpg').read_bytes()
        preview=self.client.post('/api/observations/OBS-001/segment',json=selection)
        self.assertEqual(preview.status_code,200,preview.text[:200])
        candidate=preview.json();mask=np.array(Image.open(io.BytesIO(base64.b64decode(candidate['mask']))))[:,:,3]>0
        self.assertGreater(mask.sum(),300)
        self.assertLess(mask.sum(),mask.size*.08) # Cable mask, not a filled selection rectangle.
        self.assertFalse(mask[:500].any()) # No mask on the factory ceiling / equipment.
        o=next(o for o in self.client.get('/api/project').json()['observations'] if o['id']=='OBS-001')
        self.assertIsNone(o.get('highlight')) # Preview is not a confirmed annotation.
        body={'revision':o['revision'],'reviewer':'Highlight reviewer','selection':selection}
        saved=self.client.patch('/api/observations/OBS-001/highlight',json=body)
        self.assertEqual(saved.status_code,200,saved.text[:200])
        h=saved.json()['highlight'];self.assertEqual(h['mask'],candidate['mask'])
        self.assertEqual(h['sourceSha256'],hashlib.sha256(before).hexdigest())
        self.assertEqual(saved.json()['reviewer'],'Test reviewer') # Independent review provenance.
        self.assertEqual(self.client.patch('/api/observations/OBS-001/highlight',json=body).status_code,409)
        archive=zipfile.ZipFile(io.BytesIO(self.client.get('/api/exports/bundle').content))
        bcf=zipfile.ZipFile(io.BytesIO(archive.read('fieldlink-issues.bcfzip')))
        self.assertEqual(bcf.read(issue['guid']+'/source-original.jpg'),before)
        self.assertNotEqual(bcf.read(issue['guid']+'/highlighted.png'),bcf.read(issue['guid']+'/evidence.png'))
        self.assertEqual(json.loads(bcf.read(issue['guid']+'/highlight.json'))['reviewer'],'Highlight reviewer')
        self.assertIn(b'highlighted.png',bcf.read(issue['guid']+'/markup.bcf'))
        self.assertEqual((store.DATA/'evidence/OBS-001.jpg').read_bytes(),before)
        remove=self.client.patch('/api/observations/OBS-001/highlight',json={'revision':saved.json()['revision'],'reviewer':'Highlight reviewer','selection':None})
        self.assertEqual(remove.status_code,200);self.assertIsNone(remove.json()['highlight'])
        self.assertEqual(remove.json()['history'][-1]['action'],'highlight removed')

    def test_invalid_bounds_and_manual_fallback(self):
        s=self.selection();s['box']['x']=.99
        self.assertEqual(self.client.post('/api/observations/OBS-001/segment',json=s).status_code,422)
        s=self.selection();s['strokes'][0]['points'][0]['x']=-1
        self.assertEqual(self.client.post('/api/observations/OBS-001/segment',json=s).status_code,422)
        self.assertEqual(self.client.post('/api/observations/missing/segment',json=self.selection()).status_code,404)
        s=self.selection();s.update(method='manual-box',strokes=[])
        r=self.client.patch('/api/observations/OBS-001/highlight',json={'revision':1,'reviewer':'Manual reviewer','selection':s})
        self.assertEqual(r.status_code,200,r.text);o=r.json()
        self.assertEqual(o['highlight']['algorithm'],'Reviewer-drawn box');self.assertIsNone(o['highlight']['mask'])
        self.assertEqual(o['status'],'suggested') # A highlight does not confirm an observation.
