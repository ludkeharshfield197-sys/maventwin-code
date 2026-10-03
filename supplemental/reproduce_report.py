"""Recompute the supplementary tables from a prepared input workspace; no Maven execution."""
from pathlib import Path
import argparse,json,os,subprocess,sys,csv

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workspace',required=True,type=Path)
    p.add_argument('--experiment-root',required=True,type=Path)
    p.add_argument('--figures',action='store_true')
    a=p.parse_args();root=a.workspace.resolve();data=a.experiment_root.resolve();here=Path(__file__).resolve().parent
    env=os.environ.copy();env.update(MAVENTWIN_WORKSPACE=str(root),MAVENTWIN_WORKSPACE_ROOT=str(root),MAVENTWIN_EXPERIMENT_ROOT=str(data))
    required=['final_evidence_v1/FINAL_PAPER_RESULTS.csv','final_evidence_v1/MODEL_DELTAS_FINAL.csv','artifacts/reviewer_revision/model/model_delta_provenance.csv','protocol/runtime_paths.json']
    missing=[x for x in required if not (root/x).exists()]
    if missing:p.error('Missing input files: '+', '.join(missing))
    for script in ['primary_summary.py','analysis.py','missingness.py','summarize_experiments.py','summarize_extended.py','rq3_refine.py','serialization_controls.py']:
        r=subprocess.run([sys.executable,str(here/script)],cwd=root,env=env)
        if r.returncode:raise SystemExit(r.returncode)
    subprocess.run([sys.executable,str(here/'reviewer_followup_analysis.py'),'details'],cwd=root,env=env,check=True)
    subprocess.run([sys.executable,str(here/'summarize_reviewer_followup.py')],cwd=root,env=env,check=True)
    report={}
    for name in ['PRIMARY_STUDY_SUMMARY','ANALYSIS_SUMMARY','MISSINGNESS_SUMMARY','EXPERIMENT_SUMMARY','EXTENDED_SUMMARY','RQ3_REFINED_SUMMARY','SERIALIZATION_CONTROL_SUMMARY','FOLLOWUP_ANALYSIS_SUMMARY','REVIEWER_FOLLOWUP_SUMMARY']:
        report[name]=json.loads((here/(name+'.json')).read_text(encoding='utf-8'))
    (here/'REPRODUCED_REPORT.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    if a.figures:
        env['MAVENTWIN_FIGURE_OUTPUT']=str(root/'analysis_outputs/figures')
        subprocess.run([sys.executable,str(here/'update_figures.py')],cwd=root,env=env,check=True)
    print('Recomputed report:',here/'REPRODUCED_REPORT.json')
if __name__=='__main__':main()
