import argparse,json,subprocess,tempfile,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'scripts'))
from run_scale_experiment import R,normalized_model,plan_from_model,flatten_tree
def main():
 p=argparse.ArgumentParser(); p.add_argument('--repo',required=True); p.add_argument('--maven-a',default='M3'); p.add_argument('--maven-b',default='M4'); a=p.parse_args(); repo=Path(a.repo); result={'model':{},'dependency_resolution':{},'execution_plan':{},'validation':{},'classification':[],'likely_causes':[]}
 for label,rt in [('a',a.maven_a.lower()),('b',a.maven_b.lower())]:
  with tempfile.TemporaryDirectory() as td:
   model=Path(td)/'effective.xml'; tree=Path(td)/'tree.json'; paths=json.loads((R/'protocol'/'runtime_paths.json').read_text()); cache=R/'tools'/'cache'/('scale-m3' if rt=='m3' else 'scale-m4')
   cmd=[str(Path(paths[rt])/'bin'/'mvn.cmd'),'-B','-ntp','-N','-s',str(R/'protocol'/'settings.xml'),'-gs',str(R/'protocol'/'settings.xml'),f'-Dmaven.repo.local={cache}','org.apache.maven.plugins:maven-help-plugin:3.5.1:effective-pom',f'-Doutput={model}','org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree','-DoutputType=json',f'-DoutputFile={tree}','validate']
   cp=subprocess.run(cmd,cwd=repo,text=True,capture_output=True); result['validation'][label]={'exit_code':cp.returncode}; result['model'][label]=normalized_model(model) if model.exists() else None; result['execution_plan'][label]=plan_from_model(model) if model.exists() else None; result['dependency_resolution'][label]=flatten_tree(json.loads(tree.read_text())) if tree.exists() else None
 ma,mb=result['model'].get('a'),result['model'].get('b'); da,db=result['dependency_resolution'].get('a'),result['dependency_resolution'].get('b'); pa,pb=result['execution_plan'].get('a'),result['execution_plan'].get('b')
 if ma!=mb: result['classification'].append('MODEL_DIFFERENCE'); result['likely_causes'].append('MODEL_OR_PLUGIN_SELECTION')
 if da!=db: result['classification'].append('DEPENDENCY_RESOLUTION_DIFFERENCE'); result['likely_causes'].append('DEPENDENCY_MEDIATION')
 if pa!=pb: result['classification'].append('EXECUTION_PLAN_DIFFERENCE'); result['likely_causes'].append('PLUGIN_EXECUTION_INJECTION')
 if result['validation'].get('a',{}).get('exit_code')==0 and result['validation'].get('b',{}).get('exit_code')!=0: result['classification'].append('M3_PASS_M4_FAIL')
 print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__': main()
