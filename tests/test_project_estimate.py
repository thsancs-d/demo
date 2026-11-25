import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from progress_tracker import current_rows, estimate_overall, update_estimates
from stages import get_stages


def rows(p=60, missing=('dam_foundation','electromechanical')):
    stages=[{'id':s['id'],'status':'in_progress','confidence':.8,'evidence':'test observation','progress_estimate':{'percent':p,'range_pct':[p-10,p+10],'scope_basis':'test scope','completed_basis':'test extent'}} for s in get_stages('reservoir') if s['id'] not in missing]
    return current_rows({'stages':stages},None,'2020-01')

class OverallTests(unittest.TestCase):
    def test_partial_coverage_extrapolation(self):
        a=estimate_overall(rows()); self.assertEqual(a['current_coverage_pct'],85); self.assertEqual(a['project_progress_pct'],60); self.assertEqual(a['project_progress_method'],'coverage_extrapolation'); self.assertEqual(a['assumed_weight_pct'],15); self.assertIsNone(a['total_estimate_pct'])
    def test_model_overall(self):
        a=estimate_overall(rows(),{'overall_estimate':{'percent':63,'basis':'test basis','unknown_assumptions':'test assumption'}}); self.assertEqual(a['project_progress_pct'],63); self.assertEqual(a['project_progress_method'],'model_overall')
    def test_bad_model_rejected(self):
        for v in (99,float('nan'),True,'63'):
            a=estimate_overall(rows(),{'overall_estimate':{'percent':v,'basis':'test','unknown_assumptions':'test'}}); self.assertEqual(a['project_progress_method'],'coverage_extrapolation')
    def test_inadequate_coverage(self):
        a=estimate_overall(rows(missing=('dam_body',))); self.assertIsNone(a['project_progress_pct'])
    def test_full_coverage(self):
        a=estimate_overall(rows(missing=())); self.assertEqual(a['project_progress_pct'],60); self.assertEqual(a['project_progress_method'],'all_stage_weighted')
    def test_migrate_delta(self):
        state={'history':[{'stages':rows(40)},{'stages':rows(60)}]}; update_estimates(state); self.assertEqual(state['history'][1]['overall']['project_progress_delta_pp'],20); self.assertEqual(state['history'][1]['overall']['previous_project_progress_pct'],40)

if __name__=='__main__': unittest.main()
