from experiments import *
import sys, copy
sys.path.insert(0,str(ROOT/'scripts'))
from final_evidence_runner import extract_model,model_deltas
def run():
    repos=['apache/commons-io','apache/commons-cli','FasterXML/jackson-core','FasterXML/jackson-databind'];rows=[]
    for repo in repos:
        sid=repo.replace('/','__');original=ROOT/'final_evidence_v1/measurements'/sid/'m3-r1/effective-pom.xml'
        a=extract_model(original);raw=original.read_bytes();root=ET.parse(original).getroot()
        controls=[]
        controls.append(('formatting','selected_equal',copy.deepcopy(root)))
        x=copy.deepcopy(root);props=x.find('m:properties',NS)
        if props is not None:props[:]=list(reversed(list(props)))
        controls.append(('property_order','selected_equal',x))
        x=copy.deepcopy(root);plugins=x.find('m:build/m:plugins',NS)
        if plugins is not None:plugins[:]=list(reversed(list(plugins)))
        controls.append(('plugin_order','selected_equal',x))
        x=copy.deepcopy(root);version=x.find('m:build/m:plugins/m:plugin/m:version',NS)
        if version is not None:version.text='99.0.0'
        controls.append(('plugin_version','selected_different',x))
        x=copy.deepcopy(root);dep=x.find('m:dependencies/m:dependency/m:version',NS)
        if dep is not None:dep.text='99.0.0'
        else:
            deps=x.find('m:dependencies',NS)
            if deps is None:deps=ET.SubElement(x,'{'+NS['m']+'}dependencies')
            d=ET.SubElement(deps,'{'+NS['m']+'}dependency')
            for k,v in [('groupId','org.maventwin.controls'),('artifactId','selected-positive'),('version','1.0')]:ET.SubElement(d,'{'+NS['m']+'}'+k).text=v
        controls.append(('dependency_version','selected_different',x))
        for name,truth,x in controls:
            ET.indent(x,space='    ');path=OUT/'serialization_controls'/sid/(name+'.xml');path.parent.mkdir(parents=True,exist_ok=True);ET.ElementTree(x).write(path,encoding='utf-8',xml_declaration=True)
            cls,ds=model_deltas(repo,'synthetic-transformation',a,extract_model(path));positive=cls not in ['MODEL_IDENTICAL','MODEL_PROPERTY_ONLY']
            rows.append({'repo':repo,'transformation':name,'truth':truth,'raw_different':raw!=path.read_bytes(),'maventwin_positive':positive,'classification':cls,'delta_rows':len(ds),'correct':positive==(truth=='selected_different')})
    with (CODE/'SERIALIZATION_CONTROLS.csv').open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    dump(CODE/'SERIALIZATION_CONTROL_SUMMARY.json',{'pairs':len(rows),'negative_controls':sum(r['truth']=='selected_equal' for r in rows),'positive_controls':sum(r['truth']=='selected_different' for r in rows),'raw_false_positives':sum(r['truth']=='selected_equal' and r['raw_different'] for r in rows),'selected_false_positives':sum(r['truth']=='selected_equal' and r['maventwin_positive'] for r in rows),'selected_false_negatives':sum(r['truth']=='selected_different' and not r['maventwin_positive'] for r in rows),'definition':'Synthetic transformations of captured XML, evaluated against the selected-field construct; not measurements of runtime incompatibility.'})
    print(json.dumps({'controls':len(rows),'correct':sum(r['correct'] for r in rows)}))
if __name__=='__main__':run()
