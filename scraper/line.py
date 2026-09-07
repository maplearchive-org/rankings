"""One line of a slice asset."""

import re

_NEWLINE = re.compile(rb"[\n\r]")


def slice_line(offset, body):
    """
    Build ``{"o":<offset>,"r":<the API's body, verbatim>}`` as bytes.

    The body is spliced in as bytes and is never parsed, and never even
    decoded. exp values reach magnitudes like 795025135043493, and on the
    archive's side JSON.parse rounds those silently while the rounded value
    still looks entirely plausible - every (level, exp) comparison the ban
    detection rests on would be quietly wrong. Python's own integers would not
    round, which is not the point: the point is that bytes never decoded and
    never re-encoded are provably the bytes the API sent, so nothing this
    worker does can be the reason a digit changed.
    """
    if _NEWLINE.search(body):
        raise ValueError(
            f"The response at offset {offset} contains a newline. This API "
            "returns compact JSON; a pretty-printed body would break the line "
            "format, and failing here beats writing a silently truncated page."
        )
    return b'{"o":%d,"r":' % offset + body + b"}"
