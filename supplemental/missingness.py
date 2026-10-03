from experiments import *
from collections import Counter,defaultdict
import statistics
def describe(values):
    x=sorted(values)
    return {'n':len(x),'median':statistics.median(x) if x else None,'min':min(x) if x else None,'max':max(x) if x else None}
def run():
    frozen=read(ROOT/'final_evidence_v1/samples/FROZEN_POPULATION.csv');samples={x['repo']:x for x in read(ROOT/'samples/scale_samples.csv')}
    records=[]
    retry={x['repo']:x for x in json.loads((OUT/'acquisition_retry/results.json').read_text())}
    verified={x['repo']:x for x in json.loads((CODE/'ACTIVITY_METADATA.json').read_text())} if (CODE/'ACTIVITY_METADATA.json').exists() else {}
    for f in frozen:
        if f['recovery_status'] not in ['POM_COMPLETE','NETWORK_UNKNOWN']:continue
        sid=f['repo'].replace('/','__');inc=f['recovery_status']=='POM_COMPLETE'
        path=(ROOT/'final_evidence_v1/snapshots'/sid/'pom.xml') if inc else (OUT/'acquisition_retry'/sid/'pom.xml')
        row=dict(repo=f['repo'],commit=f['commit'],group='retained' if inc else 'acquisition_unknown',stratum=samples[f['repo']]['stratum'],root_available=path.exists(),root_pom_bytes='',root_module_count='',root_dependency_count='',root_plugin_count='',commit_date=samples[f['repo']].get('commit_date',''),activity_date_valid=False)
        # Some original acquisition records substituted collection time for commit time; retain and flag rather than treating as activity.
        row['activity_date_valid']=bool(verified.get(f['repo'],{}).get('commit_date_verified'))
        row['verified_commit_date']=verified.get(f['repo'],{}).get('commit_date_verified','')
        row['frozen_commit_age_days']=''
        if row['activity_date_valid']:
            date=datetime.fromisoformat(row['verified_commit_date'].replace('Z','+00:00'));row['frozen_commit_age_days']=(datetime(2026,10,3,tzinfo=timezone.utc)-date).total_seconds()/86400
        if path.exists():
            try:
                r=ET.parse(path).getroot();row.update(root_pom_bytes=path.stat().st_size,root_module_count=len(r.findall('m:modules/m:module',NS)),root_dependency_count=len(r.findall('m:dependencies/m:dependency',NS)),root_plugin_count=len(r.findall('m:build/m:plugins/m:plugin',NS)))
            except Exception as e:row['parse_error']=str(e)
        records.append(row)
    summary={'groups':{},'retry':dict(Counter(x['status'] for x in retry.values())),'metrics_definition':'Root declared modules/dependencies/plugins, not recursive reactor size; all root POMs at the original commits.','activity_note':'Original timestamps containing fractional collection-time precision are flagged as unverified; no star counts are used because original stars=0 were placeholders.'}
    for group in ['retained','acquisition_unknown']:
        subset=[x for x in records if x['group']==group]
        summary['groups'][group]={'total':len(subset),'roots_available':sum(x['root_available'] for x in subset),'strata':dict(Counter(x['stratum'] for x in subset)),'metrics':{k:describe([x[k] for x in subset if isinstance(x[k],(int,float))]) for k in ['root_pom_bytes','root_module_count','root_dependency_count','root_plugin_count','frozen_commit_age_days']}}
    summary['cliffs_delta_lost_vs_retained']={}
    for key in ['root_pom_bytes','root_module_count','root_dependency_count','root_plugin_count','frozen_commit_age_days']:
        a=[x[key] for x in records if x['group']=='acquisition_unknown' and isinstance(x[key],(int,float))];b=[x[key] for x in records if x['group']=='retained' and isinstance(x[key],(int,float))]
        summary['cliffs_delta_lost_vs_retained'][key]=sum((x>y)-(x<y) for x in a for y in b)/(len(a)*len(b)) if a and b else None
    with (CODE/'MISSINGNESS_FEATURES.csv').open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)
    dump(CODE/'MISSINGNESS_SUMMARY.json',summary);print(json.dumps(summary,indent=2),flush=True)
if __name__=='__main__':run()
