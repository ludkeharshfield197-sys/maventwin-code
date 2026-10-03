import json, csv, sys, urllib.request, urllib.parse, time, subprocess, os, shutil
from pathlib import Path
from harness import R, runtime_env, run, sha, utc, dump, NS, ET, snapshot_sources, budget

TARGET_NEW=120
CUTOFF='2024-10-01'
ROOT=R/'samples'/'scale_sources'
SCREEN=R/'samples'/'scale_screening'

def api(url):
    req=urllib.request.Request(url,headers={'Accept':'application/vnd.github+json','User-Agent':'maventwin-scale-acquisition'})
    with urllib.request.urlopen(req,timeout=45) as r:return json.loads(r.read())

def candidates():
    old={x['repo'] for x in json.loads((R/'samples'/'sample_lock.json').read_text())['samples']}
    out=[]
    seed=R/'samples'/'scale_candidate_seed.json'
    if seed.exists():
        for repo in json.loads(seed.read_text()):
            if repo in old or any(y['repo']==repo for y in out):continue
            org=repo.split('/')[0]
            out.append({'repo':repo,'org':org,'stratum':'Apache' if org.lower()=='apache' else 'Eclipse' if org.lower() in ['eclipse','eclipse-ee4j'] else 'Spring' if org.lower() in ['spring-projects','spring-io'] else 'Independent','stars':0,'pushed_at':None,'html_url':'https://github.com/'+repo})
        extras=[R/'samples'/'scale_candidate_extra.json',R/'samples'/'scale_candidate_extra2.json',R/'samples'/'scale_candidate_extra3.json']
        for extra in extras:
          if extra.exists():
            for repo in json.loads(extra.read_text()):
                if repo in old or any(y['repo']==repo for y in out):continue
                org=repo.split('/')[0]
                out.append({'repo':repo,'org':org,'stratum':'Apache' if org.lower()=='apache' else 'Eclipse' if org.lower() in ['eclipse','eclipse-ee4j'] else 'Spring' if org.lower() in ['spring-projects','spring-io'] else 'Independent','stars':0,'pushed_at':None,'html_url':'https://github.com/'+repo})
        return out
    queries=[
      'language:Java stars:>=50 pushed:>=2024-10-01 fork:false',
      'language:Java stars:>=10 pushed:>=2024-10-01 fork:false'
    ]
    for q in queries:
        for page in [1,2,3]:
            url='https://api.github.com/search/repositories?'+urllib.parse.urlencode({'q':q,'sort':'updated','order':'desc','per_page':100,'page':page})
            try:data=api(url)
            except Exception as e:
                print('API_FAILED',repr(e),flush=True);continue
            for x in data.get('items',[]):
                repo=x['full_name'];org=repo.split('/')[0]
                if repo in old or any(y['repo']==repo for y in out):continue
                out.append({'repo':repo,'org':org,'stratum':'Apache' if org.lower()=='apache' else 'Eclipse' if org.lower() in ['eclipse','eclipse-ee4j'] else 'Spring' if org.lower() in ['spring-projects','spring-io'] else 'Independent','stars':x.get('stargazers_count',0),'pushed_at':x.get('pushed_at'),'html_url':x.get('html_url'),'default_branch':x.get('default_branch')})
            if len(out)>=700:break
        if len(out)>=700:break
    return out

def git(src,*args):
    env=os.environ.copy();env.update(GIT_TERMINAL_PROMPT='0',GCM_INTERACTIVE='never')
    return subprocess.check_output(['git','-c','core.longpaths=true','-c',f'safe.directory={src.as_posix()}','-C',str(src),*args],text=True,env=env,stdin=subprocess.DEVNULL,timeout=90).strip()

def remote_head(repo):
    env=os.environ.copy();env.update(GIT_TERMINAL_PROMPT='0',GCM_INTERACTIVE='never')
    p=subprocess.Popen(['git','ls-remote','https://github.com/'+repo+'.git','HEAD'],text=True,env=env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:out,_=p.communicate(timeout=12)
    except subprocess.TimeoutExpired:
        subprocess.run(['taskkill','/PID',str(p.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);raise RuntimeError('REMOTE_HEAD_TIMEOUT')
    if p.returncode!=0:raise RuntimeError('REMOTE_HEAD_UNAVAILABLE')
    return out.split()[0]

def remote_date(repo,commit):
    try:
        b=urllib.request.urlopen(f'https://github.com/{repo}/commits/{commit}.atom',timeout=8).read().decode('utf-8','replace')
        m=re.search(r'<updated>([^<]+)</updated>',b);return m.group(1) if m else utc()
    except Exception:return utc()

def raw_file(repo,commit,path):
    url=f'https://raw.githubusercontent.com/{repo}/{commit}/{path}'
    try:
        with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'maventwin-scale'}),timeout=30) as r:return r.read()
    except Exception:return None

def sparse_root(repo,commit,src):
    src.mkdir(parents=True,exist_ok=True)
    pom=raw_file(repo,commit,'pom.xml')
    if pom is None:return False
    (src/'pom.xml').write_bytes(pom)
    meta={'repo':repo,'commit':commit,'acquisition':'root-pom-and-mvn-config-from-raw-github','revision_url':f'https://github.com/{repo}/tree/{commit}'}
    dump(src/'.maventwin-source.json',meta)
    # Metadata eligibility needs the root model only; project extensions are fetched
    # later for the frozen scale experiment, so screening stays cheap and read-only.
    # Fetch relative parent POMs needed by effective-model construction.
    try:
        root=ET.fromstring(pom);rel=root.findtext('{http://maven.apache.org/POM/4.0.0}parent/{http://maven.apache.org/POM/4.0.0}relativePath')
        rel=rel or '../pom.xml'
        if rel and rel.endswith('.xml') and not rel.startswith('http'):
            parent=Path(rel.replace('\\','/'));p=raw_file(repo,commit,parent.as_posix())
            if p is not None:
                dst=src/parent;dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes(p)
    except Exception:pass
    return True

def classify(src):
    return src.name

def screen_one(c,idx,worker='serial'):
    sid=c['repo'].replace('/','__');src=ROOT/sid;out=SCREEN/sid
    row={**c,'id':sid,'source_path':str(src),'eligible':False,'selection_order':idx}
    try:
        if src.exists() and not (src/'pom.xml').exists():shutil.rmtree(src,ignore_errors=True)
        commit=remote_head(c['repo']);date=remote_date(c['repo'],commit)
        if not sparse_root(c['repo'],commit,src):raise RuntimeError('NO_ROOT_POM_AT_HEAD')
        if date[:10]<CUTOFF:raise RuntimeError('INACTIVE_24_MONTHS')
        pom=src/'pom.xml'
        if not pom.exists():raise RuntimeError('NO_ROOT_POM')
        paths,e=runtime_env('m3');e.update(GIT_CONFIG_COUNT='1',GIT_CONFIG_KEY_0='safe.directory',GIT_CONFIG_VALUE_0=src.as_posix())
        if worker!='serial':
            cache=R/'tools'/f'scale-cache-{worker}';cache.mkdir(parents=True,exist_ok=True)
            home=R/'tools'/f'scale-home-{worker}';home.mkdir(parents=True,exist_ok=True)
            e['MAVEN_USER_HOME']=str(home);e['MAVEN_OPTS']=e['MAVEN_OPTS'].replace(str(R/'tools'/'java-user-home'),str(home))
        else:cache=R/'tools'/'cache'/'m3'
        settings=R/'protocol'/'settings.xml';modelout=out/(f'worker-{worker}' if worker!='serial' else '')/'m3-r1'/'model'
        argv=[str(Path(paths['m3'])/'bin'/'mvn.cmd'),'-B','-ntp','-N','-e','-s',str(settings),'-gs',str(settings),f'-Dmaven.repo.local={cache}','-Dstyle.color=never','org.apache.maven.plugins:maven-help-plugin:3.5.1:effective-pom',f'-Doutput={modelout}/effective-pom-m3.xml']
        rec=run(argv,src,modelout,e,timeout=180)
        if rec['exit_code']!=0 or rec['timeout'] or not (modelout/'effective-pom-m3.xml').exists():raise RuntimeError('M3_MODEL_FAILED')
        root=ET.parse(modelout/'effective-pom-m3.xml').getroot()
        row.update(commit=commit,commit_date=date,pom='pom.xml',pom_sha256=sha(pom),source_manifest_sha256=hashlib_sha(src),packaging=root.findtext('m:packaging','jar',NS),modules=[x.text for x in root.findall('m:modules/m:module',NS)],model_command=rec,acquisition_mode='root_pom_and_mvn_config_raw')
        row['eligible']=True;row['eligibility_basis']='M3 effective-model success on JDK21; metadata only; public repository; root POM unit'
        dump(out/'screening.json',row);print('ELIGIBLE',idx,sid,flush=True);return row
    except Exception as e:
        row['exclusion']=str(e);dump(out/'screening.json',row);print('EXCLUDED',idx,sid,str(e),flush=True);return None

def hashlib_sha(src):
    import hashlib
    return hashlib.sha256(json.dumps(snapshot_sources(src),sort_keys=True).encode()).hexdigest()

def main():
    existing=json.loads((R/'samples'/'sample_lock.json').read_text())['samples']
    target=TARGET_NEW
    if (R/'samples'/'scale_sample_lock.json').exists():raise RuntimeError('SCALE_SAMPLE_ALREADY_LOCKED')
    cs=candidates();print('CANDIDATES',len(cs),flush=True)
    selected=[];seen=set(x['repo'] for x in existing);org_counts={}
    # Enforce the requested upper bounds while retaining the purposive convenience design.
    max_total={'Apache':37,'Eclipse':22,'Spring':15}
    idx=0
    for c in cs:
        if len(selected)>=target:break
        if c['repo'] in seen:continue
        if c['stratum'] in max_total and sum(1 for x in existing+selected if x.get('stratum')==c['stratum'])>=max_total[c['stratum']]:continue
        idx+=1;row=screen_one(c,idx)
        if row:
            selected.append(row);seen.add(c['repo'])
            dump(R/'samples'/'scale_progress.json',{'started_utc':utc(),'selected':selected,'attempted':idx,'target_new':target})
    if len(selected)!=target:raise RuntimeError(f'ONLY_{len(selected)}_NEW_ELIGIBLE')
    rows=[]
    for i,x in enumerate(selected,31):
        rows.append({'id':x['id'],'repo':x['repo'],'stratum':x['stratum'],'commit':x['commit'],'commit_date':x['commit_date'],'source_path':x['source_path'],'pom':x['pom'],'packaging':x['packaging'],'module_count':len(x.get('modules',[])),'stars':x.get('stars',0)})
    with (R/'samples'/'scale_samples.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    dump(R/'samples'/'scale_sample_lock.json',{'frozen_utc':utc(),'samples_csv_sha256':sha(R/'samples'/'scale_samples.csv'),'samples':rows,'total_with_existing':150,'m4_runs_before_lock':0,'eligibility':'M3-only metadata screening before any scale M4 run'})
    print('SCALE_LOCKED',len(rows),flush=True)
def worker_main(worker,total):
    old={x['repo'] for x in json.loads((R/'samples'/'sample_lock.json').read_text())['samples']};cs=candidates();selected=[]
    for idx,c in enumerate(cs):
        if idx%total!=worker or c['repo'] in old:continue
        prior=SCREEN/c['repo'].replace('/','__')/'screening.json'
        if prior.exists():
            try:
                oldrow=json.loads(prior.read_text())
                continue
            except Exception:pass
        row=screen_one(c,idx+1,str(worker))
        if row:selected.append(row)
        if len(selected)>=38:break
    dump(R/'samples'/f'scale_worker_{worker}.json',selected);print('WORKER_DONE',worker,len(selected),flush=True)
if __name__=='__main__':
    if len(sys.argv)>=3 and sys.argv[1]=='--worker':worker_main(int(sys.argv[2]),int(sys.argv[3]))
    else:main()
