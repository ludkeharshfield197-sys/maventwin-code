from experiments import *
from collections import Counter
def main():
    model=read(ROOT/'final_evidence_v1/MODEL_DELTAS_FINAL.csv');graph=read(ROOT/'final_evidence_v1/RESOLUTION_DELTAS_FINAL.csv');paper=read(ROOT/'final_evidence_v1/FINAL_PAPER_RESULTS.csv');observations=[]
    for x in model:observations.append(dict(repo=x['repo'],layer='model',entity=x['entity'],field=x['field'],m3=x['m3_value'],m4=x['m4_value']))
    for x in graph:observations.append(dict(repo=x['repo'],layer='graph',entity=x['groupId']+':'+x['artifactId'],field=x['difference_type'],m3=x['m3_version'],m4=x['m4_version']))
    for x in paper:
        if x['confirmed_validation_regression']=='true':
            entity='org.apache.maven.plugins:maven-surefire-plugin' if x['repo']=='twilio/twilio-java' else 'com.gradle:develocity-maven-extension'
            observations.append(dict(repo=x['repo'],layer='validation',entity=entity,field='DUPLICATE_PLUGIN' if 'twilio' in x['repo'] else 'EXTENSION_STARTUP',m3='PASS',m4='FAIL'))
    results=[]
    for obs in observations:
        sid=obs['repo'].replace('/','__');base=ROOT/'final_evidence_v1/mvnup'/sid
        log='\n'.join(p.read_text(encoding='utf-8',errors='replace') for p in [base/'stdout.txt',base/'stderr.txt'] if p.exists());log=re.sub(r'\x1b\[[0-9;]*m','',log)
        entity=obs['entity'];bits=entity.split(':');aid=bits[1];eid=bits[2] if len(bits)>2 else ''
        lines=[l for l in log.splitlines() if re.search(r'(?<![\w.-])'+re.escape(aid)+r'(?![\w.-])',l,re.I)]
        # Header/strategy names supply generic context; require a concrete entity and the observed field change.
        specific=[];mentions=[];diagnostics=[]
        for line in lines:
            if 'at org.' in line or 'at com.' in line:continue
            if '[ERROR]' in line and obs['field']!='DUPLICATE_PLUGIN':diagnostics.append(line);continue
            mentions.append(line)
            a=obs['m3'].strip('"');b=obs['m4'].strip('"')
            version_pair=bool(a and b and a!=b and a in line and b in line)
            if obs['layer']=='validation' and obs['field']=='DUPLICATE_PLUGIN' and re.search(r'duplicate|must be unique',line,re.I):specific.append(line)
            elif obs['layer']=='model' and eid and eid in line and re.search(r'configuration|execution|removed|added',line,re.I):specific.append(line)
            elif obs['layer'] in ['model','graph'] and obs['field'] in ['version','VERSION_CHANGED'] and version_pair:specific.append(line)
        label='SPECIFIC_FINDING' if specific else ('ENTITY_MENTION' if mentions else ('TOOL_DIAGNOSTIC' if diagnostics else 'GENERIC_OR_NONE'))
        results.append({**obs,'label':label,'evidence_quote':' | '.join((specific or mentions or diagnostics)[:3])})
    with (CODE/'RQ3_OBSERVATION_CORRESPONDENCE.csv').open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(results[0]));w.writeheader();w.writerows(results)
    summary={layer:dict(Counter(x['label'] for x in results if x['layer']==layer)) for layer in ['model','graph','validation']}
    summary['unit']='Concrete delta rows for model/graph and confirmed diagnostic cases for validation; rows within repository are dependent.'
    summary['method']='Deterministic text matching with displayed evidence quotes; no independent human agreement is claimed.'
    dump(CODE/'RQ3_REFINED_SUMMARY.json',summary);print(json.dumps(summary,indent=2))
    for label in ['SPECIFIC_FINDING','ENTITY_MENTION','TOOL_DIAGNOSTIC']:
        unique={x['evidence_quote'] for x in results if x['label']==label}
        print(label,list(unique)[:12])
if __name__=='__main__':main()
