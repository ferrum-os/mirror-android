import subprocess, xml.etree.ElementTree as ET, os, shutil

ORG = os.environ["TARGET_ORG"]
VISIBILITY = os.environ.get("VISIBILITY", "public")
TAG_NAME = os.environ.get("SNAPSHOT_TAG", os.environ.get("MANIFEST_BRANCH", "android-2.2_r1.1"))
WORKDIR = "aosp-source"

manifest_path = os.path.join(WORKDIR, ".repo", "manifest.xml")
projects = ET.parse(manifest_path).getroot().findall("project")

manifest_entries = []  # (repo_name, path, [preserved child elements])

for p in projects:
    path = p.get("path") or p.get("name")
    name = p.get("name")
    repo_name = name.replace("/", "_")
    full = f"{ORG}/{repo_name}"
    print(f"== {path} -> {full}", flush=True)

    # sync just this one project, current branch only, no tag refs (saves disk)
    subprocess.run(
        ["repo", "sync", "-j4", "-c", "--no-tags", "--force-sync", path],
        cwd=WORKDIR, check=True,
    )

    # create the destination repo (no-op if it already exists)
    subprocess.run(["gh", "repo", "create", full, f"--{VISIBILITY}", "-y"], check=False)

    proj_dir = os.path.join(WORKDIR, path)
    remote_url = f"https://github.com/{full}.git"

    subprocess.run(["git", "-C", proj_dir, "remote", "remove", "github"], check=False)
    subprocess.run(["git", "-C", proj_dir, "remote", "add", "github", remote_url], check=True)

    # push the pinned commit as master
    subprocess.run(["git", "-C", proj_dir, "push", "github", "HEAD:refs/heads/master"], check=True)

    # tag HEAD (the exact revision this project was pinned to) and push it — idempotent via -f
    subprocess.run(["git", "-C", proj_dir, "tag", "-f", TAG_NAME], check=True)
    subprocess.run(["git", "-C", proj_dir, "push", "github", f"refs/tags/{TAG_NAME}", "-f"], check=True)

    children = [(c.tag, dict(c.attrib)) for c in p if c.tag in ("copyfile", "linkfile")]
    manifest_entries.append((repo_name, path, children))

    # reclaim disk before the next project
    shutil.rmtree(proj_dir, ignore_errors=True)

# --- generate default.xml for the mirrored manifest repo ---
root = ET.Element("manifest")
ET.SubElement(root, "remote", {"name": "github", "fetch": f"https://github.com/{ORG}/"})
ET.SubElement(root, "default", {"remote": "github", "revision": f"refs/tags/{TAG_NAME}", "sync-j": "4"})

for repo_name, path, children in manifest_entries:
    proj_el = ET.SubElement(root, "project", {"name": repo_name, "path": path})
    for tag, attrib in children:
        ET.SubElement(proj_el, tag, attrib)

ET.ElementTree(root).write("default.xml", encoding="utf-8", xml_declaration=True)
print(f"Wrote default.xml with {len(manifest_entries)} projects, tag={TAG_NAME}")