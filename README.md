# rankings

Daily world ranking snapshots for MapleStory GMS NA and EU, scraped from
Nexon's public, no-auth ranking API and published as one GitHub release per
ranking day. This repository only collects and publishes; it does nothing
with the data beyond that.

## What a release contains

A release is tagged with the ranking day it covers, as an ISO date (for
example `2026-09-07`), and carries two kinds of asset:

- one gzipped NDJSON file per slice of a world's ranking, named
  `<region>-<world_id>-<from>-<to>.ndjson.gz`, where `from` and `to` are the
  range of rank offsets that file covers;
- one `manifest.json`, listing every slice the day was partitioned into: the
  offsets it covers, how many pages it was expected to hold, how many pages
  actually landed, and whether it is `missing`, `partial`, or `complete`.

That is everything a reader needs without asking anyone: the tag is the
ranking day, the assets are the data, and the manifest says which offsets
each asset covers and whether the day is trustworthy.

### One line of an asset

Each line of an `.ndjson.gz` file is `{"o":<offset>,"r":<body>}`, where `o`
is the `page_index` offset the line was fetched at and `r` is Nexon's
response body for that page, spliced in **verbatim** - never parsed, never
even decoded.

That matters because of `exp`. The largest values seen so far are around
`795025135043493` - about a factor of eleven below 2^53, so `JSON.parse`
still returns them exactly, and this format is not fixing a corruption that
is already happening. It is removing the need to know when it starts. A
character at the level cap accumulates `exp` without the reset every other
level-up brings, so the number only climbs, and past 2^53 `JSON.parse` rounds
it silently while the rounded value still looks entirely plausible - nothing
in the output says a digit changed.

So: **quote `exp` before any JavaScript parses a line**, or extract it as a
string ahead of parsing the rest. A parser that has already run is a parser
that has already lost the precision this format exists to keep, and it will
not tell you which day that started.

## Retention

Ranking assets (`*.ndjson.gz`) are removed from releases older than thirty
days. Manifests are kept forever: `manifest.json` is the record of what each
ranking day was actually partitioned against, and it stays useful long after
the raw pages it describes are gone.

## Pace

Every address this service scrapes from makes one request every 0.3 seconds,
strictly serial, and is retired after at most 500 of them. That is about
two-thirds of the roughly 800 requests per five-minute window the evidence
says one address can make before Nexon starts answering 403.

**Do not raise it.** The margin exists because nobody has measured exactly
where the ceiling is, only that 500 at this pace stays under it; closing
that margin to save a few minutes is how a run finds out where the ceiling
actually sits, mid-day, with no way to retry an address until it clears.

The work is split across many short-lived runners so that no single address
makes more than 500 requests in a run. That is the whole reason for the
fan-out - it is not a way around a rate limit, and describing it as one
would suggest a limit is being evaded rather than respected.

## How deep a day reaches

The service keeps every character at level 275 or above, in each of the six
worlds it tracks - four in GMS NA, two in GMS EU - not a fixed number of
pages. How deep that reaches changes as the population levels up, so the
first run of each ranking day binary-searches the boundary per world and
then holds it fixed for the rest of that day: a second search landing on a
different page would move the partition underneath a repair, and a page
could fall between the old slices and the new ones and be fetched by
neither.

A day is currently about 45 slices covering roughly 22,300 pages - Kronos
alone accounts for about 15,400 of them. The manifest records both the depth
found for each world (`depths`) and the level the whole run was published
against (`floor`), so a reader can tell what a release was scraped to
without recomputing it.

## When it runs

Once a day, at 18:00 UTC, on a schedule - not hourly. A run has two waves:
the first scrapes every slice the day's manifest says is missing, and a
second re-fetches whatever the first wave did not complete.

The retry lives inside the run rather than as a separate, later firing
because a workflow triggered by a schedule cannot dispatch itself using the
token GitHub gives it automatically (`GITHUB_TOKEN`); doing it any other way
would mean holding a personal access token as an organisation secret, and
needing no credential anywhere in this repository is one of the properties
this design was chosen for.

## The archive

The consumer of these releases is [maplearchive.org](https://maplearchive.org).
