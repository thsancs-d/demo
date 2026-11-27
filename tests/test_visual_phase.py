import sys,json,unittest,tempfile,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'src'))
from visual_phase import compute_phase_progress
from vlm_report import build_prompt
from summarize import collect, summarize_reservoir
from evaluate import evaluate
from stages import get_stages

def est(p,lo,hi): return dict(percent=p,range_pct=[lo,hi],scope_basis='测试：可辨认的完整计划范围',completed_basis='测试：已施工范围和未完成范围')
def stage(**kw): return dict(id='dam_body',status='in_progress',evidence='测试：坝面局部成型',phase='late',before_status='in_progress',before_phase='early',before_evidence='测试：初步填筑',progress_estimate=est(70,60,80),before_progress_estimate=est(20,10,30)) | kw
class V3(unittest.TestCase):
    def test_percentage(self):
        p=compute_phase_progress([stage()]); self.assertEqual(p['dam_after']['percent'],70);self.assertEqual(p['after']['estimated_assessable_progress_pct'],70);self.assertIsNone(p['after']['estimated_total_progress_pct']);self.assertEqual(p['after']['overall_possible_range_pct'],[24,92]);self.assertEqual(p['common_progress_delta_pp'],50)
    def test_no_fixed_stage_conversion(self):
        self.assertIsNone(compute_phase_progress([stage(progress_estimate=None)])['dam_after'])
        self.assertEqual(compute_phase_progress([stage(progress_estimate=est(31,25,45))])['dam_after']['percent'],31)
    def test_invalid(self):
        for e in (est(101,80,100),est(40,50,80),est(True,0,100),est(50,40,60)|{'scope_basis':''},est(100,99,100)):
            self.assertIsNone(compute_phase_progress([stage(progress_estimate=e)])['dam_after'])
    def test_duplicate(self): self.assertIsNone(compute_phase_progress([stage(),stage()])['dam_after'])
    def test_hidden(self):
        r=compute_phase_progress([stage(id='dam_foundation',before_status='not_started',before_progress_estimate=est(0,0,0))]);self.assertEqual(r['common_weight'],0)
    def test_all_estimated(self):
        p=compute_phase_progress([stage(id=s['id']) for s in get_stages('reservoir')]);self.assertEqual(p['after']['estimated_total_progress_pct'],70)
    def test_context(self):
        ctx=json.loads((ROOT/'config/aigawa_context.json').read_text()); p=build_prompt('2019-06','2020-04',True,False,'reservoir',ctx); self.assertIn('中央心墙型堆石坝',p); self.assertIn('before_progress_estimate',p);self.assertNotIn('2022-01-26',p);self.assertNotIn('不要输出任何百分比数字',p)
    def test_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);out=root/'report'; f=root/'response.json';f.write_text(json.dumps({'stages':[stage()]}));images=ROOT/'datasets/aigawa/images'
            run=subprocess.run([sys.executable,str(ROOT/'src/vlm_report.py'),'--project-type','reservoir','--before',str(images/'2019-06.png'),'--after',str(images/'2020-04.png'),'--before-date','2019-06','--after-date','2020-04','--response-file',str(f),'--out',str(out)],check=True,capture_output=True,text=True)
            r=json.loads((out/'vlm_raw.json').read_text());self.assertEqual(r['meta']['execution_mode'],'offline_replay');self.assertEqual(r['progress']['dam_after']['percent'],70);self.assertEqual(len(collect(tmp,'reservoir')),1);self.assertTrue((out/'prompt.txt').exists());self.assertIn('70%',(out/'report.md').read_text());self.assertIn('施工进度',run.stdout);self.assertNotIn('状态评分',run.stdout)
            r['meta']['execution_mode']='live';(out/'vlm_raw.json').write_text(json.dumps(r));summarize_reservoir(collect(tmp,'reservoir'),tmp);self.assertIn('70%',(root/'summary_reservoir.md').read_text())
    def test_evaluate(self):
        labels={'project':'p','records':[{'month':'2022-02','dam_fill_percent':100}]};r={'meta':{'after_date':'2022-02','execution_mode':'live','context':{'project_name':'p'}},'progress':{'stages':[{'id':'dam_body','phase':'visually_complete','progress_estimate':est(100,100,100)}]}};self.assertEqual(evaluate(labels,[r])[0]['endpoint_difference_pp'],0);r['meta']['execution_mode']='offline_replay';self.assertEqual(evaluate(labels,[r]),[])
if __name__=='__main__':unittest.main()
