import subprocess, xml.etree.ElementTree as ET, os, sys

ORG = os.environ["TARGET_ORG"]
VISIBILITY = os.environ.get("VISIBILITY", "public")
TAG_NAME = os.environ.get("SNAPSHOT_TAG", os.environ.get("MANIFEST_BRANCH", "android-2.2_r1.1"))
WORKDIR = os.path.abspath("aosp-source")

# Handle repo manifest location (manifest.xml or manifests/default.xml)
manifest_path = os.path.join(WORKDIR, ".repo", "manifest.xml")
if not os.path.exists(manifest_path):
    manifest_path = os.path.join(WORKDIR, ".repo", "manifests", "default.xml")

if not os.path.exists(manifest_path):
    sys.exit(f"Error: Manifest file not found at {manifest_path}")

projects = ET.parse(manifest_path).getroot().findall("project")
manifest_entries = []

for p in projects:
    name = p.get("name")
    path = p.get("path", name)  # 'path' attribute defines the local directory relative to WORKDIR
    repo_name = name.replace("/", "_")
    full = f"{ORG}/{repo_name}"
    proj_dir = os.path.join(WORKDIR, path)

    print(f"== Processing: {path} -> {full}", flush=True)

    if not os.path.exists(proj_dir):
        print(f"Skipping {path}: Directory does not exist on disk.", flush=True)
        continue

    # Ensure repository exists on GitHub
    subprocess.run(["gh", "repo", "create", full, f"--{VISIBILITY}"], check=False)

    remote_url = f"https://github.com/{full}.git"
    
    # Git ops inside checked-out project directory
    subprocess.run(["git", "-C", proj_dir, "remote", "remove", "github"], stderr=subprocess.DEVNULL, check=False)
    subprocess.run(["git", "-C", proj_dir, "remote", "add", "github", remote_url], check=True)
    subprocess.run(["git", "-C", proj_dir, "push", "github", "HEAD:refs/heads/master", "--force"], check=True)

    subprocess.run(["git", "-C", proj_dir, "tag", "-f", TAG_NAME], check=True)
    subprocess.run(["git", "-C", proj_dir, "push", "github", f"refs/tags/{TAG_NAME}", "-f"], check=True)

    children = [(c.tag, dict(c.attrib)) for c in p if c.tag in ("copyfile", "linkfile")]
    manifest_entries.append((repo_name, path, children))

# Construct updated default.xml
root = ET.Element("manifest")
ET.SubElement(root, "remote", {"name": "github", "fetch": f"https://github.com/{ORG}/"})
ET.SubElement(root, "default", {"remote": "github", "revision": f"refs/tags/{TAG_NAME}", "sync-j": "4"})

for repo_name, path, children in manifest_entries:
    proj_el = ET.SubElement(root, "project", {"name": repo_name, "path": path})
    for tag, attrib in children:
        ET.SubElement(proj_el, tag, attrib)

output_xml_path = os.path.abspath("default.xml")
ET.ElementTree(root).write(output_xml_path, encoding="utf-8", xml_declaration=True)
print(f"Wrote {output_xml_path} with {len(manifest_entries)} projects.")
