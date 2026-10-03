"""Supplementary analyses of the original frozen study; never overwrite inputs."""
import os
from pathlib import Path
from collections import Counter, defaultdict
import csv, hashlib, json, re, statistics, difflib, xml.etree.ElementTree as ET

ROOT=Path(os.environ.get('MAVENTWIN_WORKSPACE_ROOT',os.environ.get('MAVENTWIN_WORKSPACE',Path(__file__).resolve().parents[1]))).resolve()
OUT=Path(__file__).resolve().parent
DATA=Path(os.environ.get('MAVENTWIN_EXPERIMENT_ROOT',ROOT/'supplementary_results')).resolve()
NS={'m':'http://maven.apache.org/POM/4.0.0'}
def read(p):
    with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def write(name, rows, fields=None):
    p=OUT/name;p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields or list(rows[0]));w.writeheader();w.writerows(rows)
def dump(name,v):
    (OUT/name).write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')
def digest(v):return hashlib.sha256(v.encode()).hexdigest()

def analyses():
    paper=read(ROOT/'final_evidence_v1/FINAL_PAPER_RESULTS.csv')
    deltas=read(ROOT/'final_evidence_v1/MODEL_DELTAS_FINAL.csv')
    prov=read(ROOT/'artifacts/reviewer_revision/model/model_delta_provenance.csv')
    assert len(deltas)==len(prov)==269
    lookup=defaultdict(list)
    for p in prov:
        entity=p['plugin_groupId']+':'+p['plugin_artifactId']
        if p['execution_id']:entity+=':'+p['execution_id']
        lookup[(p['repo'],p['field_category'],entity,p['configuration_path'],p['maven3_value_sha256'],p['maven4_value_sha256'])].append(p)
    retained=defaultdict(set);rows=[]
    for d in deltas:
        key=(d['repo'],d['category'],d['entity'],d['field'],digest(d['m3_value']),digest(d['m4_value']))
        matched=lookup.get(key,[])
        if not matched:raise ValueError('Unmatched provenance row: '+repr(key[:4]))
        label=matched[0]['provenance_class']
        common=(d['category']=='PLUGIN_EXECUTION_DECLARATION_CHANGED' and d['field']=='configuration' and d['entity'] in ['org.apache.maven.plugins:maven-site-plugin:default-site','org.apache.maven.plugins:maven-site-plugin:default-deploy'])
        runtime=label in ['DEFAULT_LIFECYCLE','MAVEN_RUNTIME_SYNTHESIZED']
        source=label in ['USER_ROOT_POM','USER_MODULE_POM']
        retained['all'].add(d['repo'])
        if not common:retained['remove_two_common'].add(d['repo'])
        if not runtime:retained['remove_all_runtime'].add(d['repo'])
        if source:retained['source_linked_only'].add(d['repo'])
        if label=='UNKNOWN':retained['unresolved_only'].add(d['repo'])
        rows.append({**d,'provenance_class':label,'common_site_signature':str(common).lower(),'runtime_default':str(runtime).lower()})
    stages=[('all','All selected-field differences'),('remove_two_common','Remove the two ubiquitous site-configuration signatures'),('remove_all_runtime','Remove all runtime/default provenance rows'),('source_linked_only','Keep source-linked provenance rows only'),('unresolved_only','Keep unresolved provenance rows only')]
    ablation=[dict(stage=k,description=desc,repositories=len(retained[k]),denominator=50,repository_ids=';'.join(sorted(retained[k]))) for k,desc in stages]
    write('MODEL_ABLATION.csv',ablation);write('MODEL_ABLATION_ROWS.csv',rows)
    # Raw byte / line comparisons are descriptive baselines, using the identical four XML inputs.
    benchmark=[]
    for p in paper:
        if p['model_comparable']!='MODEL_COMPARABLE':continue
        base=ROOT/'final_evidence_v1/measurements'/p['repo'].replace('/','__')
        texts={(rt,n):(base/f'{rt}-r{n}/effective-pom.xml').read_text(encoding='utf-8-sig') for rt in ['m3','m4'] for n in [1,2]}
        a=texts['m3',1].splitlines();b=texts['m4',1].splitlines()
        changed=sum(len(x[1:])>=0 for x in [])
        diff=list(difflib.ndiff(a,b));count=sum(x.startswith(('+ ','- ')) for x in diff)
        ds=[x for x in deltas if x['repo']==p['repo']]
        benchmark.append(dict(repo=p['repo'],raw_cross_runtime_different=texts['m3',1]!=texts['m4',1],raw_m3_within_runtime_different=texts['m3',1]!=texts['m3',2],raw_m4_within_runtime_different=texts['m4',1]!=texts['m4',2],raw_changed_lines=count,structured_delta_rows=len(ds),maventwin_model_positive=p['model_semantic_divergence']))
    write('RAW_XML_BASELINE.csv',benchmark)
    baseline_summary={'pairs':len(benchmark),'raw_cross_runtime_positive':sum(x['raw_cross_runtime_different'] for x in benchmark),'raw_m3_repeat_different':sum(x['raw_m3_within_runtime_different'] for x in benchmark),'raw_m4_repeat_different':sum(x['raw_m4_within_runtime_different'] for x in benchmark),'median_raw_changed_lines':statistics.median(x['raw_changed_lines'] for x in benchmark),'median_structured_delta_rows':statistics.median(x['structured_delta_rows'] for x in benchmark),'classification_note':'All stable model pairs are selected-field positive; these inputs cannot estimate between-runtime false-positive specificity.'}
    dump('ANALYSIS_SUMMARY.json',{'ablation':ablation,'raw_xml':baseline_summary})
    print(json.dumps({'ablation':[(x['stage'],x['repositories']) for x in ablation],'baseline':baseline_summary},ensure_ascii=False),flush=True)

if __name__=='__main__':analyses()
