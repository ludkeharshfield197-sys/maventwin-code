from summarize_experiments import *
import sys
sys.path.insert(0,str(ROOT/'scripts'))
from final_evidence_runner import extract_model,model_deltas

def records(base,runtimes=('m3','m4')):
    return {rt:[json.loads(p.read_text()) for n in [1,2] if (p:=base/f'{rt}-r{n}/command.json').exists()] for rt in runtimes}
def outcomes(rs):return ';'.join('TIMEOUT' if r['timeout'] else ('PASS' if r['exit_code']==0 else 'FAIL') for r in rs)
def graphs_at(base,rt):
    vals=[]
    for n in [1,2]:
        p=base/f'{rt}-r{n}/tree.json';c=base/f'{rt}-r{n}/command.json'
        if p.exists() and c.exists():
            r=json.loads(c.read_text())
            if r['exit_code']==0 and not r['timeout']:vals.append(tree_nodes(json.loads(p.read_text(encoding='utf-8-sig'))))
    return vals
def stable_pair(base):
    vals={rt:graphs_at(base,rt) for rt in ['m3','m4']}
    stable=all(len(v)==2 and v[0]==v[1] for v in vals.values())
    return stable,(vals['m3'][0]!=vals['m4'][0] if stable else ''),vals
def core():
    rows=[]
    for name in ['pax-exam','neo4j-driver']:
        for variant in ['default','transitivity_false']:
            base=OUT/'minimal_graphs'/name/variant;r=records(base);stable,diff,vals=stable_pair(base)
            chosen={rt:sorted(set(':'.join(x[:3]) for x in vs[0] if x[1] in ['jcl-over-slf4j','netty-handler','netty-tcnative-classes'])) if vs else [] for rt,vs in vals.items()}
            rows.append(dict(case=name,variant=variant,m3=outcomes(r['m3']),m4=outcomes(r['m4']),stable=stable,different=diff,m3_versions=';'.join(chosen['m3']),m4_versions=';'.join(chosen['m4'])))
    csvwrite('MINIMAL_GRAPH_SUMMARY.csv',rows)
    apply=[]
    for repo in ['twilio__twilio-java','apache__curator','apache__commons-compress','spring-projects__spring-data-neo4j']:
        base=OUT/'apply_cases'/repo;r=records(base/'post');stable,diff,_=stable_pair(base/'post')
        edit=json.loads((base/'edit_manifest.json').read_text())
        a={x['path']:x['sha256'] for x in edit['before']};b={x['path']:x['sha256'] for x in edit['after']}
        changed=[k for k in sorted(set(a)|set(b)) if a.get(k)!=b.get(k)]
        apply.append(dict(repo=repo,apply_success=edit['apply_result']['exit_code']==0,m3_post=outcomes(r['m3']),m4_post=outcomes(r['m4']),graph_stable=stable,graph_different=diff,changed_files=';'.join(changed)))
    csvwrite('APPLY_SUMMARY.csv',apply)
    release=[]
    for base in sorted((OUT/'release_sensitivity').iterdir()):
        if not base.is_dir():continue
        r=records(base,('m310',));gs=graphs_at(base,'m310');stable=len(gs)==2 and gs[0]==gs[1]
        prior=OUT/'graph/jdk21'/base.name/'baseline';old={rt:graphs_at(prior,rt) for rt in ['m3','m4']}
        release.append(dict(repo=base.name,maven310=outcomes(r['m310']),graph_stable=stable,equals_maven3916=(gs[0]==old['m3'][0] if stable and old['m3'] else ''),equals_maven4rc7=(gs[0]==old['m4'][0] if stable and old['m4'] else '')))
    csvwrite('RELEASE_SENSITIVITY.csv',release)
    return dict(minimal=rows,apply=apply,release=release)

def api_only():
    rows=[];deltas=[]
    for case in sorted((OUT/'api_without_help/runs').glob('*')):
        vals={rt:[] for rt in ['m3','m4']};rs=records(case)
        for rt in vals:
            for n in [1,2]:
                p=case/f'{rt}-r{n}/observer/000-model.xml'
                if p.exists():
                    m=extract_model(p);m.pop('properties',None);vals[rt].append(m)
        stable=all(len(v)==2 and v[0]==v[1] for v in vals.values())
        d=[]
        if stable:_,d=model_deltas(case.name.replace('__','/'),'',* [vals[rt][0] for rt in ['m3','m4']]);deltas+=d
        original=[extract_model(ROOT/'final_evidence_v1/measurements'/case.name/f'{rt}-r1/effective-pom.xml') for rt in ['m3','m4']]
        _,od=model_deltas(case.name,'',*original)
        key=lambda x:(x['category'],x['entity'],x['field'])
        match=len(set(map(key,d))&set(map(key,od)))
        rows.append(dict(repo=case.name,api_captures=sum(map(len,vals.values())),api_within_runtime_stable=stable,cross_runtime_difference=(vals['m3'][0]!=vals['m4'][0] if stable else ''),delta_rows=len(d),original_delta_keys_recovered=match,original_delta_keys=len(set(map(key,od))),m3_validate=outcomes(rs['m3']),m4_validate=outcomes(rs['m4'])))
    csvwrite('API_WITHOUT_HELP.csv',rows);csvwrite('API_WITHOUT_HELP_DELTAS.csv',deltas);return rows

def builds():
    rows=[]
    for base in sorted((OUT/'build_impact').glob('*')):
        if not base.is_dir():continue
        rs=records(base);logs=[];artifacts=[];categories=[]
        for rt in ['m3','m4']:
            for n in [1,2]:
                arm=base/f'{rt}-r{n}';cmd=arm/'command.json'
                if not cmd.exists():continue
                r=json.loads(cmd.read_text());log=(arm/'stdout.txt').read_text(encoding='utf-8',errors='replace')
                invocations=[x.strip() for x in log.splitlines() if re.search(r'--- .*:.*:.*',x)]
                logs.append(dict(runtime=rt,repeat=n,plugin_invocations=invocations))
                errors=[x for x in log.splitlines() if '[ERROR]' in x]
                env=any(x in log for x in ['Could not resolve','could not be resolved','Connection reset','Remote host terminated','handshake','Read timed out','PKIX','not found in the local repository','has not been downloaded','No plugin found'])
                prerequisite='Cannot find matching toolchain definitions' in log or 'No matching toolchains found' in log
                category='TIME_LIMIT' if r['timeout'] else ('PASS' if r['exit_code']==0 else ('ENVIRONMENT_PREREQUISITE' if prerequisite else ('RESOLUTION_ENVIRONMENT' if env else 'PROJECT_BUILD_FAILURE')))
                categories.append(dict(runtime=rt,repeat=n,category=category,diagnostic=' | '.join(errors[:3])))
                p=arm/'target_manifest.json'
                if p.exists():artifacts.append(dict(runtime=rt,repeat=n,manifest=json.loads(p.read_text())))
        dump(base/'actual_invocations.json',logs);dump(base/'build_classification.json',categories)
        rows.append(dict(repo=base.name,runs=sum(map(len,rs.values())),m3=outcomes(rs['m3']),m4=outcomes(rs['m4']),successful_runs=sum(r['exit_code']==0 and not r['timeout'] for v in rs.values() for r in v),invocation_records=len(logs),categories=';'.join(x['runtime']+'-r'+str(x['repeat'])+':'+x['category'] for x in categories)))
    csvwrite('BUILD_IMPACT.csv',rows);return rows

def plans():
    rows=[]
    for area in ['plan_recheck','central_plans','late_package_plans','late_central_plans','late_central_materialized','late_central_completed']:
        for base in sorted((OUT/area).glob('*')):
            if not base.is_dir():continue
            vals={rt:[] for rt in ['m3','m4']};central={rt:[] for rt in vals}
            for rt in vals:
                for n in [1,2]:
                    p=base/'runs'/f'{rt}-r{n}/observer/000-plan.tsv'
                    if p.exists():
                        ps=list(csv.DictReader(p.open(encoding='utf-8-sig'),delimiter='\t'))
                        vals[rt].append([(x['groupId'],x['artifactId'],x['version'],x['executionId'],x['goal']) for x in ps])
                        central[rt].append(';'.join(x['executionId']+':'+x['goal'] for x in ps if x['artifactId']=='central-publishing-maven-plugin'))
            stable=all(len(v)==2 and v[0]==v[1] for v in vals.values())
            rows.append(dict(experiment=area,repo=base.name,plan_records=sum(map(len,vals.values())),within_runtime_stable=stable,ordered_invocations_different=(vals['m3'][0]!=vals['m4'][0] if stable else ''),m3_central=' | '.join(central['m3']),m4_central=' | '.join(central['m4'])))
    csvwrite('PLAN_RECHECK.csv',rows);return rows

def reactors():
    rows=[]
    for area in ['reactor_tests','gson_targeted_tests','reactor_repaired','reactor_materialized','reactor_central_materialized','reactor_closure']:
        for base in sorted((OUT/area).glob('*')):
            if not base.is_dir():continue
            rs=records(base/'runs');counts={rt:[] for rt in ['m3','m4']}
            for rt in counts:
                for n in [1,2]:
                    p=base/'runs'/f'{rt}-r{n}/test_reports.json'
                    if p.exists():
                        tests=json.loads(p.read_text());counts[rt].append({k:sum(int(x.get(k,0) or 0) for x in tests) for k in ['tests','failures','errors','skipped']})
            artifacts=[]
            for rt in ['m3','m4']:
                for n in [1,2]:
                    p=base/'runs'/f'{rt}-r{n}/artifacts.json'
                    if p.exists():artifacts.append({x['path']:x['sha256'] for x in json.loads(p.read_text())})
            common=set.intersection(*(set(x) for x in artifacts)) if len(artifacts)==4 else set()
            identical=all(len({x[k] for x in artifacts})==1 for k in common) if common else ''
            rows.append(dict(experiment=area,repo=base.name,runs=sum(map(len,rs.values())),m3=outcomes(rs['m3']),m4=outcomes(rs['m4']),m3_test_counts=json.dumps(counts['m3']),m4_test_counts=json.dumps(counts['m4']),common_artifact_paths=';'.join(sorted(common)),common_artifacts_identical=identical))
    csvwrite('REACTOR_AND_TESTS.csv',rows);return rows

def main():
    data=core();data.update(api_only=api_only(),builds=builds(),plans=plans(),reactors=reactors());dump(CODE/'EXTENDED_SUMMARY.json',data)
    print(json.dumps({k:v if k in [] else len(v) for k,v in data.items()}))
if __name__=='__main__':main()
