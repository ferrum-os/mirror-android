import os
import subprocess
import sys
import xml.etree.ElementTree as ET

ORG = os.environ["TARGET_ORG"]
VISIBILITY = os.environ.get("VISIBILITY", "public")
TAG_NAME = os.environ.get("SNAPSHOT_TAG", os.environ.get("MANIFEST_BRANCH", "android-2.2_r1.1"))

BASE_DIR = os.path.abspath(os.getcwd())
WORKDIR = os.path.join(BASE_DIR, "aosp-source")

# Use the resolved manifest produced by `repo manifest -r`
manifest_path = os.path.join(WORKDIR, "flattened_manifest.xml")

# Fallback to manifests/default.xml if flattened_manifest.xml isn't generated
if not os.path.exists(manifest_path):
    manifest_path = os.path.join(WORKDIR, ".repo", "manifests", "default.xml")

if not os.path.exists(manifest_path):
    sys.exit(f"ERROR: Cannot locate manifest file at {manifest_path}")

print(f"Reading manifest from: {manifest_path}")

tree = ET.parse(manifest_path)
root = tree.getroot()
projects = root.findall("project")

manifest_entries = []

for p in projects:
    name = p.get("name")
    path = p.get("path", name)  # Default path to name if path attribute is absent
    repo_name = name.replace("/", "_")
    full_target = f"{ORG}/{repo_name}"
    proj_dir = os.path.abspath(os.path.join(WORKDIR, path))

    print(f"\n[+] Processing: {name} ({path}) -> {full_target}", flush=True)

    if not os.path.exists(proj_dir):
        print(f"    [!] Directory missing on disk: {proj_dir}. Skipping...", flush=True)
        continue

    # Create GitHub repository under the target organization
    subprocess.run(["gh", "repo", "create", full_target, f"--{VISIBILITY}"], check=False)

    remote_url = f"https://github.com/{full_target}.git"

    try:
        subprocess.run(["git", "-C", proj_dir, "remote", "remove", "github"], capture_output=True, check=False)
        subprocess.run(["git", "-C", proj_dir, "remote", "add", "github", remote_url], check=True)
        
        # Push master branch
        subprocess.run(["git", "-C", proj_dir, "push", "github", "HEAD:refs/heads/master", "--force"], check=True)
        
        # Tag and push tag
        subprocess.run(["git", "-C", proj_dir, "tag", "-f", TAG_NAME], check=True)
        subprocess.run(["git", "-C", proj_dir, "push", "github", f"refs/tags/{TAG_NAME}", "--force"], check=True)

        children = [(c.tag, dict(c.attrib)) for c in p if c.tag in ("copyfile", "linkfile")]
        manifest_entries.append((repo_name, path, children))
    except subprocess.CalledProcessError as e:
        print(f"    [!] Error processing {path}: {e}", file=sys.stderr)

# Construct final default.xml for your destination manifest repository
root_out = ET.Element("manifest")
ET.SubElement(root_out, "remote", {"name": "github", "fetch": f"https://github.com/{ORG}/"})
ET.SubElement(root_out, "default", {"remote": "github", "revision": f"refs/tags/{TAG_NAME}", "sync-j": "4"})

for repo_name, path, children in manifest_entries:
    proj_el = ET.SubElement(root_out, "project", {"name": repo_name, "path": path})
    for tag, attrib in children:
        ET.SubElement(proj_el, tag, attrib)

out_xml = os.path.join(BASE_DIR, "default.xml")
ET.ElementTree(root_out).write(out_xml, encoding="utf-8", xml_declaration=True)
print(f"\nSuccessfully wrote {out_xml} with {len(manifest_entries)} projects.")
