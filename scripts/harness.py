import os  # Configurable workspace; no machine-specific paths.
from pathlib import Path
import os,sys,json,hashlib,subprocess,time,datetime,platform,xml.etree.ElementTree as ET,csv,re,shutil
R=(Path(os.environ.get("MAVENTWIN_WORKSPACE", Path(__file__).resolve().parents[1])).resolve())
NS={'m':'http://maven.apache.org/POM/4.0.0'}
def utc(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
def dump(p,x):
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf-8')
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def size(): return sum(p.stat().st_size for p in R.rglob('*') if p.is_file())
def budget():
    n=size()
    if n>13_000_000_000: raise RuntimeError(f'DATA_BUDGET_STOP {n}')
    return n
def run(argv,cwd,out,env=None,timeout=240):
    env=(env or os.environ).copy();env['GIT_TERMINAL_PROMPT']='0';env['GCM_INTERACTIVE']='never'
    out.mkdir(parents=True,exist_ok=True);start=utc();t=time.monotonic()
    with (out/'stdout.txt').open('wb') as so,(out/'stderr.txt').open('wb') as se:
        p=subprocess.Popen(argv,cwd=str(cwd),env=env,stdin=subprocess.DEVNULL,stdout=so,stderr=se)
        timed=False
        try: code=p.wait(timeout)
        except subprocess.TimeoutExpired:
            timed=True
            subprocess.run(['taskkill','/PID',str(p.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            code=p.wait()
    rec={'argv':argv,'cwd':str(cwd),'started_utc':start,'finished_utc':utc(),'exit_code':code,'timeout':timed,'elapsed_seconds':round(time.monotonic()-t,3),'stdout_sha256':sha(out/'stdout.txt'),'stderr_sha256':sha(out/'stderr.txt')}
    dump(out/'command.json',rec);return rec
def runtime_env(runtime):
    paths=json.loads((R/'protocol'/'runtime_paths.json').read_text());jdk=paths['jdk']
    e=os.environ.copy()
    for k in list(e):
        if k.upper().startswith(('MAVEN','M2_')) or k.upper() in ['JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH']:e.pop(k,None)
    home=R/'tools'/'homes'/runtime;home.mkdir(parents=True,exist_ok=True)
    temp=R/'tools'/'tmp';temp.mkdir(exist_ok=True)
    jhome=R/'tools'/'java-user-home';jhome.mkdir(exist_ok=True)
    e.update(JAVA_HOME=jdk,MAVEN_HOME=paths[runtime],MAVEN_USER_HOME=str(home),MAVEN_SKIP_RC='true',MAVEN_OPTS=f'-Xmx768m -Dfile.encoding=UTF-8 -Duser.language=en -Duser.country=US -Duser.timezone=UTC -Duser.home={jhome} -Dscan=false',TEMP=str(temp),TMP=str(temp),PATH=str(Path(jdk)/'bin')+os.pathsep+e['PATH'])
    return paths,e
def inventory(cache):
    ans={}
    for p in sorted(cache.rglob('*')):
        if p.is_file() and not p.name.endswith(('.lastUpdated','.lock','.tmp')):
            ans[p.relative_to(cache).as_posix()]={'bytes':p.stat().st_size,'sha256':sha(p)}
    return ans
def maven(sample,runtime,kind,round_no=1,phase='metadata_diff'):
    paths,e=runtime_env(runtime);sid=sample['id'];src=R/'samples'/'sources'/sid
    e.update(GIT_CONFIG_COUNT='1',GIT_CONFIG_KEY_0='safe.directory',GIT_CONFIG_VALUE_0=src.as_posix())
    out=R/phase/sid/(f'{runtime}-r{round_no}')/kind
    if (out/'command.json').exists():
        old=json.loads((out/'command.json').read_text())
        logs=(out/'stdout.txt').read_text(errors='replace')+(out/'stderr.txt').read_text(errors='replace')
        if old['exit_code']==0 or not re.search(r'handshake|Could not transfer|Connection reset|connect timed out',logs,re.I):return old
        preserved=out/'previous-transport-failure';preserved.mkdir(exist_ok=True)
        for fname in ['stdout.txt','stderr.txt','command.json']:
            shutil.copy2(out/fname,preserved/fname)
    cache=R/'tools'/'cache'/runtime;cache.mkdir(parents=True,exist_ok=True)
    if runtime=='m4':
        seeded=[]
        for source in (R/'tools'/'cache'/'m3').rglob('*'):
            if not source.is_file():continue
            rel=source.relative_to(R/'tools'/'cache'/'m3')
            if any('SNAPSHOT' in x for x in rel.parts) or source.name.startswith('maven-metadata') or source.suffix in ['.lastUpdated','.lock','.tmp']:continue
            dest=cache/rel
            if not dest.exists():
                dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,dest)
                seeded.append({'path':rel.as_posix(),'sha256':sha(dest),'bytes':dest.stat().st_size})
        dump(out/'cache-seeding.json',{'from':'m3','copied_missing_only':seeded})
    settings=R/'protocol'/'settings.xml'
    args=['-B','-ntp','-N','-e','-s',str(settings),'-gs',str(settings),f'-Dmaven.repo.local={cache}','-Dstyle.color=never']
    if kind=='model':args+=['org.apache.maven.plugins:maven-help-plugin:3.5.1:effective-pom',f'-Doutput={out}/effective-pom-{runtime}.xml']
    elif kind=='tree':args+=['org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree','-DoutputType=json','-Dverbose=false',f'-DoutputFile={out}/dependency-tree.json']
    elif kind=='mediation':args+=['org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree','-DoutputType=text','-Dverbose=true','-Dtokens=standard',f'-DoutputFile={out}/dependency-tree-verbose.txt']
    elif kind=='validate':args+=['validate']
    elif kind=='mvnup':args=['check','-B','--color','never','--directory',str(src),'-s',str(settings),'-gs',str(settings),f'-Dmaven.repo.local={cache}']
    else:raise ValueError(kind)
    exe=Path(paths[runtime])/'bin'/('mvnup.cmd' if kind=='mvnup' else 'mvn.cmd')
    rec=run([str(exe)]+args,src,out,e,timeout=180)
    for retry in range(1,3):
        log=(out/'stdout.txt').read_text(errors='replace')+(out/'stderr.txt').read_text(errors='replace')
        if rec['exit_code']==0 or not re.search(r'handshake|Could not transfer|Connection reset|connect timed out',log,re.I):break
        archived=out/f'infra-attempt-{retry}';archived.mkdir(exist_ok=True)
        for fname in ['stdout.txt','stderr.txt','command.json']:
            shutil.copy2(out/fname,archived/fname)
        dump(archived/'cache-artifacts.json',inventory(cache))
        from transport_repair import repair
        repair(log,cache,archived)
        # Remove only failure markers in this experiment-owned cache, preserving each marker.
        for marker in cache.rglob('*.lastUpdated'):
            assert marker.resolve().is_relative_to((R/'tools'/'cache').resolve())
            backup=archived/'failure-markers'/marker.relative_to(cache);backup.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(marker,backup);marker.unlink()
        rec=run([str(exe)]+args,src,out,e,timeout=180)
        print('INFRA_RETRY',sid,runtime,kind,retry,rec['exit_code'],flush=True)
    dump(out/'environment.json',{k:e[k] for k in ['JAVA_HOME','MAVEN_HOME','MAVEN_USER_HOME','MAVEN_SKIP_RC','MAVEN_OPTS','TEMP','TMP','PATH']})
    fixed_env={k:v for k,v in e.items() if k not in ['MAVEN_HOME','MAVEN_USER_HOME']}
    dump(out/'environment-fingerprint.json',{'sha256_without_runtime_specific_homes':hashlib.sha256(json.dumps(fixed_env,sort_keys=True).encode()).hexdigest(),'variable_names':sorted(fixed_env),'note':'Inherited values are not dumped because they may include credentials; controlled values are in environment.json.'})
    dump(out/'cache-artifacts.json',inventory(cache));return rec
def snapshot_sources(src):
    return {p.relative_to(src).as_posix():sha(p) for p in src.rglob('*') if p.is_file() and '.git' not in p.parts and 'target' not in p.parts}
def prereview(src):
    files=list((src/'.mvn').rglob('*')) if (src/'.mvn').exists() else []
    notes=[]
    for p in files:
        if p.is_file() and p.name in ['maven.config','jvm.config','extensions.xml']:
            text=p.read_text(encoding='utf-8',errors='replace');notes.append({'file':str(p.relative_to(src)),'text':text})
            if p.name=='jvm.config' and any(x in text for x in ['-javaagent','-agentpath','-agentlib']):return False,notes
            if p.name=='maven.config' and re.search(r'(?m)^\s*(test|package|install|deploy|compile|verify|clean)\s*$',text):return False,notes
    return True,notes
def acquire():
    if (R/'samples'/'sample_lock.json').exists():raise RuntimeError('Sample already frozen; acquisition cannot rewrite the lock')
    candidates=json.loads((R/'samples'/'candidates.json').read_text())
    rows=[];audit=[];seen=set()
    if (R/'samples'/'screening.json').exists():
        audit=json.loads((R/'samples'/'screening.json').read_text());rows=[x for x in audit if x.get('eligible')];seen={x['commit'] for x in rows}
    done={x['repo'] for x in audit}
    for i,c in enumerate(candidates):
        if len(rows)>=30:break
        if c['repo'] in done:continue
        budget();sid=c['repo'].replace('/','__');src=R/'samples'/'sources'/sid
        info={**c,'id':sid,'pom':'pom.xml','selection_order':i+1,'url':'https://github.com/'+c['repo']+'.git','eligible':False}
        print('SCREEN',i+1,c['repo'],flush=True)
        src.parent.mkdir(parents=True,exist_ok=True)
        try:
            if not (src/'.git').exists():
                for attempt in range(1,4):
                    rec=run(['git','-c','core.longpaths=true','clone','--depth','1','--single-branch',info['url'],str(src)],R,R/'samples'/'acquisition'/sid/f'clone-{attempt}',timeout=100)
                    if rec['exit_code']==0:break
                if rec['exit_code']!=0:raise RuntimeError('ACQUISITION_FAILED')
            def git(*args):
                ge=os.environ.copy();ge.update(GIT_TERMINAL_PROMPT='0',GCM_INTERACTIVE='never')
                return subprocess.check_output(['git','-c',f'safe.directory={src.as_posix()}','-C',str(src),*args],text=True,env=ge,stdin=subprocess.DEVNULL,timeout=100).strip()
            try:git('rev-parse','--verify','HEAD')
            except subprocess.CalledProcessError:
                assert src.resolve().is_relative_to((R/'samples'/'sources').resolve())
                git('fetch','--depth','1','origin','HEAD');git('checkout','--detach','FETCH_HEAD')
            info.update(commit=git('rev-parse','HEAD'),commit_date=git('show','-s','--format=%cI','HEAD'),canonical_url=git('remote','get-url','origin'))
            if info['commit'] in seen:raise RuntimeError('DUPLICATE_COMMIT_REPOSITORY_ALIAS')
            if info['commit_date'][:10]<'2024-09-29':raise RuntimeError('INACTIVE_24_MONTHS')
            if not (src/'pom.xml').exists():raise RuntimeError('NO_ROOT_POM')
            ok,notes=prereview(src);dump(R/'samples'/'acquisition'/sid/'config-review.json',notes)
            if not ok:raise RuntimeError('PROJECT_CONFIG_UNSAFE_FOR_METADATA')
            # Record README and POM content hashes without running any source code.
            info['pom_sha256']=sha(src/'pom.xml');info['source_manifest_sha256']=hashlib.sha256(json.dumps(snapshot_sources(src),sort_keys=True).encode()).hexdigest()
            rec=maven(info,'m3','model',phase='samples/screening')
            if rec['exit_code']!=0 or rec['timeout']:raise RuntimeError('M3_MODEL_FAILED')
            model=R/'samples'/'screening'/sid/'m3-r1'/'model'/'effective-pom-m3.xml'
            if not model.exists():raise RuntimeError('NO_EFFECTIVE_MODEL')
            tree=ET.parse(model).getroot()
            urls=[x.text for x in tree.findall('.//m:repository/m:url',NS) if x.text]
            info['repositories']=urls
            info['modules']=[x.text for x in tree.findall('m:modules/m:module',NS)]
            info['packaging']=tree.findtext('m:packaging','jar',NS)
            info['eligible']=True;info['eligibility_basis']='M3 effective-model success on JDK21; metadata only; no service required; public resolution observed; root POM unit'
            rows.append(info);seen.add(info['commit']);print('ELIGIBLE',len(rows),sid,flush=True)
        except Exception as ex:info['exclusion']=str(ex);print('EXCLUDED',sid,str(ex),flush=True)
        audit.append(info);dump(R/'samples'/'screening.json',audit)
    if len(rows)!=30:raise RuntimeError(f'Only {len(rows)} eligible samples; no M4 experiments allowed')
    p=R/'samples'/'samples_v1.csv'
    with p.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=['id','repo','stratum','commit','commit_date','pom','packaging','url']);w.writeheader();w.writerows({k:x[k] for k in w.fieldnames} for x in rows)
    dump(R/'samples'/'sample_lock.json',{'frozen_utc':utc(),'m4_project_runs_before_lock':0,'samples_csv_sha256':sha(p),'candidates_sha256':sha(R/'samples'/'candidates.json'),'protocol_sha256':sha(R/'protocol'/'PROTOCOL_V1.md'),'samples':rows})
    print('LOCKED',len(rows),flush=True)
if __name__=='__main__':
    if sys.argv[1]=='acquire':acquire()
