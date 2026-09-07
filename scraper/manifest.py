"""The state of a ranking day, as the archive will read it."""

import gzip
import json
import os
from datetime import datetime, timezone

from floor import FLOOR
from slices import RANKS_PER_PAGE, slices

FORMAT_VERSION = 1


def _path(day):
    return os.path.join("manifests", f"{day}.json")


def count_pages(out_dir="out"):
    """Pages actually in each file under `out_dir`, counted from the file
    rather than claimed."""
    counted = {}
    if os.path.isdir(out_dir):
        for name in sorted(os.listdir(out_dir)):
            if not name.endswith(".ndjson.gz"):
                continue
            with gzip.open(os.path.join(out_dir, name), "rb") as handle:
                body = handle.read()
            counted[name] = len([line for line in body.split(b"\n") if line.strip()])
    return counted


def read_manifest(day):
    """The manifest committed for a ranking day, or None when the day is new."""
    if not os.path.exists(_path(day)):
        return None
    with open(_path(day), encoding="utf-8") as handle:
        return json.load(handle)


def write_manifest(manifest):
    os.makedirs("manifests", exist_ok=True)
    with open(_path(manifest["ranking_day"]), "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)
        handle.write("\n")


def depths_of(manifest):
    """The depths this ranking day was partitioned against, or {}."""
    return (manifest or {}).get("depths") or {}


def merge_manifest(day, previous, counted, depths=None):
    """
    The state of a ranking day, from what is actually on disk.

    ``counted`` maps an asset name to the number of pages the file really
    holds - counted by decompressing it, not taken from what the scraping job
    said it wrote. A job that dies mid-write would otherwise report a number
    its own file does not back up. The archive does not trust this manifest
    either; it counts rows in its own database. But there is no reason for it
    to be wrong here.

    `depths` is used only for a world the ranking day has no recorded depth
    for yet. **A depth, once recorded, is discovered once and then fixed.**
    Two searches could disagree by a page - an API hiccup, a retry, an
    off-by-one at a boundary - and if the partition moved between the first
    run and a repair, a page could fall between the old slices and the new
    ones and be fetched by neither. A recorded depth cannot move. The ranking
    does not change inside a ranking day, so the boundary found at 18:05 is
    the boundary at 03:00 and there is nothing to gain by looking again.

    The merge is per world, not all-or-nothing: a world the day has no depth
    for yet must stay free to gain one from a later firing - the same day's
    repair wave, or the next day this world's search fails again - even
    though every other world's depth is already fixed. Treating the whole
    map as a single fixed-or-not unit would freeze that one missing world out
    for the rest of the day the moment any other world's depth was recorded.

    This is the manifest as a work plan, which the archive's third link
    permits: it decides how far to look, never whether the day is whole.
    """
    recorded = dict(depths_of(previous))
    for key, value in (depths or {}).items():
        recorded.setdefault(key, value)
    before = {one["asset"]: one for one in (previous or {}).get("slices", [])}

    out = []
    for one in slices(recorded):
        if one["asset"] in counted:
            present = counted[one["asset"]]
        else:
            present = before.get(one["asset"], {}).get("pages_present", 0)

        if present == 0:
            status = "missing"
        elif present == one["pages_expected"]:
            status = "complete"
        else:
            status = "partial"

        out.append({**one, "pages_present": present, "status": status})

    return {
        "format_version": FORMAT_VERSION,
        "ranking_day": day,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ranks_per_page": RANKS_PER_PAGE,
        "floor": FLOOR,
        "depths": recorded,
        "slices": out,
    }


def incomplete_slices(manifest):
    """The slices a run still has to fetch. A blocked slice is not done."""
    return [one for one in manifest["slices"] if one["status"] != "complete"]
