"""Materialize the remaining validation dependency from Maven Central."""
from experiments import *
from reactor_followup import fetch_artifact
import zipfile
if __name__=='__main__':
    cache=OUT/'openrewrite_full_checkouts/repository'
    if len(sys.argv)>1:
        source=Path(sys.argv[1]);relative=Path('com/puppycrawl/tools/checkstyle/10.20.1/checkstyle-10.20.1.jar')
        with zipfile.ZipFile(source) as archive:
            assert archive.testzip() is None
        destination=cache/relative;destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source,destination)
        tracking=destination.parent/'_remote.repositories'
        text=tracking.read_text() if tracking.exists() else ''
        if 'checkstyle-10.20.1.jar>central=' not in text:
            tracking.write_text(text+'\ncheckstyle-10.20.1.jar>central=\n')
        dump(OUT/'openrewrite_full_checkouts/dependency_materialization.json',dict(
            artifact='com.puppycrawl.tools:checkstyle:10.20.1',
            source_url='https://repo.maven.apache.org/maven2/'+relative.as_posix(),
            bytes=destination.stat().st_size,sha256=hashlib.sha256(destination.read_bytes()).hexdigest()))
    else:
        fetch_artifact(cache,'com.puppycrawl.tools','checkstyle','10.20.1',origin='https://repo.maven.apache.org/maven2')
    print('Checkstyle materialization complete',flush=True)
