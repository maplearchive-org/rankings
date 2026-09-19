"""One line of a slice asset."""

import re

_NEWLINE = re.compile(rb"[\n\r]")

# What the API started sending on 2026-09-18: one \n after the closing brace.
# Nothing else about the response changed - the JSON in front of it is as
# compact as it ever was, and every rank is still there.
_TRAILING_NEWLINE = re.compile(rb"[\n\r]+\Z")


def slice_line(offset, body):
    """
    Build ``{"o":<offset>,"r":<the API's body, verbatim>}`` as bytes.

    The body is spliced in as bytes and is never parsed, and never even
    decoded. exp values reach magnitudes like 795025135043493. That is still a
    factor of about eleven below 2^53, so JSON.parse returns it exactly today -
    this format is not fixing a corruption that is already happening. It is
    making sure nobody has to know the date it starts. A character at the level
    cap keeps accumulating exp without the reset every other level-up brings,
    so the number only climbs, and on the day it crosses, JSON.parse rounds
    silently while the rounded value still looks entirely plausible - every
    (level, exp) comparison the archive's ban detection rests on would be
    quietly wrong from then on, with nothing in the output saying so.

    Python's own integers would not round, which is not the point: the point is
    that bytes never decoded and never re-encoded are provably the bytes the
    API sent, so nothing this worker does can be the reason a digit changed.

    A newline *after* the body is dropped rather than refused. This guard was
    written against a pretty-printed body, where newlines sit between the
    fields and there is no way to tell a whole page from a truncated one. A
    newline the line format is about to add itself is not that: it carries no
    content, and what precedes it is the same compact page as always. Trimming
    the tail is a byte operation, not a decode, so the guarantee above is
    untouched - the digits between the braces are still never looked at.
    """
    body = _TRAILING_NEWLINE.sub(b"", body)
    if _NEWLINE.search(body):
        raise ValueError(
            f"The response at offset {offset} contains a newline inside the "
            "body. This API returns compact JSON; a pretty-printed body would "
            "break the line format, and refusing this page beats writing a "
            "silently truncated one."
        )
    return b'{"o":%d,"r":' % offset + body + b"}"
