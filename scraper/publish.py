"""Build the manifest for a ranking day from the files that actually arrived."""

import argparse
import gzip
import json
import os

from manifest import merge_manifest, read_manifest, write_manifest

parser = argparse.ArgumentParser()
parser.add_argument("--day", required=True)
parser.add_argument("--depths", default="{}")
args = parser.parse_args()

# Pages actually in each file, counted from the file rather than claimed.
counted = {}
if os.path.isdir("out"):
    for name in sorted(os.listdir("out")):
        if not name.endswith(".ndjson.gz"):
            continue
        with gzip.open(os.path.join("out", name), "rb") as handle:
            body = handle.read()
        counted[name] = len([line for line in body.split(b"\n") if line.strip()])

manifest = merge_manifest(
    args.day, read_manifest(args.day), counted, json.loads(args.depths)
)
write_manifest(manifest)

complete = len([one for one in manifest["slices"] if one["status"] == "complete"])
print(f"{args.day}: {complete} of {len(manifest['slices'])} slices complete.")
