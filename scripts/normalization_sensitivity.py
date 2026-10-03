from differential import *

def old_xmlnode(e,sid):
    children=[old_xmlnode(x,sid) for x in e]
    if local(e.tag)=='dependency':
        if not any(x['tag']=='scope' for x in children):children.append({'tag':'scope','attrs':{},'text':'compile','children':[]})
        children.sort(key=lambda x:x['tag'])
    if local(e.tag)=='properties':children.sort(key=lambda x:x['tag'])
    return {'tag':local(e.tag),'attrs':dict(sorted(e.attrib.items())),'text':normal_text(e.text,sid),'children':children}

def sensitivity():
    out=[]
    for sid in ['mybatis__spring','oshi__oshi']:
        obs={}
        for rt in ['m3','m4']:
            states=[]
            for n in [1,2]:
                p=R/'metadata_diff'/sid/f'{rt}-r{n}/model'/f'effective-pom-{rt}.xml';root=ET.parse(p).getroot();m={}
                for key in SECTIONS:
                    e=root.find('/'.join('m:'+x for x in key.split('/')),NS);m[key]=old_xmlnode(e,sid) if e is not None else None
                states.append(m)
            obs[rt]={'stable_before_correction':states[0]==states[1],'within_runtime_deltas_before_correction':model_deltas(*states)}
        out.append({'id':sid,'observations':obs})
    dump(R/'verification/normalization-sensitivity.json',{'original_automated_unknown_repos':['mybatis__spring','oshi__oshi','eclipse-ee4j__jaxb-api'],'original_unknown_rate':.1,'model_sensitivity':out,'jaxb_original_flag_reason':'Optional Codehaus prefix transport warning matched generic regex; terminal copyright failure occurred identically in all four runs.','raw_inputs_unchanged':True})
if __name__=='__main__':sensitivity()
