import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from progress_tracker import history_context,image_roles,build_update_prompt,update_estimates,estimate_breakdown,PROMPT_VERSION
from test_project_estimate import rows

class CumulativeV7Tests(unittest.TestCase):
    def history(self):
        h=[dict(date=d,stages=rows(p),prompt_version=PROMPT_VERSION,model_inferred_stages=[]) for d,p in [('2019-06',30),('2020-04',40),('2021-01',60)]]
        update_estimates({'history':h}); return h
    def test_baseline_and_previous_and_all_totals(self):
        h=self.history(); c=history_context(h)
        self.assertEqual(c['baseline']['estimated_project_pct'],30)
        self.assertEqual(c['previous']['estimated_project_pct'],60)
        self.assertEqual([r['estimated_project_pct'] for r in c['history']],[30,40,60])
        self.assertEqual(h[-1]['overall']['baseline_progress_delta_pp'],30)
        self.assertEqual(h[-1]['overall']['project_progress_delta_pp'],20)
    def test_roles_and_dedup(self):
        h=self.history()
        self.assertEqual([r['role'] for r in image_roles([], '2019-06')],['current_and_baseline'])
        self.assertEqual([r['role'] for r in image_roles(h[:1], '2020-04',True)],['baseline_and_previous','current','ssim_previous_to_current'])
        self.assertEqual([r['date'] for r in image_roles(h,'2022-02',True)],['2019-06','2021-01','2022-02','2022-02'])
    def test_v6_migration_keeps_weighted_inference(self):
        i=[dict(id='dam_foundation',percent=90,range_pct=[60,100],basis='prior',assumption='uncertain')]
        h={'date':'2020-01','stages':rows(),'prompt_version':'v6-evidence-first','model_inferred_stages':i}
        update_estimates({'history':[h]}); self.assertEqual(h['overall']['project_progress_pct'],estimate_breakdown(h['stages'],i)['project_progress_pct'])
    def test_no_current_answer_or_future_labels(self):
        h=self.history(); h[-1]['future_label']=987654321
        p=build_update_prompt({},h,'2022-02',True)
        self.assertNotIn('987654321',p); self.assertIn('不得当作实测量',p); self.assertIn('不把前期总值加上本期累计值',p)
    def test_decline_allowed(self):
        h=self.history(); h.append(dict(date='2022-02',stages=rows(50),prompt_version=PROMPT_VERSION)); update_estimates({'history':h})
        self.assertEqual(h[-1]['overall']['project_progress_delta_pp'],-10)
