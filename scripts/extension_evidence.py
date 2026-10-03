from explain_model import *

def collect():
    lock=json.loads((R/'samples/sample_lock.json').read_text());out=[]
    for s in lock['samples']:
        observations={}
        for rt in ['m3','m4']:
            for n in [1,2]:
                p=R/'metadata_diff'/s['id']/f'{rt}-r{n}/model'/f'effective-pom-{rt}.xml'
                root=ET.parse(p).getroot();plugins=[]
                for x in root.findall('m:build/m:plugins/m:plugin',NS):
                    if x.findtext('m:artifactId','',NS) not in ['central-publishing-maven-plugin','maven-deploy-plugin']:continue
                    plugins.append({'artifactId':x.findtext('m:artifactId','',NS),'version':x.findtext('m:version','',NS),'extensions':x.findtext('m:extensions','',NS),'executions':[{'id':e.findtext('m:id','',NS),'phase':e.findtext('m:phase','',NS),'goals':[g.text for g in e.findall('m:goals/m:goal',NS)]} for e in x.findall('m:executions/m:execution',NS)]})
                observations[f'{rt}-r{n}']={'effective_pom_sha256':sha(p),'plugins':plugins}
        def central(key):return next((p for p in observations[key]['plugins'] if p['artifactId']=='central-publishing-maven-plugin'),None)
        if central('m3-r1') and central('m3-r1')!=central('m4-r1'):
            case={'id':s['id'],'observations':observations,'repeatable':all(central(f'{rt}-r1')==central(f'{rt}-r2') for rt in ['m3','m4']),'observation':'M3 exported effective model includes injected-central-publishing/deploy/publish; M4 does not.','interpretation':'MODEL_DIVERGENCE; actual deployment plan and publication behavior untested.'}
            dump(R/'metadata_diff'/s['id']/'extension-binding-evidence.json',case);out.append(case)
    dump(R/'metrics/extension-binding-cases.json',out);print([(x['id'],x['repeatable']) for x in out])
if __name__=='__main__':collect()
