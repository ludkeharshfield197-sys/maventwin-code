from differential import *
def childs(node,tag):return [x for x in (node or {}).get('children',[]) if x['tag']==tag]
def child(node,tag):return next(iter(childs(node,tag)),None)
def txt(node,tag):return (child(node,tag) or {}).get('text','')
def propmap(node):return {x['tag']:x['text'] for x in (node or {}).get('children',[])}
def pluginmap(node):
    if node and node['tag']=='pluginManagement':node=child(node,'plugins')
    return {(txt(x,'groupId') or 'org.apache.maven.plugins')+':'+txt(x,'artifactId'):x for x in childs(node,'plugin')}
def explain(a,b):
    changes=[]
    for section in SECTIONS:
        if a[section]==b[section]:continue
        if section=='properties':
            x,y=propmap(a[section]),propmap(b[section])
            for key in sorted(set(x)|set(y)):
                if x.get(key)!=y.get(key):changes.append({'section':section,'key':key,'m3':x.get(key),'m4':y.get(key)})
        elif section in ['build/plugins','build/pluginManagement']:
            x,y=pluginmap(a[section]),pluginmap(b[section])
            for key in sorted(set(x)|set(y)):
                if x.get(key)!=y.get(key):
                    changes.append({'section':section,'key':key,'m3_version':txt(x.get(key),'version'),'m4_version':txt(y.get(key),'version'),'change':'ADDED' if key not in x else 'REMOVED' if key not in y else 'CHANGED','details':model_deltas(x.get(key),y.get(key))})
            order1=list(x);order2=list(y)
            if set(order1)==set(order2) and order1!=order2:changes.append({'section':section,'change':'ORDER_CHANGED','m3':order1,'m4':order2})
        else:changes.append({'section':section,'details':model_deltas(a[section],b[section])})
    return changes
if __name__=='__main__':
    lock=json.loads((R/'samples'/'sample_lock.json').read_text())
    for s in lock['samples']:
        try:
            states=[json.loads((R/'metadata_diff'/s['id']/f'{rt}-r1'/'normalized-state.json').read_text()) for rt in ['m3','m4']]
            ans=explain(states[0]['model']['value'],states[1]['model']['value']);dump(R/'metadata_diff'/s['id']/'model-explanation.json',ans)
            print(s['id'],[(x['section'],x.get('key',x.get('change')),x.get('m3_version',x.get('m3')),x.get('m4_version',x.get('m4'))) for x in ans])
        except (FileNotFoundError,KeyError):pass
