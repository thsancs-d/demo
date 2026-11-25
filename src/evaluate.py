"""Compare the final known dam fill milestone with photo-based estimates."""
import argparse,json
from pathlib import Path

def evaluate(labels, reports):
    truth = {r['month']:r for r in labels['records'] if r.get('dam_fill_percent') == 100}
    rows=[]
    for report in reports:
        meta=report.get('meta',{}); month=meta.get('after_date')
        if month not in truth or meta.get('execution_mode')!='live': continue
        if (meta.get('context') or {}).get('project_name') != labels.get('project'): continue
        dam=next((r for r in report.get('progress',{}).get('stages',[]) if r.get('id')=='dam_body'),{})
        est=dam.get('progress_estimate'); phase=dam.get('phase','unclear')
        value=est['percent'] if est else None
        verdict='无法估算' if value is None else '与填筑完成标签一致' if value==100 else '与填筑完成标签不一致（需复核）'
        rows.append({'date':month,'label':'坝体填筑完成','label_percent':100,'predicted_visual_percent':value,'predicted_range_pct':est['range_pct'] if est else None,'endpoint_difference_pp':round(value-100,2) if value is not None else None,'predicted_phase':phase,'verdict':verdict,'note':'仅验证坝体填筑完成节点；不能用外观估计验证体积误差或全水库进度。'})
    return rows

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--labels',default='datasets/aigawa/labels.json');p.add_argument('--reports',default='output/aigawa_v3');a=p.parse_args()
    labels=json.loads(Path(a.labels).read_text()); root=Path(a.reports)
    rows=evaluate(labels,[json.loads(f.read_text()) for f in sorted(root.glob('*/vlm_raw.json'))])
    print(json.dumps(rows,ensure_ascii=False,indent=2))
    if not rows: print('尚无可比较的线上报告；不生成虚假准确率。')
if __name__=='__main__':main()
