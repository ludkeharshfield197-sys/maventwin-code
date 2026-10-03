import os  # Configurable workspace; no machine-specific paths.
from pathlib import Path
import urllib.request, json, hashlib, zipfile, subprocess, platform, os, time
R=(Path(os.environ.get("MAVENTWIN_WORKSPACE", Path(__file__).resolve().parents[1])).resolve())
def get(url):
    req=urllib.request.Request(url,headers={'User-Agent':'MavenTwin-research-pilot'})
    with urllib.request.urlopen(req,timeout=90) as f: return f.read()
def savejson(path,x): path.write_text(json.dumps(x,indent=2,ensure_ascii=False),encoding='utf-8')
records=[]
for ver in ['3.9.16','4.0.0-rc-7']:
    url=f'https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/{ver}/apache-maven-{ver}-bin.zip'
    p=R/'tools'/url.split('/')[-1]
    if not p.exists(): p.write_bytes(get(url))
    data=p.read_bytes(); expected=get(url+'.sha512').decode().strip().split()[0]
    assert hashlib.sha512(data).hexdigest()==expected
    records.append({'url':url,'sha512':expected,'bytes':len(data)})
    if not (R/'tools'/f'apache-maven-{ver}').exists():
        with zipfile.ZipFile(p) as z: z.extractall(R/'tools')
    print('Maven ready',ver,flush=True)
savejson(R/'evidence'/'maven-distributions.json',records)
url='https://api.adoptium.net/v3/assets/latest/21/hotspot?architecture=x64&heap_size=normal&image_type=jdk&jvm_impl=hotspot&os=windows&vendor=eclipse'
assets=json.loads(get(url)); asset=assets[0]; savejson(R/'evidence'/'jdk-source.json',asset)
pkg=asset['binary']['package']; p=R/'tools'/pkg['name']
if not p.exists(): p.write_bytes(get(pkg['link']))
assert hashlib.sha256(p.read_bytes()).hexdigest()==pkg['checksum']
with zipfile.ZipFile(p) as z:
    top=z.namelist()[0].split('/')[0]
    if not (R/'tools'/top).exists(): z.extractall(R/'tools')
savejson(R/'protocol'/'runtime_paths.json',{'jdk':str(R/'tools'/top),'m3':str(R/'tools'/'apache-maven-3.9.16'),'m4':str(R/'tools'/'apache-maven-4.0.0-rc-7')})
print('JDK ready',top,flush=True)
