from harness import *
from collections import defaultdict
from functools import lru_cache
SECTIONS=['dependencies','dependencyManagement','build/plugins','build/pluginManagement','profiles','properties','modules','repositories','pluginRepositories']
def local(tag):return tag.split('}')[-1]
@lru_cache(maxsize=None)
def normal_replacements(sid):
    paths=json.loads((R/'protocol'/'runtime_paths.json').read_text())
    replacements=[(str(R/'samples'/'sources'/sid),'<PROJECT>'),(paths['m3'],'<MAVEN_HOME>'),(paths['m4'],'<MAVEN_HOME>'),(str(R/'tools'/'cache'/'m3'),'<LOCAL_REPO>'),(str(R/'tools'/'cache'/'m4'),'<LOCAL_REPO>'),(str(R/'tools'/'homes'/'m3'),'<MAVEN_USER_HOME>'),(str(R/'tools'/'homes'/'m4'),'<MAVEN_USER_HOME>')]
    return replacements

def normal_text(s,sid):
    if s is None:return ''
    s=s.strip()
    for prefix,repl in normal_replacements(sid):
        for p in [prefix,prefix.replace('\\','/'),prefix.replace('\\','\\\\')]:s=s.replace(p,repl)
    s=re.sub(r'(<(?:PROJECT|MAVEN_HOME|LOCAL_REPO|MAVEN_USER_HOME)>)([^\s<>]*)',lambda m:m.group(1)+m.group(2).replace('\\','/'),s)
    return s
def xmlnode(e,sid):
    children=[xmlnode(x,sid) for x in e]
    if local(e.tag)=='dependency':
        if not any(x['tag']=='scope' for x in children):children.append({'tag':'scope','attrs':{},'text':'compile','children':[]})
        children.sort(key=lambda x:x['tag'])
    if local(e.tag)=='properties':children.sort(key=lambda x:x['tag'])
    text=normal_text(e.text,sid)
    # Source-traced wall-clock interpolation only; never erase outputTimestamp.
    if (sid=='mybatis__spring' and local(e.tag)=='timestamp' and re.fullmatch(r'\d{4}-\d\d-\d\d \d\d:\d\d:\d\d[+-]\d{4}',text)) or (sid=='oshi__oshi' and local(e.tag)=='Build-Time' and re.fullmatch(r'\d{4}-\d\d-\d\d \d\d:\d\d:\d\d',text)):
        text='<BUILD_WALL_CLOCK>'
    return {'tag':local(e.tag),'attrs':dict(sorted(e.attrib.items())),'text':text,'children':children}
def normalize_model(p,sid):
    root=ET.parse(p).getroot();out={}
    for key in SECTIONS:
        e=root.find('/'.join('m:'+x for x in key.split('/')),NS)
        out[key]=xmlnode(e,sid) if e is not None else None
    return out
def flatten_graph(root):
    nodes=[]
    def visit(n,parents):
        record={k:n.get(k) for k in ['groupId','artifactId','version','type','classifier','scope','optional']}
        record['optional']=str(record['optional']).lower()=='true'
        record['classifier']=record['classifier'] or '';record['scope']=record['scope'] or ''
        record.update(depth=len(parents),parent_path=parents)
        record['mediation']={k:v for k,v in n.items() if k not in ['children','groupId','artifactId','version','type','classifier','scope','optional']}
        nodes.append(record)
        coord=':'.join(str(record[k] or '') for k in ['groupId','artifactId','type','classifier','version'])
        for ch in n.get('children',[]):visit(ch,parents+[coord])
    visit(root,[]);return nodes
def jsonkey(x):return json.dumps(x,sort_keys=True,ensure_ascii=False)
def model_deltas(a,b,path=''):
    if a==b:return []
    if isinstance(a,dict) and isinstance(b,dict):
        out=[]
        for k in sorted(set(a)|set(b)):out+=model_deltas(a.get(k),b.get(k),path+'/'+k)
        return out
    if isinstance(a,list) and isinstance(b,list) and len(a)==len(b):
        out=[]
        for i,(x,y) in enumerate(zip(a,b)):out+=model_deltas(x,y,path+'/'+str(i))
        return out
    return [{'path':path,'m3':a,'m4':b}]
def graph_deltas(a,b):
    ans=[]
    def idx(nodes):
        d=defaultdict(list)
        for n in nodes:
            if n['depth']==0:continue
            d[tuple(n[k] for k in ['groupId','artifactId','type','classifier'])].append(n)
        return d
    x,y=idx(a),idx(b)
    for key in sorted(set(x)|set(y)):
        if key not in x:ans.append({'type':'ADDED','identity':key,'m4':y[key]});continue
        if key not in y:ans.append({'type':'REMOVED','identity':key,'m3':x[key]});continue
        for field,label in [('version','VERSION_CHANGED'),('scope','SCOPE_CHANGED'),('parent_path','PATH_CHANGED'),('mediation','MEDIATION_CHANGED'),('optional','OPTIONAL_CHANGED')]:
            v1=sorted(set(jsonkey(n[field]) for n in x[key]));v2=sorted(set(jsonkey(n[field]) for n in y[key]))
            if v1!=v2:ans.append({'type':label,'identity':key,'m3':v1,'m4':v2})
    return ans
def safe_validation(model):
    root=ET.parse(model).getroot();executions=[];blocked=[]
    allowed={'maven-enforcer-plugin':{'enforce'},'maven-checkstyle-plugin':{'check'},'apache-rat-plugin':{'check'},'maven-artifact-plugin':{'check-buildplan'},'buildnumber-maven-plugin':{'create','create-timestamp'},'build-helper-maven-plugin':{'timestamp-property','parse-version','regex-property','regex-properties','bsh-property'},'spring-javaformat-maven-plugin':{'validate'},'maven-toolchains-plugin':{'toolchain','select-jdk-toolchain'}}
    allowed['build-helper-maven-plugin'].discard('bsh-property')
    allowed['spotless-maven-plugin']={'check'}
    allowed['git-commit-id-maven-plugin']={'revision'}
    allowed['glassfish-copyright-maven-plugin']={'check'}
    # Audited default-phase bindings: these run after validate (or have no default phase).
    later_or_unbound={'maven-remote-resources-plugin':{'process'},'maven-jar-plugin':{'test-jar','jar'},'maven-source-plugin':{'jar','jar-no-fork','test-jar','test-jar-no-fork'},'maven-surefire-plugin':{'test'},'jacoco-maven-plugin':{'check','prepare-agent','report'},'maven-site-plugin':{'attach-descriptor'},'kotlin-maven-plugin':{'compile','test-compile'},'license-maven-plugin':{'check'},'maven-javadoc-plugin':{'aggregate','jar'},'maven-artifact-plugin':{'buildinfo'},'maven-failsafe-plugin':{'integration-test','verify'},'gradle-module-metadata-maven-plugin':{'gmm'},'formatter-maven-plugin':{'format'},'impsort-maven-plugin':{'sort'},'exec-maven-plugin':{'java'},'bnd-maven-plugin':{'bnd-process'},'forbiddenapis':{'check','testCheck'}}
    for p in root.findall('m:build/m:plugins/m:plugin',NS):
        aid=p.findtext('m:artifactId','',NS)
        for ex in p.findall('m:executions/m:execution',NS):
            phase=ex.findtext('m:phase','',NS)
            goals=[n.text for n in ex.findall('m:goals/m:goal',NS)]
            if not phase and goals and not set(goals).issubset(later_or_unbound.get(aid,set())|allowed.get(aid,set())):
                blocked.append({'plugin':aid,'goals':goals,'reason':'UNREVIEWED_DEFAULT_PHASE'})
            if phase=='validate' or (not phase and goals and set(goals).issubset(allowed.get(aid,set()))):
                item={'plugin':aid,'groupId':p.findtext('m:groupId','org.apache.maven.plugins',NS),'version':p.findtext('m:version','',NS),'id':ex.findtext('m:id','',NS),'goals':[n.text for n in ex.findall('m:goals/m:goal',NS)]}
                executions.append(item)
                if aid not in allowed or not set(item['goals']).issubset(allowed[aid]):blocked.append(item)
                if aid=='spotless-maven-plugin' and any('custom' in local(e.tag).lower() for e in p.iter()):blocked.append(item)
    return {'allowed':not blocked,'validate_executions':executions,'blocked_executions':blocked,'limitation':'Conservative review includes explicitly bound validate and safe metadata goals with implicit phases; audited later/unbound goals do not execute at validate.'}
def state(sample,runtime,n):
    base=R/'metadata_diff'/sample['id']/f'{runtime}-r{n}';out={}
    for kind in ['model','tree','validate']:
        cmd=base/kind/'command.json'
        if not cmd.exists():out[kind]={'status':'NOT_RUN'};continue
        rec=json.loads(cmd.read_text());status='PASS' if rec['exit_code']==0 and not rec['timeout'] else ('TIMEOUT' if rec['timeout'] else 'FAIL')
        out[kind]={'status':status}
        if status=='FAIL':
            log='\n'.join(p.read_text(encoding='utf-8',errors='replace') for p in [base/kind/'stdout.txt',base/kind/'stderr.txt'] if p.exists())
            errors=[normal_text(l.split('[ERROR]',1)[-1],sample['id']) for l in log.splitlines() if '[ERROR]' in l]
            out[kind]['error_signature']=errors
        try:
            if kind=='model' and status=='PASS':out[kind]['value']=normalize_model(base/kind/f'effective-pom-{runtime}.xml',sample['id'])
            if kind=='tree' and status=='PASS':out[kind]['value']=flatten_graph(json.loads((base/kind/'dependency-tree.json').read_text(encoding='utf-8-sig')))
        except Exception as e:out[kind]={'status':'PARSE_ERROR','error':str(e)}
    dump(base/'normalized-state.json',out);return out
def compare(sample,n):
    a,b=state(sample,'m3',n),state(sample,'m4',n);out={'id':sample['id'],'round':n}
    for kind in ['model','tree']:
        if 'value' in a[kind] and 'value' in b[kind]:out[kind+'_differences']=(model_deltas if kind=='model' else graph_deltas)(a[kind]['value'],b[kind]['value'])
        else:out[kind+'_differences']=None
    out['statuses']={k:[a[k]['status'],b[k]['status']] for k in a}
    v=out['statuses']['validate'];out['validation_category']=f'{v[0]}_M3_{v[1]}_M4'
    out['has_difference']=bool(out['model_differences'] or out['tree_differences'] or any(x[0]!=x[1] for x in out['statuses'].values()))
    dump(R/'metadata_diff'/sample['id']/f'difference-r{n}.json',out);return out
def phaseb():
    lock=json.loads((R/'samples'/'sample_lock.json').read_text());assert len(lock['samples'])==30
    assert sha(R/'samples'/'samples_v1.csv')==lock['samples_csv_sha256']
    for sample in lock['samples']:
        sid=sample['id'];src=R/'samples'/'sources'/sid;budget();print('PHASE_B',sid,flush=True)
        before=snapshot_sources(src)
        for n in [1,2]:
            # Always repeat both arms to distinguish normalization noise from stable treatment.
            for rt in (['m3','m4'] if n==1 else ['m4','m3']):
                for kind in ['model','tree','mediation','validate']:
                    if kind=='validate':
                        model=R/'metadata_diff'/sid/f'{rt}-r{n}'/'model'/f'effective-pom-{rt}.xml'
                        if not model.exists():
                            # Maven validation may itself supply a useful model-error diagnostic; source POM is reviewed instead.
                            model=src/'pom.xml'
                        review=safe_validation(model);dump(R/'metadata_diff'/sid/f'{rt}-r{n}'/'validation-safety.json',review)
                        if not review['allowed']:print('BLOCK_VALIDATE',sid,rt,flush=True);continue
                    rec=maven(sample,rt,kind,n);print(rt,n,kind,rec['exit_code'],rec['elapsed_seconds'],flush=True)
            compare(sample,n)
        observed=[json.loads((R/'metadata_diff'/sid/f'difference-r{n}.json').read_text()) for n in [1,2]]
        dump(R/'metadata_diff'/sid/'pre-baseline-observations.json',{'recorded_utc':utc(),'source':'paired metadata measurements before mvnup','rounds':observed})
        dump(R/'verification'/(sid+'-source-integrity.json'),{'unchanged':before==snapshot_sources(src),'before_sha256':hashlib.sha256(jsonkey(before).encode()).hexdigest(),'after_sha256':hashlib.sha256(jsonkey(snapshot_sources(src)).encode()).hexdigest()})
        rec=maven(sample,'m4','mvnup',1,phase='mvnup');print('MVNUP',rec['exit_code'],flush=True)
        dump(R/'verification'/(sid+'-post-mvnup-source-integrity.json'),{'unchanged':before==snapshot_sources(src)})
        bdir=R/'mvnup'/sid/'m4-r1'/'mvnup'
        lines=((bdir/'stdout.txt').read_text(errors='replace')+'\n'+(bdir/'stderr.txt').read_text(errors='replace')).splitlines()
        dump(bdir/'extracted-messages.json',{'warnings':[l for l in lines if 'WARN' in l],'errors':[l for l in lines if 'ERROR' in l],'recommendation_lines':[l for l in lines if re.search('upgrad|replac|recommend|compatib|change',l,re.I)],'exit_code':rec['exit_code'],'timeout':rec['timeout'],'raw_logs_authoritative':True})
    dump(R/'evidence'/'phase_b_completed.json',{'completed_utc':utc(),'repositories':30,'sample_lock_sha256':sha(R/'samples'/'sample_lock.json'),'phase_c_started':False})
    print('PHASE_B_COMPLETE',flush=True)
if __name__=='__main__':phaseb()
