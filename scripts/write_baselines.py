import os  # Configurable workspace; no machine-specific paths.
import csv,json
from pathlib import Path
R=(Path(os.environ.get("MAVENTWIN_WORKSPACE", Path(__file__).resolve().parents[1])).resolve())
rows=list(csv.DictReader((R/'metrics'/'FINAL_REPOSITORY_RESULTS.csv').open(encoding='utf-8')))
data=[]
for r in rows:
 data.append({'repo':r['repo'],'simple_effective_pom_diff':r['model_divergence'],'simple_dependency_tree_diff':r['resolution_divergence'],'maventwin_meaningful':r['meaningful_divergence'],'mvnup_relation':r['mvnup_relation']})
with (R/'metrics'/'BASELINE_RESULTS.csv').open('w',newline='',encoding='utf-8') as f:
 w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)
(R/'metrics'/'BASELINE_RESULTS.json').write_text(json.dumps({'scope':'all 150 frozen rows; UNKNOWN retained','rows':data},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'rows':len(data),'pom_diff':sum(x['simple_effective_pom_diff']=='true' for x in data),'tree_diff':sum(x['simple_dependency_tree_diff']=='true' for x in data)}))
