"""Build the manifest for a ranking day from the files that actually arrived."""

import argparse
import json
import sys

# count_pages lives in manifest.py now - plan.py needs it too, for the repair
# wave's --out-dir, and duplicating it would let the two copies drift. The
# import keeps `publish.count_pages` resolving to the same function, so
# anything that patches or reads it under that name still works.
from manifest import count_pages, merge_manifest, read_manifest, write_manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--day", required=True)
    parser.add_argument("--depths", default="{}")
    args = parser.parse_args()

    manifest = merge_manifest(
        args.day, read_manifest(args.day), count_pages(), json.loads(args.depths)
    )

    if not manifest["slices"]:
        # No world has ever had its floor recorded for this day - not "every
        # world happens to be empty", which the real six never are. Writing
        # this would hand parseManifest a manifest it accepts happily, and
        # the archive would import nothing and report every world
        # incomplete, with nothing anywhere naming the cause.
        print(
            f"{args.day}: refusing to publish a manifest with no slices - "
            "no world's depth was ever recorded. Pass --depths from the "
            "plan step.",
            file=sys.stderr,
        )
        return 1

    write_manifest(manifest)

    complete = len(
        [one for one in manifest["slices"] if one["status"] == "complete"]
    )
    print(f"{args.day}: {complete} of {len(manifest['slices'])} slices complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
