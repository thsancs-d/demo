import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from progress_tracker import aggregate,current_rows,build_update_prompt,date_key
from stages import get_stages

def item(sid,p):
    return {'id':sid,'status':'done' if p==100 else 'not_started' if p==0 else 'in_progress','evidence':'test observation','confidence':.8,'progress_estimate':{'percent':p,'range_pct':[p,p],'scope_basis':'test scope','completed_basis':'test extent'}}

class TrackerTests(unittest.TestCase):
    def test_total_all(self):
        rows=current_rows({'stages':[item(s['id'],60) for s in get_stages('reservoir')]},None,'2020-01')
        a=aggregate(rows); self.assertEqual(a['total_estimate_pct'],60); self.assertEqual(a['total_possible_range_pct'],[60,60]); self.assertIsNone(a['total_reference_pct'])
    def test_unknown_not_zero(self):
        a=aggregate(current_rows({'stages':[item('dam_body',80)]},None,'2020-01'))
        self.assertIsNone(a['total_estimate_pct']); self.assertEqual(a['total_possible_range_pct'],[32,92]); self.assertEqual(a['total_reference_pct'],62)
    def test_all_unknown(self):
        a=aggregate(current_rows({'stages':[]},None,'2020-01')); self.assertIsNone(a['total_reference_pct']); self.assertEqual(a['total_possible_range_pct'],[0,100])
    def test_carry_is_not_current(self):
        old={'stages':current_rows({'stages':[item('dam_body',80)]},None,'2020-01')}
        r=current_rows({'stages':[{'id':'dam_body','status':'unclear','evidence':'blocked','carry_previous':True}]},old,'2020-02')
        dam=next(x for x in r if x['id']=='dam_body'); self.assertEqual(dam['observed_date'],'2020-01'); self.assertEqual(dam['source'],'historical_only'); self.assertEqual(aggregate(r)['current_coverage_pct'],0)
    def test_no_forced_growth(self):
        old={'stages':current_rows({'stages':[item('dam_body',80)]},None,'2020-01')}
        r=current_rows({'stages':[item('dam_body',60)]},old,'2020-02'); self.assertEqual(next(x for x in r if x['id']=='dam_body')['progress_estimate']['percent'],60)
    def test_prompt_first_and_update(self):
        self.assertIn('基准进度不等于0%',build_update_prompt({},[],'2020-01'))
        old={'date':'2020-01','stages':current_rows({'stages':[item('dam_body',30)]},None,'2020-01')}
        p=build_update_prompt({},[old],'2020-02'); self.assertIn('永久基准',p); self.assertIn('2020-01',p)
    def test_dates(self):
        with self.assertRaises(ValueError): date_key('2020-13')
if __name__=='__main__': unittest.main()
