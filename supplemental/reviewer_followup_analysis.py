"""Additional captured-result analyses for the reviewer revision."""
from experiments import *
from collections import Counter,defaultdict
import statistics,platform,time
sys.path.insert(0,str(ROOT/'scripts'))
from final_evidence_runner import extract_model,model_deltas,graph_from_run

def write(name,rows):
    with (CODE/name).open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def details():
    papers=read(ROOT/'final_evidence_v1/FINAL_PAPER_RESULTS.csv')
    excluded=[];durations=[];model_controls=[];all_controls=[];ablation=[]
    for row in papers:
        if row['pom_complete']!='true':continue
        sid=row['repo'].replace('/','__');base=ROOT/'final_evidence_v1/measurements'/sid
        for layer,col,folder in [('model','model_comparable','model'),('graph','resolution_comparable','resolution'),('validation','validation_comparable','validate')]:
            records=[];logs=[];status=[]
            for rt in ['m3','m4']:
                for n in [1,2]:
                    arm=base/f'{rt}-r{n}';command=arm/folder/'command.json'
                    if command.exists():
                        c=json.loads(command.read_text());records.append(c)
                        durations.append(dict(repo=row['repo'],layer=layer,runtime=rt,repetition=n,seconds=c['elapsed_seconds'],exit_code=c['exit_code'],timeout=c['timeout']))
                    for stream in ['stdout.txt','stderr.txt']:
                        p=arm/folder/stream
                        if p.exists():logs.append(p.read_text(encoding='utf-8',errors='replace'))
                    p=arm/'validation.json'
                    if layer=='validation' and p.exists():status.append(json.loads(p.read_text()))
            if row[col] in ['true','MODEL_COMPARABLE','RESOLUTION_COMPARABLE']:continue
            text='\n'.join(logs);codes=[x.get('exit_code') for x in records]
            errors=[s.strip() for s in text.splitlines() if '[ERROR]' in s]
            if any(x.get('status')=='UNSAFE_NOT_RUN' for x in status):reason='RECORDED_NOT_RUN'
            elif not records:reason='COMMAND_RECORD_UNAVAILABLE'
            elif any(x.get('timeout') for x in records):reason='TIME_LIMIT'
            elif any(x in text for x in ['must be unique','Non-parseable POM','Malformed POM','MavenPluginManager was not overridden','DevelocityLifecycleManager','must be a constant version',"'parent.relativePath'","Child subproject"]):reason='MODEL_OR_EXTENSION_STARTUP'
            elif any(x in text for x in ['Could not resolve','could not be resolved','not found in the local repository','has not been downloaded','Could not transfer','AccessDeniedException','zip file is empty','zip END header not found','PKIX','Remote host terminated','Connection reset']):reason='ARTIFACT_RESOLUTION_OR_CACHE'
            elif any(x not in [None,0] for x in codes):reason='OTHER_COMMAND_FAILURE'
            elif len(records)<4:reason='INCOMPLETE_CAPTURE'
            else:reason='OUTPUT_MISSING_PARSE_OR_REPEAT_GATE'
            if reason=='OUTPUT_MISSING_PARSE_OR_REPEAT_GATE' and layer=='model':
                models=[]
                for rt in ['m3','m4']:
                    for n in [1,2]:
                        p=base/f'{rt}-r{n}/model.json'
                        if p.exists():models.append(json.loads(p.read_text(encoding='utf-8')))
                if len(models)==4 and (models[0]!=models[1] or models[2]!=models[3]):reason='WITHIN_RUNTIME_UNSTABLE'
            excluded.append(dict(repo=row['repo'],layer=layer,reason=reason,captured_commands=len(records),exit_codes=json.dumps(codes),diagnostic=' | '.join(errors[:3]),status_details=json.dumps(status) if layer=='validation' else ''))
        for rt in ['m3','m4']:
            captures=[]
            for n in [1,2]:
                p=base/f'{rt}-r{n}/effective-pom.xml';c=base/f'{rt}-r{n}/model/command.json'
                if not p.exists() or not c.exists():continue
                command=json.loads(c.read_text())
                if command['exit_code']!=0 or command.get('timeout'):continue
                try:captures.append((p.read_bytes(),extract_model(p)))
                except ET.ParseError:continue
            if len(captures)==2:
                _,d=model_deltas(row['repo'],row['commit'],captures[0][1],captures[1][1])
                selected=[x for x in d if x['category'] not in ['MODEL_PROPERTY_ONLY','MODEL_REPRESENTATION_ONLY']]
                all_controls.append(dict(repo=row['repo'],runtime=rt,primary_comparable=row['model_comparable']=='MODEL_COMPARABLE',raw_positive=captures[0][0]!=captures[1][0],structured_positive=bool(selected),structured_rows=len(selected),categories=';'.join(sorted({x['category'] for x in selected}))))
        if row['model_comparable']=='MODEL_COMPARABLE':
            vals={};texts={}
            for rt in ['m3','m4']:
                for n in [1,2]:
                    p=base/f'{rt}-r{n}/effective-pom.xml';texts[rt,n]=p.read_bytes();vals[rt,n]=extract_model(p)
                _,d=model_deltas(row['repo'],row['commit'],vals[rt,1],vals[rt,2])
                relevant=[x for x in d if x['category'] not in ['MODEL_PROPERTY_ONLY','MODEL_REPRESENTATION_ONLY']]
                model_controls.append(dict(repo=row['repo'],runtime=rt,control='same_revision_same_runtime_repeat',raw_positive=texts[rt,1]!=texts[rt,2],structured_positive=bool(relevant),structured_rows=len(relevant)))
            _,d=model_deltas(row['repo'],row['commit'],vals['m3',1],vals['m4',1])
            retained=[x for x in d if 'CONFIGURATION' not in x['category'] and x['field']!='configuration' and x['category'] not in ['MODEL_PROPERTY_ONLY','MODEL_REPRESENTATION_ONLY']]
            ablation.append(dict(repo=row['repo'],positive_without_configuration=bool(retained),retained_rows=len(retained),categories=';'.join(sorted({x['category'] for x in retained}))))
    write('LAYER_EXCLUSIONS.csv',excluded);write('PRIMARY_COMMAND_DURATIONS.csv',durations);write('REAL_REPEAT_CONTROLS.csv',model_controls);write('ALL_REAL_REPEAT_CONTROLS.csv',all_controls);write('NON_CONFIGURATION_ABLATION.csv',ablation)
    bounds=[]
    primary=dict(model=(50,50),graph=(53,2),confirmed_validation=(47,2))
    for layer,(available,positive) in primary.items():
        for total in [61,116,150]:
            bounds.append(dict(layer=layer,population=total,observed=available,positive=positive,missing=total-available,lower=positive/total,upper=(positive+total-available)/total))
    write('MISSING_OUTCOME_BOUNDS.csv',bounds)
    perf={}
    for layer in ['model','graph','validation']:
        xs=[x for x in durations if x['layer']==layer]
        sums=defaultdict(float)
        for x in xs:sums[x['repo']]+=x['seconds']
        perf[layer]=dict(commands=len(xs),median_command_seconds=statistics.median(x['seconds'] for x in xs),total_command_seconds=sum(x['seconds'] for x in xs),median_four_capture_seconds=statistics.median(sums.values()))
    result=dict(exclusions={l:dict(Counter(x['reason'] for x in excluded if x['layer']==l)) for l in ['model','graph','validation']},non_configuration_positive=sum(x['positive_without_configuration'] for x in ablation),repeat_controls=dict(pairs=len(model_controls),raw_positive=sum(x['raw_positive'] for x in model_controls),structured_positive=sum(x['structured_positive'] for x in model_controls)),missing_bounds=bounds,primary_command_timing=perf)
    result['all_successful_repeat_controls']=dict(pairs=len(all_controls),raw_positive=sum(x['raw_positive'] for x in all_controls),structured_positive=sum(x['structured_positive'] for x in all_controls),structured_positive_repositories=sorted({x['repo'] for x in all_controls if x['structured_positive']}))
    dump(CODE/'FOLLOWUP_ANALYSIS_SUMMARY.json',result);print(json.dumps(result,indent=2),flush=True)

def benchmark():
    papers=[x for x in read(ROOT/'final_evidence_v1/FINAL_PAPER_RESULTS.csv') if x['model_comparable']=='MODEL_COMPARABLE']
    pairs=[]
    for row in papers:
        base=ROOT/'final_evidence_v1/measurements'/row['repo'].replace('/','__')
        for a,b,kind in [('m3-r1','m3-r2','repeat_m3'),('m4-r1','m4-r2','repeat_m4'),('m3-r1','m4-r1','cross_runtime')]:pairs.append((row,base/a/'effective-pom.xml',base/b/'effective-pom.xml',kind))
    rows=[]
    import tracemalloc
    for method in ['raw_bytes','structured']:
        times=[];matches=[]
        for repeat in range(5):
            start=time.perf_counter();answer=[]
            for row,a,b,kind in pairs:
                if method=='raw_bytes':v=a.read_bytes()!=b.read_bytes()
                else:
                    _,ds=model_deltas(row['repo'],row['commit'],extract_model(a),extract_model(b));v=any(x['category'] not in ['MODEL_PROPERTY_ONLY','MODEL_REPRESENTATION_ONLY'] for x in ds)
                answer.append(v)
            elapsed=time.perf_counter()-start;times.append(elapsed);matches=answer
            rows.append(dict(method=method,repeat=repeat+1,pairs=len(pairs),seconds=elapsed,positive=sum(answer)))
        tracemalloc.start()
        for row,a,b,kind in pairs:
            if method=='raw_bytes':_=(a.read_bytes()!=b.read_bytes())
            else:_=model_deltas(row['repo'],row['commit'],extract_model(a),extract_model(b))
        _,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
        # A separate tracing pass measures Python allocation peaks; it is excluded from timing.
        dump(CODE/f'BENCHMARK_{method.upper()}.json',dict(method=method,pairs=len(pairs),rounds=5,median_seconds=statistics.median(times),peak_python_bytes=peak,positive=sum(matches),environment=dict(python=sys.version,platform=platform.platform(),processor=platform.processor())))
    write('ANALYSIS_BENCHMARK.csv',rows)
    source_size()
    print('BENCHMARK COMPLETE',flush=True)

def source_size():
    source=ROOT/'public_code'
    if not source.exists():source=ROOT
    loc=[]
    for p in sorted(source.rglob('*')):
        if p.suffix in ['.py','.java'] and '__pycache__' not in p.parts:
            lines=p.read_text(encoding='utf-8').splitlines();loc.append(dict(path=p.relative_to(source).as_posix(),language=p.suffix,physical_lines=len(lines),nonblank_lines=sum(bool(x.strip()) for x in lines)))
    write('SOURCE_SIZE.csv',loc);dump(CODE/'SOURCE_SIZE_SUMMARY.json',dict(files=len(loc),physical_lines=sum(x['physical_lines'] for x in loc),nonblank_lines=sum(x['nonblank_lines'] for x in loc),definition='Released Python/Java implementation, experiment runners and tests; physical/nonblank lines, not logical statements.'))
    print('SOURCE SIZE COMPLETE',flush=True)

if __name__=='__main__':
    {'details':details,'benchmark':benchmark,'source_size':source_size}[sys.argv[1]]()
