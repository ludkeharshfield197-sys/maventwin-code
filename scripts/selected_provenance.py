from harness import *

def collect():
    rows=json.loads((R/'metrics/repo_results.json').read_text());report=[]
    for row in rows:
        sid=row['id'];observations=[]
        for rt in ['m3','m4']:
            for n in [1,2]:
                base=R/'metadata_diff'/sid/f'{rt}-r{n}';sp=base/'normalized-state.json';ip=base/'tree'/'cache-artifacts.json'
                if not sp.exists() or not ip.exists():continue
                state=json.loads(sp.read_text());inv=json.loads(ip.read_text());nodes=state['tree'].get('value',[]);items=[]
                for node in nodes:
                    if node['depth']==0:continue
                    g,a,v=node['groupId'],node['artifactId'],node['version'];typ=node['type'] or 'jar';classifier=node['classifier'] or ''
                    folder=f'{g.replace(".","/")}/{a}/{v}/';stem=f'{a}-{v}';pom=folder+stem+'.pom'
                    ext='jar' if typ in ['jar','test-jar','bundle','maven-plugin','java-source','javadoc'] else typ
                    if typ=='test-jar' and not classifier:classifier='tests'
                    payload=folder+stem+('-'+classifier if classifier else '')+'.'+ext
                    items.append({'groupId':g,'artifactId':a,'version':v,'type':typ,'classifier':node['classifier'],'scope':node['scope'],'pom_cache_path':pom,'pom':inv.get(pom),'payload_cache_path':payload,'payload':inv.get(payload),'payload_status':'HASHED_IN_COMMAND_CACHE' if payload in inv else 'NOT_PRESENT_IN_COMMAND_CACHE_METADATA_ONLY'})
                observations.append({'runtime':rt,'round':n,'tree_status':state['tree']['status'],'selected_nodes':len(items),'poms_with_checksums':sum(x['pom'] is not None for x in items),'payloads_with_checksums':sum(x['payload'] is not None for x in items),'items':items})
        ans={'id':sid,'note':'Evidence of bytes present at each tree command. Absence of a library JAR is expected for metadata-only collection; no artifact semantic comparison is claimed.','observations':observations}
        dump(R/'metadata_diff'/sid/'selected-artifact-provenance.json',ans);report.append({**{k:v for k,v in ans.items() if k!='observations'},'observations':[{k:v for k,v in o.items() if k!='items'} for o in observations]})
    dump(R/'metrics'/'selected-artifact-provenance-summary.json',report)
    print('PROVENANCE_REPOS',len(report),'MISSING_SELECTED_POM_RECORDS',sum(o['selected_nodes']-o['poms_with_checksums'] for r in report for o in r['observations']))
if __name__=='__main__':collect()
