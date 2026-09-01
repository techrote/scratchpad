#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import random
import re
import secrets
from collections import Counter
from pathlib import Path


# HTML markup is retained verbatim. Only text between tags is rewritten.
MARKUP_RE = re.compile(
    r"<!--.*?-->|<![^>]*>|<[^>]*>",
    re.DOTALL,
)

START_TAG_RE = re.compile(
    r"^<\s*([A-Za-z][\w:.-]*)"
)

END_TAG_RE = re.compile(
    r"^<\s*/\s*([A-Za-z][\w:.-]*)"
)

VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}

# Text inside these elements is not rendered as ordinary page text.
NON_RENDERED_TAGS = {
    "script",
    "style",
    "template",
    "noscript",
}


def split_html(source: str) -> list[tuple[str, bool]]:
    """
    Split the source into:

        (raw_fragment, is_rendered_text)

    Rendered text includes:

      - all text inside <body>
      - the text inside <title>

    Text inside script, style, template, or noscript is excluded.

    HTML tags, attributes, CSS, comments, and declarations are retained
    exactly as they appeared in the source file.
    """
    parts: list[tuple[str, bool]] = []

    stack: list[str] = []

    in_body = 0
    in_title = 0
    non_rendered = 0

    cursor = 0

    def is_rendered() -> bool:
        return (
            (in_body > 0 or in_title > 0)
            and non_rendered == 0
        )

    for match in MARKUP_RE.finditer(source):
        # Text preceding this tag.
        if match.start() > cursor:
            parts.append(
                (
                    source[cursor:match.start()],
                    is_rendered(),
                )
            )

        token = match.group(0)

        # Markup itself is never shuffled.
        parts.append((token, False))

        end_match = END_TAG_RE.match(token)
        start_match = START_TAG_RE.match(token)

        if end_match:
            tag = end_match.group(1).lower()

            # sketch-journal-03.html is well formed, so pop through the
            # corresponding opening tag.
            while stack:
                popped = stack.pop()

                in_body -= popped == "body"
                in_title -= popped == "title"
                non_rendered -= popped in NON_RENDERED_TAGS

                if popped == tag:
                    break

        elif start_match:
            tag = start_match.group(1).lower()

            self_closing = (
                token.rstrip().endswith("/>")
                or tag in VOID_TAGS
            )

            if not self_closing:
                stack.append(tag)

                in_body += tag == "body"
                in_title += tag == "title"
                non_rendered += tag in NON_RENDERED_TAGS

        cursor = match.end()

    # Any text after the final tag.
    if cursor < len(source):
        parts.append(
            (
                source[cursor:],
                is_rendered(),
            )
        )

    return parts


def derange_characters(
    characters: list[str],
    rng: random.Random,
) -> list[str]:
    """
    Randomly permute the character inventory while avoiding visibly
    unchanged positions.

    Because repeated characters exist, an ordinary random shuffle would
    leave many locations displaying the same character by coincidence.

    This groups equal characters, randomises the group and occurrence
    ordering, then rotates the complete sequence far enough that no
    character group overlaps its original positions.

    A perfect zero-match arrangement is possible whenever no single
    character occupies more than half of all positions. That condition
    is satisfied by sketch-journal-03.html.
    """
    total = len(characters)

    if total < 2:
        return characters.copy()

    groups: dict[str, list[int]] = {}

    for index, character in enumerate(characters):
        groups.setdefault(character, []).append(index)

    position_groups = list(groups.values())

    # Randomise both the character-group ordering and the occurrence
    # ordering inside each group.
    rng.shuffle(position_groups)

    for positions in position_groups:
        rng.shuffle(positions)

    ordered_positions = [
        index
        for positions in position_groups
        for index in positions
    ]

    ordered_values = [
        characters[index]
        for index in ordered_positions
    ]

    largest_group = max(
        len(positions)
        for positions in position_groups
    )

    if largest_group <= total // 2:
        # Any shift in this range guarantees that no equal-character
        # block overlaps its original block.
        shift = rng.randint(
            largest_group,
            total - largest_group,
        )
    else:
        # A zero-match arrangement would be mathematically impossible
        # if one character occupied more than half the positions.
        # This shift minimises the unavoidable number of matches.
        shift = largest_group

    shuffled = [""] * total

    for offset, destination in enumerate(ordered_positions):
        shuffled[destination] = ordered_values[
            (offset + shift) % total
        ]

    return shuffled


def randomise_visible_text(
    source: str,
    rng: random.Random,
) -> tuple[str, int, int, int]:
    """
    Shuffle every rendered non-whitespace character globally.

    Whitespace is deliberately left in its original slot so that line
    structure, word spacing, indentation, and page geometry do not move.
    """
    parts = split_html(source)

    decoded_parts: list[list[str] | None] = []
    original_characters: list[str] = []

    # Gather one global pool containing both ordinary page text and all
    # of the coloured cell glyphs.
    for raw, is_rendered_text in parts:
        if not is_rendered_text:
            decoded_parts.append(None)
            continue

        # Decode any HTML entities to the actual displayed characters.
        characters = list(html.unescape(raw))
        decoded_parts.append(characters)

        original_characters.extend(
            character
            for character in characters
            if not character.isspace()
        )

    shuffled_characters = derange_characters(
        original_characters,
        rng,
    )

    replacements = iter(shuffled_characters)
    output: list[str] = []

    # Refill every original non-whitespace character slot.
    for (raw, _), characters in zip(parts, decoded_parts):
        if characters is None:
            output.append(raw)
            continue

        rebuilt = "".join(
            character
            if character.isspace()
            else next(replacements)
            for character in characters
        )

        # Escape any shuffled character that could otherwise become
        # accidental HTML syntax.
        output.append(
            html.escape(
                rebuilt,
                quote=False,
            )
        )

    fixed_positions = sum(
        original == shuffled
        for original, shuffled in zip(
            original_characters,
            shuffled_characters,
        )
    )

    return (
        "".join(output),
        len(original_characters),
        len(Counter(original_characters)),
        fixed_positions,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Shuffle all rendered HTML text characters without moving "
            "their slots or changing the document styling."
        )
    )

    parser.add_argument(
        "input",
        nargs="?",
        default="sketch-journal-02-rejected.html",
        help=(
            "source HTML file "
            "(default: sketch-journal-03.html)"
        ),
    )

    parser.add_argument(
        "output",
        nargs="?",
        default="sketch-journal-02-rejected-all.html",
        help=(
            "output HTML file "
            "(default: sketch-journal-02-all-visible-swapped.html)"
        ),
    )

    parser.add_argument(
        "--seed",
        type=int,
        help=(
            "optional integer seed for reproducing exactly the same "
            "shuffle"
        ),
    )

    args = parser.parse_args()

    source_path = Path(args.input)
    output_path = Path(args.output)

    if not source_path.is_file():
        raise SystemExit(
            f"Input file not found: {source_path}"
        )

    if source_path.resolve() == output_path.resolve():
        raise SystemExit(
            "Input and output paths must be different."
        )

    # Generate and print a seed when none is supplied, allowing every
    # random result to be reproduced later.
    seed = (
        args.seed
        if args.seed is not None
        else secrets.randbits(64)
    )

    rng = random.Random(seed)

    source = source_path.read_text(
        encoding="utf-8"
    )

    (
        result,
        slot_count,
        distinct_count,
        fixed_count,
    ) = randomise_visible_text(
        source,
        rng,
    )

    output_path.write_text(
        result,
        encoding="utf-8",
        newline="",
    )

    print(f"Created: {output_path}")
    print(f"Seed: {seed}")
    print(
        "Rendered non-whitespace character slots shuffled: "
        f"{slot_count:,}"
    )
    print(
        "Distinct characters in the global pool: "
        f"{distinct_count:,}"
    )
    print(
        "Slots retaining the same visible character: "
        f"{fixed_count:,}"
    )
    print(
        "Whitespace, HTML tags, attributes, CSS, colours, "
        "positions and angles: unchanged"
    )


if __name__ == "__main__":
    main()
    main()