from experiments import *
base=OUT/'instrument';classes=base/'late-classes';classes.mkdir(parents=True,exist_ok=True)
cmd=[str(Path(RT['jdk'])/'bin/javac.exe'),'--release','17','-cp',str(Path(RT['m3'])/'lib/*'),'-d',str(classes),str(CODE/'ObserverLate.java')]
r=subprocess.run(cmd,capture_output=True,text=True);print(r.stdout,r.stderr);assert r.returncode==0
p=classes/'META-INF/plexus/components.xml';p.parent.mkdir(parents=True,exist_ok=True)
p.write_text('<component-set><components><component><role>org.apache.maven.AbstractMavenLifecycleParticipant</role><role-hint>maventwin-observer-late</role-hint><implementation>org.maventwin.observer.ObserverLate</implementation><requirements><requirement><role>org.apache.maven.lifecycle.internal.LifecycleExecutionPlanCalculator</role><field-name>calculator</field-name></requirement></requirements></component></components></component-set>')
jar=base/'maventwin-observer-late.jar'
with zipfile.ZipFile(jar,'w',zipfile.ZIP_DEFLATED) as z:
    for f in classes.rglob('*'):
        if f.is_file():z.write(f,f.relative_to(classes).as_posix())
dump(base/'late-build.json',{'command':cmd,'jar_sha256':sha(jar)});print(jar)
