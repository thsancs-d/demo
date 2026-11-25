import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import subprocess
import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from stages import compute_progress, get_stages
from vlm_report import build_prompt, normalize_vlm, render_report
from quantity_progress import calculate_quantities
from cpm_core import compare_photos, _parse_roi
from summarize import collect

class TestIntegration(unittest.TestCase):
    def test_profiles(self):
        self.assertEqual(len(get_stages('building')),9)
        self.assertEqual(len(get_stages('reservoir')),8)
        for name in ('building','reservoir'):
            self.assertEqual(sum(s['weight'] for s in get_stages(name)),100)
    def test_prompt(self):
        p=build_prompt('a','b',True,False,'reservoir')
        self.assertIn('水库专项规则',p)
        self.assertIn('dam_body',p)
        self.assertNotIn('id="masonry"',p)
        self.assertIn('id="masonry"',build_prompt('a','b',False))
    def test_missing_and_duplicates(self):
        s={'id':'dam_body','status':'done','evidence':'可见特征','confidence':0.9}
        p=compute_progress([s,s], 'reservoir')
        self.assertIsNone(p['progress_pct'])
        self.assertEqual(len(p['stages']),8)
        self.assertEqual(p['counted_weight'],0)
    def test_score(self):
        p=compute_progress([dict(id='dam_body',status='in_progress',evidence='坝体填筑层')],'reservoir')
        self.assertEqual((p['progress_pct'],p['progress_floor'],p['counted_weight']),(50,20,40))
    def test_hidden(self):
        v=normalize_vlm({'stages':[dict(id='dam_foundation',status='not_started',evidence='不可见')]},'reservoir')
        self.assertEqual(v['stages'][1]['status'],'unclear')
    def test_quantities(self):
        d=json.loads((ROOT/'config/reservoir_quantities.example.json').read_text())
        self.assertEqual(calculate_quantities(d)['progress_pct'],59.5)
        d['items'].append(d['items'][0])
        with self.assertRaises(ValueError): calculate_quantities(d)
    def test_report(self):
        v=normalize_vlm({},'reservoir');p=compute_progress(v['stages'],'reservoir')
        md=render_report(v,p,dict(before='a',after='b',before_date='a',after_date='b',model='mock',time='now',project_type='reservoir'))
        self.assertIn('无法判断',md)
        self.assertIn('未提供工程量',md)
    def test_roi(self):
        with self.assertRaises(ValueError): _parse_roi('0.9,0,0.5,1',100,100)
    def test_summarize(self):
        with tempfile.TemporaryDirectory() as tmp:
            for typ in ('building','reservoir'):
                p=Path(tmp)/typ;p.mkdir();(p/'vlm_raw.json').write_text(json.dumps({'meta':{'project_type':typ,'after_date':'2026-10-01'},'vlm':{},'progress':{}}))
            self.assertEqual(len(collect(tmp,'reservoir')),1)
    def test_cv_and_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp); rng=np.random.default_rng(11)
            a=rng.integers(0,256,(360,480,3),dtype=np.uint8); b=a.copy(); b[130:210,160:240]=[30,120,220]
            cv2.imwrite(str(p/'a.jpg'),a);cv2.imwrite(str(p/'b.jpg'),b)
            r=compare_photos(str(p/'a.jpg'),str(p/'b.jpg'),str(p/'cv'))
            self.assertGreater(r['stats']['ransac_inliers'],12)
            self.assertGreater(r['stats']['changed_pixel_ratio'],0)
            run=subprocess.run([sys.executable,str(ROOT/'src/run_reservoir.py'),'--before',str(p/'a.jpg'),'--after',str(p/'b.jpg'),'--out',str(p/'run'),'--dry-run'],capture_output=True,text=True,check=True)
            self.assertIn('未调用 API',run.stdout)
            self.assertTrue((p/'run/cv_quality.json').exists())

if __name__=='__main__': unittest.main()
