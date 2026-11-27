import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from progress_tracker import build_update_prompt,estimate_breakdown,update_estimates,PROMPT_VERSION
from test_project_estimate import rows

class PromptV6Tests(unittest.TestCase):
    def test_prompt_prior_total_explicit_reference(self):
        history=[dict(date='2020-01',stages=rows(),overall={'project_progress_pct':87.123456})]
        p=build_update_prompt({},history,'2020-02',True)
        self.assertIn('87.123456',p)
        self.assertIn('历史总进度、分项百分比、推断和外推',p)
        self.assertNotIn('overall_estimate',p)
        self.assertIn('inferred_stages',p)
        self.assertIn('永久基准',p)
    def test_weighted_inferred(self):
        i=[dict(id='dam_foundation',percent=90,range_pct=[60,100],basis='prior evidence',assumption='not verified'),dict(id='electromechanical',percent=10,range_pct=[0,50],basis='prior evidence',assumption='not verified')]
        a=estimate_breakdown(rows(),i)
        self.assertEqual(a['project_progress_pct'],60.5)
        self.assertEqual(a['current_coverage_pct'],85)
        self.assertEqual(a['project_progress_method'],'stage_inference_weighted')
        self.assertEqual(a['total_possible_range_pct'],[42.5,74.5])
    def test_partial_inference_fallback(self):
        i=[dict(id='dam_foundation',percent=90,range_pct=[60,100],basis='prior',assumption='uncertain')]
        a=estimate_breakdown(rows(),i)
        self.assertEqual(a['project_progress_pct'],63)
        self.assertEqual(a['extrapolated_stages'][0]['id'],'electromechanical')
    def test_reject_invalid_and_visible_duplicates(self):
        i=[dict(id='dam_foundation',percent=90,range_pct=[90,90],basis='prior',assumption='uncertain'),dict(id='dam_body',percent=99,range_pct=[80,100],basis='prior',assumption='uncertain')]
        a=estimate_breakdown(rows(),i)
        self.assertEqual(a['project_progress_pct'],60)
        self.assertEqual(a['inferred_stages'],[])
    def test_legacy_history_unchanged(self):
        h={'stages':rows(),'model_overall_estimate':{'percent':63,'basis':'test','unknown_assumptions':'test'}}
        new={'stages':rows(),'prompt_version':PROMPT_VERSION,'model_inferred_stages':[]}
        state={'history':[h,new]}; update_estimates(state)
        self.assertEqual(h['overall']['project_progress_pct'],63)
        self.assertEqual(new['overall']['project_progress_pct'],60)
    def test_low_coverage(self):
        self.assertIsNone(estimate_breakdown(rows(missing=('dam_body',)),[])['project_progress_pct'])
