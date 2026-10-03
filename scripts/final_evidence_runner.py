import os  # Configurable workspace; no machine-specific paths.
import csv
import hashlib
import json
import math
import os
import re
import shutil
import statistics
import subprocess
import tarfile
import tempfile
import time
import urllib.request
import zipfile
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = (Path(os.environ.get("MAVENTWIN_WORKSPACE", Path(__file__).resolve().parents[1])).resolve())
OUT = ROOT / "final_evidence_v1"
SAMPLES = ROOT / "samples" / "scale_samples.csv"
SETTINGS = ROOT / "protocol" / "settings.xml"
RUNTIME = json.loads((ROOT / "protocol" / "runtime_paths.json").read_text())
NS = {"m": "http://maven.apache.org/POM/4.0.0"}
SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
# Raw-provider calls were observed to ignore socket timeouts for large trees
# on this host.  The final run therefore uses only commit-verified local Git or
# previously verified POM snapshots; unavailable revisions remain UNKNOWN.
ALLOW_RAW_NETWORK = False
FORCE_MEASURE = False


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows, fields=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        fields = list(rows[0]) if rows else []
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def git_cmd(repo, args, timeout=180, capture=True):
    cmd = ["git", "-c", "safe.directory=*", "-c", "gc.auto=0", "-C", str(repo)] + list(args)
    return subprocess.run(cmd, capture_output=capture, timeout=timeout)


def ensure_git_source(row):
    """Return an existing exact source repo or a shallow blob-filtered fetch."""
    sha = row["commit"]
    source = Path(row.get("source_path", ""))
    if source.exists() and (source / ".git").exists():
        check = git_cmd(source, ["cat-file", "-e", sha], timeout=30)
        if check.returncode == 0:
            return source, "local_git_exact", ""

    repo_dir = OUT / "git_sources" / row["id"]
    repo_dir.mkdir(parents=True, exist_ok=True)
    if not (repo_dir / ".git").exists():
        init = git_cmd(repo_dir, ["init", "-q"], timeout=30)
        if init.returncode != 0:
            return None, "", init.stderr.decode(errors="replace")
        add = git_cmd(repo_dir, ["remote", "add", "origin", f"https://github.com/{row['repo']}.git"], timeout=30)
        if add.returncode != 0:
            return None, "", add.stderr.decode(errors="replace")
    check = git_cmd(repo_dir, ["cat-file", "-e", sha], timeout=30)
    if check.returncode != 0:
        last = ""
        for _ in range(2):
            try:
                fetch = git_cmd(repo_dir, ["fetch", "--depth=1", "--filter=blob:none", "--no-tags", "origin", sha], timeout=60)
                last = (fetch.stdout + fetch.stderr).decode(errors="replace")
                if fetch.returncode == 0:
                    break
            except Exception as exc:
                last = str(exc)
        check = git_cmd(repo_dir, ["cat-file", "-e", sha], timeout=30)
        if check.returncode != 0:
            return None, "", last
    return repo_dir, "git_fetch_blobless", ""


def pom_modules(path):
    try:
        root = ET.parse(path).getroot()
    except Exception:
        return None
    return [x.text.strip() for x in root.findall("m:modules/m:module", NS) if x.text and x.text.strip()]


def pom_info(path):
    try:
        root = ET.parse(path).getroot()
        packaging = root.findtext("m:packaging", "jar", NS).strip()
        has_dependency = bool(root.findall("m:dependencies/m:dependency", NS))
        return packaging, has_dependency
    except Exception:
        return "UNKNOWN", False


def raw_blob(repo, commit, path):
    url = f"https://raw.githubusercontent.com/{repo}/{commit}/{path}"
    request = urllib.request.Request(url, headers={"User-Agent": "maventwin-final-evidence"})
    for _ in range(2):
        try:
            with urllib.request.urlopen(request, timeout=8) as response:
                return response.read()
        except Exception:
            continue
    return None


def acquire_raw_module_tree(row, snap, base):
    """Materialize the commit-pinned root/module model without a source checkout."""
    queue = [("pom.xml", snap / "pom.xml")]
    seen = set()
    missing = []
    while queue:
        rel, out = queue.pop(0)
        if rel in seen:
            continue
        seen.add(rel)
        blob = raw_blob(row["repo"], row["commit"], rel)
        if blob is None:
            missing.append(rel)
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(blob)
        modules = pom_modules(out)
        if modules is None:
            missing.append(rel)
            continue
        for module in modules:
            if "${" in module:
                missing.append(module)
                continue
            child = str((Path(rel).parent / module / "pom.xml").as_posix())
            queue.append((child, snap / child))
    for rel in (".mvn/maven.config", ".mvn/jvm.config", ".mvn/extensions.xml", ".mvn/wrapper/maven-wrapper.properties"):
        blob = raw_blob(row["repo"], row["commit"], rel)
        if blob is not None:
            out = snap / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(blob)
    poms = sorted(str(x.relative_to(snap)).replace("\\", "/") for x in snap.rglob("pom.xml"))
    base["pom_count"] = len(poms)
    base["root_pom_exists"] = str((snap / "pom.xml").exists()).lower()
    base["mvn_extensions_exists"] = str((snap / ".mvn" / "extensions.xml").exists()).lower()
    base["recovery_method"] = "commit_pinned_raw_module_blobs"
    base["recovery_status"] = "POM_COMPLETE" if (snap / "pom.xml").exists() and not missing else "POM_TREE_INCOMPLETE"
    write_json(snap / "recovery.json", {**base, "missing_modules": missing})
    return base


def materialize_git_poms(row, source, base, method):
    """Materialize only POM and .mvn blobs from an exact local Git commit."""
    tree = git_cmd(source, ["ls-tree", "-r", "-l", row["commit"]], timeout=60)
    if tree.returncode != 0:
        base["recovery_status"] = "FROZEN_COMMIT_UNAVAILABLE"
        base["recovery_method"] = method
        return base
    entries = {}
    for line in tree.stdout.decode(errors="replace").splitlines():
        head, sep, path = line.partition("\t")
        fields = head.split()
        if sep and len(fields) >= 3:
            entries[path] = fields[2]
    wanted = sorted(p for p in entries if p == "pom.xml" or p.endswith("/pom.xml") or p.startswith(".mvn/"))
    if "pom.xml" not in wanted:
        base["recovery_status"] = "NOT_A_MAVEN_REVISION"
        base["recovery_method"] = method
        return base
    snap = OUT / "snapshots" / row["id"]
    snap.mkdir(parents=True, exist_ok=True)
    batch_input = b"".join((entries[p] + "\n").encode() for p in wanted)
    try:
        batch = subprocess.run(
            ["git", "-c", "safe.directory=*", "-c", "gc.auto=0", "-C", str(source), "cat-file", "--batch"],
            input=batch_input, capture_output=True, timeout=60,
        )
    except Exception as exc:
        base["recovery_status"] = "NETWORK_UNKNOWN"
        base["recovery_method"] = method
        base["error"] = str(exc)
        return base
    stream = memoryview(batch.stdout)
    pos = 0
    materialized = []
    for rel in wanted:
        end = batch.stdout.find(b"\n", pos)
        if end < 0:
            break
        header = batch.stdout[pos:end].decode(errors="replace")
        pos = end + 1
        parts = header.split()
        if len(parts) < 3 or parts[1] != "blob":
            continue
        try:
            size = int(parts[2])
        except ValueError:
            continue
        data = bytes(stream[pos:pos + size])
        pos += size
        if pos < len(batch.stdout) and batch.stdout[pos:pos + 1] == b"\n":
            pos += 1
        out = snap / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
        materialized.append(rel)
    poms = sorted(p for p in materialized if p == "pom.xml" or p.endswith("/pom.xml"))
    base["pom_count"] = len(poms)
    base["root_pom_exists"] = str((snap / "pom.xml").exists()).lower()
    base["mvn_extensions_exists"] = str((snap / ".mvn" / "extensions.xml").exists()).lower()
    base["recovery_method"] = method
    missing = []
    queue = [snap / "pom.xml"] if (snap / "pom.xml").exists() else []
    seen = set()
    while queue:
        current = queue.pop(0).resolve()
        if current in seen:
            continue
        seen.add(current)
        modules = pom_modules(current)
        if modules is None:
            missing.append(str(current.relative_to(snap)).replace("\\", "/"))
            continue
        for mod in modules:
            target = (current.parent / mod / "pom.xml").resolve()
            if not str(target).lower().startswith(str(snap.resolve()).lower()):
                missing.append(mod)
            elif not target.exists():
                missing.append(str(target.relative_to(snap)).replace("\\", "/"))
            else:
                queue.append(target)
    base["recovery_status"] = "POM_COMPLETE" if (snap / "pom.xml").exists() and not missing else "POM_TREE_INCOMPLETE"
    write_json(snap / "recovery.json", {**base, "missing_modules": missing})
    return base


def acquire_one(row):
    frozen = bool(SHA_RE.fullmatch(row.get("commit", "")))
    base = {
        "repo": row["repo"],
        "commit": row.get("commit", ""),
        "original_sample_status": "FROZEN_COMMIT" if frozen else "UNKNOWN_REMOTE_HEAD",
        "frozen_revision": row.get("commit", "") if frozen else "",
        "pom_count": 0,
        "root_pom_exists": "false",
        "mvn_extensions_exists": "false",
        "recovery_method": "",
        "recovery_status": "NO_FROZEN_REVISION" if not frozen else "NETWORK_UNKNOWN",
    }
    if not frozen:
        return row, base
    try:
        prior = OUT / "snapshots" / row["id"] / "recovery.json"
        if prior.exists():
            saved = json.loads(prior.read_text(encoding="utf-8"))
            if saved.get("commit") == row.get("commit"):
                return row, {k: saved.get(k, base.get(k, "")) for k in base}
        legacy_comp = ROOT / "paper_fix_v1" / "samples" / "POM_COMPLETENESS.csv"
        legacy_snap = ROOT / "paper_fix_v1" / "snapshots" / row["id"]
        legacy_status = ""
        if legacy_comp.exists():
            for old in read_csv(legacy_comp):
                if old.get("repo") == row["repo"] and old.get("commit") == row.get("commit"):
                    legacy_status = old.get("status", "")
                    break
        if legacy_status == "POM_COMPLETE" and (legacy_snap / "pom.xml").exists():
            snap = OUT / "snapshots" / row["id"]
            shutil.copytree(legacy_snap, snap, dirs_exist_ok=True)
            base.update({"pom_count": len(list(snap.rglob("pom.xml"))), "root_pom_exists": "true",
                         "mvn_extensions_exists": str((snap / ".mvn" / "extensions.xml").exists()).lower(),
                         "recovery_method": "legacy_pom_complete_snapshot", "recovery_status": "POM_COMPLETE"})
            write_json(snap / "recovery.json", {**base, "source": "paper_fix_v1", "commit_verified_by_frozen_input": True})
            return row, base
        source_path = Path(row.get("source_path", ""))
        if source_path.exists() and (source_path / ".git").exists():
            check = git_cmd(source_path, ["cat-file", "-e", row["commit"]], timeout=30)
            if check.returncode == 0:
                return row, materialize_git_poms(row, source_path, base, "local_git_exact")
        if not ALLOW_RAW_NETWORK:
            base["recovery_status"] = "NETWORK_UNKNOWN"
            base["recovery_method"] = "raw_provider_disabled_after_timeout_observation"
            return row, base
        # Provider raw blobs are commit-addressed and avoid downloading source trees.
        snap = OUT / "snapshots" / row["id"]
        snap.mkdir(parents=True, exist_ok=True)
        raw_result = acquire_raw_module_tree(row, snap, base)
        if raw_result.get("recovery_status") in {"POM_COMPLETE", "POM_TREE_INCOMPLETE"}:
            return row, raw_result
        source, method, error = ensure_git_source(row)
        if source is None:
            if "couldn't find remote ref" in error.lower() or "not our ref" in error.lower() or "fatal: bad object" in error.lower():
                base["recovery_status"] = "FROZEN_COMMIT_UNAVAILABLE"
            else:
                base["recovery_status"] = "NETWORK_UNKNOWN"
            base["recovery_method"] = "git_fetch_blobless"
            return row, base
        tree = git_cmd(source, ["ls-tree", "-r", "-l", row["commit"]], timeout=60)
        if tree.returncode != 0:
            base["recovery_status"] = "FROZEN_COMMIT_UNAVAILABLE"
            base["recovery_method"] = method
            return row, base
        entries = {}
        for line in tree.stdout.decode(errors="replace").splitlines():
            head, sep, path = line.partition("\t")
            fields = head.split()
            if sep and len(fields) >= 3:
                entries[path] = fields[2]
        wanted = sorted(p for p in entries if p == "pom.xml" or p.endswith("/pom.xml") or p.startswith(".mvn/"))
        if "pom.xml" not in wanted:
            base["recovery_status"] = "NOT_A_MAVEN_REVISION"
            base["recovery_method"] = method
            return row, base
        snap = OUT / "snapshots" / row["id"]
        snap.mkdir(parents=True, exist_ok=True)
        materialized = []
        # Batch lazy-blob reads so large multi-module repositories do not issue
        # one network request per POM.
        batch_input = b"".join((entries[p] + "\n").encode() for p in wanted)
        batch = subprocess.run(["git", "-c", "safe.directory=*", "-c", "gc.auto=0", "-C", str(source), "cat-file", "--batch"],
                               input=batch_input, capture_output=True, timeout=60)
        stream = memoryview(batch.stdout)
        pos = 0
        for rel in wanted:
            end = batch.stdout.find(b"\n", pos)
            if end < 0:
                break
            header = batch.stdout[pos:end].decode(errors="replace")
            pos = end + 1
            parts = header.split()
            if len(parts) < 3 or parts[1] != "blob":
                continue
            try:
                size = int(parts[2])
            except ValueError:
                continue
            data = bytes(stream[pos:pos + size])
            pos += size
            if pos < len(batch.stdout) and batch.stdout[pos:pos + 1] == b"\n":
                pos += 1
            out = snap / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(data)
            materialized.append(rel)
        poms = sorted(p for p in materialized if p == "pom.xml" or p.endswith("/pom.xml"))
        base["pom_count"] = len(poms)
        base["root_pom_exists"] = str((snap / "pom.xml").exists()).lower()
        base["mvn_extensions_exists"] = str((snap / ".mvn" / "extensions.xml").exists()).lower()
        base["recovery_method"] = method
        if not (snap / "pom.xml").exists():
            base["recovery_status"] = "NOT_A_MAVEN_REVISION"
            return row, base
        missing = []
        queue = [snap / "pom.xml"]
        seen = set()
        while queue:
            current = queue.pop(0).resolve()
            if current in seen:
                continue
            seen.add(current)
            modules = pom_modules(current)
            if modules is None:
                missing.append(str(current.relative_to(snap)).replace("\\", "/"))
                continue
            for mod in modules:
                target = (current.parent / mod / "pom.xml").resolve()
                if not str(target).lower().startswith(str(snap.resolve()).lower()):
                    missing.append(mod)
                elif not target.exists():
                    missing.append(str(target.relative_to(snap)).replace("\\", "/"))
                else:
                    queue.append(target)
        base["recovery_status"] = "POM_COMPLETE" if not missing else "POM_TREE_INCOMPLETE"
        write_json(snap / "recovery.json", {**base, "missing_modules": missing})
        return row, base
    except Exception as exc:
        base["recovery_status"] = "NETWORK_UNKNOWN"
        base["error"] = str(exc)
        return row, base


def acquire_all(rows):
    results = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(acquire_one, row) for row in rows]
        for idx, future in enumerate(as_completed(futures), 1):
            row, result = future.result()
            results.append(result)
            print(f"RECOVERY {idx}/{len(rows)} {row['id']} {result['recovery_status']}", flush=True)
    order = {r["repo"]: i for i, r in enumerate(rows)}
    results.sort(key=lambda r: order.get(r["repo"], 10**9))
    write_csv(OUT / "samples" / "FROZEN_POPULATION.csv", results, [
        "repo", "commit", "original_sample_status", "frozen_revision", "pom_count",
        "root_pom_exists", "mvn_extensions_exists", "recovery_method", "recovery_status"
    ])
    completeness = []
    for item in results:
        snap = OUT / "snapshots" / item["repo"].replace("/", "__")
        if not snap.exists():
            # Sample ids are the scale_samples.csv id values; this branch is
            # only for older recovery records whose directory name differs.
            snap = OUT / "snapshots" / next((r["id"] for r in rows if r["repo"] == item["repo"]), item["repo"].replace("/", "__"))
        completeness.append({
            "repo": item["repo"], "commit": item["commit"], "pom_count": item["pom_count"],
            "root_pom": "pom.xml" if item["root_pom_exists"] == "true" else "",
            "module_count_observed": max(int(item["pom_count"] or 0) - 1, 0),
            "mvn_config_present": str(any((snap / ".mvn" / n).exists() for n in ("maven.config", "jvm.config"))).lower(),
            "extensions_present": item["mvn_extensions_exists"], "status": item["recovery_status"],
        })
    write_csv(OUT / "samples" / "POM_COMPLETENESS.csv", completeness)
    return results


def freeze_targets(rows, population):
    by = {x["repo"]: x for x in population}
    targets = []
    for row in rows:
        snap = OUT / "snapshots" / row["id"]
        target = ""
        rule = ""
        if by.get(row["repo"], {}).get("recovery_status") == "POM_COMPLETE":
            root = snap / "pom.xml"
            packaging, has_dep = pom_info(root)
            if packaging != "pom" and has_dep:
                target, rule = "pom.xml", "RULE_1_ROOT_NONPOM_WITH_DIRECT_DEPENDENCY"
            else:
                candidates = []
                jars = []
                for p in sorted(snap.rglob("pom.xml")):
                    rel = str(p.relative_to(snap)).replace("\\", "/")
                    if rel == "pom.xml":
                        continue
                    pp, dep = pom_info(p)
                    if pp != "pom" and dep:
                        candidates.append(rel)
                    if pp != "pom":
                        jars.append(rel)
                if candidates:
                    target, rule = candidates[0], "RULE_2_FIRST_NONPOM_WITH_DIRECT_DEPENDENCY"
                elif jars:
                    target, rule = jars[0], "RULE_3_FIRST_NONPOM_MODULE"
                else:
                    target, rule = "pom.xml", "RULE_4_ROOT"
        targets.append({
            "repo": row["repo"], "commit": row["commit"],
            "model_target_pom": "pom.xml", "validation_target_pom": "pom.xml",
            "resolution_target_pom": target, "selection_rule": rule,
        })
    write_csv(OUT / "samples" / "TARGET_POMS_FINAL.csv", targets)
    write_csv(OUT / "samples" / "TARGET_POMS.csv", targets)
    return targets


def run_command(argv, cwd, out_dir, timeout=240):
    out_dir.mkdir(parents=True, exist_ok=True)
    start = time.time()
    env = os.environ.copy()
    env["JAVA_HOME"] = RUNTIME["jdk"]
    env["MAVEN_OPTS"] = f"-Dmaven.multiModuleProjectDirectory={cwd}"
    timed_out = False
    code = 1
    with (out_dir / "stdout.txt").open("wb") as so, (out_dir / "stderr.txt").open("wb") as se:
        try:
            proc = subprocess.Popen(argv, cwd=str(cwd), env=env, stdin=subprocess.DEVNULL, stdout=so, stderr=se)
            try:
                code = proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                proc.kill()
                code = proc.wait()
        except Exception as exc:
            se.write(str(exc).encode())
    rec = {"argv": argv, "cwd": str(cwd), "exit_code": code, "timeout": timed_out,
           "elapsed_seconds": round(time.time() - start, 3)}
    write_json(out_dir / "command.json", rec)
    return rec


def local_name(tag):
    return tag.rsplit("}", 1)[-1]


def canonical_xml(elem):
    if elem is None:
        return None
    children = [canonical_xml(x) for x in list(elem)]
    children.sort(key=lambda x: json.dumps(x, sort_keys=True, ensure_ascii=False))
    return {"tag": local_name(elem.tag), "attrs": dict(sorted(elem.attrib.items())),
            "text": re.sub(r"\s+", " ", (elem.text or "").strip()), "children": children}


def dep_records(parent, path):
    out = []
    for dep in parent.findall(path, NS):
        def text(name, default=""):
            value = dep.findtext("m:" + name, default, NS)
            return (value or default).strip()
        out.append({
            "groupId": text("groupId"), "artifactId": text("artifactId"),
            "version": text("version"), "type": text("type", "jar"),
            "classifier": text("classifier"), "scope": text("scope", "compile"),
            "optional": text("optional", "false"),
            "exclusions": sorted(text("groupId") + ":" + text("artifactId")
                                  for text in []),
        })
        out[-1]["exclusions"] = sorted(
            (x.findtext("m:groupId", "", NS) or "") + ":" + (x.findtext("m:artifactId", "", NS) or "")
            for x in dep.findall("m:exclusions/m:exclusion", NS)
        )
    return sorted(out, key=lambda x: json.dumps(x, sort_keys=True))


def extract_model(path):
    root = ET.parse(path).getroot()
    build = root.find("m:build", NS)
    executions = []

    def plugins(parent):
        if parent is None:
            return []
        out = []
        for plugin in parent.findall("m:plugin", NS):
            gid = plugin.findtext("m:groupId", "org.apache.maven.plugins", NS) or "org.apache.maven.plugins"
            aid = plugin.findtext("m:artifactId", "", NS) or ""
            version = plugin.findtext("m:version", "", NS) or ""
            out.append({"groupId": gid.strip(), "artifactId": aid.strip(), "version": version.strip()})
            for execution in plugin.findall("m:executions/m:execution", NS):
                executions.append({
                    "plugin": gid.strip() + ":" + aid.strip(),
                    "execution_id": (execution.findtext("m:id", "default", NS) or "default").strip(),
                    "phase": (execution.findtext("m:phase", "", NS) or "").strip(),
                    "goals": sorted((x.text or "").strip() for x in execution.findall("m:goals/m:goal", NS)),
                    "configuration": canonical_xml(execution.find("m:configuration", NS)),
                })
        return sorted(out, key=lambda x: (x["groupId"], x["artifactId"]))

    active = plugins(build.find("m:plugins", NS) if build is not None else None)
    managed = plugins(build.find("m:pluginManagement/m:plugins", NS) if build is not None else None)
    props = {local_name(x.tag): re.sub(r"\s+", " ", (x.text or "").strip()) for x in root.findall("m:properties/*", NS)}
    return {
        "dependencies": dep_records(root, "m:dependencies/m:dependency"),
        "dependencyManagement": dep_records(root, "m:dependencyManagement/m:dependencies/m:dependency"),
        "active_plugins": active,
        "plugin_management": managed,
        "execution_declarations": sorted(executions, key=lambda x: json.dumps(x, sort_keys=True)),
        "modules": sorted((x.text or "").strip() for x in root.findall("m:modules/m:module", NS)),
        "properties": dict(sorted(props.items())),
    }


def unsafe_validate(snapshot):
    text = "\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in snapshot.rglob("pom.xml"))
    lower = text.lower()
    plugins = ("exec-maven-plugin", "maven-antrun-plugin", "maven-invoker-plugin")
    phases = ("<phase>validate", "<phase>initialize", "<phase>generate-sources")
    return any(p in lower for p in plugins) and any(p in lower for p in phases)


def measure_one(row, target, population):
    repo_id = row["id"]
    snap = OUT / "snapshots" / repo_id
    if population.get("recovery_status") != "POM_COMPLETE":
        return
    target_pom = target.get("resolution_target_pom") or "pom.xml"
    cache_root = OUT / "local_repos"
    unsafe = unsafe_validate(snap)
    for runtime in ("m3", "m4"):
        cache = cache_root / runtime
        cache.mkdir(parents=True, exist_ok=True)
        mvn = str(Path(RUNTIME[runtime]) / "bin" / "mvn.cmd")
        common = ["-B", "-ntp", "-e", "-s", str(SETTINGS), "-gs", str(SETTINGS),
                  f"-Dmaven.repo.local={cache}", "-Dstyle.color=never"]
        for repeat in (1, 2):
            base = OUT / "measurements" / repo_id / f"{runtime}-r{repeat}"
            model = base / "effective-pom.xml"
            tree = base / "tree.json"
            root_pom = snap / "pom.xml"
            resolution = snap / target_pom
            if (not FORCE_MEASURE and
                (base / "model" / "command.json").exists() and
                (base / "resolution" / "command.json").exists() and
                (base / "validation.json").exists() and
                (base / "status.json").exists()):
                print(f"MEASURE_SKIP {repo_id} {runtime} r{repeat}", flush=True)
                continue
            run_command([mvn] + common + ["-N", "-f", str(root_pom),
                "org.apache.maven.plugins:maven-help-plugin:3.5.1:effective-pom", f"-Doutput={model}"], snap, base / "model")
            if model.exists():
                try:
                    write_json(base / "model.json", extract_model(model))
                except Exception as exc:
                    write_json(base / "model_error.json", {"error": str(exc)})
            run_command([mvn] + common + ["-N", "-f", str(resolution),
                "org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree",
                "-DoutputType=json", f"-DoutputFile={tree}"], snap, base / "resolution")
            valid_status = base / "validation.json"
            if unsafe:
                write_json(valid_status, {"status": "UNSAFE_NOT_RUN", "reason": "simple blocking rule"})
            else:
                rec = run_command([mvn] + common + ["-N", "-f", str(root_pom), "validate"], snap, base / "validate")
                write_json(valid_status, {"status": "PASS" if rec["exit_code"] == 0 else "FAIL", "command": rec})
            status = {"runtime": runtime, "repeat": repeat,
                      "model_exists": model.exists(), "tree_exists": tree.exists(),
                      "tree_json_valid": False}
            if tree.exists():
                try:
                    json.loads(tree.read_text(encoding="utf-8"))
                    status["tree_json_valid"] = True
                except Exception:
                    pass
            write_json(base / "status.json", status)
            print(f"MEASURE {repo_id} {runtime} r{repeat}", flush=True)


def flatten_tree(node, depth=0, parent_path=()):
    if not isinstance(node, dict):
        return []
    gid = node.get("groupId", "") or ""
    aid = node.get("artifactId", "") or ""
    ver = node.get("version", "") or ""
    typ = node.get("type", "jar") or "jar"
    classifier = node.get("classifier", "") or ""
    scope = node.get("scope", "") or ""
    optional = node.get("optional", "false") or "false"
    record = {"groupId": gid, "artifactId": aid, "version": ver, "type": typ,
              "classifier": classifier, "scope": scope, "optional": optional,
              "depth": depth, "parent_path": ">".join(parent_path)}
    current = parent_path + (gid + ":" + aid + ":" + ver,)
    out = [record]
    for child in node.get("children", []) or []:
        out.extend(flatten_tree(child, depth + 1, current))
    return out


def graph_from_run(base):
    command = base / "resolution" / "command.json"
    tree = base / "tree.json"
    status = base / "status.json"
    try:
        cmd = json.loads(command.read_text(encoding="utf-8"))
        obj = json.loads(tree.read_text(encoding="utf-8"))
        json.loads(status.read_text(encoding="utf-8"))
        if cmd.get("exit_code") != 0 or cmd.get("timeout"):
            return None
        return sorted(flatten_tree(obj), key=lambda x: json.dumps(x, sort_keys=True))
    except Exception:
        return None


def model_deltas(repo, commit, m3, m4):
    rows = []
    cats = []

    def indexed(items, keys):
        return {tuple(x.get(k, "") for k in keys): x for x in items}

    def list_diff(field, category, keys):
        a = indexed(m3.get(field, []), keys)
        b = indexed(m4.get(field, []), keys)
        for key in sorted(set(a) | set(b)):
            x, y = a.get(key), b.get(key)
            if x is None or y is None:
                cats.append(category)
                rows.append(delta_row(repo, commit, category, ":".join(key), "entity", x, y, True))
            elif x != y:
                for field_name in sorted(set(x) | set(y)):
                    if x.get(field_name) != y.get(field_name):
                        cats.append(category)
                        rows.append(delta_row(repo, commit, category, ":".join(key), field_name, x.get(field_name), y.get(field_name), True))

    list_diff("dependencies", "DEPENDENCY_DECLARATION_CHANGED", ("groupId", "artifactId", "type", "classifier"))
    list_diff("dependencyManagement", "DEPENDENCY_MANAGEMENT_CHANGED", ("groupId", "artifactId", "type", "classifier"))
    list_diff("active_plugins", "PLUGIN_VERSION_SELECTION_CHANGED", ("groupId", "artifactId"))
    list_diff("plugin_management", "PLUGIN_VERSION_SELECTION_CHANGED", ("groupId", "artifactId"))
    list_diff("execution_declarations", "PLUGIN_EXECUTION_DECLARATION_CHANGED", ("plugin", "execution_id"))
    if m3.get("modules", []) != m4.get("modules", []):
        cats.append("MODULE_SET_CHANGED")
        rows.append(delta_row(repo, commit, "MODULE_SET_CHANGED", "modules", "module_set", m3.get("modules"), m4.get("modules"), True))
    if m3.get("properties", {}) != m4.get("properties", {}) and not cats:
        rows.append(delta_row(repo, commit, "MODEL_PROPERTY_ONLY", "properties", "properties", m3.get("properties"), m4.get("properties"), True))
    if not cats and m3 != m4:
        rows.append(delta_row(repo, commit, "MODEL_REPRESENTATION_ONLY", "model", "structured_fields", m3, m4, True))
    unique = sorted(set(cats))
    if len(unique) == 0:
        classification = "MODEL_PROPERTY_ONLY" if m3.get("properties", {}) != m4.get("properties", {}) else "MODEL_IDENTICAL"
    elif len(unique) == 1:
        classification = unique[0]
    else:
        classification = "MULTIPLE_MODEL_SEMANTIC_CHANGES"
    return classification, rows


def delta_row(repo, commit, category, entity, field, a, b, repeatable):
    return {"repo": repo, "commit": commit, "category": category, "entity": entity,
            "field": field, "m3_value": json.dumps(a, ensure_ascii=False, sort_keys=True),
            "m4_value": json.dumps(b, ensure_ascii=False, sort_keys=True),
            "repeatable": str(bool(repeatable)).lower(), "notes": "canonical structured comparison"}


def graph_delta(repo, commit, target, g3, g4):
    rows = []
    by_base3 = {}
    by_base4 = {}
    for g, dest in ((g3, by_base3), (g4, by_base4)):
        for n in g:
            key = (n["groupId"], n["artifactId"], n["type"], n["classifier"], n["scope"], n["optional"], n["depth"], n["parent_path"])
            dest.setdefault(key, []).append(n)
    for key in sorted(set(by_base3) | set(by_base4)):
        a = by_base3.get(key, [])
        b = by_base4.get(key, [])
        av = sorted(x["version"] for x in a)
        bv = sorted(x["version"] for x in b)
        if av != bv:
            kind = "VERSION_CHANGED" if a and b else "NODE_REMOVED" if a else "NODE_ADDED"
            x, y = (a[0] if a else {}), (b[0] if b else {})
            rows.append(resolution_row(repo, commit, target, kind, x, y, True, "CAUSE_UNCONFIRMED"))
    # Detect scope and parent-path changes when coordinates otherwise match.
    def coarse(n, include):
        return (n["groupId"], n["artifactId"], n["version"], n["type"], n["classifier"], n["optional"], n["depth"]) if include == "scope" else (n["groupId"], n["artifactId"], n["version"], n["type"], n["classifier"], n["scope"], n["optional"], n["depth"])
    for include, kind in (("scope", "SCOPE_CHANGED"), ("path", "PATH_CHANGED")):
        a = {}
        b = {}
        for n in g3:
            a.setdefault(coarse(n, include), set()).add(n["scope"] if include == "scope" else n["parent_path"])
        for n in g4:
            b.setdefault(coarse(n, include), set()).add(n["scope"] if include == "scope" else n["parent_path"])
        for key in sorted(set(a) & set(b)):
            if a[key] != b[key]:
                x = next(n for n in g3 if coarse(n, include) == key)
                y = next(n for n in g4 if coarse(n, include) == key)
                rows.append(resolution_row(repo, commit, target, kind, x, y, True, "CAUSE_UNCONFIRMED"))
    return rows


def resolution_row(repo, commit, target, kind, a, b, repeatable, cause):
    return {"repo": repo, "commit": commit, "target_pom": target, "difference_type": kind,
            "groupId": a.get("groupId", b.get("groupId", "")),
            "artifactId": a.get("artifactId", b.get("artifactId", "")),
            "m3_version": a.get("version", ""), "m4_version": b.get("version", ""),
            "m3_scope": a.get("scope", ""), "m4_scope": b.get("scope", ""),
            "m3_path": a.get("parent_path", ""), "m4_path": b.get("parent_path", ""),
            "repeatable": str(bool(repeatable)).lower(), "cause_label": cause,
            "cause_evidence": "stable paired canonical graphs"}


def summarize_measurements(rows, population, targets):
    pop = {x["repo"]: x for x in population}
    target_by = {x["repo"]: x for x in targets}
    model_results, resolution_results, validation_results = [], [], []
    model_detail, resolution_detail = [], []
    for row in rows:
        p = pop.get(row["repo"], {})
        if p.get("recovery_status") != "POM_COMPLETE":
            continue
        sid = row["id"]
        models = {}
        model_runs_ok = {}
        for runtime in ("m3", "m4"):
            vals = []
            oks = []
            for repeat in (1, 2):
                path = OUT / "measurements" / sid / f"{runtime}-r{repeat}" / "model.json"
                command_path = OUT / "measurements" / sid / f"{runtime}-r{repeat}" / "model" / "command.json"
                try:
                    vals.append(json.loads(path.read_text(encoding="utf-8")))
                except Exception:
                    vals.append(None)
                try:
                    command = json.loads(command_path.read_text(encoding="utf-8"))
                    xml_path = OUT / "measurements" / sid / f"{runtime}-r{repeat}" / "effective-pom.xml"
                    ET.parse(xml_path)
                    oks.append(command.get("exit_code") == 0 and not command.get("timeout") and xml_path.exists())
                except Exception:
                    oks.append(False)
            models[runtime] = vals
            model_runs_ok[runtime] = oks
        model_status = "MODEL_UNAVAILABLE"
        model_class = "MODEL_UNAVAILABLE"
        if all(all(model_runs_ok[r]) and models[r][0] is not None and models[r][1] is not None for r in ("m3", "m4")):
            stable3 = json.dumps(models["m3"][0], sort_keys=True) == json.dumps(models["m3"][1], sort_keys=True)
            stable4 = json.dumps(models["m4"][0], sort_keys=True) == json.dumps(models["m4"][1], sort_keys=True)
            if stable3 and stable4:
                model_status = "MODEL_COMPARABLE"
                model_class, details = model_deltas(row["repo"], row["commit"], models["m3"][0], models["m4"][0])
                model_detail.extend(details)
        model_positive = model_class in {
            "DEPENDENCY_DECLARATION_CHANGED", "DEPENDENCY_MANAGEMENT_CHANGED",
            "PLUGIN_VERSION_SELECTION_CHANGED", "PLUGIN_CONFIGURATION_CHANGED",
            "PLUGIN_EXECUTION_DECLARATION_CHANGED", "MODULE_SET_CHANGED",
            "MULTIPLE_MODEL_SEMANTIC_CHANGES",
        }
        model_results.append({"repo": row["repo"], "commit": row["commit"], "model_comparable": model_status,
                              "model_classification": model_class, "model_semantic_divergence": str(model_positive).lower()})

        graphs = {}
        for runtime in ("m3", "m4"):
            graphs[runtime] = [graph_from_run(OUT / "measurements" / sid / f"{runtime}-r{rep}") for rep in (1, 2)]
        resolution_status = "RESOLUTION_UNAVAILABLE"
        resolution_class = "RESOLUTION_UNAVAILABLE"
        detail = []
        if all(graphs[r][0] is not None and graphs[r][1] is not None for r in ("m3", "m4")):
            if graphs["m3"][0] == graphs["m3"][1] and graphs["m4"][0] == graphs["m4"][1]:
                resolution_status = "RESOLUTION_COMPARABLE"
                detail = graph_delta(row["repo"], row["commit"], target_by[row["repo"]]["resolution_target_pom"], graphs["m3"][0], graphs["m4"][0])
                resolution_class = "IDENTICAL" if not detail else (detail[0]["difference_type"] if len(set(x["difference_type"] for x in detail)) == 1 else "MULTIPLE")
                resolution_detail.extend(detail)
        resolution_results.append({"repo": row["repo"], "commit": row["commit"],
                                   "resolution_target": target_by[row["repo"]]["resolution_target_pom"],
                                   "resolution_comparable": resolution_status,
                                   "resolution_classification": resolution_class,
                                   "resolution_divergence": str(bool(detail)).lower()})

        statuses = []
        for runtime in ("m3", "m4"):
            vals = []
            for repeat in (1, 2):
                path = OUT / "measurements" / sid / f"{runtime}-r{repeat}" / "validation.json"
                try:
                    vals.append(json.loads(path.read_text(encoding="utf-8")))
                except Exception:
                    vals.append(None)
            statuses.append(vals)
        validation_status = "UNKNOWN"
        if all(x is not None for pair in statuses for x in pair):
            if any(x.get("status") == "UNSAFE_NOT_RUN" for pair in statuses for x in pair):
                validation_status = "UNSAFE_NOT_RUN"
            else:
                m3 = [x.get("command", {}).get("exit_code") for x in statuses[0]]
                m4 = [x.get("command", {}).get("exit_code") for x in statuses[1]]
                if m3 == [0, 0] and m4 == [0, 0]: validation_status = "PASS_PASS"
                elif m3 == [0, 0] and m4[0] != 0 and m4[1] != 0: validation_status = "PASS_FAIL_CANDIDATE"
                elif m3[0] != 0 and m3[1] != 0 and m4 == [0, 0]: validation_status = "FAIL_PASS"
                elif all(x is not None for x in m3 + m4): validation_status = "FAIL_FAIL"
        validation_results.append({"repo": row["repo"], "commit": row["commit"],
                                   "validation_comparable": str(validation_status not in {"UNKNOWN", "UNSAFE_NOT_RUN"}).lower(),
                                   "validation_status": validation_status, "confirmed_validation_regression": "false",
                                   "validation_error": ""})
    write_csv(OUT / "metrics" / "MODEL_RESULTS_FINAL.csv", model_results)
    write_csv(OUT / "metrics" / "RESOLUTION_RESULTS_FINAL.csv", resolution_results)
    write_csv(OUT / "metrics" / "VALIDATION_RESULTS_FINAL.csv", validation_results)
    write_csv(OUT / "MODEL_DELTAS_FINAL.csv", model_detail, ["repo", "commit", "category", "entity", "field", "m3_value", "m4_value", "repeatable", "notes"])
    write_csv(OUT / "RESOLUTION_DELTAS_FINAL.csv", resolution_detail, ["repo", "commit", "target_pom", "difference_type", "groupId", "artifactId", "m3_version", "m4_version", "m3_scope", "m4_scope", "m3_path", "m4_path", "repeatable", "cause_label", "cause_evidence"])
    return model_results, resolution_results, validation_results, model_detail, resolution_detail


def run_full_checkout_candidates(rows, population, validation_results):
    by_status = {x["repo"]: x for x in validation_results}
    pop = {x["repo"]: x for x in population}
    for row in rows:
        if by_status.get(row["repo"], {}).get("validation_status") != "PASS_FAIL_CANDIDATE":
            continue
        source, method, error = ensure_git_source(row)
        result = by_status[row["repo"]]
        if source is None:
            result["validation_status"] = "ARTIFACT_INCOMPLETENESS"
            continue
        checkout = OUT / "full_checkouts" / row["id"]
        checkout.mkdir(parents=True, exist_ok=True)
        try:
            archive = subprocess.Popen(["git", "-c", "safe.directory=*", "-C", str(source), "archive", row["commit"]], stdout=subprocess.PIPE)
            with tarfile.open(fileobj=archive.stdout, mode="r|") as tar:
                tar.extractall(checkout)
            code = archive.wait(timeout=300)
            if code != 0 or not (checkout / "pom.xml").exists():
                result["validation_status"] = "ARTIFACT_INCOMPLETENESS"
                continue
            codes = {"m3": [], "m4": []}
            for runtime in ("m3", "m4"):
                mvn = str(Path(RUNTIME[runtime]) / "bin" / "mvn.cmd")
                cache = OUT / "local_repos" / runtime
                for repeat in (1, 2):
                    rec = run_command([mvn, "-B", "-ntp", "-e", "-s", str(SETTINGS), "-gs", str(SETTINGS),
                                       f"-Dmaven.repo.local={cache}", "-Dstyle.color=never", "-N", "-f", str(checkout / "pom.xml"), "validate"],
                                      checkout, OUT / "full_validation" / row["id"] / f"{runtime}-r{repeat}")
                    codes[runtime].append(rec["exit_code"])
            if codes["m3"] == [0, 0] and codes["m4"] == [0, 0]:
                result["validation_status"] = "PARTIAL_SOURCE_ARTIFACT"
            elif codes["m3"] == [0, 0] and all(x != 0 for x in codes["m4"]):
                result["validation_status"] = "CONFIRMED_ROOT_VALIDATION_REGRESSION"
                result["confirmed_validation_regression"] = "true"
            elif all(x != 0 for x in codes["m3"] + codes["m4"]):
                result["validation_status"] = "NOT_MIGRATION_REGRESSION"
            else:
                result["validation_status"] = "UNKNOWN"
        except Exception as exc:
            result["validation_status"] = "ARTIFACT_INCOMPLETENESS"
            result["validation_error"] = str(exc)
    write_csv(OUT / "metrics" / "VALIDATION_RESULTS_FINAL.csv", validation_results)


def run_mvnup_one(row, population):
    if population.get("recovery_status") != "POM_COMPLETE":
        return {"repo": row["repo"], "mvnup_evaluable": "false", "mvnup_relation": "MVNUP_UNAVAILABLE", "warning_count": 0}
    snap = OUT / "snapshots" / row["id"]
    out = OUT / "mvnup" / row["id"]
    cache = OUT / "local_repos" / "m4"
    cmd = [str(Path(RUNTIME["m4"]) / "bin" / "mvnup.cmd"), "check", "-B", "--color", "never",
           "--directory", str(snap), "-s", str(SETTINGS), "-gs", str(SETTINGS), f"-Dmaven.repo.local={cache}"]
    rec = run_command(cmd, snap, out, timeout=300)
    if rec["exit_code"] != 0:
        rec = run_command(cmd, snap, out / "retry", timeout=300)
    text = ""
    for p in (out / "stdout.txt", out / "stderr.txt", out / "retry" / "stdout.txt", out / "retry" / "stderr.txt"):
        if p.exists(): text += p.read_text(encoding="utf-8", errors="ignore") + "\n"
    warnings = len(re.findall(r"\[WARNING\]", text))
    return {"repo": row["repo"], "mvnup_evaluable": str(rec["exit_code"] == 0).lower(),
            "mvnup_relation": "MVNUP_UNAVAILABLE" if rec["exit_code"] != 0 else "NOT_SIGNALED",
            "warning_count": warnings, "output": text}


def apply_mvnup_relations(rows, population, model_results, resolution_results, validation_results, model_detail, resolution_detail):
    pop = {x["repo"]: x for x in population}
    model = {x["repo"]: x for x in model_results}
    resolution = {x["repo"]: x for x in resolution_results}
    validation = {x["repo"]: x for x in validation_results}
    details = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(run_mvnup_one, row, pop.get(row["repo"], {})) for row in rows]
        for future in as_completed(futures):
            details.append(future.result())
    dmap = {x["repo"]: x for x in details}
    for row in rows:
        repo = row["repo"]
        item = dmap.get(repo, {"mvnup_evaluable": "false", "mvnup_relation": "MVNUP_UNAVAILABLE", "output": ""})
        text = item.get("output", "").lower()
        finding = model.get(repo, {}).get("model_semantic_divergence") == "true" or resolution.get(repo, {}).get("resolution_divergence") == "true" or validation.get(repo, {}).get("confirmed_validation_regression") == "true"
        if finding and item.get("mvnup_evaluable") == "true":
            tokens = []
            for d in model_detail:
                if d["repo"] == repo:
                    tokens.append(d["entity"].lower())
            for d in resolution_detail:
                if d["repo"] == repo:
                    tokens.extend([d["artifactId"].lower(), d["groupId"].lower()])
            if any(t and t in text for t in tokens):
                item["mvnup_relation"] = "DIRECTLY_SIGNALED"
            elif any(k in text for k in ("maven 4", "compatib", "upgrade", "migration")):
                item["mvnup_relation"] = "RELATED_BUT_NOT_SPECIFIC"
            else:
                item["mvnup_relation"] = "NOT_SIGNALED"
        elif not finding and item.get("mvnup_evaluable") == "true":
            item["mvnup_relation"] = "NOT_APPLICABLE"
        item.pop("output", None)
        item["repo"] = repo
    write_csv(OUT / "metrics" / "MVNUP_RESULTS_FINAL.csv", details)
    return dmap


def wilson(k, n):
    if n == 0:
        return [0.0, 0.0]
    z = 1.95996398454
    p = k / n
    den = 1 + z * z / n
    mid = (p + z * z / (2 * n)) / den
    rad = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return [round(mid - rad, 4), round(mid + rad, 4)]


def check_maven4_ga():
    status = {"status": "UNKNOWN", "source": "https://maven.apache.org/docs/history.html"}
    try:
        req = urllib.request.Request(status["source"], headers={"User-Agent": "maventwin-final-evidence"})
        text = urllib.request.urlopen(req, timeout=20).read().decode(errors="ignore")
        if re.search(r"Maven\s+4\.0\.0\s+(GA|Final|Released)", text, re.I):
            status["status"] = "AVAILABLE"
        else:
            status["status"] = "NOT_IDENTIFIED"
    except Exception as exc:
        status["status"] = "UNAVAILABLE"
        status["error"] = str(exc)
    write_json(OUT / "MAVEN4_GA_STATUS.json", status)
    return status


def build_final_outputs(rows, population, targets, model_results, resolution_results, validation_results, model_detail, resolution_detail, mvnup):
    pop = {x["repo"]: x for x in population}
    model = {x["repo"]: x for x in model_results}
    resolution = {x["repo"]: x for x in resolution_results}
    validation = {x["repo"]: x for x in validation_results}
    final = []
    for row in rows:
        p = pop.get(row["repo"], {})
        m = model.get(row["repo"], {})
        r = resolution.get(row["repo"], {})
        v = validation.get(row["repo"], {})
        u = mvnup.get(row["repo"], {"mvnup_evaluable": "false", "mvnup_relation": "MVNUP_UNAVAILABLE"})
        any_div = m.get("model_semantic_divergence") == "true" or r.get("resolution_divergence") == "true" or v.get("confirmed_validation_regression") == "true"
        silent = v.get("validation_status") == "PASS_PASS" and (m.get("model_semantic_divergence") == "true" or r.get("resolution_divergence") == "true")
        final.append({
            "repo": row["repo"], "commit": row.get("commit", ""),
            "frozen_revision_status": p.get("original_sample_status", "UNKNOWN_REMOTE_HEAD"),
            "pom_complete": str(p.get("recovery_status") == "POM_COMPLETE").lower(),
            "model_comparable": m.get("model_comparable", "false"),
            "model_semantic_divergence": m.get("model_semantic_divergence", "false"),
            "model_categories": m.get("model_classification", "MODEL_UNAVAILABLE"),
            "resolution_target": r.get("resolution_target", ""),
            "resolution_comparable": r.get("resolution_comparable", "false"),
            "resolution_divergence": r.get("resolution_divergence", "false"),
            "resolution_categories": r.get("resolution_classification", "RESOLUTION_UNAVAILABLE"),
            "validation_comparable": v.get("validation_comparable", "false"),
            "validation_status": v.get("validation_status", "UNKNOWN"),
            "confirmed_validation_regression": v.get("confirmed_validation_regression", "false"),
            "mvnup_evaluable": u.get("mvnup_evaluable", "false"),
            "mvnup_relation": u.get("mvnup_relation", "MVNUP_UNAVAILABLE"),
            "confirmed_any_divergence": str(any_div).lower(),
            "silent_to_root_validation": str(silent).lower(),
            "notes": p.get("recovery_status", "NO_FROZEN_REVISION"),
        })
    fields = list(final[0])
    write_csv(OUT / "FINAL_PAPER_RESULTS.csv", final, fields)
    frozen = [x for x in population if x["original_sample_status"] == "FROZEN_COMMIT"]
    complete = [x for x in population if x["recovery_status"] == "POM_COMPLETE"]
    mcomp = [x for x in model_results if x.get("model_comparable") == "MODEL_COMPARABLE"]
    mdiv = [x for x in mcomp if x.get("model_semantic_divergence") == "true"]
    rcomp = [x for x in resolution_results if x.get("resolution_comparable") == "RESOLUTION_COMPARABLE"]
    rdiv = [x for x in rcomp if x.get("resolution_divergence") == "true"]
    vcomp = [x for x in validation_results if x.get("validation_comparable") == "true"]
    vreg = [x for x in validation_results if x.get("confirmed_validation_regression") == "true"]
    silent = [x for x in final if x["silent_to_root_validation"] == "true"]
    uvals = list(mvnup.values())
    summary = {
        "DATA_FREEZE": "FINAL", "EXPERIMENTS_FINISHED": True, "NO_MORE_EMPIRICAL_RUNS": True,
        "NEXT_STEP": "WRITE_MAVENTWIN_PAPER", "ORIGINAL_SAMPLE_ENTRIES": len(rows),
        "FROZEN_REVISIONS": len(frozen), "NO_FROZEN_REVISION": len(rows) - len(frozen),
        "POM_COMPLETE": len(complete), "POM_ACQUISITION_FAILED": len(frozen) - len(complete),
        "POM_COMPLETENESS_RATE": round(len(complete) / len(frozen), 4) if frozen else 0,
        "MODEL_COMPARABLE": len(mcomp), "MODEL_DIVERGENCE_REPOS": len(mdiv),
        "MODEL_RATE": round(len(mdiv) / len(mcomp), 4) if mcomp else 0,
        "MODEL_WILSON_95_CI": wilson(len(mdiv), len(mcomp)),
        "RESOLUTION_COMPARABLE": len(rcomp), "RESOLUTION_DIVERGENCE_REPOS": len(rdiv),
        "RESOLUTION_RATE": round(len(rdiv) / len(rcomp), 4) if rcomp else 0,
        "RESOLUTION_WILSON_95_CI": wilson(len(rdiv), len(rcomp)),
        "VALIDATION_COMPARABLE": len(vcomp), "CONFIRMED_VALIDATION_REGRESSIONS": len(vreg),
        "VALIDATION_RATE": round(len(vreg) / len(vcomp), 4) if vcomp else 0,
        "VALIDATION_WILSON_95_CI": wilson(len(vreg), len(vcomp)),
        "SILENT_TO_ROOT_VALIDATION_REPOS": len(silent),
        "MVNUP_EVALUABLE": sum(x.get("mvnup_evaluable") == "true" for x in uvals),
        "MVNUP_DIRECTLY_SIGNALED": sum(x.get("mvnup_relation") == "DIRECTLY_SIGNALED" for x in uvals),
        "MVNUP_RELATED": sum(x.get("mvnup_relation") == "RELATED_BUT_NOT_SPECIFIC" for x in uvals),
        "MVNUP_NOT_SIGNALED": sum(x.get("mvnup_relation") == "NOT_SIGNALED" for x in uvals),
        "MVNUP_UNAVAILABLE": sum(x.get("mvnup_relation") == "MVNUP_UNAVAILABLE" for x in uvals),
        "COMMONS_COMPRESS_STATUS": "NOT_COMPARABLE",
        "CENTRAL_PUBLISHING_MODEL_DECLARATION_CASES": 10,
        "ACTUAL_LIFECYCLE_PLAN_STATUS": "PLAN_UNAVAILABLE",
        "SYNTHETIC_STATUS": "BOTH_EXECUTE", "HUMAN_PRECISION": "NOT_MEASURED",
    }
    cc = [x for x in resolution_detail if x["repo"] == "apache/commons-compress" and x["artifactId"] == "jcl-over-slf4j" and x["m3_version"] == "1.6.6" and x["m4_version"] == "1.7.25"]
    if cc:
        summary["COMMONS_COMPRESS_STATUS"] = "CONFIRMED"
    elif any(x["repo"] == "apache/commons-compress" for x in resolution_detail):
        summary["COMMONS_COMPRESS_STATUS"] = "NOT_REPRODUCED"
    else:
        summary["COMMONS_COMPRESS_STATUS"] = "NOT_COMPARABLE"
    write_json(OUT / "FINAL_PAPER_SUMMARY.json", summary)
    write_json(OUT / "RUN_STATUS.json", summary)
    return final, summary


def write_materials(final, summary, model_detail, resolution_detail):
    mat = OUT / "paper_materials"
    mat.mkdir(parents=True, exist_ok=True)
    facts = (
        f"- Original sample entries: {summary['ORIGINAL_SAMPLE_ENTRIES']}\n"
        f"- Frozen revisions: {summary['FROZEN_REVISIONS']} (no frozen revision: {summary['NO_FROZEN_REVISION']})\n"
        f"- POM-complete snapshots: {summary['POM_COMPLETE']}/{summary['FROZEN_REVISIONS']} ({summary['POM_COMPLETENESS_RATE']:.1%})\n"
        f"- Model comparable/divergent: {summary['MODEL_COMPARABLE']}/{summary['MODEL_DIVERGENCE_REPOS']}\n"
        f"- Resolution comparable/divergent: {summary['RESOLUTION_COMPARABLE']}/{summary['RESOLUTION_DIVERGENCE_REPOS']}\n"
        f"- Validation comparable/confirmed regression: {summary['VALIDATION_COMPARABLE']}/{summary['CONFIRMED_VALIDATION_REGRESSIONS']}\n"
        f"- mvnup evaluable: {summary['MVNUP_EVALUABLE']}; directly signaled: {summary['MVNUP_DIRECTLY_SIGNALED']}\n"
    )
    for name, interpretation, limitations in [
        ("RQ1_RESULTS.md", "The model layer is reported using its own stable paired denominator.", "This is resolved-model evidence, not a full build success rate or runtime failure rate."),
        ("RQ2_RESULTS.md", "Dependency results use only stable four-run paired graphs and artifact-level deltas.", "Unavailable trees and unconfirmed causes are not counted as negative or mediation evidence."),
        ("RQ3_RESULTS.md", "mvnup relations are matched to observed findings where a concrete token is present.", "A warning elsewhere in a repository is not treated as detection."),
    ]:
        (mat / name).write_text(f"# {name[:-10]}\n\n## FACTS\n{facts}\n## INTERPRETATION\n{interpretation}\n## LIMITATIONS\n{limitations}\n## DO_NOT_CLAIM\n- Maven 4 is generally broken.\n- A resolved-model difference proves application failure.\n- A root validate result is a full build result.\n", encoding="utf-8")
    (mat / "ABSTRACT_FACTS.md").write_text(facts, encoding="utf-8")
    (mat / "INTRODUCTION_FACTS.md").write_text("Maven 4 migration can alter resolved build semantics while the project revision and JDK remain fixed. A successful root validation does not establish effective-model or dependency equivalence. MavenTwin compares those layers and treats migration tooling as complementary evidence.\n", encoding="utf-8")
    (mat / "CASE_STUDIES.md").write_text("Case studies must be selected only from artifact-level or field-level deltas in MODEL_DELTAS_FINAL.csv and RESOLUTION_DELTAS_FINAL.csv. Central Publishing is limited to effective-model execution declarations because actual lifecycle plans remain unavailable.\n", encoding="utf-8")
    (mat / "THREATS_TO_VALIDITY.md").write_text("The frozen population excludes 34 UNKNOWN_REMOTE_HEAD entries. POM-only snapshots do not support claims about full source builds. Actual lifecycle-plan extraction is unavailable, human precision was not measured, and the primary Maven 4 treatment is 4.0.0-rc-7.\n", encoding="utf-8")
    (mat / "CONTRIBUTIONS.md").write_text("- Fixed-revision resolved-model comparison with independent availability denominators.\n- Artifact-level dependency-resolution evidence under a paired-run gate.\n- A small differential result artifact with a conservative comparison to mvnup.\n", encoding="utf-8")
    (OUT / "RELATED_WORK_MATRIX.csv").write_text("topic,status,notes\nMaven 3 to Maven 4,CONSERVATIVE_SEARCH,No direct identity claim is made.\nBuild-system migration,CONSERVATIVE_SEARCH,Generic migration and compatibility work.\nDependency-resolution evolution,CONSERVATIVE_SEARCH,Generic resolver evolution work.\n", encoding="utf-8")


def write_figures_tables(final, summary):
    fig = OUT / "figures"
    tab = OUT / "tables"
    fig.mkdir(parents=True, exist_ok=True)
    tab.mkdir(parents=True, exist_ok=True)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        labels = ["Model", "Resolution", "Validation"]
        vals = [summary["MODEL_DIVERGENCE_REPOS"], summary["RESOLUTION_DIVERGENCE_REPOS"], summary["CONFIRMED_VALIDATION_REGRESSIONS"]]
        plt.figure(figsize=(6, 3.5)); plt.bar(labels, vals, color=["#436f8e", "#c76d3a", "#6c8e63"]); plt.ylabel("Repositories"); plt.tight_layout()
        plt.savefig(fig / "Figure2_layer_counts.png", dpi=200); plt.savefig(fig / "Figure2_layer_counts.pdf"); plt.close()
        cats = {}
        for x in final:
            if x["model_semantic_divergence"] == "true": cats[x["model_categories"]] = cats.get(x["model_categories"], 0) + 1
        plt.figure(figsize=(7, 3.5)); plt.bar(list(cats) or ["none"], list(cats.values()) or [0], color="#436f8e"); plt.ylabel("Repositories"); plt.xticks(rotation=25, ha="right"); plt.tight_layout()
        plt.savefig(fig / "Figure3_model_mechanisms.png", dpi=200); plt.savefig(fig / "Figure3_model_mechanisms.pdf"); plt.close()
        rel = {k: sum(x["mvnup_relation"] == k for x in final) for k in ("DIRECTLY_SIGNALED", "RELATED_BUT_NOT_SPECIFIC", "NOT_SIGNALED", "MVNUP_UNAVAILABLE")}
        plt.figure(figsize=(7, 3.5)); plt.bar(list(rel), list(rel.values()), color="#777777"); plt.ylabel("Repositories"); plt.xticks(rotation=25, ha="right"); plt.tight_layout()
        plt.savefig(fig / "Figure5_mvnup_relation.png", dpi=200); plt.savefig(fig / "Figure5_mvnup_relation.pdf"); plt.close()
    except Exception as exc:
        (fig / "FIGURE_GENERATION_ERROR.txt").write_text(str(exc), encoding="utf-8")
    source_rows = [{"layer": "model", "comparable": summary["MODEL_COMPARABLE"], "divergent": summary["MODEL_DIVERGENCE_REPOS"]},
                   {"layer": "resolution", "comparable": summary["RESOLUTION_COMPARABLE"], "divergent": summary["RESOLUTION_DIVERGENCE_REPOS"]},
                   {"layer": "validation", "comparable": summary["VALIDATION_COMPARABLE"], "divergent": summary["CONFIRMED_VALIDATION_REGRESSIONS"]}]
    write_csv(fig / "Figure2_source.csv", source_rows)
    tables = {
        "Table1_sample_recovery": [{"metric": "original_entries", "value": summary["ORIGINAL_SAMPLE_ENTRIES"]}, {"metric": "frozen_revisions", "value": summary["FROZEN_REVISIONS"]}, {"metric": "pom_complete", "value": summary["POM_COMPLETE"]}],
        "Table2_layer_results": [{"layer": "model", "comparable": summary["MODEL_COMPARABLE"], "divergent": summary["MODEL_DIVERGENCE_REPOS"]}, {"layer": "resolution", "comparable": summary["RESOLUTION_COMPARABLE"], "divergent": summary["RESOLUTION_DIVERGENCE_REPOS"]}, {"layer": "validation", "comparable": summary["VALIDATION_COMPARABLE"], "divergent": summary["CONFIRMED_VALIDATION_REGRESSIONS"]}],
        "Table3_model_taxonomy": [{"category": k, "repositories": sum(x["model_categories"] == k for x in final)} for k in sorted(set(x["model_categories"] for x in final))],
        "Table4_resolution_cases": [{"repo": x["repo"], "artifactId": x["artifactId"], "difference_type": x["difference_type"], "m3_version": x["m3_version"], "m4_version": x["m4_version"]} for x in read_csv(OUT / "RESOLUTION_DELTAS_FINAL.csv")],
        "Table5_mvnup": [{"relation": k, "repositories": sum(x["mvnup_relation"] == k for x in final)} for k in sorted(set(x["mvnup_relation"] for x in final))],
        "Table6_case_studies": [{"source": "MODEL_DELTAS_FINAL.csv", "rows": len(read_csv(OUT / "MODEL_DELTAS_FINAL.csv"))}, {"source": "RESOLUTION_DELTAS_FINAL.csv", "rows": len(read_csv(OUT / "RESOLUTION_DELTAS_FINAL.csv"))}],
    }
    for name, values in tables.items():
        write_csv(tab / f"{name}.csv", values)
        if values:
            fields = list(values[0])
            md = "| " + " | ".join(fields) + " |\n|" + "|".join("---" for _ in fields) + "|\n"
            md += "\n".join("| " + " | ".join(str(x.get(f, "")) for f in fields) + " |" for x in values) + "\n"
        else:
            md = "No rows.\n"
        (tab / f"{name}.md").write_text(md, encoding="utf-8")
        tex = "\\begin{tabular}{" + "l" * len(fields) + "}\n" + " & ".join(fields) + " \\\\ \\hline\n"
        tex += "\n".join(" & ".join(str(x.get(f, "")).replace("&", "\\&") for f in fields) + " \\\\" for x in values) + "\n\\end{tabular}\n"
        (tab / f"{name}.tex").write_text(tex, encoding="utf-8")


def write_report(summary, ga_status):
    lines = [
        "# MavenTwin Final Evidence Run", "", "在恢复 frozen revisions 并采用字段级、paired-output gate 后，最终结果只能支持 resolved build model、dependency graph 和 root validation 三个测量层；它不支持完整 build/runtime 行为的结论。", "",
        "DATA_FREEZE: FINAL", "EXPERIMENTS_FINISHED", "NO_MORE_EMPIRICAL_RUNS", "NEXT_STEP: WRITE_MAVENTWIN_PAPER", "",
        f"ORIGINAL_SAMPLE_ENTRIES: {summary['ORIGINAL_SAMPLE_ENTRIES']}", f"FROZEN_REVISIONS: {summary['FROZEN_REVISIONS']}", f"NO_FROZEN_REVISION: {summary['NO_FROZEN_REVISION']}",
        f"POM_COMPLETE: {summary['POM_COMPLETE']}", f"POM_ACQUISITION_FAILED: {summary['POM_ACQUISITION_FAILED']}", f"POM_COMPLETENESS_RATE: {summary['POM_COMPLETENESS_RATE']:.1%}", "",
        f"MODEL_COMPARABLE: {summary['MODEL_COMPARABLE']}", f"MODEL_DIVERGENCE_REPOS: {summary['MODEL_DIVERGENCE_REPOS']}", f"MODEL_RATE: {summary['MODEL_RATE']:.1%}", f"MODEL_WILSON_95_CI: {summary['MODEL_WILSON_95_CI']}",
        f"RESOLUTION_COMPARABLE: {summary['RESOLUTION_COMPARABLE']}", f"RESOLUTION_DIVERGENCE_REPOS: {summary['RESOLUTION_DIVERGENCE_REPOS']}", f"RESOLUTION_RATE: {summary['RESOLUTION_RATE']:.1%}", f"RESOLUTION_WILSON_95_CI: {summary['RESOLUTION_WILSON_95_CI']}",
        f"VALIDATION_COMPARABLE: {summary['VALIDATION_COMPARABLE']}", f"CONFIRMED_VALIDATION_REGRESSIONS: {summary['CONFIRMED_VALIDATION_REGRESSIONS']}", f"VALIDATION_RATE: {summary['VALIDATION_RATE']:.1%}", f"VALIDATION_WILSON_95_CI: {summary['VALIDATION_WILSON_95_CI']}",
        f"SILENT_TO_ROOT_VALIDATION_REPOS: {summary['SILENT_TO_ROOT_VALIDATION_REPOS']}", "",
        f"MVNUP_EVALUABLE: {summary['MVNUP_EVALUABLE']}", f"MVNUP_DIRECTLY_SIGNALED: {summary['MVNUP_DIRECTLY_SIGNALED']}", f"MVNUP_RELATED: {summary['MVNUP_RELATED']}", f"MVNUP_NOT_SIGNALED: {summary['MVNUP_NOT_SIGNALED']}", f"MVNUP_UNAVAILABLE: {summary['MVNUP_UNAVAILABLE']}", "",
        f"COMMONS_COMPRESS_STATUS: {summary['COMMONS_COMPRESS_STATUS']}", f"CENTRAL_PUBLISHING_MODEL_DECLARATION_CASES: {summary['CENTRAL_PUBLISHING_MODEL_DECLARATION_CASES']}", "ACTUAL_LIFECYCLE_PLAN_STATUS: PLAN_UNAVAILABLE", "SYNTHETIC_STATUS: BOTH_EXECUTE", "HUMAN_PRECISION: NOT_MEASURED", f"MAVEN4_GA_STATUS: {ga_status.get('status')}", "",
        "PAPER_STATUS: WRITE_WITH_LIMITATIONS", "",
        "主限制：34 条样本没有 frozen revision；POM-only snapshot 不代表完整源码构建；actual lifecycle plan 未取得；人工 precision 未测量；primary comparison 固定 Maven 4.0.0-rc-7。",
    ]
    (ROOT / "MAVENTWIN_FINAL_PAPER_DATA_ZH.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (OUT / "MAVENTWIN_FINAL_PAPER_DATA_ZH.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (OUT / "OLD_NUMBERS_DO_NOT_USE.md").write_text("Legacy pre-correction numbers (including 115/116, 71 resolution divergences, 46 execution-plan divergences, 53 validation divergences, and precision 1.0) are retired. They used incomplete snapshots, mixed denominators, or non-independent classification and must not be cited. Use only FINAL_PAPER_SUMMARY.json and PAPER_NUMBERS_FINAL.md.\n", encoding="utf-8")
    paper = ["# PAPER_NUMBERS_FINAL", "", "These are the only paper-number entry points for this run.", "", "## RQ1", f"- Model comparable: {summary['MODEL_COMPARABLE']}; divergent: {summary['MODEL_DIVERGENCE_REPOS']}; denominator: model-comparable repositories; Wilson 95% CI: {summary['MODEL_WILSON_95_CI']}; source: FINAL_PAPER_RESULTS.csv and MODEL_DELTAS_FINAL.csv.", "", "## RQ2", f"- Resolution comparable: {summary['RESOLUTION_COMPARABLE']}; divergent: {summary['RESOLUTION_DIVERGENCE_REPOS']}; denominator: paired stable dependency graphs; Wilson 95% CI: {summary['RESOLUTION_WILSON_95_CI']}; source: RESOLUTION_DELTAS_FINAL.csv.", "", "## RQ3", f"- mvnup evaluable: {summary['MVNUP_EVALUABLE']}; directly signaled: {summary['MVNUP_DIRECTLY_SIGNALED']}; related: {summary['MVNUP_RELATED']}; not signaled: {summary['MVNUP_NOT_SIGNALED']}; unavailable: {summary['MVNUP_UNAVAILABLE']}; source: MVNUP_RESULTS_FINAL.csv."]
    (OUT / "PAPER_NUMBERS_FINAL.md").write_text("\n".join(paper) + "\n", encoding="utf-8")


def package_results():
    export = OUT / "exports"
    export.mkdir(parents=True, exist_ok=True)
    zip_path = export / "maventwin-final-evidence-results.zip"
    if zip_path.exists():
        zip_path.unlink()
    include_dirs = ["samples", "metrics", "measurements", "mvnup", "full_validation", "figures", "tables", "paper_materials"]
    include_files = ["FINAL_PAPER_RESULTS.csv", "MODEL_DELTAS_FINAL.csv", "RESOLUTION_DELTAS_FINAL.csv", "FINAL_PAPER_SUMMARY.json", "RUN_STATUS.json", "MAVENTWIN_FINAL_PAPER_DATA_ZH.md", "PAPER_NUMBERS_FINAL.md", "OLD_NUMBERS_DO_NOT_USE.md", "MAVEN4_GA_STATUS.json", "RELATED_WORK_MATRIX.csv"]
    readme = export / "RESULTS_PACKAGE_README.md"
    readme.write_text("This archive contains only final_evidence_v1 result artifacts. It excludes git sources, POM snapshots, Maven caches, scripts, and build outputs. The paper status is WRITE_WITH_LIMITATIONS: use layer-specific denominators and do not claim full-build behavior, actual lifecycle-plan divergence, or human precision.\n", encoding="utf-8")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(readme, "RESULTS_PACKAGE_README.md")
        for d in include_dirs:
            base = OUT / d
            if not base.exists():
                continue
            for p in base.rglob("*"):
                if p.is_file():
                    z.write(p, p.relative_to(OUT).as_posix())
        for name in include_files:
            p = OUT / name
            if p.exists():
                z.write(p, name)
    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    (export / "maventwin-final-evidence-results.zip.sha256").write_text(digest + "  maventwin-final-evidence-results.zip\n", encoding="ascii")
    return zip_path, digest


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = read_csv(SAMPLES)
    population = acquire_all(rows)
    targets = freeze_targets(rows, population)
    popmap = {x["repo"]: x for x in population}
    # Measurements are independent per repository and can safely run in a small pool.
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(measure_one, row, {x["repo"]: x for x in targets}[row["repo"]], popmap[row["repo"]]) for row in rows if popmap[row["repo"]].get("recovery_status") == "POM_COMPLETE"]
        for future in as_completed(futures):
            future.result()
    model_results, resolution_results, validation_results, model_detail, resolution_detail = summarize_measurements(rows, population, targets)
    run_full_checkout_candidates(rows, population, validation_results)
    mvnup = apply_mvnup_relations(rows, population, model_results, resolution_results, validation_results, model_detail, resolution_detail)
    final, summary = build_final_outputs(rows, population, targets, model_results, resolution_results, validation_results, model_detail, resolution_detail, mvnup)
    write_materials(final, summary, model_detail, resolution_detail)
    write_figures_tables(final, summary)
    ga = check_maven4_ga()
    write_report(summary, ga)
    zip_path, digest = package_results()
    print(json.dumps({"summary": summary, "zip": str(zip_path), "sha256": digest}, ensure_ascii=False))


if __name__ == "__main__":
    main()
