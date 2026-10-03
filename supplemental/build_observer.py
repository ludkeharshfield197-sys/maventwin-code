from pathlib import Path
import subprocess, zipfile, shutil
from experiments import ROOT,OUT,CODE,RT,dump,sha
base=OUT/'instrument';classes=base/'classes';classes.mkdir(parents=True,exist_ok=True)
cmd=[str(Path(RT['jdk'])/'bin/javac.exe'),'--release','17','-cp',str(Path(RT['m3'])/'lib/*'),'-d',str(classes),str(CODE/'Observer.java')]
p=subprocess.run(cmd,capture_output=True,text=True);print(p.stdout,p.stderr);assert p.returncode==0
meta=classes/'META-INF/plexus/components.xml';meta.parent.mkdir(parents=True,exist_ok=True)
meta.write_text('<component-set><components><component><role>org.apache.maven.AbstractMavenLifecycleParticipant</role><role-hint>maventwin-observer</role-hint><implementation>org.maventwin.observer.Observer</implementation><requirements><requirement><role>org.apache.maven.lifecycle.internal.LifecycleExecutionPlanCalculator</role><field-name>calculator</field-name></requirement></requirements></component></components></component-set>')
jar=base/'maventwin-observer.jar'
with zipfile.ZipFile(jar,'w',zipfile.ZIP_DEFLATED) as z:
    for f in classes.rglob('*'):
        if f.is_file():z.write(f,f.relative_to(classes).as_posix())
dump(base/'build.json',{'command':cmd,'jar_sha256':sha(jar),'java_release':17});print(jar)
