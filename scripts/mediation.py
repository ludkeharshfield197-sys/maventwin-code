import os  # Configurable workspace; no machine-specific paths.
"""Parse pinned dependency-plugin text annotations into structural evidence, never raw-text diffs."""
import re,json
from pathlib import Path
def parse_tree(text):
    rows=[];stack=[]
    for line in text.splitlines():
        connector=re.search(r'(\+-|\\-) ',line)
        depth=connector.start()//3+1 if connector else 0
        body=line[connector.end():] if connector else line
        if body.startswith('(') and body.endswith(')'):body=body[1:-1]
        if ' - ' in body:coord,annotation=body.split(' - ',1)
        elif ' (' in body:coord,annotation=body.split(' (',1);annotation=annotation.rstrip(')')
        else:coord,annotation=body,''
        bits=coord.strip().split(':')
        if len(bits) not in [4,5,6]:continue
        group,artifact,typ=bits[:3]
        if len(bits)==4:classifier='';version=bits[3];scope=''
        elif len(bits)==5:classifier='';version,scope=bits[3:]
        else:classifier,version,scope=bits[3:]
        match=re.search(r'omitted for conflict with ([^;\s)]+)',annotation)
        state='OMITTED_CONFLICT' if match else 'OMITTED_DUPLICATE' if 'omitted for duplicate' in annotation else 'OMITTED_OTHER' if 'omitted' in annotation else 'INCLUDED'
        stack=stack[:depth];row={'groupId':group,'artifactId':artifact,'type':typ,'classifier':classifier,'version':version,'scope':scope,'depth':depth,'parent_path':stack[:],'state':state,'conflict_winner':match.group(1) if match else None,'annotation':annotation}
        rows.append(row);stack.append(':'.join([group,artifact,typ,classifier,version]))
    return rows
def winner_changes(a,b,selected_changes):
    def winners(rows):
        d={}
        for n in rows:
            if n['state']=='OMITTED_CONFLICT':
                key=tuple(n[k] for k in ['groupId','artifactId','type','classifier']);d.setdefault(key,set()).add(n['conflict_winner'])
        return d
    x,y=winners(a),winners(b);changed={tuple(z['identity']) for z in selected_changes if z['type']=='VERSION_CHANGED'}
    return [{'type':'MEDIATION_CHANGED','identity':key,'m3_winners':sorted(x[key]),'m4_winners':sorted(y[key]),'evidence':'Changed conflict-winner annotations and selected version; no claim about the underlying causal mechanism.'} for key in sorted(set(x)&set(y)&changed) if x[key]!=y[key]]
if __name__=='__main__':
    r=(Path(os.environ.get("MAVENTWIN_WORKSPACE", Path(__file__).resolve().parents[1])).resolve())
    for p in (r/'metadata_diff').glob('*/m*-r*/mediation/dependency-tree-verbose.txt'):
        rows=parse_tree(p.read_text(encoding='utf-8-sig'));(p.parent/'mediation-evidence.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
