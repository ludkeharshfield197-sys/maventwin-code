import os  # Configurable workspace; no machine-specific paths.
import json
from pathlib import Path
R=(Path(os.environ.get("MAVENTWIN_WORKSPACE", Path(__file__).resolve().parents[1])).resolve())
p=R/'metrics'/'FINAL_SUMMARY.json'
s=json.loads(p.read_text(encoding='utf-8'))
s['maven4_ga']='Maven 4 GA not listed on Apache Maven download page checked 2026-10-01; fixed study runtime remains Maven 4.0.0-rc-7'
p.write_text(json.dumps(s,ensure_ascii=False,indent=2),encoding='utf-8')
p=R/'MAVENTWIN_FINAL_STUDY_REPORT_ZH.md'
t=p.read_text(encoding='utf-8').replace('状态：EXPERIMENTS_FINISHED','MAVEN4_GA_STATUS: Maven 4 GA not listed on Apache Maven download page checked 2026-10-01; no GA rerun performed.\n\n状态：EXPERIMENTS_FINISHED')
p.write_text(t,encoding='utf-8')
