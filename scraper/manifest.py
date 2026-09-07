"""The state of a ranking day, as the archive will read it."""

import json
import os
from datetime import datetime, timezone

from floor import FLOOR
from slices import RANKS_PER_PAGE, slices

FORMAT_VERSION = 1


def _path(day):
    return os.path.join("manifests", f"{day}.json")


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

    `depths` is used only when the ranking day has none recorded yet. **The
    depth of a ranking day is discovered once and then fixed.** Two searches
    could disagree by a page - an API hiccup, a retry, an off-by-one at a
    boundary - and if the partition moved between the first run and a repair,
    a page could fall between the old slices and the new ones and be fetched
    by neither. A recorded depth cannot move. The ranking does not change
    inside a ranking day, so the boundary found at 18:05 is the boundary at
    03:00 and there is nothing to gain by looking again.

    This is the manifest as a work plan, which the archive's third link
    permits: it decides how far to look, never whether the day is whole.
    """
    recorded = depths_of(previous) or dict(depths or {})
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
