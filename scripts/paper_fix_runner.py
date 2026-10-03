import os  # Configurable workspace; no machine-specific paths.
import csv, json, os, re, shutil, subprocess, sys, time, hashlib, urllib.request
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = (Path(os.environ.get("MAVENTWIN_WORKSPACE", Path(__file__).resolve().parents[1])).resolve())
OUT = ROOT / 'paper_fix_v1'
SAMPLES = ROOT / 'samples' / 'scale_samples.csv'
NS = {'m':'http://maven.apache.org/POM/4.0.0'}
RUNTIME = json.loads((ROOT/'protocol'/'runtime_paths.json').read_text())
SETTINGS = ROOT/'protocol'/'settings.xml'

def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')

def read_rows(path):
    with path.open(encoding='utf-8') as f:
        return list(csv.DictReader(f))

def raw_url(repo, commit, path):
    u = f'https://raw.githubusercontent.com/{repo}/{commit}/{path}'
    req = urllib.request.Request(u, headers={'User-Agent':'maventwin-paper-fix'})
    try:
        with urllib.request.urlopen(req, timeout=30) as r: return r.read()
    except Exception: return None

def tree_api(repo, commit):
    u = f'https://api.github.com/repos/{repo}/git/trees/{commit}?recursive=1'
    req = urllib.request.Request(u, headers={'User-Agent':'maventwin-paper-fix','Accept':'application/vnd.github+json'})
    with urllib.request.urlopen(req, timeout=45) as r: return json.loads(r.read())

def acquire_snapshots(rows):
    snap_root = OUT/'snapshots'; sample_dir = OUT/'samples'; sample_dir.mkdir(parents=True, exist_ok=True)
    result=[]
    for i,row in enumerate(rows,1):
        sid=row['id']; dst=snap_root/sid
        rec={'repo':row['repo'],'commit':row['commit'],'pom_count':0,'root_pom':'','module_count_observed':0,'mvn_config_present':False,'extensions_present':False,'status':'POM_ACQUISITION_FAILED'}
        if not row.get('analyzable','').lower()=='true' or not re.fullmatch(r'[0-9a-f]{40}', row.get('commit','')):
            rec['status']='POM_ACQUISITION_FAILED'; result.append(rec); continue
        try:
            local=Path(row.get('source_path','')) if row.get('source_path') else None
            local_paths=[]
            if local and local.exists() and (local/'pom.xml').exists():
                for p in local.rglob('*'):
                    if p.is_file() and (p.name=='pom.xml' or str(p.relative_to(local)).replace('\\','/').startswith('.mvn/')):
                        local_paths.append(str(p.relative_to(local)).replace('\\','/'))
                paths=local_paths
            else:
                data=tree_api(row['repo'],row['commit'])
                paths=[x['path'] for x in data.get('tree',[]) if x.get('type')=='blob' and (x['path']=='pom.xml' or x['path'].endswith('/pom.xml') or x['path'].startswith('.mvn/'))]
            if not any(p=='pom.xml' for p in paths): rec['status']='NO_MAVEN_MODEL'; result.append(rec); continue
            if dst.exists(): shutil.rmtree(dst)
            for p in sorted(paths):
                b=(local/p).read_bytes() if local and (local/p).exists() else raw_url(row['repo'],row['commit'],p)
                if b is None: continue
                q=dst/p; q.parent.mkdir(parents=True,exist_ok=True); q.write_bytes(b)
            poms=sorted(str(x.relative_to(dst)).replace('\\','/') for x in dst.rglob('pom.xml'))
            rec['pom_count']=len(poms); rec['root_pom']='pom.xml' if (dst/'pom.xml').exists() else ''
            rec['module_count_observed']=max(0,len(poms)-1)
            rec['mvn_config_present']=any(x.startswith('.mvn/') and x.endswith(('maven.config','jvm.config')) for x in paths)
            rec['extensions_present']=any(x=='.mvn/extensions.xml' for x in paths)
            root_pack,_,root_mods=pom_info(dst/'pom.xml')
            expected=set()
            for m in root_mods:
                q=(Path(m)/'pom.xml').as_posix()
                expected.add(q)
            rec['status']='POM_COMPLETE' if (dst/'pom.xml').exists() and expected.issubset(set(poms)) else 'POM_ACQUISITION_FAILED'
        except Exception as e:
            rec['error']=str(e)
        result.append(rec)
        print(f'SNAPSHOT {i}/{len(rows)} {sid} {rec["status"]}', flush=True)
    fields=['repo','commit','pom_count','root_pom','module_count_observed','mvn_config_present','extensions_present','status']
    with (sample_dir/'POM_COMPLETENESS.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(result)
    return result

def pom_info(path):
    try:
        r=ET.parse(path).getroot(); packaging=r.findtext('m:packaging','jar',NS); deps=r.findall('m:dependencies/m:dependency',NS)
        mods=[x.text.strip() for x in r.findall('m:modules/m:module',NS) if x.text and x.text.strip()]
        return packaging, bool(deps), mods
    except Exception: return 'UNKNOWN',False,[]

def freeze_targets(rows, completeness):
    by={x['repo']:x for x in completeness}; out=[]
    for row in rows:
        sid=row['id']; snap=OUT/'snapshots'/sid; root=snap/'pom.xml'; target=''; rule=''
        if by.get(row['repo'],{}).get('status')=='POM_COMPLETE' and root.exists():
            rp,rd,mods=pom_info(root)
            if rp!='pom' and rd: target='pom.xml'; rule='RULE_1_ROOT_NONPOM_WITH_DIRECT_DEPENDENCY'
            else:
                candidates=[]
                for p in sorted(snap.rglob('pom.xml')):
                    rel=str(p.relative_to(snap)).replace('\\','/')
                    if rel=='pom.xml': continue
                    pp,has,_=pom_info(p)
                    if pp!='pom' and has: candidates.append((rel,'RULE_2_FIRST_NONPOM_WITH_DIRECT_DEPENDENCY'))
                if candidates: target,rule=candidates[0]
                else:
                    jars=[]
                    for p in sorted(snap.rglob('pom.xml')):
                        rel=str(p.relative_to(snap)).replace('\\','/')
                        if rel=='pom.xml': continue
                        pp,_,_=pom_info(p)
                        if pp!='pom': jars.append((rel,'RULE_3_FIRST_NONPOM_MODULE'))
                    if jars: target,rule=jars[0]
                    else: target,rule='pom.xml','RULE_4_ROOT'
        out.append({'repo':row['repo'],'commit':row['commit'],'model_target_pom':'pom.xml','validation_target_pom':'pom.xml','resolution_target_pom':target,'selection_rule':rule})
    with (OUT/'samples'/'TARGET_POMS.csv').open('w',newline='',encoding='utf-8') as f:
        fields=list(out[0]); w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(out)
    return out

def run_cmd(argv,cwd,out,timeout=180):
    out.mkdir(parents=True,exist_ok=True); start=time.time()
    with (out/'stdout.txt').open('wb') as so,(out/'stderr.txt').open('wb') as se:
        env=os.environ.copy(); env['JAVA_HOME']=RUNTIME['jdk']; env['MAVEN_OPTS']=f'-Dmaven.multiModuleProjectDirectory={cwd}'
        p=subprocess.Popen(argv,cwd=str(cwd),env=env,stdout=so,stderr=se,stdin=subprocess.DEVNULL)
        timed=False
        try: code=p.wait(timeout)
        except subprocess.TimeoutExpired:
            timed=True; p.kill(); code=p.wait()
    rec={'argv':argv,'cwd':str(cwd),'exit_code':code,'timeout':timed,'elapsed_seconds':round(time.time()-start,3)}
    write_json(out/'command.json',rec); return rec

def canon_text(x):
    if x is None:return ''
    s=(x.text or '').strip(); s=re.sub(r'([A-Za-z]:\\|/[^ ]*/)([^ ]*)', lambda m:'<PATH>', s)
    return s

def dep_records(parent, tag):
    out=[]
    for d in parent.findall(tag,NS):
        def t(k,default=''): return d.findtext('m:'+k,default,NS)
        out.append({'groupId':t('groupId'),'artifactId':t('artifactId'),'version':t('version'),'type':t('type','jar'),'classifier':t('classifier'),'scope':t('scope','compile'),'optional':t('optional','false'),'exclusions':sorted((x.findtext('m:groupId','',NS)+':'+x.findtext('m:artifactId','',NS)) for x in d.findall('m:exclusions/m:exclusion',NS))})
    return sorted(out,key=lambda x:json.dumps(x,sort_keys=True))

def model_extract(path):
    r=ET.parse(path).getroot(); build=r.find('m:build',NS)
    plugins=[]; pm=[]; ex=[]
    def plugin_list(parent):
        z=[]
        if parent is None:return z
        for p in parent.findall('m:plugin',NS):
            gid=p.findtext('m:groupId','org.apache.maven.plugins',NS); aid=p.findtext('m:artifactId','',NS); ver=p.findtext('m:version','',NS)
            z.append({'groupId':gid,'artifactId':aid,'version':ver})
            for e in p.findall('m:executions/m:execution',NS):
                cfg=e.find('m:configuration',NS)
                ex.append({'plugin':gid+':'+aid,'execution_id':e.findtext('m:id','default',NS),'phase':e.findtext('m:phase','',NS),'goals':sorted(x.text or '' for x in e.findall('m:goals/m:goal',NS)),'configuration':ET.tostring(cfg,encoding='unicode') if cfg is not None else ''})
        return sorted(z,key=lambda x:(x['groupId'],x['artifactId']))
    plugins=plugin_list(build.find('m:plugins',NS) if build is not None else None); pm=plugin_list(build.find('m:pluginManagement/m:plugins',NS) if build is not None else None)
    props={x.tag.split('}',1)[-1]:canon_text(x) for x in r.findall('m:properties/*',NS)}
    return {'dependencies':dep_records(r,'m:dependencies/m:dependency'),'dependencyManagement':dep_records(r,'m:dependencyManagement/m:dependencies/m:dependency'),'active_plugins':plugins,'plugin_management':pm,'execution_declarations':sorted(ex,key=lambda x:json.dumps(x,sort_keys=True)),'modules':sorted(x.text or '' for x in r.findall('m:modules/m:module',NS)),'properties':props}

def do_measure(rows, targets, completeness):
    target_by={x['repo']:x for x in targets}; comp={x['repo']:x for x in completeness}; mroot=OUT/'measurements'; cache_root=OUT/'local_repos'; model_rows=[]; res_rows=[]; val_rows=[]
    for i,row in enumerate(rows,1):
        sid=row['id']; snap=OUT/'snapshots'/sid
        if comp[row['repo']]['status']!='POM_COMPLETE': continue
        resolution_p=target_by[row['repo']]['resolution_target_pom'] or 'pom.xml'
        for rt in ('m3','m4'):
            for rep in (1,2):
                base=mroot/sid/f'{rt}-r{rep}'; base.mkdir(parents=True,exist_ok=True); local=cache_root/rt; local.mkdir(parents=True,exist_ok=True)
                mvn=str(Path(RUNTIME[rt])/'bin'/'mvn.cmd'); model=base/'effective-pom.xml'; tree=base/'tree.json'; target=snap/'pom.xml'; cwd=snap
                common=['-B','-ntp','-e','-s',str(SETTINGS),'-gs',str(SETTINGS),f'-Dmaven.repo.local={local}','-Dstyle.color=never']
                rec=run_cmd([mvn]+common+['-N','org.apache.maven.plugins:maven-help-plugin:3.5.1:effective-pom',f'-Doutput={model}'],cwd,base/'model')
                if model.exists(): write_json(base/'model.json',model_extract(model))
                trgt=snap/resolution_p; tbase=base/'resolution'; trgt.parent.mkdir(parents=True,exist_ok=True)
                trec=run_cmd([mvn]+common+['-N','-f',str(trgt),'org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree','-DoutputType=json',f'-DoutputFile={tree}'],cwd,tbase)
                vrec=run_cmd([mvn]+common+['-N','validate'],cwd,base/'validate')
                write_json(base/'status.json',{'model':rec,'tree':trec,'validate':vrec,'model_exists':model.exists(),'tree_exists':tree.exists(),'tree_json_valid':False})
                if tree.exists():
                    try: json.loads(tree.read_text(encoding='utf-8')); write_json(base/'status.json',{'model':rec,'tree':trec,'validate':vrec,'model_exists':model.exists(),'tree_exists':True,'tree_json_valid':True})
                    except Exception: pass
                print(f'MEASURE {i}/{len(rows)} {sid} {rt} r{rep}',flush=True)
        a=[]; b=[]
        for rt in ('m3','m4'):
            for rep in (1,2):
                p=mroot/sid/f'{rt}-r{rep}'
                a.append(json.loads((p/'model.json').read_text()) if (p/'model.json').exists() else None)
                b.append(json.loads((p/'tree.json').read_text()) if (p/'tree.json').exists() else None)
        m3r=[json.loads((mroot/sid/f'm3-r{x}/model.json').read_text()) for x in (1,2) if (mroot/sid/f'm3-r{x}/model.json').exists()]; m4r=[json.loads((mroot/sid/f'm4-r{x}/model.json').read_text()) for x in (1,2) if (mroot/sid/f'm4-r{x}/model.json').exists()]
        model_cls='MODEL_UNAVAILABLE'
        if len(m3r)==2 and len(m4r)==2:
            s3=json.dumps(m3r[0],sort_keys=True); s4=json.dumps(m4r[0],sort_keys=True)
            if s3==json.dumps(m3r[1],sort_keys=True) and s4==json.dumps(m4r[1],sort_keys=True):
                if s3==s4: model_cls='IDENTICAL'
                else:
                    changed=[k for k in m3r[0] if m3r[0][k]!=m4r[0][k]]
                    mapping={'dependencies':'DEPENDENCY_DECLARATION_CHANGED','dependencyManagement':'DEPENDENCY_MANAGEMENT_CHANGED','active_plugins':'PLUGIN_VERSION_SELECTION_CHANGED','plugin_management':'PLUGIN_VERSION_SELECTION_CHANGED','execution_declarations':'PLUGIN_EXECUTION_DECLARATION_CHANGED','modules':'MODULE_SET_CHANGED'}
                    sem=[mapping[k] for k in changed if k in mapping]
                    model_cls=sem[0] if len(set(sem))==1 else ('MULTIPLE_MODEL_CHANGES' if sem else 'PROPERTY_ONLY')
        trees=[]
        for rt in ('m3','m4'):
            vals=[]
            for rep in (1,2):
                p=mroot/sid/f'{rt}-r{rep}/tree.json'; st=mroot/sid/f'{rt}-r{rep}/status.json'
                try:
                    q=json.loads(p.read_text()); vals.append(q)
                except Exception: vals.append(None)
            trees.append(vals)
        res='RESOLUTION_UNAVAILABLE'; graph_delta=[]
        if all(x is not None for pair in trees for x in pair):
            if trees[0][0]==trees[0][1] and trees[1][0]==trees[1][1]:
                res='IDENTICAL' if trees[0][0]==trees[1][0] else 'MULTIPLE'
        vals=[]
        for rt in ('m3','m4'):
            codes=[]
            for rep in (1,2): codes.append(json.loads((mroot/sid/f'{rt}-r{rep}/status.json').read_text())['validate']['exit_code'])
            vals.append(codes)
        v='UNKNOWN'
        if all(len(x)==2 for x in vals):
            v='PASS_PASS' if vals[0]==[0,0] and vals[1]==[0,0] else 'PASS_FAIL_CANDIDATE' if vals[0]==[0,0] and vals[1]!=[0,0] else 'FAIL_PASS' if vals[0]!=[0,0] and vals[1]==[0,0] else 'FAIL_FAIL'
        model_rows.append({'repo':row['repo'],'commit':row['commit'],'model_classification':model_cls})
        res_rows.append({'repo':row['repo'],'commit':row['commit'],'resolution_status':res,'target_pom':resolution_p})
        val_rows.append({'repo':row['repo'],'commit':row['commit'],'validation_status':v})
    for name,data in [('MODEL_DELTA.csv',model_rows),('RESOLUTION_RESULTS.csv',res_rows),('VALIDATION_RESULTS.csv',val_rows)]:
        with (OUT/'metrics'/name).open('w',newline='',encoding='utf-8') as f:
            w=csv.DictWriter(f,fieldnames=list(data[0]) if data else ['repo']); w.writeheader(); w.writerows(data)
    return model_rows,res_rows,val_rows

def do_measure_fast(rows, targets, completeness, worker=0, workers=1):
    target_by={x['repo']:x for x in targets}; comp={x['repo']:x for x in completeness}; mroot=OUT/'measurements'; cache_root=ROOT/'tools'/'cache'
    complete_index=0
    for i,row in enumerate(rows,1):
        sid=row['id']; snap=OUT/'snapshots'/sid
        if comp[row['repo']]['status']!='POM_COMPLETE': continue
        if complete_index % workers != worker: complete_index += 1; continue
        complete_index += 1
        resolution_p=target_by[row['repo']]['resolution_target_pom'] or 'pom.xml'
        for rt in ('m3','m4'):
            for rep in (1,2):
                base=mroot/sid/f'{rt}-r{rep}'; local=cache_root/('scale-m3' if rt=='m3' else 'scale-m4'); local.mkdir(parents=True,exist_ok=True)
                mvn=str(Path(RUNTIME[rt])/'bin'/'mvn.cmd'); model=base/'effective-pom.xml'; tree=base/'tree.json'; trgt=snap/resolution_p
                common=['-B','-ntp','-e','-s',str(SETTINGS),'-gs',str(SETTINGS),f'-Dmaven.repo.local={local}','-Dstyle.color=never']
                if not model.exists():
                    rec=run_cmd([mvn]+common+['-N','org.apache.maven.plugins:maven-help-plugin:3.5.1:effective-pom',f'-Doutput={model}'],snap,base/'model')
                    if model.exists(): write_json(base/'model.json',model_extract(model))
                if not tree.exists() or not (base/'status.json').exists():
                    trec=run_cmd([mvn]+common+['-N','-f',str(trgt),'org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree','-DoutputType=json',f'-DoutputFile={tree}','validate'],snap,base/'resolution')
                    vrec={'exit_code':trec['exit_code'],'timeout':trec['timeout'],'elapsed_seconds':trec['elapsed_seconds']}
                    write_json(base/'status.json',{'tree':trec,'validate':vrec,'tree_exists':tree.exists(),'tree_json_valid':False})
                    if tree.exists():
                        try: json.loads(tree.read_text(encoding='utf-8')); write_json(base/'status.json',{'tree':trec,'validate':vrec,'tree_exists':True,'tree_json_valid':True})
                        except Exception: pass
                print(f'FAST_MEASURE {i}/{len(rows)} {sid} {rt} r{rep}',flush=True)
    return do_measure_summary(rows,targets,completeness)

def do_measure_summary(rows, targets, completeness):
    mroot=OUT/'measurements'; comp={x['repo']:x for x in completeness}; target_by={x['repo']:x for x in targets}; model_rows=[]; res_rows=[]; val_rows=[]
    for row in rows:
        if comp[row['repo']]['status']!='POM_COMPLETE': continue
        sid=row['id']; model_files=[]; trees=[]; vals=[]
        for rt in ('m3','m4'):
            mr=[]; tr=[]; vr=[]
            for rep in (1,2):
                p=mroot/sid/f'{rt}-r{rep}'
                mr.append(json.loads((p/'model.json').read_text()) if (p/'model.json').exists() else None)
                try: tr.append(json.loads((p/'tree.json').read_text()))
                except Exception: tr.append(None)
                try: vr.append(json.loads((p/'status.json').read_text())['validate']['exit_code'])
                except Exception: vr.append(None)
            model_files.append(mr); trees.append(tr); vals.append(vr)
        model_cls='MODEL_UNAVAILABLE'; m3,m4=model_files
        if all(x is not None for pair in model_files for x in pair) and json.dumps(m3[0],sort_keys=True)==json.dumps(m3[1],sort_keys=True) and json.dumps(m4[0],sort_keys=True)==json.dumps(m4[1],sort_keys=True):
            if json.dumps(m3[0],sort_keys=True)==json.dumps(m4[0],sort_keys=True): model_cls='IDENTICAL'
            else:
                mapping={'dependencies':'DEPENDENCY_DECLARATION_CHANGED','dependencyManagement':'DEPENDENCY_MANAGEMENT_CHANGED','active_plugins':'PLUGIN_VERSION_SELECTION_CHANGED','plugin_management':'PLUGIN_VERSION_SELECTION_CHANGED','execution_declarations':'PLUGIN_EXECUTION_DECLARATION_CHANGED','modules':'MODULE_SET_CHANGED'}
                ch=[mapping[k] for k in m3[0] if m3[0][k]!=m4[0][k] and k in mapping]; model_cls=ch[0] if len(set(ch))==1 else ('MULTIPLE_MODEL_CHANGES' if ch else 'PROPERTY_ONLY')
        res='RESOLUTION_UNAVAILABLE'
        if all(x is not None for pair in trees for x in pair): res='IDENTICAL' if trees[0][0]==trees[0][1]==trees[1][0]==trees[1][1] else ('MULTIPLE' if trees[0][0]==trees[0][1] and trees[1][0]==trees[1][1] else 'RESOLUTION_NONDETERMINISTIC')
        v='UNKNOWN'
        if vals[0]==[0,0] and vals[1]==[0,0]: v='PASS_PASS'
        elif vals[0]==[0,0] and vals[1]!=[0,0]: v='PASS_FAIL_CANDIDATE'
        elif vals[0]!=[0,0] and vals[1]==[0,0]: v='FAIL_PASS'
        elif all(x is not None for pair in vals for x in pair): v='FAIL_FAIL'
        model_rows.append({'repo':row['repo'],'commit':row['commit'],'model_classification':model_cls})
        res_rows.append({'repo':row['repo'],'commit':row['commit'],'resolution_status':res,'target_pom':target_by[row['repo']]['resolution_target_pom']})
        val_rows.append({'repo':row['repo'],'commit':row['commit'],'validation_status':v})
    for name,data in [('MODEL_DELTA.csv',model_rows),('RESOLUTION_RESULTS.csv',res_rows),('VALIDATION_RESULTS.csv',val_rows)]:
        with (OUT/'metrics'/name).open('w',newline='',encoding='utf-8') as f:
            w=csv.DictWriter(f,fieldnames=list(data[0]) if data else ['repo']);w.writeheader();w.writerows(data)
    return model_rows,res_rows,val_rows

def main():
    OUT.mkdir(exist_ok=True); (OUT/'legacy_reference').mkdir(exist_ok=True)
    (OUT/'legacy_reference'/'LEGACY_RESULTS_NOT_FOR_PAPER.md').write_text('# Legacy results\n\nThe pre-correction outputs under `metrics/` and `MAVENTWIN_FINAL_STUDY_REPORT_ZH.md` are retained for reference only and must not supply final paper numbers.\n',encoding='utf-8')
    rows=read_rows(SAMPLES); comp=acquire_snapshots(rows); targets=freeze_targets(rows,comp); do_measure_fast(rows,targets,comp)
    write_json(OUT/'RUN_STATUS.json',{'DATA_FREEZE':'FINAL','NEXT_STEP':'WRITE_PAPER','sample_total':len(rows),'pom_complete':sum(x['status']=='POM_COMPLETE' for x in comp),'acquisition_failed':sum(x['status']!='POM_COMPLETE' for x in comp)})
if __name__=='__main__':
    if len(sys.argv)>=3 and sys.argv[1]=='worker':
        rows=read_rows(SAMPLES); comp=read_rows(OUT/'samples'/'POM_COMPLETENESS.csv'); targets=read_rows(OUT/'samples'/'TARGET_POMS.csv'); do_measure_fast(rows,targets,comp,int(sys.argv[2]),int(sys.argv[3]) if len(sys.argv)>3 else 1)
    else: main()
