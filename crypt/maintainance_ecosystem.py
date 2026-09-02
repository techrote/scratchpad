#!/usr/bin/env python3
"""
MAINTENANCE ECOSYSTEM
=====================
A dependency-free terminal toy containing *only* six easter-egg systems.
Designed for Windows Terminal first, but also runs in a normal POSIX terminal.

Keys
----
  G      robot gremlin
  B      loose-hardware / aChar spill
  T      phantom maintenance transmission
  M      relay moth swarm
  C      cable crawler
  L      unauthorized maintenance lift
  R      trigger one random event
  A      toggle rare ambient auto-events
  Ctrl-X toggle the aChar FX control layer
  ?      help
  Q      quit

When aChar FX control layer is active:
  Space  burst
  +/-    spawn rate
  [/]    previous/next aChar family
  D      direction mode
  P      palette phase
  R      randomise FX parameters
  Esc    close FX layer

Design/refinement notes
-----------------------
1. ROBOT GREMLIN
   Initial: hatch + cute robot appearance.
   Refine 1: hatch now physically opens and the gremlin pathfinds over the
             terminal's divider topology instead of teleporting.
   Refine 2: it changes pose for horizontal/vertical travel, idles, explores
             multiple destinations, returns to the hatch, and can collect
             settled loose hardware.
   Refine 3: relay moths actively flee it, making the cosmetic systems share
             one little world.

2. LOOSE HARDWARE -> aCHAR FX SYSTEM
   Initial: one falling bolt/washer.
   Refine 1: multiple simultaneous aChars, gravity, bounces, settling, trails,
             colour LUTs and multiple animated glyph families.
   Refine 2: horizontal/vertical/mixed travel and a manually toggled FX layer
             with live controls for density, family, direction and palette.
   Refine 3: the original 'machine is falling apart' spill still exists as B,
             while the same engine can run as a general terminal visualizer.

3. PHANTOM MAINTENANCE TRANSMISSION
   Initial: a sardonic line appears in unused telemetry space.
   Refine 1: staged carrier acquisition, channel identification, signal meter,
             type-on reveal and fade-out.
   Refine 2: curated messages can react to world context (gremlin, bolts,
             moths, cable crawler, lift) without ever pretending to be a real
             application error.
   Refine 3: controlled character corruption gives weak channels a believable
             'wrong wire, wrong room' feel.

4. RELAY MOTHS (new)
   Initial: tiny glyph-moths orbit indicator lamps.
   Refine 1: simple flock/attractor motion, lamp switching and resting.
   Refine 2: they flee the gremlin and are disturbed by nearby moving aChars.
   Refine 3: density remains bounded and old moths naturally disperse.

5. CABLE CRAWLER (new)
   Initial: a luminous creature/current crawls along panel wiring.
   Refine 1: it pathfinds strictly through the same divider graph used by the
             gremlin, so it genuinely follows the console topology.
   Refine 2: persistent phosphor trail, occasional sparks, and temporary
             'repairs' of deliberately missing divider cells.
   Refine 3: it chooses several destinations before vanishing rather than
             repeating one canned animation.

6. UNAUTHORIZED MAINTENANCE LIFT (new)
   Initial: tiny elevator crosses a vertical service shaft.
   Refine 1: multi-stage movement: arrival, door opening, dwell, closing,
             multiple stops, departure.
   Refine 2: random/contextual cargo and tiny status captions imply a much
             larger facility outside the terminal.
   Refine 3: the shaft is derived from live terminal geometry and rebuilds on
             resize.
"""

from __future__ import annotations

import math
import os
import random
import shutil
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Set, Tuple


ESC = "\x1b"
SYNC_BEGIN = ESC + "[?2026h"
SYNC_END = ESC + "[?2026l"
ALT_ON = ESC + "[?1049h"
ALT_OFF = ESC + "[?1049l"
HIDE_CURSOR = ESC + "[?25l"
SHOW_CURSOR = ESC + "[?25h"
RESET = ESC + "[0m"
HOME = ESC + "[H"
CLEAR = ESC + "[2J"

Coord = Tuple[int, int]


def clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


def sign(v: float) -> int:
    return (v > 0) - (v < 0)


class InputReader:
    """Non-blocking single-key reader for Windows and POSIX terminals."""

    def __init__(self) -> None:
        self.is_windows = os.name == "nt"
        self._old_term = None

        if self.is_windows:
            self._enable_windows_vt()
        else:
            import termios
            import tty

            self._termios = termios
            self._tty = tty

            if sys.stdin.isatty():
                self._old_term = termios.tcgetattr(sys.stdin.fileno())
                tty.setcbreak(sys.stdin.fileno())

    def _enable_windows_vt(self) -> None:
        try:
            import ctypes
            from ctypes import wintypes

            kernel32 = ctypes.windll.kernel32
            handle = kernel32.GetStdHandle(-11)
            mode = wintypes.DWORD()

            if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                kernel32.SetConsoleMode(handle, mode.value | 0x0004)
        except Exception:
            pass

    def read_keys(self) -> List[str]:
        out: List[str] = []

        if self.is_windows:
            import msvcrt

            while msvcrt.kbhit():
                ch = msvcrt.getwch()

                if ch in ("\x00", "\xe0"):
                    if msvcrt.kbhit():
                        msvcrt.getwch()
                    continue

                out.append(ch)

            return out

        import select

        while True:
            ready, _, _ = select.select([sys.stdin], [], [], 0)

            if not ready:
                break

            ch = sys.stdin.read(1)

            if not ch:
                break

            out.append(ch)

        return out

    def close(self) -> None:
        if not self.is_windows and self._old_term is not None:
            try:
                self._termios.tcsetattr(
                    sys.stdin.fileno(),
                    self._termios.TCSADRAIN,
                    self._old_term,
                )
            except Exception:
                pass


class Canvas:
    def __init__(self, width: int, height: int) -> None:
        self.w = width
        self.h = height

        n = width * height

        self.chars = [" "] * n
        self.fg = [None] * n
        self.bold = [False] * n

    def _idx(self, x: int, y: int) -> int:
        return y * self.w + x

    def put(
        self,
        x: int,
        y: int,
        ch: str,
        fg: Optional[int] = None,
        bold: bool = False,
    ) -> None:
        if 0 <= x < self.w and 0 <= y < self.h and ch:
            i = self._idx(x, y)

            self.chars[i] = ch[0]
            self.fg[i] = fg
            self.bold[i] = bold

    def text(
        self,
        x: int,
        y: int,
        s: str,
        fg: Optional[int] = None,
        bold: bool = False,
        max_width: Optional[int] = None,
    ) -> None:
        if y < 0 or y >= self.h:
            return

        if max_width is not None:
            s = s[:max(0, max_width)]

        for i, ch in enumerate(s):
            self.put(x + i, y, ch, fg, bold)

    def hline(
        self,
        x1: int,
        x2: int,
        y: int,
        ch: str = "-",
        fg: int = 240,
    ) -> None:
        if x2 < x1:
            x1, x2 = x2, x1

        for x in range(max(0, x1), min(self.w - 1, x2) + 1):
            self.put(x, y, ch, fg)

    def vline(
        self,
        x: int,
        y1: int,
        y2: int,
        ch: str = "|",
        fg: int = 240,
    ) -> None:
        if y2 < y1:
            y1, y2 = y2, y1

        for y in range(max(0, y1), min(self.h - 1, y2) + 1):
            self.put(x, y, ch, fg)

    def box(
        self,
        x: int,
        y: int,
        w: int,
        h: int,
        fg: int = 240,
    ) -> None:
        if w < 2 or h < 2:
            return

        self.hline(x + 1, x + w - 2, y, "-", fg)
        self.hline(x + 1, x + w - 2, y + h - 1, "-", fg)

        self.vline(x, y + 1, y + h - 2, "|", fg)
        self.vline(x + w - 1, y + 1, y + h - 2, "|", fg)

        corners = (
            (x, y),
            (x + w - 1, y),
            (x, y + h - 1),
            (x + w - 1, y + h - 1),
        )

        for px, py in corners:
            self.put(px, py, "+", fg)

    def render(self) -> str:
        pieces: List[str] = [
            SYNC_BEGIN,
            HOME,
        ]

        current_fg: Optional[int] = None
        current_bold = False

        for y in range(self.h):
            for x in range(self.w):
                i = self._idx(x, y)

                fg = self.fg[i]
                bold = self.bold[i]

                if fg != current_fg or bold != current_bold:
                    if fg is None and not bold:
                        pieces.append(RESET)
                    else:
                        codes = []

                        if bold:
                            codes.append("1")

                        if fg is not None:
                            codes.append(f"38;5;{fg}")

                        pieces.append(
                            ESC
                            + "["
                            + ";".join(codes)
                            + "m"
                        )

                    current_fg = fg
                    current_bold = bold

                pieces.append(self.chars[i])

            if y != self.h - 1:
                pieces.append("\n")

        pieces.extend(
            [
                RESET,
                SYNC_END,
            ]
        )

        return "".join(pieces)


class Stage:
    """
    Static industrial scenery.

    More importantly, the panel dividers form a real movement graph shared by
    the gremlin and cable crawler.
    """

    def __init__(
        self,
        w: int,
        h: int,
    ) -> None:
        self.w = w
        self.h = h

        self.graph: Set[Coord] = set()
        self.graph_list: List[Coord] = []

        self.gaps: Set[Coord] = set()
        self.repaired_until: Dict[Coord, float] = {}

        self.lamps: List[Coord] = []

        self.hlines: List[int] = []
        self.vlines: List[int] = []

        self.hatch: Coord = (5, 5)

        self.shaft_x = 10

        self.y_top = 6
        self.y_mid = 12
        self.y_bottom = 18

        self.rebuild(w, h)

    def rebuild(
        self,
        w: int,
        h: int,
    ) -> None:
        self.w = w
        self.h = h

        self.graph.clear()
        self.gaps.clear()
        self.repaired_until.clear()

        self.y_top = max(
            5,
            min(
                h - 10,
                7,
            ),
        )

        self.y_bottom = max(
            self.y_top + 8,
            h - 8,
        )

        self.y_mid = (
            self.y_top
            + self.y_bottom
        ) // 2

        x1 = max(
            18,
            w // 3,
        )

        x2 = min(
            w - 18,
            (2 * w) // 3,
        )

        if x2 <= x1 + 8:
            x1 = max(
                12,
                w // 2 - 10,
            )

            x2 = min(
                w - 12,
                w // 2 + 10,
            )

        self.vlines = [
            x1,
            x2,
        ]

        self.hlines = sorted(
            set(
                [
                    self.y_top,
                    self.y_mid,
                    self.y_bottom,
                ]
            )
        )

        self.shaft_x = x2

        self.hatch = (
            min(
                max(
                    7,
                    w // 10,
                ),
                max(
                    7,
                    x1 - 6,
                ),
            ),
            self.y_top,
        )

        # Main horizontal divider graph.
        for y in self.hlines:
            for x in range(
                1,
                w - 1,
            ):
                self.graph.add(
                    (x, y)
                )

        # Main vertical divider graph.
        for x in self.vlines:
            for y in range(
                self.y_top,
                h - 1,
            ):
                self.graph.add(
                    (x, y)
                )

        # Additional branches make traversal more interesting.
        branch_y = min(
            h - 3,
            self.y_mid + 4,
        )

        for x in range(
            x1,
            x2 + 1,
        ):
            self.graph.add(
                (x, branch_y)
            )

        for y in range(
            self.y_top,
            branch_y + 1,
        ):
            self.graph.add(
                (x1 + 5, y)
            )

        # Intentional visual breaks in the dividers.
        # They remain graph-connected but look broken.
        candidates = [
            (
                min(
                    w - 3,
                    x1 + 7,
                ),
                self.y_mid,
            ),
            (
                max(
                    2,
                    x2 - 9,
                ),
                self.y_bottom,
            ),
            (
                x2,
                min(
                    h - 3,
                    self.y_mid + 3,
                ),
            ),
        ]

        self.gaps = {
            p
            for p in candidates
            if p in self.graph
        }

        self.graph_list = sorted(
            self.graph
        )

        self.lamps = [
            (
                max(
                    3,
                    x1 - 5,
                ),
                max(
                    2,
                    self.y_top - 3,
                ),
            ),
            (
                min(
                    w - 4,
                    x1 + 8,
                ),
                max(
                    2,
                    self.y_top - 3,
                ),
            ),
            (
                min(
                    w - 4,
                    x2 + 7,
                ),
                max(
                    2,
                    self.y_top - 3,
                ),
            ),
            (
                max(
                    3,
                    x1 - 6,
                ),
                min(
                    h - 3,
                    self.y_bottom + 3,
                ),
            ),
            (
                min(
                    w - 4,
                    x2 + 8,
                ),
                min(
                    h - 3,
                    self.y_bottom + 3,
                ),
            ),
        ]

    def neighbors(
        self,
        p: Coord,
    ) -> Iterable[Coord]:
        x, y = p

        for q in (
            (x + 1, y),
            (x - 1, y),
            (x, y + 1),
            (x, y - 1),
        ):
            if q in self.graph:
                yield q

    def path(
        self,
        start: Coord,
        goal: Coord,
    ) -> List[Coord]:
        if start not in self.graph:
            return []

        if goal not in self.graph:
            return []

        queue = deque(
            [start]
        )

        prev: Dict[
            Coord,
            Optional[Coord],
        ] = {
            start: None
        }

        while queue:
            p = queue.popleft()

            if p == goal:
                break

            for q in self.neighbors(p):
                if q not in prev:
                    prev[q] = p
                    queue.append(q)

        if goal not in prev:
            return []

        out = []

        p: Optional[Coord] = goal

        while p is not None:
            out.append(p)
            p = prev[p]

        out.reverse()

        return out

    def far_random_node(
        self,
        rng: random.Random,
        start: Coord,
        min_dist: int = 20,
    ) -> Coord:
        if not self.graph_list:
            return start

        sx, sy = start

        far = [
            p
            for p in self.graph_list
            if (
                abs(p[0] - sx)
                + abs(p[1] - sy)
                >= min_dist
            )
        ]

        return rng.choice(
            far
            or self.graph_list
        )

    def mark_repaired(
        self,
        p: Coord,
        seconds: float = 6.0,
    ) -> None:
        if p in self.gaps:
            self.repaired_until[p] = (
                time.monotonic()
                + seconds
            )

    def is_repaired(
        self,
        p: Coord,
        now: float,
    ) -> bool:
        until = self.repaired_until.get(
            p,
            0.0,
        )

        if until <= now:
            self.repaired_until.pop(
                p,
                None,
            )
            return False

        return True

    def render(
        self,
        c: Canvas,
        now: float,
        ambient: bool,
    ) -> None:
        w = self.w
        h = self.h

        c.box(
            0,
            0,
            w,
            h,
            238,
        )

        title = (
            " MAINTENANCE ECOSYSTEM "
            "// NOTHING HERE IS A CONTROL SYSTEM "
        )

        c.text(
            2,
            0,
            title[
                :max(
                    0,
                    w - 4,
                )
            ],
            244,
            True,
        )

        for y in self.hlines:
            c.hline(
                1,
                w - 2,
                y,
                "-",
                239,
            )

        for x in self.vlines:
            c.vline(
                x,
                self.y_top,
                h - 2,
                "|",
                239,
            )

        for x in self.vlines:
            for y in self.hlines:
                c.put(
                    x,
                    y,
                    "+",
                    245,
                )

        x1, x2 = self.vlines

        branch_y = min(
            h - 3,
            self.y_mid + 4,
        )

        c.hline(
            x1,
            x2,
            branch_y,
            "-",
            237,
        )

        c.vline(
            x1 + 5,
            self.y_top,
            branch_y,
            "|",
            237,
        )

        c.put(
            x1,
            branch_y,
            "+",
            244,
        )

        c.put(
            x2,
            branch_y,
            "+",
            244,
        )

        c.put(
            x1 + 5,
            self.y_top,
            "+",
            244,
        )

        c.put(
            x1 + 5,
            branch_y,
            "+",
            244,
        )

        # Visual gaps.
        for p in self.gaps:
            if self.is_repaired(
                p,
                now,
            ):
                c.put(
                    p[0],
                    p[1],
                    "#",
                    154,
                    True,
                )
            else:
                c.put(
                    p[0],
                    p[1],
                    " ",
                    None,
                )

        # Pure scenery.
        labels = [
            (
                2,
                2,
                "AUX MAINT / OBSERVATION ONLY",
            ),
            (
                x1 + 2,
                2,
                "UNLICENSED SERVICE SPACE",
            ),
            (
                x2 + 2,
                2,
                "BAY 13 ROUTING UNKNOWN",
            ),
            (
                2,
                self.y_top + 2,
                "loose hardware expected",
            ),
            (
                x1 + 2,
                self.y_top + 2,
                "do not feed relay moths",
            ),
            (
                x2 + 2,
                self.y_top + 2,
                "lift permit: missing",
            ),
        ]

        for x, y, s in labels:
            c.text(
                x,
                y,
                s,
                242,
                False,
                max(
                    0,
                    w - x - 2,
                ),
            )

        # Indicator lamps.
        for i, (x, y) in enumerate(
            self.lamps
        ):
            pulse = int(
                now
                * (
                    2.0
                    + i * 0.13
                )
            ) % 4

            fg = (
                82,
                83,
                119,
                120,
            )[pulse]

            c.put(
                x,
                y,
                "o",
                fg,
                pulse == 3,
            )

        # Gremlin hatch baseline.
        hx, hy = self.hatch

        c.text(
            max(
                1,
                hx - 3,
            ),
            hy,
            "[==]",
            245,
            True,
        )

        # Lift shaft.
        for y in range(
            self.y_top + 1,
            h - 2,
            3,
        ):
            c.put(
                self.shaft_x,
                y,
                ":",
                244,
            )

        status = (
            f" A ambient:"
            f"{'ON' if ambient else 'OFF'}"
            "  G/B/T/M/C/L events"
            "  Ctrl-X aChar FX"
            "  ? help"
            "  Q quit "
        )

        c.text(
            2,
            h - 1,
            status[
                :max(
                    0,
                    w - 4,
                )
            ],
            244,
        )


@dataclass
class ACharKind:
    name: str
    frames: Tuple[str, ...]
    palette: Tuple[int, ...]
    frame_rate: float

    gravity: float = 0.0
    bounce: float = 0.0

    trail: str = ""


@dataclass
class AChar:
    x: float
    y: float

    vx: float
    vy: float

    kind: int

    age: float
    ttl: float
    phase: float

    settled: bool = False
    hardware: bool = False

    bounces: int = 0

    trail: deque = field(
        default_factory=lambda: deque(
            maxlen=7
        )
    )


class ACharField:
    def __init__(
        self,
        rng: random.Random,
    ) -> None:
        self.rng = rng

        # Each aChar type is intentionally tiny:
        #
        # frames + colour LUT + rates + physics.
        #
        # This is the beginning of the proposed data-defined aChar system.
        self.kinds = [
            ACharKind(
                "bolt",
                (
                    "|",
                    "/",
                    "-",
                    "\\",
                ),
                (
                    250,
                    252,
                    255,
                    245,
                ),
                10,
                12.0,
                0.45,
                ".",
            ),
            ACharKind(
                "washer",
                (
                    "o",
                    "O",
                    "0",
                    "O",
                ),
                (
                    250,
                    247,
                    255,
                ),
                7,
                10.0,
                0.38,
                ".",
            ),
            ACharKind(
                "screw",
                (
                    "+",
                    "x",
                    "+",
                    "x",
                ),
                (
                    244,
                    250,
                    255,
                ),
                12,
                11.0,
                0.40,
                ".",
            ),
            ACharKind(
                "spark",
                (
                    ".",
                    "*",
                    "+",
                    "*",
                ),
                (
                    226,
                    220,
                    214,
                    208,
                ),
                18,
                2.0,
                0.15,
                "'",
            ),
            ACharKind(
                "slash",
                (
                    "/",
                    "-",
                    "\\",
                    "|",
                ),
                (
                    45,
                    51,
                    87,
                    123,
                    159,
                    195,
                ),
                16,
                0.0,
                0.8,
                ".",
            ),
            ACharKind(
                "bit",
                (
                    "0",
                    "1",
                    "o",
                    ".",
                ),
                (
                    39,
                    45,
                    51,
                    87,
                    123,
                ),
                14,
                0.0,
                0.8,
                ":",
            ),
            ACharKind(
                "chevron",
                (
                    ">",
                    ">",
                    "=",
                    ">",
                ),
                (
                    81,
                    117,
                    153,
                    189,
                ),
                12,
                0.0,
                0.8,
                "-",
            ),
            ACharKind(
                "rune",
                (
                    "*",
                    "+",
                    "x",
                    "+",
                ),
                (
                    201,
                    207,
                    213,
                    219,
                ),
                9,
                0.0,
                0.8,
                ".",
            ),
        ]

        self.items: List[AChar] = []

        self.fx_mode = False

        self.spawn_rate = 5.0
        self.spawn_acc = 0.0

        self.selected_kind = 4

        self.direction_index = 4

        self.directions = [
            "DOWN",
            "UP",
            "LEFT",
            "RIGHT",
            "MIXED",
            "RADIAL",
        ]

        self.palette_phase = 0

        self.max_items = 180

        self.total_spills = 0

    def toggle_fx(self) -> None:
        self.fx_mode = not self.fx_mode

    def _append(
        self,
        item: AChar,
    ) -> None:
        if len(
            self.items
        ) >= self.max_items:
            self.items.pop(0)

        self.items.append(
            item
        )

    def spawn_spark(
        self,
        x: float,
        y: float,
        count: int = 2,
    ) -> None:
        for _ in range(count):
            self._append(
                AChar(
                    x=x,
                    y=y,
                    vx=self.rng.uniform(
                        -5,
                        5,
                    ),
                    vy=self.rng.uniform(
                        -5,
                        1,
                    ),
                    kind=3,
                    age=0,
                    ttl=self.rng.uniform(
                        0.5,
                        1.4,
                    ),
                    phase=(
                        self.rng.random()
                        * 5
                    ),
                )
            )

    def trigger_hardware_spill(
        self,
        stage: Stage,
    ) -> None:
        """
        The original Easter egg survives as a special preset of the larger
        aChar engine.
        """

        self.total_spills += 1

        x_choices = [
            stage.vlines[0],
            stage.vlines[1],
            self.rng.randint(
                4,
                max(
                    5,
                    stage.w - 5,
                ),
            ),
        ]

        base_x = self.rng.choice(
            x_choices
        )

        count = self.rng.randint(
            4,
            11,
        )

        for _ in range(count):
            k = self.rng.choice(
                [
                    0,
                    0,
                    1,
                    2,
                    3,
                ]
            )

            self._append(
                AChar(
                    x=clamp(
                        base_x
                        + self.rng.uniform(
                            -3,
                            3,
                        ),
                        2,
                        stage.w - 3,
                    ),
                    y=max(
                        2,
                        stage.y_top
                        - self.rng.uniform(
                            2,
                            7,
                        ),
                    ),
                    vx=self.rng.uniform(
                        -3.5,
                        3.5,
                    ),
                    vy=self.rng.uniform(
                        -2.0,
                        2.0,
                    ),
                    kind=k,
                    age=0,
                    ttl=self.rng.uniform(
                        8,
                        18,
                    ),
                    phase=(
                        self.rng.random()
                        * 10
                    ),
                    hardware=(
                        k
                        in (
                            0,
                            1,
                            2,
                        )
                    ),
                )
            )

    def _spawn_fx_one(
        self,
        stage: Stage,
    ) -> None:
        kind = self.selected_kind

        mode = self.directions[
            self.direction_index
        ]

        margin = 2

        speed = self.rng.uniform(
            4.0,
            12.0,
        )

        x = self.rng.uniform(
            margin,
            max(
                margin + 1,
                stage.w
                - margin
                - 1,
            ),
        )

        y = self.rng.uniform(
            margin,
            max(
                margin + 1,
                stage.h
                - margin
                - 1,
            ),
        )

        vx = 0.0
        vy = 0.0

        if mode == "DOWN":
            y = margin
            vy = speed

        elif mode == "UP":
            y = (
                stage.h
                - margin
                - 1
            )
            vy = -speed

        elif mode == "LEFT":
            x = (
                stage.w
                - margin
                - 1
            )
            vx = -speed

        elif mode == "RIGHT":
            x = margin
            vx = speed

        elif mode == "RADIAL":
            x = stage.w / 2
            y = stage.h / 2

            angle = (
                self.rng.random()
                * math.tau
            )

            vx = (
                math.cos(angle)
                * speed
            )

            vy = (
                math.sin(angle)
                * speed
                * 0.55
            )

        else:
            angle = (
                self.rng.random()
                * math.tau
            )

            vx = (
                math.cos(angle)
                * speed
            )

            vy = (
                math.sin(angle)
                * speed
                * 0.55
            )

        self._append(
            AChar(
                x=x,
                y=y,
                vx=vx,
                vy=vy,
                kind=kind,
                age=0,
                ttl=self.rng.uniform(
                    5,
                    14,
                ),
                phase=(
                    self.rng.random()
                    * 5
                ),
            )
        )

    def burst_fx(
        self,
        stage: Stage,
        count: int = 24,
    ) -> None:
        for _ in range(count):
            self._spawn_fx_one(
                stage
            )

    def handle_fx_key(
        self,
        key: str,
        stage: Stage,
    ) -> bool:
        if not self.fx_mode:
            return False

        if key == "\x1b":
            self.fx_mode = False
            return True

        kl = key.lower()

        if key == " ":
            self.burst_fx(
                stage
            )

        elif key in (
            "+",
            "=",
        ):
            self.spawn_rate = min(
                40.0,
                self.spawn_rate
                + 1.0,
            )

        elif key == "-":
            self.spawn_rate = max(
                0.0,
                self.spawn_rate
                - 1.0,
            )

        elif key == "[":
            self.selected_kind = (
                self.selected_kind
                - 1
            ) % len(
                self.kinds
            )

        elif key == "]":
            self.selected_kind = (
                self.selected_kind
                + 1
            ) % len(
                self.kinds
            )

        elif kl == "d":
            self.direction_index = (
                self.direction_index
                + 1
            ) % len(
                self.directions
            )

        elif kl == "p":
            self.palette_phase = (
                self.palette_phase
                + 1
            ) % 32

        elif kl == "r":
            self.selected_kind = (
                self.rng.randrange(
                    len(
                        self.kinds
                    )
                )
            )

            self.direction_index = (
                self.rng.randrange(
                    len(
                        self.directions
                    )
                )
            )

            self.spawn_rate = (
                self.rng.uniform(
                    2.0,
                    20.0,
                )
            )

            self.palette_phase = (
                self.rng.randrange(
                    32
                )
            )

        else:
            return False

        return True

    def update(
        self,
        dt: float,
        stage: Stage,
    ) -> None:
        if (
            self.fx_mode
            and self.spawn_rate > 0
        ):
            self.spawn_acc += (
                dt
                * self.spawn_rate
            )

            while (
                self.spawn_acc
                >= 1.0
            ):
                self.spawn_acc -= 1.0

                self._spawn_fx_one(
                    stage
                )

        alive: List[AChar] = []

        for a in self.items:
            a.age += dt

            if a.age >= a.ttl:
                continue

            if a.settled:
                alive.append(a)
                continue

            a.trail.appendleft(
                (
                    int(
                        round(a.x)
                    ),
                    int(
                        round(a.y)
                    ),
                )
            )

            kind = self.kinds[
                a.kind
            ]

            a.vy += (
                kind.gravity
                * dt
            )

            old_y = a.y

            a.x += (
                a.vx
                * dt
            )

            a.y += (
                a.vy
                * dt
            )

            # Side walls.
            if a.x <= 1:
                a.x = 1

                a.vx = (
                    abs(a.vx)
                    * 0.8
                )

            elif (
                a.x
                >= stage.w - 2
            ):
                a.x = (
                    stage.w - 2
                )

                a.vx = (
                    -abs(a.vx)
                    * 0.8
                )

            # Hardware interacts with panel dividers.
            if (
                a.hardware
                and a.vy > 0
            ):
                levels = (
                    list(
                        stage.hlines
                    )
                    + [
                        stage.h - 2
                    ]
                )

                for ly in levels:
                    if (
                        old_y < ly
                        <= a.y
                    ):
                        a.y = ly - 1

                        a.vy = (
                            -abs(a.vy)
                            * kind.bounce
                        )

                        a.vx *= 0.72

                        a.bounces += 1

                        if (
                            abs(a.vy)
                            < 1.1
                            or a.bounces
                            >= 4
                        ):
                            a.settled = True
                            a.vx = 0
                            a.vy = 0

                        break

            # Generic FX aChars wrap around all edges.
            if not a.hardware:
                if a.y < 1:
                    a.y = (
                        stage.h - 2
                    )

                elif (
                    a.y
                    > stage.h - 2
                ):
                    a.y = 1

                if a.x < 1:
                    a.x = (
                        stage.w - 2
                    )

                elif (
                    a.x
                    > stage.w - 2
                ):
                    a.x = 1

            elif (
                a.y
                > stage.h - 1
            ):
                a.y = (
                    stage.h - 2
                )

                a.settled = True

            alive.append(a)

        self.items = alive

    def collect_near(
        self,
        x: int,
        y: int,
        radius: int = 2,
    ) -> int:
        kept = []
        collected = 0

        for a in self.items:
            if (
                a.hardware
                and a.settled
                and (
                    abs(a.x - x)
                    + abs(a.y - y)
                    <= radius
                )
            ):
                collected += 1
            else:
                kept.append(a)

        self.items = kept

        return collected

    def disturbance_near(
        self,
        x: float,
        y: float,
        radius: float = 5.0,
    ) -> float:
        r2 = (
            radius
            * radius
        )

        total = 0

        for a in self.items:
            dx = a.x - x
            dy = a.y - y

            if (
                dx * dx
                + dy * dy
                <= r2
            ):
                total += 1

        return float(total)

    def render(
        self,
        c: Canvas,
    ) -> None:
        for a in self.items:
            kind = self.kinds[
                a.kind
            ]

            if (
                kind.trail
                and not a.settled
            ):
                for (
                    j,
                    (tx, ty),
                ) in enumerate(
                    list(
                        a.trail
                    )[1:5],
                    start=1,
                ):
                    c.put(
                        tx,
                        ty,
                        kind.trail,
                        236
                        + min(
                            4,
                            j,
                        ),
                    )

            frame = int(
                (
                    a.age
                    + a.phase
                )
                * kind.frame_rate
            ) % len(
                kind.frames
            )

            ch = kind.frames[
                frame
            ]

            pal = kind.palette

            fg = pal[
                (
                    frame
                    + self.palette_phase
                )
                % len(pal)
            ]

            c.put(
                int(
                    round(a.x)
                ),
                int(
                    round(a.y)
                ),
                ch,
                fg,
                (
                    a.hardware
                    and a.settled
                ),
            )

        if self.fx_mode:
            info = (
                " aCHAR FX :: "
                f"{self.kinds[self.selected_kind].name:<8} "
                f"dir={self.directions[self.direction_index]:<6} "
                f"rate={self.spawn_rate:04.1f}/s "
                "[ ] type  "
                "D dir  "
                "P palette  "
                "+/- rate  "
                "Space burst  "
                "R random  "
                "Esc close "
            )

            y = max(
                1,
                c.h - 3,
            )

            c.text(
                2,
                y,
                info[
                    :max(
                        0,
                        c.w - 4,
                    )
                ],
                159,
                True,
            )


class Gremlin:
    def __init__(
        self,
        rng: random.Random,
    ) -> None:
        self.rng = rng

        self.state = "hidden"

        self.timer = 0.0

        self.route: List[
            Coord
        ] = []

        self.route_i = 0
        self.move_acc = 0.0

        self.journeys_left = 0

        self.facing = "right"

        self.collected = 0
        self.appearances = 0

        self.pos: Coord = (
            0,
            0,
        )

    @property
    def active(self) -> bool:
        return (
            self.state
            != "hidden"
        )

    def trigger(
        self,
        stage: Stage,
    ) -> None:
        if self.active:
            # Triggering G while he is already out convinces him to stay out.
            self.journeys_left = min(
                5,
                self.journeys_left
                + 1,
            )
            return

        self.appearances += 1

        self.state = "opening"

        self.timer = 0.0

        self.pos = stage.hatch

        self.route = []
        self.route_i = 0

        self.journeys_left = (
            self.rng.randint(
                2,
                4,
            )
        )

    def _new_route(
        self,
        stage: Stage,
        goal: Optional[
            Coord
        ] = None,
    ) -> None:
        start = (
            self.pos
            if self.pos
            in stage.graph
            else stage.hatch
        )

        if goal is None:
            goal = (
                stage.far_random_node(
                    self.rng,
                    start,
                    max(
                        12,
                        stage.w // 4,
                    ),
                )
            )

        route = stage.path(
            start,
            goal,
        )

        self.route = (
            route
            or [start]
        )

        self.route_i = 0
        self.move_acc = 0.0

    def update(
        self,
        dt: float,
        stage: Stage,
        achars: ACharField,
    ) -> None:
        if self.state == "hidden":
            return

        self.timer += dt

        if self.state == "opening":
            if self.timer >= 0.65:
                self.timer = 0.0

                self.state = (
                    "explore"
                )

                self._new_route(
                    stage
                )

            return

        if self.state == "idle":
            if (
                self.timer
                >= self.rng.uniform(
                    0.45,
                    1.0,
                )
            ):
                self.timer = 0.0

                if (
                    self.journeys_left
                    > 0
                ):
                    self.journeys_left -= 1

                    self.state = (
                        "explore"
                    )

                    self._new_route(
                        stage
                    )

                else:
                    self.state = (
                        "return"
                    )

                    self._new_route(
                        stage,
                        stage.hatch,
                    )

            return

        if self.state == "closing":
            if self.timer >= 0.65:
                self.state = (
                    "hidden"
                )

                self.timer = 0.0

            return

        if not self.route:
            self._new_route(
                stage,
                (
                    stage.hatch
                    if self.state
                    == "return"
                    else None
                ),
            )

        self.move_acc += (
            dt * 9.0
        )

        while (
            self.move_acc
            >= 1.0
            and self.route_i
            < len(self.route) - 1
        ):
            self.move_acc -= 1.0

            old = self.route[
                self.route_i
            ]

            self.route_i += 1

            self.pos = self.route[
                self.route_i
            ]

            dx = (
                self.pos[0]
                - old[0]
            )

            dy = (
                self.pos[1]
                - old[1]
            )

            if dx > 0:
                self.facing = (
                    "right"
                )

            elif dx < 0:
                self.facing = (
                    "left"
                )

            elif dy != 0:
                self.facing = (
                    "climb"
                )

            # Gremlin can actually tidy loose hardware.
            self.collected += (
                achars.collect_near(
                    *self.pos,
                    radius=2,
                )
            )

        if (
            self.route_i
            >= len(self.route) - 1
        ):
            if (
                self.state
                == "return"
                and self.pos
                == stage.hatch
            ):
                self.state = (
                    "closing"
                )

                self.timer = 0.0

            else:
                self.state = (
                    "idle"
                )

                self.timer = 0.0

    def render(
        self,
        c: Canvas,
        stage: Stage,
        now: float,
    ) -> None:
        hx, hy = stage.hatch

        if self.state == "opening":
            phase = int(
                self.timer / 0.13
            ) % 4

            doors = [
                "[==]",
                "[--]",
                "[  ]",
                "<  >",
            ][phase]

            c.text(
                max(
                    1,
                    hx - 3,
                ),
                hy,
                doors,
                220,
                True,
            )

            if phase >= 2:
                c.put(
                    hx - 1,
                    hy - 1,
                    "o",
                    220,
                    True,
                )

            return

        if self.state == "closing":
            phase = int(
                self.timer / 0.13
            ) % 4

            doors = [
                "<  >",
                "[  ]",
                "[--]",
                "[==]",
            ][phase]

            c.text(
                max(
                    1,
                    hx - 3,
                ),
                hy,
                doors,
                220,
                True,
            )

            return

        if self.state == "hidden":
            return

        x, y = self.pos

        bob = (
            int(
                now * 7
            )
            & 1
        )

        if self.facing == "right":
            sprite = (
                (
                    " o_",
                    "<|>",
                    "/ \\",
                )
                if bob
                else (
                    "_o ",
                    "<|>",
                    "/ \\",
                )
            )

        elif self.facing == "left":
            sprite = (
                (
                    "_o ",
                    "<|>",
                    "/ \\",
                )
                if bob
                else (
                    " o_",
                    "<|>",
                    "/ \\",
                )
            )

        else:
            sprite = (
                (
                    " o ",
                    "/|\\",
                    "^ ^",
                )
                if bob
                else (
                    " o ",
                    "\\|/",
                    "v v",
                )
            )

        for sy, row in enumerate(
            sprite
        ):
            c.text(
                x - 1,
                y - 1 + sy,
                row,
                220,
                True,
            )

        if (
            self.collected
            and int(
                now * 2
            )
            % 8
            == 0
        ):
            c.text(
                max(
                    1,
                    x - 3,
                ),
                max(
                    1,
                    y - 2,
                ),
                (
                    f"+{self.collected}"
                    " bolt"
                ),
                179,
            )


class PhantomTransmission:
    MESSAGES = [
        "GROUND WAS OPTIONAL, APPARENTLY.",
        "THE FUTURE FAILED ITS CONTINUITY TEST.",
        "NO FAULT FOUND. MORALE REPLACED.",
        "THE MACHINE DENIES KNOWING YOU.",
        "BAY 13 REQUESTS A BETTER BAY 13.",
        "MAINTENANCE REQUEST CLOSED BEFORE OPENING.",
        "SOMEONE LABELLED THE DARK CABLE 'SPARE'.",
        "THE PANEL HUMS IN A KEY NOT COVERED BY WARRANTY.",
        "SHIFT CHANGE DELAYED BY PHILOSOPHICAL DISPUTE WITH A RELAY.",
        "WHO SIGNED OFF ON GRAVITY IN THIS SECTION?",
        "AUX POWER REPORTS IT IS DOING ITS BEST.",
        "THE CORRIDOR MAP HAS FILED FOR INDEPENDENCE.",
        "PLEASE STOP NAMING THE FAULTS. THEY RESPOND TO IT.",
        "WE HAVE ISOLATED THE PROBLEM TO EVERYTHING AFTER TUESDAY.",
        "CHANNEL CLEAR. SITUATION LESS SO.",
        "THE RED LIGHT IS DECORATIVE UNTIL FURTHER NOTICE.",
        "BAY 13 HAS MOVED AGAIN.",
        "DO NOT TRUST A CONNECTOR THAT LOOKS CONFIDENT.",
        "THIS MESSAGE WAS NOT APPROVED BY MAINTENANCE.",
        "THE NIGHT SHIFT LEFT US A NOTE. IT JUST SAYS 'NO'.",
    ]

    def __init__(
        self,
        rng: random.Random,
    ) -> None:
        self.rng = rng

        self.state = "idle"
        self.timer = 0.0

        self.message = ""
        self.channel = ""

        self.strength = 0.0

        self.transmissions = 0

    @property
    def active(self) -> bool:
        return (
            self.state
            != "idle"
        )

    def trigger(
        self,
        context: Dict[
            str,
            bool,
        ],
    ) -> None:
        self.transmissions += 1

        contextual = []

        if context.get(
            "gremlin"
        ):
            contextual.append(
                "MAINT: SMALL UNIT OUT OF HATCH AGAIN. DO NOT ENCOURAGE IT."
            )

        if context.get(
            "hardware"
        ):
            contextual.append(
                "BAY 13 TO STORES: SEND BOLTS. APPARENTLY ALL OF THEM."
            )

        if context.get(
            "moths"
        ):
            contextual.append(
                "RELAY ROOM REPORTS MOTHS. RELAYS DECLINE COMMENT."
            )

        if context.get(
            "crawler"
        ):
            contextual.append(
                "UNREGISTERED CURRENT OBSERVED CRAWLING AGAINST THE ARROWS."
            )

        if context.get(
            "lift"
        ):
            contextual.append(
                "WHO AUTHORIZED THE LIFT? SECOND QUESTION: WHERE IS IT GOING?"
            )

        pool = (
            list(
                self.MESSAGES
            )
            + contextual * 2
        )

        self.message = (
            self.rng.choice(
                pool
            )
        )

        self.channel = (
            self.rng.choice(
                [
                    "BAY 13",
                    "AUX RADIO",
                    "MAINT CH-0?",
                    "SERVICE RETURN",
                    "LOCAL CARRIER",
                ]
            )
        )

        self.strength = (
            self.rng.uniform(
                0.35,
                0.98,
            )
        )

        self.state = (
            "acquire"
        )

        self.timer = 0.0

    def update(
        self,
        dt: float,
    ) -> None:
        if self.state == "idle":
            return

        self.timer += dt

        if (
            self.state
            == "acquire"
            and self.timer
            >= 1.0
        ):
            self.state = (
                "identify"
            )

            self.timer = 0.0

        elif (
            self.state
            == "identify"
            and self.timer
            >= 1.1
        ):
            self.state = (
                "message"
            )

            self.timer = 0.0

        elif (
            self.state
            == "message"
            and self.timer
            >= 5.5
        ):
            self.state = (
                "fade"
            )

            self.timer = 0.0

        elif (
            self.state
            == "fade"
            and self.timer
            >= 1.5
        ):
            self.state = "idle"
            self.timer = 0.0

    def _corrupt(
        self,
        text: str,
        intensity: float,
    ) -> str:
        if intensity <= 0:
            return text

        chars = list(text)

        # Stable for several frames rather than random TV static every frame.
        local = random.Random(
            int(
                self.timer * 8
            )
            + len(text) * 97
        )

        replacements = (
            "#?./:-_"
        )

        for i, ch in enumerate(
            chars
        ):
            if (
                ch != " "
                and local.random()
                < intensity
            ):
                chars[i] = (
                    local.choice(
                        replacements
                    )
                )

        return "".join(
            chars
        )

    def render(
        self,
        c: Canvas,
        stage: Stage,
    ) -> None:
        if self.state == "idle":
            return

        x = (
            stage.vlines[1]
            + 2
        )

        y = (
            stage.y_mid
            + 1
        )

        width = max(
            12,
            c.w - x - 3,
        )

        if (
            width < 12
            or y + 4
            >= c.h
        ):
            x = 2
            y = 2
            width = max(
                12,
                c.w - 4,
            )

        c.box(
            x,
            y,
            width,
            5,
            53,
        )

        if self.state == "acquire":
            dots = (
                "."
                * (
                    1
                    + int(
                        self.timer
                        * 5
                    )
                    % 6
                )
            )

            noise = self._corrupt(
                (
                    "carrier search"
                    " // wrong wire"
                    + dots
                ),
                0.18,
            )

            c.text(
                x + 2,
                y + 1,
                noise,
                244,
                max_width=(
                    width - 4
                ),
            )

            bars = int(
                clamp(
                    self.timer,
                    0,
                    1,
                )
                * 8
            )

            c.text(
                x + 2,
                y + 2,
                (
                    "SIGNAL "
                    + "|"
                    * bars
                    + "."
                    * (
                        8
                        - bars
                    )
                ),
                45,
                True,
            )

            return

        if self.state == "identify":
            c.text(
                x + 2,
                y + 1,
                self.channel,
                51,
                True,
                width - 4,
            )

            label = (
                "UNREGISTERED "
                "MAINTENANCE "
                "CHANNEL"
            )

            c.text(
                x + 2,
                y + 2,
                self._corrupt(
                    label,
                    (
                        1
                        - self.strength
                    )
                    * 0.12,
                ),
                45,
                False,
                width - 4,
            )

            c.text(
                x + 2,
                y + 3,
                (
                    "LOCK "
                    f"{int(self.strength * 100):02d}%"
                ),
                39,
            )

            return

        reveal = len(
            self.message
        )

        if self.state == "message":
            reveal = min(
                len(
                    self.message
                ),
                int(
                    self.timer
                    * 26
                ),
            )

        shown = (
            self.message[
                :reveal
            ]
        )

        corruption = (
            1
            - self.strength
        ) * (
            0.12
            if self.state
            == "message"
            else 0.03
        )

        shown = self._corrupt(
            shown,
            corruption,
        )

        fg = (
            51
            if self.state
            == "message"
            else 240
        )

        c.text(
            x + 2,
            y + 1,
            (
                self.channel
                + " // RX"
            ),
            fg,
            True,
            width - 4,
        )

        inner = (
            width - 4
        )

        c.text(
            x + 2,
            y + 2,
            shown[:inner],
            fg,
            False,
            inner,
        )

        if len(shown) > inner:
            c.text(
                x + 2,
                y + 3,
                shown[
                    inner:
                    inner * 2
                ],
                fg,
                False,
                inner,
            )


@dataclass
class Moth:
    x: float
    y: float

    vx: float
    vy: float

    target: int

    age: float
    ttl: float

    rest: float = 0.0


class RelayMoths:
    def __init__(
        self,
        rng: random.Random,
    ) -> None:
        self.rng = rng

        self.moths: List[
            Moth
        ] = []

        self.swarms = 0

        self.max_moths = 70

    @property
    def active(self) -> bool:
        return bool(
            self.moths
        )

    def trigger(
        self,
        stage: Stage,
    ) -> None:
        self.swarms += 1

        if not stage.lamps:
            return

        target = (
            self.rng.randrange(
                len(
                    stage.lamps
                )
            )
        )

        lx, ly = (
            stage.lamps[
                target
            ]
        )

        for _ in range(
            self.rng.randint(
                12,
                28,
            )
        ):
            angle = (
                self.rng.random()
                * math.tau
            )

            radius = (
                self.rng.uniform(
                    1,
                    8,
                )
            )

            self.moths.append(
                Moth(
                    x=(
                        lx
                        + math.cos(
                            angle
                        )
                        * radius
                    ),
                    y=(
                        ly
                        + math.sin(
                            angle
                        )
                        * radius
                        * 0.5
                    ),
                    vx=self.rng.uniform(
                        -2,
                        2,
                    ),
                    vy=self.rng.uniform(
                        -1,
                        1,
                    ),
                    target=target,
                    age=0,
                    ttl=self.rng.uniform(
                        12,
                        28,
                    ),
                )
            )

        self.moths = self.moths[
            -self.max_moths:
        ]

    def update(
        self,
        dt: float,
        stage: Stage,
        gremlin: Gremlin,
        achars: ACharField,
    ) -> None:
        alive: List[Moth] = []

        gx, gy = (
            gremlin.pos
        )

        for m in self.moths:
            m.age += dt

            if m.age >= m.ttl:
                continue

            if (
                m.target
                >= len(
                    stage.lamps
                )
            ):
                m.target = 0

            tx, ty = (
                stage.lamps[
                    m.target
                ]
            )

            dx = tx - m.x
            dy = ty - m.y

            dist = (
                math.hypot(
                    dx,
                    dy,
                )
                + 0.001
            )

            # Attraction + small tangential acceleration gives a crude orbit.
            ax = (
                dx / dist
                * 5.0
                + (
                    -dy / dist
                )
                * 2.4
            )

            ay = (
                dy / dist
                * 3.0
                + (
                    dx / dist
                )
                * 1.4
            )

            # Gremlin fright response.
            if gremlin.active:
                rgx = (
                    m.x - gx
                )

                rgy = (
                    m.y - gy
                )

                gd = (
                    math.hypot(
                        rgx,
                        rgy,
                    )
                    + 0.001
                )

                if gd < 9:
                    ax += (
                        rgx / gd
                        * (
                            26
                            / gd
                        )
                    )

                    ay += (
                        rgy / gd
                        * (
                            16
                            / gd
                        )
                    )

            # Lots of nearby aChars make the moths jitter away.
            disturbance = (
                achars.disturbance_near(
                    m.x,
                    m.y,
                    4,
                )
            )

            if disturbance:
                ax += (
                    self.rng.uniform(
                        -1,
                        1,
                    )
                    * disturbance
                )

                ay += (
                    self.rng.uniform(
                        -0.7,
                        0.7,
                    )
                    * disturbance
                )

            # Sometimes a moth lands near its lamp.
            if (
                dist < 1.6
                and self.rng.random()
                < 0.018
            ):
                m.rest = (
                    self.rng.uniform(
                        0.3,
                        1.4,
                    )
                )

            if m.rest > 0:
                m.rest -= dt

                m.vx *= 0.82
                m.vy *= 0.82

            else:
                m.vx = (
                    m.vx
                    + ax * dt
                    + self.rng.uniform(
                        -0.8,
                        0.8,
                    )
                    * dt
                ) * 0.985

                m.vy = (
                    m.vy
                    + ay * dt
                    + self.rng.uniform(
                        -0.5,
                        0.5,
                    )
                    * dt
                ) * 0.985

                if (
                    dist < 2
                    and self.rng.random()
                    < 0.012
                    and stage.lamps
                ):
                    m.target = (
                        self.rng.randrange(
                            len(
                                stage.lamps
                            )
                        )
                    )

            speed = (
                math.hypot(
                    m.vx,
                    m.vy,
                )
            )

            if speed > 8:
                m.vx *= (
                    8
                    / speed
                )

                m.vy *= (
                    8
                    / speed
                )

            m.x += (
                m.vx
                * dt
            )

            m.y += (
                m.vy
                * dt
            )

            m.x = clamp(
                m.x,
                1,
                stage.w - 2,
            )

            m.y = clamp(
                m.y,
                1,
                stage.h - 2,
            )

            alive.append(m)

        self.moths = alive

    def render(
        self,
        c: Canvas,
        now: float,
    ) -> None:
        glyphs = (
            ".",
            "^",
            "'",
            "v",
        )

        for i, m in enumerate(
            self.moths
        ):
            frame = (
                int(
                    now * 12
                    + i * 1.7
                )
                % len(
                    glyphs
                )
            )

            fg = (
                244,
                250,
                229,
                223,
            )[frame]

            c.put(
                int(
                    round(m.x)
                ),
                int(
                    round(m.y)
                ),
                glyphs[
                    frame
                ],
                fg,
                frame == 1,
            )


class CableCrawler:
    def __init__(
        self,
        rng: random.Random,
    ) -> None:
        self.rng = rng

        self.active = False

        self.route: List[
            Coord
        ] = []

        self.i = 0
        self.acc = 0.0

        self.tail: deque = deque(
            maxlen=18
        )

        self.trail: Dict[
            Coord,
            float,
        ] = {}

        self.hops_left = 0

        self.runs = 0

    @property
    def pos(self) -> Coord:
        if self.route:
            return self.route[
                min(
                    self.i,
                    len(
                        self.route
                    )
                    - 1,
                )
            ]

        return (
            0,
            0,
        )

    def trigger(
        self,
        stage: Stage,
    ) -> None:
        if not stage.graph_list:
            return

        self.runs += 1

        start = (
            self.rng.choice(
                stage.graph_list
            )
        )

        goal = (
            stage.far_random_node(
                self.rng,
                start,
                max(
                    15,
                    stage.w // 3,
                ),
            )
        )

        self.route = (
            stage.path(
                start,
                goal,
            )
        )

        self.i = 0
        self.acc = 0.0

        self.tail.clear()
        self.trail.clear()

        self.hops_left = (
            self.rng.randint(
                2,
                4,
            )
        )

        self.active = bool(
            self.route
        )

    def _continue(
        self,
        stage: Stage,
    ) -> None:
        start = self.pos

        goal = (
            stage.far_random_node(
                self.rng,
                start,
                max(
                    12,
                    stage.w // 4,
                ),
            )
        )

        self.route = (
            stage.path(
                start,
                goal,
            )
        )

        self.i = 0
        self.acc = 0.0

    def update(
        self,
        dt: float,
        stage: Stage,
        achars: ACharField,
    ) -> None:
        # Trails decay even after the crawler itself has left.
        for p in list(
            self.trail
        ):
            self.trail[p] -= dt

            if (
                self.trail[p]
                <= 0
            ):
                self.trail.pop(
                    p,
                    None,
                )

        if (
            not self.active
            or not self.route
        ):
            return

        self.acc += (
            dt * 18.0
        )

        while (
            self.acc
            >= 1.0
            and self.active
        ):
            self.acc -= 1.0

            p = self.route[
                self.i
            ]

            self.tail.appendleft(
                p
            )

            self.trail[p] = (
                self.rng.uniform(
                    0.35,
                    1.2,
                )
            )

            # The crawler "repairs" decorative broken wires.
            if p in stage.gaps:
                stage.mark_repaired(
                    p,
                    self.rng.uniform(
                        4,
                        9,
                    ),
                )

                achars.spawn_spark(
                    p[0],
                    p[1],
                    self.rng.randint(
                        1,
                        3,
                    ),
                )

            elif (
                self.rng.random()
                < 0.045
            ):
                achars.spawn_spark(
                    p[0],
                    p[1],
                    1,
                )

            if (
                self.i
                < len(
                    self.route
                )
                - 1
            ):
                self.i += 1

            else:
                if self.hops_left > 0:
                    self.hops_left -= 1

                    self._continue(
                        stage
                    )

                else:
                    self.active = False
                    break

    def render(
        self,
        c: Canvas,
    ) -> None:
        for (
            p,
            ttl,
        ) in self.trail.items():
            fg = (
                22
                if ttl < 0.5
                else 28
            )

            c.put(
                p[0],
                p[1],
                ".",
                fg,
            )

        if (
            not self.active
            or not self.route
        ):
            return

        tail = list(
            self.tail
        )

        for (
            j,
            (x, y),
        ) in enumerate(
            reversed(
                tail[:14]
            )
        ):
            fg = (
                22
                + min(
                    5,
                    j // 3,
                )
            )

            c.put(
                x,
                y,
                "=",
                fg,
            )

        x, y = self.pos

        c.put(
            x,
            y,
            "@",
            46,
            True,
        )


class MaintenanceLift:
    CARGO = [
        "[]",
        "<>",
        "##",
        "oo",
        "??",
        "//",
        "\\\\",
        "..",
        "!!",
        "--",
    ]

    def __init__(
        self,
        rng: random.Random,
    ) -> None:
        self.rng = rng

        self.state = "hidden"

        self.y = 0.0
        self.target_y = 0.0

        self.stops: List[
            int
        ] = []

        self.timer = 0.0

        self.cargo = "[]"
        self.caption = (
            "NO PERMIT"
        )

        self.rides = 0

        self.direction = -1

    @property
    def active(self) -> bool:
        return (
            self.state
            != "hidden"
        )

    def trigger(
        self,
        stage: Stage,
        gremlin: Gremlin,
    ) -> None:
        if self.active:
            # Repeated L presses add service stops rather than resetting it.
            candidates = [
                stage.y_top + 2,
                stage.y_mid,
                stage.y_bottom,
            ]

            self.stops.append(
                self.rng.choice(
                    candidates
                )
            )

            return

        self.rides += 1

        candidates = sorted(
            set(
                [
                    stage.y_top + 2,
                    stage.y_mid,
                    stage.y_bottom,
                    max(
                        stage.y_top + 2,
                        stage.h - 5,
                    ),
                ]
            )
        )

        count = self.rng.randint(
            1,
            min(
                3,
                len(
                    candidates
                ),
            ),
        )

        self.stops = (
            self.rng.sample(
                candidates,
                count,
            )
        )

        self.y = float(
            stage.h - 3
        )

        self.target_y = float(
            self.stops.pop(0)
        )

        self.direction = (
            sign(
                self.target_y
                - self.y
            )
            or -1
        )

        self.cargo = (
            self.rng.choice(
                self.CARGO
            )
        )

        # If the gremlin has been collecting bolts, one lift cargo variant
        # occasionally implies they entered the maintenance supply chain.
        if (
            gremlin.collected
            and self.rng.random()
            < 0.35
        ):
            self.cargo = "b+"

        self.caption = (
            self.rng.choice(
                [
                    "NO PERMIT",
                    "SERVICE?",
                    "B13 LIFT",
                    "NOT LISTED",
                ]
            )
        )

        self.state = "moving"
        self.timer = 0.0

    def update(
        self,
        dt: float,
        stage: Stage,
    ) -> None:
        if self.state == "hidden":
            return

        self.timer += dt

        if self.state == "moving":
            dy = (
                self.target_y
                - self.y
            )

            step = (
                sign(dy)
                * 8.0
                * dt
            )

            if (
                abs(step)
                >= abs(dy)
            ):
                self.y = (
                    self.target_y
                )

                self.state = (
                    "opening"
                )

                self.timer = 0.0

            else:
                self.y += step

            return

        if (
            self.state
            == "opening"
            and self.timer
            >= 0.65
        ):
            self.state = "dwell"
            self.timer = 0.0

        elif (
            self.state
            == "dwell"
            and self.timer
            >= 1.9
        ):
            self.state = (
                "closing"
            )

            self.timer = 0.0

        elif (
            self.state
            == "closing"
            and self.timer
            >= 0.65
        ):
            self.timer = 0.0

            if self.stops:
                self.target_y = float(
                    self.stops.pop(0)
                )

                self.direction = (
                    sign(
                        self.target_y
                        - self.y
                    )
                    or -1
                )

                self.state = (
                    "moving"
                )

            else:
                self.target_y = float(
                    stage.h - 3
                )

                self.direction = (
                    sign(
                        self.target_y
                        - self.y
                    )
                    or 1
                )

                self.state = (
                    "depart"
                )

        elif self.state == "depart":
            dy = (
                self.target_y
                - self.y
            )

            step = (
                sign(dy)
                * 9.0
                * dt
            )

            if (
                abs(step)
                >= abs(dy)
            ):
                self.state = (
                    "hidden"
                )

                self.timer = 0.0

            else:
                self.y += step

    def render(
        self,
        c: Canvas,
        stage: Stage,
    ) -> None:
        if self.state == "hidden":
            return

        x = stage.shaft_x

        y = int(
            round(
                self.y
            )
        )

        phase = 0

        if self.state in (
            "opening",
            "closing",
        ):
            phase = min(
                2,
                int(
                    self.timer
                    / 0.22
                ),
            )

            if (
                self.state
                == "closing"
            ):
                phase = (
                    2
                    - phase
                )

        elif self.state == "dwell":
            phase = 2

        doors = [
            "[||]",
            "[  ]",
            "<  >",
        ][phase]

        c.text(
            x - 2,
            y - 1,
            "+---+",
            208,
            True,
        )

        c.text(
            x - 2,
            y,
            doors.ljust(5),
            214,
            True,
        )

        c.text(
            x - 2,
            y + 1,
            "+---+",
            208,
            True,
        )

        if self.state == "dwell":
            c.text(
                x - 1,
                y,
                self.cargo[:2],
                229,
                True,
            )

            cap = self.caption

            c.text(
                max(
                    1,
                    x
                    - len(cap)
                    // 2,
                ),
                max(
                    1,
                    y - 2,
                ),
                cap,
                179,
            )


class AmbientScheduler:
    """
    Rare randomized automatic events.

    All six Easter eggs remain manually triggerable, but leaving the app alone
    lets the maintenance ecosystem occasionally misbehave on its own.
    """

    def __init__(
        self,
        rng: random.Random,
    ) -> None:
        self.rng = rng

        self.enabled = True

        self.next: Dict[
            str,
            float,
        ] = {}

        self.reset_all(
            time.monotonic(),
            soon=True,
        )

    def reset_all(
        self,
        now: float,
        soon: bool = False,
    ) -> None:
        ranges = {
            "g": (
                18,
                55,
            ),
            "b": (
                12,
                38,
            ),
            "t": (
                25,
                70,
            ),
            "m": (
                16,
                48,
            ),
            "c": (
                20,
                60,
            ),
            "l": (
                28,
                85,
            ),
        }

        for (
            k,
            (lo, hi),
        ) in ranges.items():
            if soon:
                lo = max(
                    4,
                    lo * 0.25,
                )

                hi = max(
                    7,
                    hi * 0.25,
                )

            self.next[k] = (
                now
                + self.rng.uniform(
                    lo,
                    hi,
                )
            )

    def due(
        self,
        now: float,
    ) -> List[str]:
        if not self.enabled:
            return []

        out = []

        ranges = {
            "g": (
                30,
                95,
            ),
            "b": (
                22,
                65,
            ),
            "t": (
                45,
                120,
            ),
            "m": (
                28,
                80,
            ),
            "c": (
                36,
                95,
            ),
            "l": (
                55,
                150,
            ),
        }

        for (
            k,
            when,
        ) in list(
            self.next.items()
        ):
            if now >= when:
                out.append(k)

                lo, hi = ranges[k]

                self.next[k] = (
                    now
                    + self.rng.uniform(
                        lo,
                        hi,
                    )
                )

        return out


class App:
    FPS = 20.0

    def __init__(self) -> None:
        self.rng = random.Random()

        self.rng.seed(
            time.time_ns()
            ^ os.getpid()
        )

        size = (
            shutil.get_terminal_size(
                (
                    110,
                    36,
                )
            )
        )

        self.w = max(
            20,
            size.columns,
        )

        self.h = max(
            12,
            size.lines,
        )

        self.stage = Stage(
            self.w,
            self.h,
        )

        self.achars = ACharField(
            self.rng
        )

        self.gremlin = Gremlin(
            self.rng
        )

        self.phantom = (
            PhantomTransmission(
                self.rng
            )
        )

        self.moths = RelayMoths(
            self.rng
        )

        self.crawler = (
            CableCrawler(
                self.rng
            )
        )

        self.lift = (
            MaintenanceLift(
                self.rng
            )
        )

        self.ambient = (
            AmbientScheduler(
                self.rng
            )
        )

        self.input = (
            InputReader()
        )

        self.help = False
        self.running = True

        self.last_size = (
            self.w,
            self.h,
        )

    def context(
        self,
    ) -> Dict[
        str,
        bool,
    ]:
        return {
            "gremlin": (
                self.gremlin.active
            ),
            "hardware": any(
                a.hardware
                for a
                in self.achars.items
            ),
            "moths": (
                self.moths.active
            ),
            "crawler": (
                self.crawler.active
            ),
            "lift": (
                self.lift.active
            ),
        }

    def trigger(
        self,
        key: str,
    ) -> None:
        if key == "g":
            self.gremlin.trigger(
                self.stage
            )

        elif key == "b":
            self.achars.trigger_hardware_spill(
                self.stage
            )

        elif key == "t":
            self.phantom.trigger(
                self.context()
            )

        elif key == "m":
            self.moths.trigger(
                self.stage
            )

        elif key == "c":
            self.crawler.trigger(
                self.stage
            )

        elif key == "l":
            self.lift.trigger(
                self.stage,
                self.gremlin,
            )

    def handle_key(
        self,
        key: str,
    ) -> None:
        # Ctrl-X always toggles the dedicated special-FX layer.
        if key == "\x18":
            self.achars.toggle_fx()
            return

        # While the FX layer is active its local controls take precedence.
        if self.achars.handle_fx_key(
            key,
            self.stage,
        ):
            return

        kl = key.lower()

        if kl == "q":
            self.running = False

        elif key == "?":
            self.help = (
                not self.help
            )

        elif kl == "a":
            self.ambient.enabled = (
                not self.ambient.enabled
            )

        elif kl == "r":
            self.trigger(
                self.rng.choice(
                    list(
                        "gbtmcl"
                    )
                )
            )

        elif kl in "gbtmcl":
            self.trigger(
                kl
            )

    def check_resize(
        self,
    ) -> None:
        size = (
            shutil.get_terminal_size(
                (
                    110,
                    36,
                )
            )
        )

        w = max(
            20,
            size.columns,
        )

        h = max(
            12,
            size.lines,
        )

        if (
            w,
            h,
        ) == self.last_size:
            return

        self.last_size = (
            w,
            h,
        )

        self.w = w
        self.h = h

        self.stage.rebuild(
            w,
            h,
        )

        # Geometry-dependent actors reset safely.
        self.gremlin.state = (
            "hidden"
        )

        self.crawler.active = False

        self.lift.state = (
            "hidden"
        )

        # Particle systems survive and are clipped into the new viewport.
        for a in self.achars.items:
            a.x = clamp(
                a.x,
                1,
                w - 2,
            )

            a.y = clamp(
                a.y,
                1,
                h - 2,
            )

        for m in self.moths.moths:
            m.x = clamp(
                m.x,
                1,
                w - 2,
            )

            m.y = clamp(
                m.y,
                1,
                h - 2,
            )

    def update(
        self,
        dt: float,
        now: float,
    ) -> None:
        for k in self.ambient.due(
            now
        ):
            self.trigger(k)

        self.achars.update(
            dt,
            self.stage,
        )

        self.gremlin.update(
            dt,
            self.stage,
            self.achars,
        )

        self.moths.update(
            dt,
            self.stage,
            self.gremlin,
            self.achars,
        )

        self.crawler.update(
            dt,
            self.stage,
            self.achars,
        )

        self.lift.update(
            dt,
            self.stage,
        )

        self.phantom.update(
            dt
        )

    def render_help(
        self,
        c: Canvas,
    ) -> None:
        w = min(
            c.w - 6,
            72,
        )

        h = min(
            c.h - 6,
            20,
        )

        x = max(
            2,
            (
                c.w - w
            )
            // 2,
        )

        y = max(
            2,
            (
                c.h - h
            )
            // 2,
        )

        c.box(
            x,
            y,
            w,
            h,
            159,
        )

        lines = [
            "HIDDEN MAINTENANCE ECOSYSTEM // OPERATOR CHEAT SHEET",
            "",
            "G  gremlin        B  loose hardware / aChar spill",
            "T  transmission   M  relay moths",
            "C  cable crawler  L  unauthorized lift",
            "R  random event   A  ambient auto-events on/off",
            "",
            "Ctrl-X  toggle aChar FX control layer",
            "  Space burst   +/- rate   [/] family",
            "  D direction  P palette  R randomise  Esc close",
            "",
            "The six systems are presentation-only. They share geometry and",
            "can react to each other, but there is no hidden application state.",
            "Resize is supported; geometry-bound creatures reset safely.",
            "",
            "? close help       Q quit",
        ]

        for (
            i,
            line,
        ) in enumerate(
            lines[
                :h - 2
            ]
        ):
            fg = (
                159
                if i == 0
                else 250
            )

            c.text(
                x + 2,
                y + 1 + i,
                line,
                fg,
                i == 0,
                w - 4,
            )

    def draw(
        self,
        now: float,
    ) -> str:
        c = Canvas(
            self.w,
            self.h,
        )

        # Shared stage first.
        self.stage.render(
            c,
            now,
            self.ambient.enabled,
        )

        # Order establishes a small visual z-stack.
        self.crawler.render(
            c
        )

        self.achars.render(
            c
        )

        self.moths.render(
            c,
            now,
        )

        self.lift.render(
            c,
            self.stage,
        )

        self.gremlin.render(
            c,
            self.stage,
            now,
        )

        self.phantom.render(
            c,
            self.stage,
        )

        if self.help:
            self.render_help(
                c
            )

        return c.render()

    def run(
        self,
    ) -> None:
        frame = (
            1.0
            / self.FPS
        )

        sys.stdout.write(
            ALT_ON
            + HIDE_CURSOR
            + CLEAR
            + HOME
        )

        sys.stdout.flush()

        last = (
            time.monotonic()
        )

        try:
            while self.running:
                start = (
                    time.monotonic()
                )

                self.check_resize()

                for key in (
                    self.input.read_keys()
                ):
                    self.handle_key(
                        key
                    )

                now = (
                    time.monotonic()
                )

                dt = min(
                    0.1,
                    max(
                        0.0,
                        now - last,
                    ),
                )

                last = now

                self.update(
                    dt,
                    now,
                )

                sys.stdout.write(
                    self.draw(
                        now
                    )
                )

                sys.stdout.flush()

                elapsed = (
                    time.monotonic()
                    - start
                )

                if elapsed < frame:
                    time.sleep(
                        frame
                        - elapsed
                    )

        except KeyboardInterrupt:
            pass

        finally:
            self.input.close()

            sys.stdout.write(
                RESET
                + SHOW_CURSOR
                + ALT_OFF
            )

            sys.stdout.flush()


def main() -> None:
    if not sys.stdout.isatty():
        print(
            "This program needs an interactive ANSI terminal.",
            file=sys.stderr,
        )

        raise SystemExit(2)

    App().run()


if __name__ == "__main__":
    main()