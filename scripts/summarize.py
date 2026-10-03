from differential import *
from mediation import parse_tree,winner_changes
def read(p):return json.loads(p.read_text(encoding='utf-8')) if p.exists() else None
def textlog(base):
    return '\n'.join(p.read_text(encoding='utf-8',errors='replace') for p in [base/'stdout.txt',base/'stderr.txt'] if p.exists())
def summarize():
    lock=read(R/'samples'/'sample_lock.json');rows=[]
    if not lock:return []
    for s in lock['samples']:
        sid=s['id'];base=R/'metadata_diff'/sid
        if not (base/'pre-baseline-observations.json').exists():continue
        diffs=[compare(s,n) for n in [1,2]];states={(rt,n):state(s,rt,n) for rt in ['m3','m4'] for n in [1,2]}
        mediation_differences=[]
        for n in [1,2]:
            parsed=[]
            for rt in ['m3','m4']:
                fp=base/f'{rt}-r{n}'/'mediation'/'dependency-tree-verbose.txt'
                nodes=parse_tree(fp.read_text(encoding='utf-8-sig')) if fp.exists() else []
                if fp.exists():dump(fp.parent/'mediation-evidence.json',nodes)
                parsed.append(nodes)
            mediation_differences.append(winner_changes(parsed[0],parsed[1],diffs[n-1]['tree_differences'] or []))
        dump(base/'mediation-differences.json',{'rounds':mediation_differences,'confirmed':mediation_differences[0]==mediation_differences[1]})
        stable={k:all(states[rt,1][k]==states[rt,2][k] for rt in ['m3','m4']) for k in ['model','tree','validate']}
        infra=[];failures=[]
        for (rt,n),st in states.items():
            for k,obs in st.items():
                if obs['status']!='PASS':
                    log=textlog(base/f'{rt}-r{n}'/k)
                    failures.append({'runtime':rt,'round':n,'command':k,'status':obs['status'],'errors':[x for x in log.splitlines() if '[ERROR]' in x][:12]})
                    # Warnings about optional prefix metadata did not cause the JAXB copyright failure.
                    known_project_failure=sid=='eclipse-ee4j__jaxb-api' and k=='validate' and 'Copyright checking failed' in log and '[ERROR] Errors: 6' in log
                    if obs['status'] in ['TIMEOUT','NOT_RUN','PARSE_ERROR'] or (not known_project_failure and re.search('Could not transfer|handshake|Connection reset|connect timed out',log,re.I)):infra.append(f'{rt}-r{n}/{k}')
        coord_conflicts=[]
        # Only immutable artifact bytes, not runtime-local tracking metadata, are compared.
        invs=[read(base/f'{rt}-r2'/'model'/'cache-artifacts.json') or {} for rt in ['m3','m4']]
        for key in set(invs[0])&set(invs[1]):
            if key.endswith(('.pom','.jar')) and invs[0][key]['sha256']!=invs[1][key]['sha256']:coord_conflicts.append(key)
        model_confirmed=bool(diffs[0]['model_differences']) and stable['model']
        tree_confirmed=bool(diffs[0]['tree_differences']) and stable['tree']
        regression=all(x['statuses']['validate']==['PASS','FAIL'] for x in diffs) and stable['validate'] and not any('/validate' in x for x in infra)
        labels=[]
        if model_confirmed:labels.append('MODEL_DIVERGENCE')
        if tree_confirmed:labels.append('RESOLUTION_DIVERGENCE')
        if regression:
            logs=textlog(base/'m4-r1'/'validate')
            labels.append('PLUGIN_COMPATIBILITY_FAILURE' if re.search('NoSuchMethodError|ClassNotFoundException|NoClassDefFoundError|UnsupportedOperationException',logs) else 'MAVEN4_VALIDATION_FAILURE')
        for kind in ['model','tree']:
            if stable[kind] and all(d['statuses'][kind]==['PASS','FAIL'] for d in diffs) and not any('/'+kind in x for x in infra):
                logs=textlog(base/'m4-r1'/kind)
                if re.search('NoSuchMethodError|ClassNotFoundException|NoClassDefFoundError|UnsupportedOperationException|AbstractMethodError|PluginIncompatibleException|requires Maven',logs):
                    if 'PLUGIN_COMPATIBILITY_FAILURE' not in labels:labels.append('PLUGIN_COMPATIBILITY_FAILURE')
        unknown=bool(infra or coord_conflicts or any(not v for v in stable.values()))
        if unknown:labels.append('UNKNOWN_INFRA')
        if not labels:labels=['IDENTICAL'] if all(all(v=='PASS' for v in pair) for pair in diffs[0]['statuses'].values()) else ['UNKNOWN_INFRA'];unknown=labels==['UNKNOWN_INFRA']
        row={'id':sid,'repo':s['repo'],'stratum':s['stratum'],'packaging':s['packaging'],'module_count':len(s['modules']),'label':'MULTIPLE' if len(labels)>1 else labels[0],'labels':labels,'confirmation':'NONDETERMINISTIC_UNKNOWN' if not all(stable.values()) else 'CONFIRMED','stable':stable,'model_divergence':model_confirmed,'resolution_divergence':tree_confirmed,'m3_pass_m4_fail':regression,'unknown':unknown,'infra_commands':infra,'artifact_byte_conflicts':coord_conflicts,'statuses':diffs[0]['statuses'],'validation_category':diffs[0]['validation_category'],'model_delta_count':len(diffs[0]['model_differences'] or []),'graph_delta_count':len(diffs[0]['tree_differences'] or []),'failures':failures}
        adjud=read(R/'mvnup'/sid/'adjudication.json')
        row['baseline']=adjud or {'status':'PENDING_ADJUDICATION'}
        semantic=read(base/'semantic-adjudication.json')
        if semantic:row['semantic_adjudication']=semantic
        dump(base/'classification.json',row);rows.append(row)
    dump(R/'metrics'/'repo_results.json',rows)
    counts={'samples_total':len(lock['samples']),'completed_repos':len(rows),'analyzable_repos':sum(not x['unknown'] for x in rows),'model_divergences':sum(x['model_divergence'] for x in rows),'resolution_divergences':sum(x['resolution_divergence'] for x in rows),'m3_pass_m4_fail':sum(x['m3_pass_m4_fail'] for x in rows),'unknown_repos':sum(x['unknown'] for x in rows),'unknown_rate':sum(x['unknown'] for x in rows)/30,'mvnup_misses':sum(x['baseline'].get('status')=='NOT_DETECTED' or any(c.get('detection')=='NOT_DETECTED' for c in x['baseline'].get('cases',[])) for x in rows)}
    dump(R/'metrics'/'counts.json',counts);print(json.dumps(counts,indent=2));return rows
if __name__=='__main__':summarize()
