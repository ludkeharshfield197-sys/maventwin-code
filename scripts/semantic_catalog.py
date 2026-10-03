"""Produce an auditable proposed case catalog; human review is required before gate evaluation."""
from harness import *

def catalog():
    rows=json.loads((R/'metrics/repo_results.json').read_text());audits={x['id']:x for x in json.loads((R/'metrics/case-audits.json').read_text())};out=[]
    for row in rows:
        a=audits[row['id']];cases=[]
        if row['resolution_divergence']:
            cases.append({'case_id':'R1','kind':'RESOLUTION_DIVERGENCE','meaningful':True,'stronger_semantic':True,'details':a['graph_deltas'],'likely_cause':'DEPENDENCY_MANAGEMENT' if row['id']=='apache__commons-compress' else 'REQUIRES_CASE_REVIEW','official_documentation':'https://maven.apache.org/ref/4.0.0-rc-7/configuration.html' if row['id']=='apache__commons-compress' else None})
        versions=[x for x in a['plugin_version_changes'] if x['section']=='build/plugins' and x['m3'] and x['m4']]
        if versions:
            cases.append({'case_id':'M1','kind':'MODEL_DIVERGENCE','meaningful':True,'stronger_semantic':False,'details':versions,'likely_cause':'LIFECYCLE_DEFAULT','caveat':'Plugin version selection in the effective build model changed; those lifecycle goals were not executed in this pilot.'})
        props=[x for x in a['property_changes'] if x['key'] in ['project.build.outputTimestamp','project.build.sourceEncoding','project.reporting.outputEncoding']]
        if props:
            cases.append({'case_id':'M2','kind':'MODEL_DIVERGENCE','meaningful':True,'stronger_semantic':False,'details':props,'likely_cause':'LIFECYCLE_DEFAULT','caveat':'Known inherited build/report/archive defaults; property effects on actual artifacts were not tested. Report sensitivity without property-only cases.'})
        extension=R/'metadata_diff'/row['id']/'extension-binding-evidence.json'
        if extension.exists() and json.loads(extension.read_text())['repeatable']:
            cases.append({'case_id':'M3','kind':'MODEL_DIVERGENCE','meaningful':True,'stronger_semantic':False,'details':json.loads(extension.read_text()),'likely_cause':'PLUGIN_COMPATIBILITY','caveat':'Dynamic extension-injected execution missing in exported M4 model. Source suggests stale mutable compatibility wrapper, but causal ablation and actual deploy behavior are untested. Not a confirmed plugin failure.'})
        if row['m3_pass_m4_fail']:
            cases.append({'case_id':'V1','kind':'MAVEN4_VALIDATION_FAILURE','meaningful':True,'stronger_semantic':True,'details':row['failures'],'likely_cause':'REQUIRES_CASE_REVIEW'})
        if row['model_divergence']:
            cases.append({'case_id':'M0','kind':'MODEL_DIVERGENCE','meaningful':False,'stronger_semantic':False,'details':{'changed_sections':a['changed_model_sections']},'caveat':'Residual export/configuration/order differences require individual review; raw model counts retain these. This row is not itself a qualifying semantic case.'})
        out.append({'id':row['id'],'paired_unknown':row['unknown'],'proposed_cases':cases,'proposed_qualifying_repo':not row['unknown'] and any(x['meaningful'] for x in cases),'proposed_stronger_repo':not row['unknown'] and any(x['stronger_semantic'] for x in cases),'review_status':'PROPOSED_NOT_FINAL'})
    dump(R/'metrics'/'proposed-semantic-catalog.json',out)
    print(json.dumps({'completed':len(out),'proposed_qualifying':sum(x['proposed_qualifying_repo'] for x in out),'proposed_stronger':sum(x['proposed_stronger_repo'] for x in out)},indent=2))
if __name__=='__main__':catalog()
