from harness import *
from collections import Counter

def inspect():
    lock=json.loads((R/'samples'/'sample_lock.json').read_text());rows=[]
    for s in lock['samples']:
        root=ET.parse(R/'samples'/'screening'/s['id']/'m3-r1'/'model'/'effective-pom-m3.xml').getroot()
        deps=root.findall('m:dependencies/m:dependency',NS)
        mutable=[]
        for d in deps:
            v=d.findtext('m:version','',NS)
            if 'SNAPSHOT' in v or '[' in v or '(' in v or v in ['LATEST','RELEASE']:
                mutable.append({'groupId':d.findtext('m:groupId','',NS),'artifactId':d.findtext('m:artifactId','',NS),'version':v})
        rows.append({'id':s['id'],'stratum':s['stratum'],'packaging':s['packaging'],'module_count':len(s['modules']),'root_dependencies':len(deps),'mutable_dependencies':mutable})
    ans={'generated_utc':utc(),'source':'Frozen sample and Maven 3 eligibility models; original partial prelock characteristics retained separately','repositories':len(rows),'strata':dict(Counter(x['stratum'] for x in rows)),'packaging':dict(Counter(x['packaging'] for x in rows)),'nonempty_declared_root_dependencies':sum(x['root_dependencies']>0 for x in rows),'repos_with_mutable_direct_dependencies':sum(bool(x['mutable_dependencies']) for x in rows),'rows':rows}
    dump(R/'metrics'/'frozen-sample-characteristics.json',ans);print(json.dumps({k:v for k,v in ans.items() if k!='rows'},indent=2))
if __name__=='__main__':inspect()
