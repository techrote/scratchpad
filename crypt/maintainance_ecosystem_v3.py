#!/usr/bin/env python3
"""
MAINTENANCE ECOSYSTEM V3 // OVERDRIVE
=====================================

A standalone ANSI terminal toy containing twelve interacting cosmetic effects.
No PlasmaRack functionality. Dependency-free.

Main effects
------------
G  Robot gremlin
B  Loose hardware / aChar spill
T  Phantom maintenance transmission
M  Relay moth swarm
C  Cable crawler
L  Unauthorized maintenance lift
O  Ghost operator
F  Signal lichen
X  Arc storm
D  Maintenance drone (ARROW KEYS steer it)          [NEW]
V  Prismatic coolant leak                            [NEW]
Z  Diagnostic aurora / scanner storm                 [NEW]

Global
------
R       random effect
A       ambient automatic events on/off
Ctrl-X  aChar FX layer
Ctrl-Y  Moth FX layer                                [NEW LAYER]
?       help
Q       quit

Arrow-controlled drone
----------------------
D            deploy / recall drone
Arrow keys   thrust
Space        boost pulse
H            toggle autopilot/hold

When aChar FX layer is open
---------------------------
Space  burst
+/-    rate
[/]    family
D      emitter geometry
V      vector field
K      collision mode
P      palette phase
R      randomize
Esc    close

When Moth FX layer is open
--------------------------
Space  summon burst around beacon
+/-    swarm target population
[/]    visual formation
V      turbulence mode
P      colour phase
R      randomize
Esc    close

V3 design intent
----------------
* The terminal is treated as a shared tiny world rather than a pile of canned
  animations.
* Existing effects are composited in layers and react to one another.
* Relay moths now have a dedicated FX/control layer that can turn them from an
  easter egg into a manually sculpted animated visualizer.
* The new drone is directly steerable using arrow keys and leaves animated
  thruster/ion effects while disturbing nearby systems.
* The coolant leak and diagnostic aurora are deliberately large, colourful,
  high-motion effects intended to make the whole terminal feel alive.
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
from typing import Deque, Dict, Iterable, List, Optional, Sequence, Set, Tuple


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


def manhattan(a: Coord, b: Coord) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


class InputReader:
    """Nonblocking key reader with real arrow-key decoding."""

    def __init__(self) -> None:
        self.is_windows = os.name == "nt"

        self._old_term = None
        self._posix_buf = ""

        if self.is_windows:
            self._enable_windows_vt()

        else:
            import termios
            import tty

            self._termios = termios
            self._tty = tty

            if sys.stdin.isatty():
                self._old_term = termios.tcgetattr(
                    sys.stdin.fileno()
                )

                tty.setcbreak(
                    sys.stdin.fileno()
                )

    def _enable_windows_vt(self) -> None:
        try:
            import ctypes
            from ctypes import wintypes

            k32 = ctypes.windll.kernel32

            handle = k32.GetStdHandle(
                -11
            )

            mode = wintypes.DWORD()

            if k32.GetConsoleMode(
                handle,
                ctypes.byref(mode),
            ):
                k32.SetConsoleMode(
                    handle,
                    mode.value | 0x0004,
                )

        except Exception:
            pass

    def read_keys(self) -> List[str]:
        if self.is_windows:
            import msvcrt

            out: List[str] = []

            arrows = {
                "H": "UP",
                "P": "DOWN",
                "K": "LEFT",
                "M": "RIGHT",
            }

            while msvcrt.kbhit():
                ch = msvcrt.getwch()

                if ch in (
                    "\x00",
                    "\xe0",
                ):
                    if msvcrt.kbhit():
                        code = msvcrt.getwch()

                        mapped = arrows.get(
                            code
                        )

                        if mapped:
                            out.append(
                                mapped
                            )

                    continue

                out.append(
                    ch
                )

            return out

        import select

        fd = sys.stdin.fileno()

        chunks = []

        while True:
            ready, _, _ = select.select(
                [sys.stdin],
                [],
                [],
                0,
            )

            if not ready:
                break

            try:
                data = os.read(
                    fd,
                    64,
                )

            except OSError:
                break

            if not data:
                break

            chunks.append(
                data.decode(
                    "utf-8",
                    "ignore",
                )
            )

        if chunks:
            self._posix_buf += "".join(
                chunks
            )

        out: List[str] = []

        mapping = {
            "\x1b[A": "UP",
            "\x1b[B": "DOWN",
            "\x1b[C": "RIGHT",
            "\x1b[D": "LEFT",
        }

        while self._posix_buf:
            matched = False

            for seq, name in mapping.items():
                if self._posix_buf.startswith(
                    seq
                ):
                    out.append(
                        name
                    )

                    self._posix_buf = (
                        self._posix_buf[
                            len(seq):
                        ]
                    )

                    matched = True
                    break

            if matched:
                continue

            if (
                self._posix_buf.startswith(
                    "\x1b["
                )
                and
                len(
                    self._posix_buf
                ) < 3
            ):
                break

            out.append(
                self._posix_buf[0]
            )

            self._posix_buf = (
                self._posix_buf[1:]
            )

        return out

    def close(self) -> None:
        if (
            not self.is_windows
            and
            self._old_term is not None
        ):
            try:
                self._termios.tcsetattr(
                    sys.stdin.fileno(),
                    self._termios.TCSADRAIN,
                    self._old_term,
                )

            except Exception:
                pass


class Canvas:
    def __init__(
        self,
        w: int,
        h: int,
    ) -> None:
        self.w = w
        self.h = h

        n = w * h

        self.chars = [
            " "
        ] * n

        self.fg: List[
            Optional[int]
        ] = [
            None
        ] * n

        self.bold = [
            False
        ] * n

    def _i(
        self,
        x: int,
        y: int,
    ) -> int:
        return (
            y * self.w
            + x
        )

    def put(
        self,
        x: int,
        y: int,
        ch: str,
        fg: Optional[int] = None,
        bold: bool = False,
    ) -> None:
        if (
            0 <= x < self.w
            and
            0 <= y < self.h
            and ch
        ):
            i = self._i(
                x,
                y,
            )

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
        if not (
            0 <= y < self.h
        ):
            return

        if max_width is not None:
            s = s[
                :max(
                    0,
                    max_width,
                )
            ]

        for j, ch in enumerate(
            s
        ):
            self.put(
                x + j,
                y,
                ch,
                fg,
                bold,
            )

    def hline(
        self,
        x1: int,
        x2: int,
        y: int,
        ch: str = "-",
        fg: int = 240,
    ) -> None:
        if x2 < x1:
            x1, x2 = (
                x2,
                x1,
            )

        for x in range(
            max(
                0,
                x1,
            ),
            min(
                self.w - 1,
                x2,
            )
            + 1,
        ):
            self.put(
                x,
                y,
                ch,
                fg,
            )

    def vline(
        self,
        x: int,
        y1: int,
        y2: int,
        ch: str = "|",
        fg: int = 240,
    ) -> None:
        if y2 < y1:
            y1, y2 = (
                y2,
                y1,
            )

        for y in range(
            max(
                0,
                y1,
            ),
            min(
                self.h - 1,
                y2,
            )
            + 1,
        ):
            self.put(
                x,
                y,
                ch,
                fg,
            )

    def box(
        self,
        x: int,
        y: int,
        w: int,
        h: int,
        fg: int = 240,
    ) -> None:
        if (
            w < 2
            or
            h < 2
        ):
            return

        self.hline(
            x + 1,
            x + w - 2,
            y,
            "-",
            fg,
        )

        self.hline(
            x + 1,
            x + w - 2,
            y + h - 1,
            "-",
            fg,
        )

        self.vline(
            x,
            y + 1,
            y + h - 2,
            "|",
            fg,
        )

        self.vline(
            x + w - 1,
            y + 1,
            y + h - 2,
            "|",
            fg,
        )

        for px, py in (
            (
                x,
                y,
            ),
            (
                x + w - 1,
                y,
            ),
            (
                x,
                y + h - 1,
            ),
            (
                x + w - 1,
                y + h - 1,
            ),
        ):
            self.put(
                px,
                py,
                "+",
                fg,
            )

    def render(self) -> str:
        out = [
            SYNC_BEGIN,
            HOME,
        ]

        current_fg: Optional[int] = None
        current_bold = False

        for y in range(
            self.h
        ):
            for x in range(
                self.w
            ):
                i = self._i(
                    x,
                    y,
                )

                fg = self.fg[i]
                bold = self.bold[i]

                if (
                    fg != current_fg
                    or
                    bold != current_bold
                ):
                    if (
                        fg is None
                        and
                        not bold
                    ):
                        out.append(
                            RESET
                        )

                    else:
                        codes = []

                        if bold:
                            codes.append(
                                "1"
                            )

                        if fg is not None:
                            codes.append(
                                f"38;5;{fg}"
                            )

                        out.append(
                            ESC
                            + "["
                            + ";".join(
                                codes
                            )
                            + "m"
                        )

                    current_fg = fg
                    current_bold = bold

                out.append(
                    self.chars[i]
                )

            if y != self.h - 1:
                out.append(
                    "\n"
                )

        out.extend(
            (
                RESET,
                SYNC_END,
            )
        )

        return "".join(
            out
        )


class Stage:
    """Shared console geometry and graph topology."""

    def __init__(
        self,
        w: int,
        h: int,
    ) -> None:
        self.w = w
        self.h = h

        self.graph: Set[
            Coord
        ] = set()

        self.graph_list: List[
            Coord
        ] = []

        self.junctions: List[
            Coord
        ] = []

        self.control_nodes: List[
            Coord
        ] = []

        self.gaps: Set[
            Coord
        ] = set()

        self.repaired_until: Dict[
            Coord,
            float,
        ] = {}

        self.lamps: List[
            Coord
        ] = []

        self.vlines: List[
            int
        ] = []

        self.hlines: List[
            int
        ] = []

        self.hatch: Coord = (
            5,
            5,
        )

        self.shaft_x = 10

        self.rebuild(
            w,
            h,
        )

    def rebuild(
        self,
        w: int,
        h: int,
    ) -> None:
        self.w = w
        self.h = h

        self.graph.clear()
        self.repaired_until.clear()

        top = max(
            5,
            min(
                7,
                h - 10,
            ),
        )

        bottom = max(
            top + 8,
            h - 8,
        )

        mid = (
            top
            + bottom
        ) // 2

        self.hlines = sorted(
            set(
                (
                    top,
                    mid,
                    bottom,
                )
            )
        )

        x1 = max(
            18,
            w // 3,
        )

        x2 = min(
            w - 18,
            (
                2 * w
            )
            // 3,
        )

        if (
            x2
            <= x1 + 8
        ):
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
            top,
        )

        for y in self.hlines:
            for x in range(
                1,
                w - 1,
            ):
                self.graph.add(
                    (
                        x,
                        y,
                    )
                )

        for x in self.vlines:
            for y in range(
                top,
                h - 1,
            ):
                self.graph.add(
                    (
                        x,
                        y,
                    )
                )

        branch_y = min(
            h - 3,
            mid + 4,
        )

        branch_x = min(
            x2 - 2,
            x1 + 5,
        )

        for x in range(
            x1,
            x2 + 1,
        ):
            self.graph.add(
                (
                    x,
                    branch_y,
                )
            )

        for y in range(
            top,
            branch_y + 1,
        ):
            self.graph.add(
                (
                    branch_x,
                    y,
                )
            )

        for y in (
            top + 3,
            bottom - 3,
        ):
            if (
                1 < y < h - 1
            ):
                for x in range(
                    max(
                        2,
                        x1 - 8,
                    ),
                    min(
                        w - 2,
                        x1 + 9,
                    ),
                ):
                    self.graph.add(
                        (
                            x,
                            y,
                        )
                    )

        # Extra lower service loop.
        loop_left = max(
            3,
            x1 - 12,
        )

        loop_right = min(
            w - 4,
            x2 + 12,
        )

        loop_y = min(
            h - 4,
            bottom + 3,
        )

        if loop_y > bottom:
            for x in range(
                loop_left,
                loop_right + 1,
            ):
                self.graph.add(
                    (
                        x,
                        loop_y,
                    )
                )

            for y in range(
                bottom,
                loop_y + 1,
            ):
                self.graph.add(
                    (
                        loop_left,
                        y,
                    )
                )

                self.graph.add(
                    (
                        loop_right,
                        y,
                    )
                )

        candidates = [
            (
                min(
                    w - 3,
                    x1 + 7,
                ),
                mid,
            ),

            (
                max(
                    2,
                    x2 - 9,
                ),
                bottom,
            ),

            (
                x2,
                min(
                    h - 3,
                    mid + 3,
                ),
            ),

            (
                max(
                    2,
                    x1 - 4,
                ),
                top + 3,
            ),
        ]

        self.gaps = {
            p
            for p
            in candidates
            if p in self.graph
        }

        self.graph_list = sorted(
            self.graph
        )

        self.junctions = [
            p
            for p
            in self.graph_list
            if sum(
                1
                for _
                in self.neighbors(
                    p
                )
            )
            >= 3
        ]

        if (
            not self.junctions
            and
            self.graph_list
        ):
            stride = max(
                1,
                len(
                    self.graph_list
                )
                // 12,
            )

            self.junctions = (
                self.graph_list[
                    ::stride
                ]
            )

        self.lamps = [
            (
                max(
                    3,
                    x1 - 5,
                ),
                max(
                    2,
                    top - 3,
                ),
            ),

            (
                min(
                    w - 4,
                    x1 + 8,
                ),
                max(
                    2,
                    top - 3,
                ),
            ),

            (
                min(
                    w - 4,
                    x2 + 7,
                ),
                max(
                    2,
                    top - 3,
                ),
            ),

            (
                max(
                    3,
                    x1 - 6,
                ),
                min(
                    h - 3,
                    bottom + 3,
                ),
            ),

            (
                min(
                    w - 4,
                    x2 + 8,
                ),
                min(
                    h - 3,
                    bottom + 3,
                ),
            ),
        ]

        self.control_nodes = []

        for x, y in self.lamps:
            self.control_nodes += [
                (
                    x,
                    y,
                ),
                (
                    int(
                        clamp(
                            x + 2,
                            2,
                            w - 3,
                        )
                    ),
                    y,
                ),
            ]

        stride = (
            max(
                1,
                len(
                    self.junctions
                )
                // 10,
            )
            if self.junctions
            else 1
        )

        self.control_nodes += (
            self.junctions[
                ::stride
            ]
        )

    def neighbors(
        self,
        p: Coord,
    ) -> Iterable[
        Coord
    ]:
        x, y = p

        for q in (
            (
                x + 1,
                y,
            ),
            (
                x - 1,
                y,
            ),
            (
                x,
                y + 1,
            ),
            (
                x,
                y - 1,
            ),
        ):
            if q in self.graph:
                yield q

    def path(
        self,
        start: Coord,
        goal: Coord,
    ) -> List[
        Coord
    ]:
        if (
            start
            not in self.graph
            or
            goal
            not in self.graph
        ):
            return []

        q: Deque[
            Coord
        ] = deque(
            [
                start
            ]
        )

        prev: Dict[
            Coord,
            Optional[Coord],
        ] = {
            start: None
        }

        while q:
            p = q.popleft()

            if p == goal:
                break

            for n in self.neighbors(
                p
            ):
                if (
                    n
                    not in prev
                ):
                    prev[n] = p
                    q.append(
                        n
                    )

        if goal not in prev:
            return []

        out: List[
            Coord
        ] = []

        p: Optional[
            Coord
        ] = goal

        while p is not None:
            out.append(
                p
            )

            p = prev[p]

        out.reverse()

        return out

    def far_node(
        self,
        rng: random.Random,
        start: Coord,
        min_dist: int = 16,
    ) -> Coord:
        far = [
            p
            for p
            in self.graph_list
            if manhattan(
                p,
                start,
            )
            >= min_dist
        ]

        return rng.choice(
            far
            or self.graph_list
            or [
                start
            ]
        )

    def nearest_graph(
        self,
        p: Coord,
    ) -> Coord:
        if not self.graph_list:
            return p

        return min(
            self.graph_list,
            key=lambda q: manhattan(
                p,
                q,
            ),
        )

    def mark_repaired(
        self,
        p: Coord,
        seconds: float = 7.0,
    ) -> None:
        if p in self.gaps:
            self.repaired_until[
                p
            ] = (
                time.monotonic()
                + seconds
            )

    def is_repaired(
        self,
        p: Coord,
        now: float,
    ) -> bool:
        until = (
            self.repaired_until.get(
                p,
                0.0,
            )
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

        c.text(
            2,
            0,
            (
                " MAINTENANCE ECOSYSTEM V3 "
                "// OVERDRIVE "
                "// PRESENTATION LAYER ONLY "
            )[
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
                self.hlines[0],
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

        branch_y = min(
            h - 3,
            self.hlines[1] + 4,
        )

        branch_x = min(
            self.vlines[1] - 2,
            self.vlines[0] + 5,
        )

        c.hline(
            self.vlines[0],
            self.vlines[1],
            branch_y,
            "-",
            237,
        )

        c.vline(
            branch_x,
            self.hlines[0],
            branch_y,
            "|",
            237,
        )

        loop_left = max(
            3,
            self.vlines[0] - 12,
        )

        loop_right = min(
            w - 4,
            self.vlines[1] + 12,
        )

        loop_y = min(
            h - 4,
            self.hlines[2] + 3,
        )

        if loop_y > self.hlines[2]:
            c.hline(
                loop_left,
                loop_right,
                loop_y,
                "=",
                236,
            )

            c.vline(
                loop_left,
                self.hlines[2],
                loop_y,
                ":",
                236,
            )

            c.vline(
                loop_right,
                self.hlines[2],
                loop_y,
                ":",
                236,
            )

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
                )

        labels = [
            (
                2,
                2,
                "AUX MAINT // ALL ERRORS COSMETIC",
            ),

            (
                self.vlines[0] + 2,
                2,
                "BAY 13 // SIGNAL ETIQUETTE OPTIONAL",
            ),

            (
                self.vlines[1] + 2,
                2,
                "DRONE PERMIT: RETROACTIVELY DENIED",
            ),

            (
                2,
                self.hlines[0] + 2,
                "loose hardware / live fauna",
            ),

            (
                self.vlines[0] + 2,
                self.hlines[0] + 2,
                "moth manifold // ctrl-y",
            ),

            (
                self.vlines[1] + 2,
                self.hlines[0] + 2,
                "coolant colour: implausible",
            ),
        ]

        for x, y, s in labels:
            c.text(
                x,
                y,
                s,
                242,
                max_width=max(
                    0,
                    w - x - 2,
                ),
            )

        for i, (
            x,
            y,
        ) in enumerate(
            self.lamps
        ):
            pulse = int(
                now
                * (
                    2.2
                    + i * 0.19
                )
            ) % 6

            fg = (
                82,
                83,
                119,
                120,
                156,
                229,
            )[pulse]

            glyph = (
                "o",
                "o",
                "O",
                "o",
                "*",
                "o",
            )[pulse]

            c.put(
                x,
                y,
                glyph,
                fg,
                pulse in (
                    2,
                    4,
                ),
            )

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

        for y in range(
            self.hlines[0] + 1,
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
            f"{'ON' if ambient else 'OFF'}  "
            "G/B/T/M/C/L/O/F/X/D/V/Z effects  "
            "Ctrl-X aChar  Ctrl-Y moth FX  "
            "? help  Q quit "
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

    frames: Tuple[
        str,
        ...
    ]

    palette: Tuple[
        int,
        ...
    ]

    fps: float

    gravity: float = 0.0
    drag: float = 0.995

    trail: str = "."


@dataclass
class AChar:
    x: float
    y: float

    vx: float
    vy: float

    kind: int
    ttl: float

    age: float = 0.0
    phase: float = 0.0

    hardware: bool = False
    settled: bool = False

    bounces: int = 0

    charge: float = 0.0

    trail: Deque[
        Coord
    ] = field(
        default_factory=lambda: deque(
            maxlen=12
        )
    )


class ACharField:
    def __init__(
        self,
        rng: random.Random,
    ) -> None:
        self.rng = rng

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
                11,
                12.0,
                .994,
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
                8,
                10.0,
                .993,
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
                13,
                11.0,
                .994,
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
                20,
                1.8,
                .985,
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
                .998,
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
                .999,
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
                .999,
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
                10,
                0.0,
                .999,
                ".",
            ),

            ACharKind(
                "bubble",
                (
                    ".",
                    "o",
                    "O",
                    "o",
                ),
                (
                    33,
                    39,
                    45,
                    51,
                ),
                9,
                -1.2,
                .996,
                ".",
            ),

            ACharKind(
                "needle",
                (
                    "'",
                    "|",
                    "!",
                    "|",
                ),
                (
                    196,
                    202,
                    208,
                    214,
                ),
                17,
                0.0,
                .999,
                "'",
            ),

            ACharKind(
                "plasma",
                (
                    "~",
                    "*",
                    "~",
                    "+",
                ),
                (
                    201,
                    207,
                    213,
                    219,
                    225,
                ),
                22,
                0.0,
                .997,
                ".",
            ),

            ACharKind(
                "cinder",
                (
                    ".",
                    ":",
                    "*",
                    ".",
                ),
                (
                    208,
                    214,
                    220,
                    226,
                ),
                14,
                -0.4,
                .992,
                "'",
            ),
        ]

        self.items: List[
            AChar
        ] = []

        self.fx_mode = False

        self.spawn_rate = 7.0
        self.spawn_acc = 0.0

        self.selected_kind = 4

        self.direction_i = 4
        self.field_i = 0
        self.collision_i = 0

        self.palette_phase = 0

        self.max_items = 340

        self.directions = [
            "DOWN",
            "UP",
            "LEFT",
            "RIGHT",
            "MIXED",
            "RADIAL",
            "RING",
            "LINE",
            "CORNERS",
        ]

        self.fields = [
            "NONE",
            "SWIRL",
            "SHEAR",
            "WAVE",
            "ATTRACT",
            "REPEL",
            "VORTEX",
        ]

        self.collisions = [
            "WRAP",
            "REFLECT",
            "DAMP",
        ]

    def toggle_fx(self) -> None:
        self.fx_mode = (
            not self.fx_mode
        )

    def add(
        self,
        a: AChar,
    ) -> None:
        if (
            len(
                self.items
            )
            >= self.max_items
        ):
            self.items.pop(
                0
            )

        self.items.append(
            a
        )

    def spawn_spark(
        self,
        x: float,
        y: float,
        count: int = 2,
    ) -> None:
        for _ in range(
            count
        ):
            self.add(
                AChar(
                    x,
                    y,

                    self.rng.uniform(
                        -6,
                        6,
                    ),

                    self.rng.uniform(
                        -5,
                        1,
                    ),

                    3,

                    self.rng.uniform(
                        .45,
                        1.5,
                    ),

                    phase=(
                        self.rng.random()
                        * 3
                    ),
                )
            )

    def spill(
        self,
        stage: Stage,
    ) -> None:
        origins = [
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

        for _ in range(
            self.rng.randint(
                10,
                22,
            )
        ):
            x = (
                self.rng.choice(
                    origins
                )
                + self.rng.uniform(
                    -4,
                    4,
                )
            )

            kind = self.rng.choice(
                (
                    0,
                    0,
                    0,
                    1,
                    2,
                    2,
                    3,
                )
            )

            self.add(
                AChar(
                    clamp(
                        x,
                        2,
                        stage.w - 3,
                    ),

                    self.rng.uniform(
                        1,
                        max(
                            2,
                            stage.hlines[0]
                            - 1,
                        ),
                    ),

                    self.rng.uniform(
                        -4.2,
                        4.2,
                    ),

                    self.rng.uniform(
                        -2.5,
                        2.0,
                    ),

                    kind,

                    self.rng.uniform(
                        10,
                        25,
                    ),

                    phase=(
                        self.rng.random()
                        * 8
                    ),

                    hardware=(
                        kind
                        in (
                            0,
                            1,
                            2,
                        )
                    ),
                )
            )

    def _spawn_fx(
        self,
        stage: Stage,
    ) -> None:
        mode = (
            self.directions[
                self.direction_i
            ]
        )

        speed = self.rng.uniform(
            4.0,
            14.0,
        )

        x = self.rng.uniform(
            2,
            max(
                3,
                stage.w - 3,
            ),
        )

        y = self.rng.uniform(
            2,
            max(
                3,
                stage.h - 3,
            ),
        )

        vx = 0.0
        vy = 0.0

        if mode == "DOWN":
            y = 2
            vy = speed

        elif mode == "UP":
            y = stage.h - 3
            vy = -speed

        elif mode == "LEFT":
            x = stage.w - 3
            vx = -speed

        elif mode == "RIGHT":
            x = 2
            vx = speed

        elif mode == "RADIAL":
            x = stage.w / 2
            y = stage.h / 2

            a = (
                self.rng.random()
                * math.tau
            )

            vx = (
                math.cos(
                    a
                )
                * speed
            )

            vy = (
                math.sin(
                    a
                )
                * speed
                * .55
            )

        elif mode == "RING":
            a = (
                self.rng.random()
                * math.tau
            )

            r = (
                min(
                    stage.w,
                    stage.h * 2,
                )
                * .28
            )

            x = (
                stage.w / 2
                + math.cos(
                    a
                )
                * r
            )

            y = (
                stage.h / 2
                + math.sin(
                    a
                )
                * r
                * .5
            )

            vx = (
                -math.sin(
                    a
                )
                * speed
            )

            vy = (
                math.cos(
                    a
                )
                * speed
                * .45
            )

        elif mode == "LINE":
            y = self.rng.choice(
                stage.hlines
            )

            x = self.rng.uniform(
                2,
                stage.w - 3,
            )

            vx = (
                self.rng.choice(
                    (
                        -1,
                        1,
                    )
                )
                * speed
            )

        elif mode == "CORNERS":
            x, y = self.rng.choice(
                (
                    (
                        2,
                        2,
                    ),
                    (
                        stage.w - 3,
                        2,
                    ),
                    (
                        2,
                        stage.h - 3,
                    ),
                    (
                        stage.w - 3,
                        stage.h - 3,
                    ),
                )
            )

            tx = stage.w / 2
            ty = stage.h / 2

            d = (
                math.hypot(
                    tx - x,
                    ty - y,
                )
                + .001
            )

            vx = (
                (
                    tx - x
                )
                / d
                * speed
            )

            vy = (
                (
                    ty - y
                )
                / d
                * speed
                * .7
            )

        else:
            a = (
                self.rng.random()
                * math.tau
            )

            vx = (
                math.cos(
                    a
                )
                * speed
            )

            vy = (
                math.sin(
                    a
                )
                * speed
                * .55
            )

        self.add(
            AChar(
                x,
                y,
                vx,
                vy,

                self.selected_kind,

                self.rng.uniform(
                    6,
                    18,
                ),

                phase=(
                    self.rng.random()
                    * 5
                ),
            )
        )

    def burst(
        self,
        stage: Stage,
        count: int = 36,
    ) -> None:
        for _ in range(
            count
        ):
            self._spawn_fx(
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

        k = (
            key.lower()
            if len(key) == 1
            else key
        )

        if key == " ":
            self.burst(
                stage
            )

        elif key in (
            "+",
            "=",
        ):
            self.spawn_rate = min(
                80.0,
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

        elif k == "d":
            self.direction_i = (
                self.direction_i
                + 1
            ) % len(
                self.directions
            )

        elif k == "v":
            self.field_i = (
                self.field_i
                + 1
            ) % len(
                self.fields
            )

        elif k == "k":
            self.collision_i = (
                self.collision_i
                + 1
            ) % len(
                self.collisions
            )

        elif k == "p":
            self.palette_phase = (
                self.palette_phase
                + 1
            ) % 96

        elif k == "r":
            self.selected_kind = (
                self.rng.randrange(
                    len(
                        self.kinds
                    )
                )
            )

            self.direction_i = (
                self.rng.randrange(
                    len(
                        self.directions
                    )
                )
            )

            self.field_i = (
                self.rng.randrange(
                    len(
                        self.fields
                    )
                )
            )

            self.collision_i = (
                self.rng.randrange(
                    len(
                        self.collisions
                    )
                )
            )

            self.spawn_rate = (
                self.rng.uniform(
                    3,
                    35,
                )
            )

            self.palette_phase = (
                self.rng.randrange(
                    96
                )
            )

        else:
            return False

        return True

    def charge_near(
        self,
        x: float,
        y: float,
        radius: float = 7.0,
        amount: float = 1.0,
    ) -> None:
        r2 = (
            radius
            * radius
        )

        for a in self.items:
            if (
                (
                    a.x - x
                )
                ** 2
                +
                (
                    a.y - y
                )
                ** 2
                <= r2
            ):
                a.charge = max(
                    a.charge,
                    amount,
                )

                a.vx += (
                    self.rng.uniform(
                        -2,
                        2,
                    )
                    * amount
                )

                a.vy += (
                    self.rng.uniform(
                        -1,
                        1,
                    )
                    * amount
                )

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
                and
                a.settled
                and
                abs(
                    a.x - x
                )
                +
                abs(
                    a.y - y
                )
                <= radius
            ):
                collected += 1

            else:
                kept.append(
                    a
                )

        self.items = kept

        return collected

    def nearest_settled_hardware(
        self,
        p: Coord,
        max_d: int = 45,
    ) -> Optional[
        Coord
    ]:
        best = None
        bd = max_d + 1

        for a in self.items:
            if not (
                a.hardware
                and
                a.settled
            ):
                continue

            q = (
                int(
                    round(
                        a.x
                    )
                ),
                int(
                    round(
                        a.y
                    )
                ),
            )

            d = manhattan(
                p,
                q,
            )

            if d < bd:
                best = q
                bd = d

        return best

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

        return float(
            sum(
                1
                for a
                in self.items
                if (
                    (
                        a.x - x
                    )
                    ** 2
                    +
                    (
                        a.y - y
                    )
                    ** 2
                    <= r2
                )
            )
        )

    def _apply_field(
        self,
        a: AChar,
        dt: float,
        stage: Stage,
        now: float,
    ) -> None:
        mode = (
            self.fields[
                self.field_i
            ]
        )

        cx = stage.w / 2
        cy = stage.h / 2

        dx = a.x - cx
        dy = (
            a.y - cy
        ) * 1.8

        r = (
            math.hypot(
                dx,
                dy,
            )
            + .001
        )

        if mode == "SWIRL":
            a.vx += (
                -dy / r
                * 4
                * dt
            )

            a.vy += (
                dx / r
                * 2
                * dt
            )

        elif mode == "SHEAR":
            a.vx += (
                math.sin(
                    a.y * .23
                    + now * 1.2
                )
                * 3
                * dt
            )

        elif mode == "WAVE":
            a.vy += (
                math.sin(
                    a.x * .17
                    + now * 2.0
                )
                * 2.5
                * dt
            )

        elif mode == "ATTRACT":
            a.vx += (
                -dx / r
                * 4.5
                * dt
            )

            a.vy += (
                -dy / r
                * 2.2
                * dt
            )

        elif mode == "REPEL":
            a.vx += (
                dx / r
                * 4.5
                * dt
            )

            a.vy += (
                dy / r
                * 2.2
                * dt
            )

        elif mode == "VORTEX":
            a.vx += (
                (
                    -dy / r
                    * 8
                )
                -
                (
                    dx / r
                    * 1.5
                )
            ) * dt

            a.vy += (
                (
                    dx / r
                    * 4
                )
                -
                (
                    dy / r
                    * .8
                )
            ) * dt

    def update(
        self,
        dt: float,
        stage: Stage,
        now: float,
    ) -> None:
        if (
            self.fx_mode
            and
            self.spawn_rate > 0
        ):
            self.spawn_acc += (
                dt
                * self.spawn_rate
            )

            while (
                self.spawn_acc
                >= 1
            ):
                self.spawn_acc -= 1

                self._spawn_fx(
                    stage
                )

        alive: List[
            AChar
        ] = []

        for a in self.items:
            a.age += dt

            if a.age >= a.ttl:
                continue

            a.charge = max(
                0.0,
                a.charge
                - dt * .6,
            )

            if a.settled:
                alive.append(
                    a
                )

                continue

            a.trail.appendleft(
                (
                    int(
                        round(
                            a.x
                        )
                    ),
                    int(
                        round(
                            a.y
                        )
                    ),
                )
            )

            kind = (
                self.kinds[
                    a.kind
                ]
            )

            self._apply_field(
                a,
                dt,
                stage,
                now,
            )

            a.vy += (
                kind.gravity
                * dt
            )

            a.vx *= kind.drag
            a.vy *= kind.drag

            old_y = a.y

            a.x += (
                a.vx
                * dt
            )

            a.y += (
                a.vy
                * dt
            )

            if (
                a.hardware
                and
                a.vy > 0
            ):
                for level in (
                    list(
                        stage.hlines
                    )
                    +
                    [
                        stage.h - 2
                    ]
                ):
                    if (
                        old_y
                        < level
                        <= a.y
                    ):
                        a.y = (
                            level - 1
                        )

                        a.vy = (
                            -abs(
                                a.vy
                            )
                            * self.rng.uniform(
                                .22,
                                .48,
                            )
                        )

                        a.vx *= .72

                        a.bounces += 1

                        if (
                            abs(
                                a.vy
                            ) < 1
                            or
                            a.bounces >= 4
                        ):
                            a.settled = True
                            a.vx = 0
                            a.vy = 0

                        break

            if not a.hardware:
                collision = (
                    self.collisions[
                        self.collision_i
                    ]
                )

                if collision == "WRAP":
                    if a.x < 1:
                        a.x = (
                            stage.w - 2
                        )

                    elif (
                        a.x
                        > stage.w - 2
                    ):
                        a.x = 1

                    if a.y < 1:
                        a.y = (
                            stage.h - 2
                        )

                    elif (
                        a.y
                        > stage.h - 2
                    ):
                        a.y = 1

                else:
                    damp = (
                        .92
                        if collision
                        == "REFLECT"
                        else .55
                    )

                    if (
                        a.x < 1
                        or
                        a.x
                        > stage.w - 2
                    ):
                        a.x = clamp(
                            a.x,
                            1,
                            stage.w - 2,
                        )

                        a.vx = (
                            -a.vx
                            * damp
                        )

                    if (
                        a.y < 1
                        or
                        a.y
                        > stage.h - 2
                    ):
                        a.y = clamp(
                            a.y,
                            1,
                            stage.h - 2,
                        )

                        a.vy = (
                            -a.vy
                            * damp
                        )

            else:
                a.x = clamp(
                    a.x,
                    1,
                    stage.w - 2,
                )

                if a.y > stage.h - 2:
                    a.y = (
                        stage.h - 2
                    )

                    a.settled = True

            alive.append(
                a
            )

        self.items = alive

    def render(
        self,
        c: Canvas,
    ) -> None:
        for a in self.items:
            kind = (
                self.kinds[
                    a.kind
                ]
            )

            for j, (
                tx,
                ty,
            ) in enumerate(
                list(
                    a.trail
                )[1:7],
                start=1,
            ):
                if not a.settled:
                    c.put(
                        tx,
                        ty,
                        kind.trail,
                        236
                        + min(
                            5,
                            j,
                        ),
                    )

            frame = int(
                (
                    a.age
                    + a.phase
                )
                * kind.fps
            ) % len(
                kind.frames
            )

            fg = (
                kind.palette[
                    (
                        frame
                        + self.palette_phase
                    )
                    % len(
                        kind.palette
                    )
                ]
            )

            if a.charge > 0:
                fg = (
                    51,
                    87,
                    123,
                    159,
                    195,
                    201,
                    207,
                )[
                    int(
                        a.charge
                        * 11
                    )
                    % 7
                ]

            c.put(
                int(
                    round(
                        a.x
                    )
                ),
                int(
                    round(
                        a.y
                    )
                ),
                kind.frames[
                    frame
                ],
                fg,
                (
                    a.charge > .35
                    or
                    (
                        a.hardware
                        and
                        a.settled
                    )
                ),
            )

        if self.fx_mode:
            s = (
                " aCHAR FX :: "
                f"{self.kinds[self.selected_kind].name:<8} "
                f"emit={self.directions[self.direction_i]:<7} "
                f"field={self.fields[self.field_i]:<7} "
                f"coll={self.collisions[self.collision_i]:<7} "
                f"rate={self.spawn_rate:04.1f}/s  "
                "[ ] type "
                "D emit "
                "V field "
                "K coll "
                "P palette "
                "+/- rate "
                "Space burst "
                "R random "
                "Esc "
            )

            c.text(
                2,
                max(
                    1,
                    c.h - 3,
                ),
                s[
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

        self.i = 0
        self.acc = 0.0

        self.pos: Coord = (
            0,
            0,
        )

        self.facing = "right"

        self.journeys = 0
        self.collected = 0

        self.mood = "curious"

        self.ride_offset = 0

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
            self.journeys += 1

            self.mood = (
                self.rng.choice(
                    (
                        "curious",
                        "busy",
                        "suspicious",
                        "delighted",
                        "feral",
                    )
                )
            )

            return

        self.state = "opening"

        self.timer = 0.0

        self.pos = stage.hatch

        self.journeys = (
            self.rng.randint(
                4,
                8,
            )
        )

    def _route_to(
        self,
        stage: Stage,
        goal: Coord,
    ) -> None:
        start = (
            self.pos
            if self.pos
            in stage.graph
            else stage.hatch
        )

        if goal not in stage.graph:
            goal = stage.nearest_graph(
                goal
            )

        self.route = (
            stage.path(
                start,
                goal,
            )
            or [
                start
            ]
        )

        self.i = 0
        self.acc = 0.0

    def _choose_goal(
        self,
        stage: Stage,
        achars: ACharField,
    ) -> Coord:
        hardware = (
            achars.nearest_settled_hardware(
                self.pos
            )
        )

        if (
            hardware
            and
            self.rng.random()
            < .74
        ):
            self.mood = (
                "salvaging"
            )

            return hardware

        self.mood = (
            self.rng.choice(
                (
                    "curious",
                    "busy",
                    "suspicious",
                    "delighted",
                    "inspecting",
                )
            )
        )

        return stage.far_node(
            self.rng,
            self.pos,
            max(
                12,
                stage.w // 4,
            ),
        )

    def update(
        self,
        dt: float,
        stage: Stage,
        achars: ACharField,
        lift: "MaintenanceLift",
        drone: "MaintenanceDrone",
    ) -> None:
        if self.state == "hidden":
            return

        self.timer += dt

        if self.state == "opening":
            if self.timer >= .8:
                self.state = (
                    "explore"
                )

                self.timer = 0.0

                self._route_to(
                    stage,
                    self._choose_goal(
                        stage,
                        achars,
                    ),
                )

            return

        if self.state == "closing":
            if self.timer >= .7:
                self.state = "hidden"
                self.timer = 0.0

            return

        if self.state == "nap":
            if (
                self.timer
                >= self.rng.uniform(
                    .6,
                    1.5,
                )
            ):
                self.timer = 0.0

                if self.journeys > 0:
                    self.journeys -= 1
                    self.state = "explore"

                    self._route_to(
                        stage,
                        self._choose_goal(
                            stage,
                            achars,
                        ),
                    )

                else:
                    self.state = "return"

                    self._route_to(
                        stage,
                        stage.hatch,
                    )

            return

        if (
            drone.active
            and
            self.state == "explore"
        ):
            if (
                manhattan(
                    self.pos,
                    (
                        int(
                            drone.x
                        ),
                        int(
                            drone.y
                        ),
                    ),
                )
                <= 3
                and
                self.rng.random()
                < .015
            ):
                self.mood = (
                    "judging drone"
                )

        if (
            lift.active
            and
            self.state == "explore"
        ):
            lx = stage.shaft_x

            ly = int(
                round(
                    lift.y
                )
            )

            if (
                abs(
                    self.pos[0]
                    - lx
                )
                <= 2
                and
                abs(
                    self.pos[1]
                    - ly
                )
                <= 2
                and
                self.rng.random()
                < .05
            ):
                self.state = "riding"

                self.ride_offset = (
                    self.pos[1]
                    - ly
                )

                self.mood = (
                    "commuting"
                )

                return

        if self.state == "riding":
            if not lift.active:
                self.state = "explore"

                self.pos = (
                    stage.nearest_graph(
                        self.pos
                    )
                )

                self._route_to(
                    stage,
                    self._choose_goal(
                        stage,
                        achars,
                    ),
                )

                return

            self.pos = (
                stage.shaft_x,
                int(
                    round(
                        lift.y
                    )
                )
                + self.ride_offset,
            )

            if (
                lift.state == "dwell"
                and
                self.rng.random()
                < .035
            ):
                self.state = (
                    "explore"
                )

                self.pos = (
                    stage.nearest_graph(
                        self.pos
                    )
                )

                self._route_to(
                    stage,
                    self._choose_goal(
                        stage,
                        achars,
                    ),
                )

            return

        if not self.route:
            self._route_to(
                stage,
                (
                    stage.hatch
                    if self.state
                    == "return"
                    else self._choose_goal(
                        stage,
                        achars,
                    )
                ),
            )

        self.acc += (
            dt * 11.5
        )

        while (
            self.acc >= 1
            and
            self.i
            < len(
                self.route
            )
            - 1
        ):
            self.acc -= 1

            old = (
                self.route[
                    self.i
                ]
            )

            self.i += 1

            self.pos = (
                self.route[
                    self.i
                ]
            )

            dx = (
                self.pos[0]
                - old[0]
            )

            dy = (
                self.pos[1]
                - old[1]
            )

            self.facing = (
                "right"
                if dx > 0
                else
                "left"
                if dx < 0
                else
                "climb"
                if dy
                else self.facing
            )

            n = (
                achars.collect_near(
                    *self.pos,
                    radius=2,
                )
            )

            if n:
                self.collected += n
                self.mood = "delighted"

        if (
            self.i
            >= len(
                self.route
            )
            - 1
        ):
            if (
                self.state == "return"
                and
                self.pos == stage.hatch
            ):
                self.state = "closing"
                self.timer = 0.0

            else:
                self.state = "nap"
                self.timer = 0.0

    def render(
        self,
        c: Canvas,
        stage: Stage,
        now: float,
    ) -> None:
        hx, hy = stage.hatch

        if self.state == "hidden":
            return

        if self.state in (
            "opening",
            "closing",
        ):
            seq = [
                "[==]",
                "[--]",
                "[  ]",
                "<  >",
            ]

            phase = min(
                3,
                int(
                    self.timer
                    / .18
                ),
            )

            if self.state == "closing":
                phase = (
                    3 - phase
                )

            c.text(
                max(
                    1,
                    hx - 3,
                ),
                hy,
                seq[
                    phase
                ],
                220,
                True,
            )

            if (
                self.state == "opening"
                and
                phase >= 2
            ):
                c.put(
                    hx - 1,
                    hy - 1,
                    "o",
                    220,
                    True,
                )

            return

        x, y = self.pos

        bob = (
            int(
                now * 8
            )
            & 1
        )

        if self.state == "nap":
            sprite = (
                (
                    " z ",
                    "_o_",
                    "/|\\",
                ),
                (
                    " Z ",
                    "_o_",
                    "/|\\",
                ),
            )[bob]

        elif self.facing == "climb":
            sprite = (
                (
                    " o ",
                    "/|\\",
                    "^ ^",
                ),
                (
                    " o ",
                    "\\|/",
                    "v v",
                ),
            )[bob]

        elif self.facing == "left":
            sprite = (
                (
                    "_o ",
                    "<|>",
                    "/ \\",
                ),
                (
                    " o_",
                    "<|>",
                    "/ \\",
                ),
            )[bob]

        else:
            sprite = (
                (
                    " o_",
                    "<|>",
                    "/ \\",
                ),
                (
                    "_o ",
                    "<|>",
                    "/ \\",
                ),
            )[bob]

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
            self.mood
            and
            int(
                now * 2
            )
            % 10
            == 0
        ):
            c.text(
                max(
                    1,
                    x
                    - len(
                        self.mood
                    )
                    // 2,
                ),
                max(
                    1,
                    y - 2,
                ),
                self.mood[
                    :14
                ],
                179,
            )


class PhantomTransmission:
    BASE = [
        "GROUND WAS OPTIONAL, APPARENTLY.",
        "THE FUTURE FAILED ITS CONTINUITY TEST.",
        "NO FAULT FOUND. MORALE REPLACED.",
        "THE MACHINE DENIES KNOWING YOU.",
        "BAY 13 REQUESTS A BETTER BAY 13.",
        "PLEASE STOP NAMING THE FAULTS. THEY RESPOND TO IT.",
        "CHANNEL CLEAR. SITUATION LESS SO.",
        "DO NOT TRUST A CONNECTOR THAT LOOKS CONFIDENT.",
        "THE NIGHT SHIFT LEFT US A NOTE. IT JUST SAYS 'NO'.",
        "AUX POWER REPORTS IT IS DOING ITS BEST.",
        "THE CORRIDOR MAP HAS FILED FOR INDEPENDENCE.",
        "THE COLOUR OF THE COOLANT IS NOT IN THE MANUAL.",
    ]

    REPLIES = [
        "COPY THAT. REGRETTABLY.",
        "NEGATIVE. TOO LATE.",
        "REPEAT LAST. ACTUALLY DON'T.",
        "MAINT ACKNOWLEDGES NOTHING.",
        "UNDERSTOOD // NOT ACCEPTED.",
    ]

    def __init__(
        self,
        rng: random.Random,
    ) -> None:
        self.rng = rng

        self.state = "idle"

        self.timer = 0.0

        self.channel = ""

        self.fragments: List[
            str
        ] = []

        self.frag_i = 0

        self.strength = .7
        self.drift = 0.0

        self.beacon: Optional[
            Coord
        ] = None

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
        stage: Stage,
    ) -> None:
        contextual = []

        mapping = {
            "gremlin":
                "SMALL UNIT OUT OF HATCH AGAIN. DO NOT ENCOURAGE IT.",

            "hardware":
                "STORES: SEND BOLTS. APPARENTLY ALL OF THEM.",

            "moths":
                "RELAY ROOM REPORTS MOTHS. RELAYS DECLINE COMMENT.",

            "crawler":
                "UNREGISTERED CURRENT OBSERVED CRAWLING AGAINST THE ARROWS.",

            "lift":
                "WHO AUTHORIZED THE LIFT? SECOND QUESTION: WHERE IS IT GOING?",

            "ghost":
                "WE CAN SEE THE CURSOR. THERE IS NO OPERATOR LOGGED IN.",

            "lichen":
                "GREEN GROWTH ON BUS 4. BUS 4 CLAIMS IT IS DECORATIVE.",

            "arc":
                "DISCHARGE EVENT CLOSED AS WEATHER. THIS IS INDOORS.",

            "drone":
                "REMOTE VEHICLE ACTIVE. REMOTE OPERATOR STATUS: ALSO REMOTE.",

            "coolant":
                "COOLANT LEAK HAS ACHIEVED SEVERAL NEW COLOURS.",

            "aurora":
                "DIAGNOSTIC DISPLAY HAS BECOME ASPIRATIONAL.",
        }

        for k, msg in mapping.items():
            if context.get(
                k
            ):
                contextual.append(
                    msg
                )

        first = self.rng.choice(
            self.BASE
            + contextual * 2
        )

        self.fragments = [
            first
        ]

        if (
            self.rng.random()
            < .62
        ):
            self.fragments.append(
                self.rng.choice(
                    self.REPLIES
                )
            )

        if (
            self.rng.random()
            < .28
        ):
            self.fragments.append(
                self.rng.choice(
                    self.BASE
                )
            )

        self.frag_i = 0

        self.channel = (
            self.rng.choice(
                (
                    "BAY 13",
                    "AUX RADIO",
                    "SERVICE RETURN",
                    "MAINT CH-0?",
                    "LOCAL CARRIER",
                )
            )
        )

        self.strength = (
            self.rng.uniform(
                .35,
                .98,
            )
        )

        self.drift = (
            self.rng.uniform(
                -.12,
                .12,
            )
        )

        self.beacon = (
            self.rng.choice(
                stage.lamps
            )
            if stage.lamps
            else None
        )

        self.state = "acquire"
        self.timer = 0.0

    def update(
        self,
        dt: float,
    ) -> None:
        if self.state == "idle":
            return

        self.timer += dt

        self.strength = clamp(
            self.strength
            + self.drift * dt,
            .25,
            .99,
        )

        if self.strength in (
            .25,
            .99,
        ):
            self.drift *= -1

        if (
            self.state == "acquire"
            and
            self.timer >= 1.0
        ):
            self.state = "identify"
            self.timer = 0.0

        elif (
            self.state == "identify"
            and
            self.timer >= 1.0
        ):
            self.state = "message"
            self.timer = 0.0

        elif (
            self.state == "message"
            and
            self.timer >= 4.4
        ):
            if (
                self.frag_i
                < len(
                    self.fragments
                )
                - 1
            ):
                self.frag_i += 1
                self.timer = 0.0

            else:
                self.state = "fade"
                self.timer = 0.0

        elif (
            self.state == "fade"
            and
            self.timer >= 1.4
        ):
            self.state = "idle"
            self.timer = 0.0

    def _corrupt(
        self,
        s: str,
        intensity: float,
    ) -> str:
        local = random.Random(
            int(
                self.timer * 9
            )
            +
            self.frag_i * 1009
            +
            len(
                s
            )
            * 31
        )

        repl = "#?./:-_"

        return "".join(
            local.choice(
                repl
            )
            if (
                ch != " "
                and
                local.random()
                < intensity
            )
            else ch
            for ch in s
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
            stage.hlines[1]
            + 1
        )

        width = max(
            16,
            c.w - x - 3,
        )

        if (
            width < 20
            or
            y + 5 >= c.h
        ):
            x = 2
            y = 2

            width = max(
                20,
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
                        self.timer * 6
                    )
                    % 7
                )
            )

            c.text(
                x + 2,
                y + 1,

                self._corrupt(
                    (
                        "carrier search "
                        "// wrong wire"
                        + dots
                    ),
                    .16,
                ),

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
                * 10
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
                        10 - bars
                    )
                ),

                45,
                True,
            )

            return

        c.text(
            x + 2,
            y + 1,

            (
                f"{self.channel}"
                " // RX "
                f"{int(self.strength * 100):02d}%"
            ),

            51,
            True,
            width - 4,
        )

        if self.state == "identify":
            c.text(
                x + 2,
                y + 2,

                self._corrupt(
                    "UNREGISTERED MAINTENANCE CHANNEL",
                    (
                        1
                        - self.strength
                    )
                    * .18,
                ),

                45,

                max_width=(
                    width - 4
                ),
            )

            return

        message = (
            self.fragments[
                self.frag_i
            ]
        )

        reveal = (
            len(
                message
            )
            if self.state == "fade"
            else min(
                len(
                    message
                ),
                int(
                    self.timer
                    * 28
                ),
            )
        )

        shown = (
            self._corrupt(
                message[
                    :reveal
                ],
                (
                    1
                    - self.strength
                )
                * .12,
            )
        )

        inner = (
            width - 4
        )

        c.text(
            x + 2,
            y + 2,
            shown[
                :inner
            ],
            (
                51
                if self.state
                == "message"
                else 240
            ),
            max_width=inner,
        )

        if (
            len(
                shown
            )
            > inner
        ):
            c.text(
                x + 2,
                y + 3,
                shown[
                    inner:
                    inner * 2
                ],
                51,
                max_width=inner,
            )

        c.text(
            x + width - 8,
            y + 4,
            (
                f"{self.frag_i + 1}"
                "/"
                f"{len(self.fragments)}"
            ),
            244,
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
    panic: float = 0.0

    phase: float = 0.0


class RelayMoths:
    """
    Relay moths plus a dedicated Moth FX layer.

    Ctrl-Y promotes the existing moth easter egg into a manually
    controllable visualizer.
    """

    def __init__(
        self,
        rng: random.Random,
    ) -> None:
        self.rng = rng

        self.moths: List[
            Moth
        ] = []

        self.max_moths = 150

        self.fx_mode = False

        self.target_population = 48

        self.formation_i = 0
        self.turbulence_i = 0

        self.palette_phase = 0

        self.beacon_x = 0.0
        self.beacon_y = 0.0

        self.beacon_phase = 0.0

        self.formations = [
            "ORBIT",
            "RIBBON",
            "VORTEX",
            "LATTICE",
            "COMET",
            "PULSE",
        ]

        self.turbulence = [
            "CALM",
            "BREEZE",
            "CHAOTIC",
            "REVERSE",
        ]

    @property
    def active(self) -> bool:
        return bool(
            self.moths
        )

    def toggle_fx(
        self,
        stage: Stage,
    ) -> None:
        self.fx_mode = (
            not self.fx_mode
        )

        if self.fx_mode:
            self.beacon_x = (
                stage.w / 2
            )

            self.beacon_y = (
                stage.h / 2
            )

    def summon(
        self,
        stage: Stage,
        count: Optional[int] = None,
    ) -> None:
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

        count = (
            count
            or
            self.rng.randint(
                20,
                42,
            )
        )

        for _ in range(
            count
        ):
            a = (
                self.rng.random()
                * math.tau
            )

            r = self.rng.uniform(
                1,
                10,
            )

            self.moths.append(
                Moth(
                    lx
                    + math.cos(
                        a
                    )
                    * r,

                    ly
                    + math.sin(
                        a
                    )
                    * r
                    * .5,

                    self.rng.uniform(
                        -2,
                        2,
                    ),

                    self.rng.uniform(
                        -1,
                        1,
                    ),

                    target,

                    0.0,

                    self.rng.uniform(
                        18,
                        42,
                    ),

                    phase=(
                        self.rng.random()
                        * math.tau
                    ),
                )
            )

        self.moths = (
            self.moths[
                -self.max_moths:
            ]
        )

    def trigger(
        self,
        stage: Stage,
    ) -> None:
        self.summon(
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

        k = (
            key.lower()
            if len(key) == 1
            else key
        )

        if key == " ":
            self.summon(
                stage,
                self.rng.randint(
                    24,
                    50,
                ),
            )

        elif key in (
            "+",
            "=",
        ):
            self.target_population = min(
                140,
                self.target_population
                + 5,
            )

        elif key == "-":
            self.target_population = max(
                5,
                self.target_population
                - 5,
            )

        elif key == "[":
            self.formation_i = (
                self.formation_i
                - 1
            ) % len(
                self.formations
            )

        elif key == "]":
            self.formation_i = (
                self.formation_i
                + 1
            ) % len(
                self.formations
            )

        elif k == "v":
            self.turbulence_i = (
                self.turbulence_i
                + 1
            ) % len(
                self.turbulence
            )

        elif k == "p":
            self.palette_phase = (
                self.palette_phase
                + 1
            ) % 64

        elif k == "r":
            self.formation_i = (
                self.rng.randrange(
                    len(
                        self.formations
                    )
                )
            )

            self.turbulence_i = (
                self.rng.randrange(
                    len(
                        self.turbulence
                    )
                )
            )

            self.target_population = (
                self.rng.randint(
                    20,
                    120,
                )
            )

            self.palette_phase = (
                self.rng.randrange(
                    64
                )
            )

        else:
            return False

        return True

    def panic_near(
        self,
        x: float,
        y: float,
        radius: float = 9.0,
    ) -> None:
        r2 = (
            radius
            * radius
        )

        for m in self.moths:
            if (
                (
                    m.x - x
                )
                ** 2
                +
                (
                    m.y - y
                )
                ** 2
                <= r2
            ):
                m.panic = 1.8

    def _fx_target(
        self,
        m: Moth,
        idx: int,
        now: float,
        stage: Stage,
    ) -> Tuple[
        float,
        float,
    ]:
        f = (
            self.formations[
                self.formation_i
            ]
        )

        cx = (
            self.beacon_x
            or stage.w / 2
        )

        cy = (
            self.beacon_y
            or stage.h / 2
        )

        phase = (
            now * 1.6
            + m.phase
            + idx * .19
        )

        if f == "RIBBON":
            return (
                cx
                + math.sin(
                    phase * .7
                )
                * stage.w
                * .32,

                cy
                + math.sin(
                    phase * 2.1
                )
                * 5,
            )

        if f == "VORTEX":
            r = (
                2
                + (
                    idx % 24
                )
                * .45
            )

            return (
                cx
                + math.cos(
                    phase
                )
                * r,

                cy
                + math.sin(
                    phase
                )
                * r
                * .45,
            )

        if f == "LATTICE":
            cols = max(
                3,
                int(
                    math.sqrt(
                        max(
                            1,
                            self.target_population,
                        )
                    )
                ),
            )

            gx = (
                idx % cols
            ) - cols / 2

            gy = (
                (
                    idx // cols
                )
                % cols
            ) - cols / 2

            return (
                cx
                + gx * 3
                + math.sin(
                    now * 2
                    + idx
                )
                * .8,

                cy
                + gy * 1.2
                + math.cos(
                    now * 2
                    + idx
                )
                * .35,
            )

        if f == "COMET":
            headx = (
                cx
                + math.cos(
                    now * .9
                )
                * stage.w
                * .25
            )

            heady = (
                cy
                + math.sin(
                    now * 1.3
                )
                * stage.h
                * .22
            )

            return (
                headx
                - (
                    idx % 35
                )
                * .55,

                heady
                + math.sin(
                    idx * .7
                    + now * 3
                )
                * 2,
            )

        if f == "PULSE":
            r = (
                4
                +
                (
                    math.sin(
                        now * 3
                        + m.phase
                    )
                    + 1
                )
                * 8
            )

            return (
                cx
                + math.cos(
                    m.phase
                    + idx * .3
                )
                * r,

                cy
                + math.sin(
                    m.phase
                    + idx * .3
                )
                * r
                * .45,
            )

        # ORBIT
        r = (
            4
            + (
                idx % 20
            )
            * .5
        )

        return (
            cx
            + math.cos(
                phase
            )
            * r,

            cy
            + math.sin(
                phase
            )
            * r
            * .5,
        )

    def update(
        self,
        dt: float,
        now: float,
        stage: Stage,
        gremlin: Gremlin,
        achars: ACharField,
        phantom: PhantomTransmission,
        arc_points: Sequence[
            Coord
        ],
        drone: "MaintenanceDrone",
        aurora: "DiagnosticAurora",
    ) -> None:
        if self.fx_mode:
            self.beacon_phase += dt

            if (
                len(
                    self.moths
                )
                < self.target_population
                and
                self.rng.random()
                < min(
                    1.0,
                    dt * 18,
                )
            ):
                self.summon(
                    stage,
                    min(
                        6,
                        self.target_population
                        - len(
                            self.moths
                        ),
                    ),
                )

        alive: List[
            Moth
        ] = []

        for idx, m in enumerate(
            self.moths
        ):
            m.age += dt

            m.panic = max(
                0.0,
                m.panic
                - dt,
            )

            if (
                m.age >= m.ttl
                and
                not self.fx_mode
            ):
                continue

            if self.fx_mode:
                m.ttl = max(
                    m.ttl,
                    m.age + 8,
                )

            if self.fx_mode:
                tx, ty = (
                    self._fx_target(
                        m,
                        idx,
                        now,
                        stage,
                    )
                )

            else:
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

                if (
                    phantom.active
                    and
                    phantom.beacon
                    and
                    self.rng.random()
                    < .025
                ):
                    tx, ty = (
                        phantom.beacon
                    )

            dx = tx - m.x
            dy = ty - m.y

            dist = (
                math.hypot(
                    dx,
                    dy,
                )
                + .001
            )

            ax = (
                dx / dist
                * 5
                +
                (
                    -dy / dist
                )
                * 2.2
            )

            ay = (
                dy / dist
                * 3
                +
                (
                    dx / dist
                )
                * 1.2
            )

            turb = (
                self.turbulence[
                    self.turbulence_i
                ]
                if self.fx_mode
                else "BREEZE"
            )

            if turb == "CALM":
                jitter = .2

            elif turb == "CHAOTIC":
                jitter = 3.2

            elif turb == "REVERSE":
                ax = (
                    -ax
                    * .6
                )

                ay = (
                    -ay
                    * .6
                )

                jitter = 1.2

            else:
                jitter = .8

            ax += (
                self.rng.uniform(
                    -jitter,
                    jitter,
                )
            )

            ay += (
                self.rng.uniform(
                    -jitter * .6,
                    jitter * .6,
                )
            )

            if gremlin.active:
                gx, gy = (
                    gremlin.pos
                )

                rx = m.x - gx
                ry = m.y - gy

                gd = (
                    math.hypot(
                        rx,
                        ry,
                    )
                    + .001
                )

                if gd < 10:
                    ax += (
                        rx / gd
                        * (
                            30 / gd
                        )
                    )

                    ay += (
                        ry / gd
                        * (
                            18 / gd
                        )
                    )

                    m.panic = max(
                        m.panic,
                        .7,
                    )

            if drone.active:
                rx = (
                    m.x
                    - drone.x
                )

                ry = (
                    m.y
                    - drone.y
                )

                dd = (
                    math.hypot(
                        rx,
                        ry,
                    )
                    + .001
                )

                if dd < 9:
                    ax += (
                        rx / dd
                        * (
                            22 / dd
                        )
                    )

                    ay += (
                        ry / dd
                        * (
                            14 / dd
                        )
                    )

                    m.panic = max(
                        m.panic,
                        .45,
                    )

            for px, py in arc_points:
                rx = m.x - px
                ry = m.y - py

                rd = (
                    math.hypot(
                        rx,
                        ry,
                    )
                    + .001
                )

                if rd < 8:
                    ax += (
                        rx / rd
                        * (
                            38 / rd
                        )
                    )

                    ay += (
                        ry / rd
                        * (
                            24 / rd
                        )
                    )

                    m.panic = max(
                        m.panic,
                        1.2,
                    )

            if aurora.active:
                wy = aurora.wave_y(
                    m.x,
                    stage,
                )

                ay += (
                    clamp(
                        wy - m.y,
                        -4,
                        4,
                    )
                    * .22
                )

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
                        -.7,
                        .7,
                    )
                    * disturbance
                )

            if (
                dist < 1.5
                and
                self.rng.random()
                < .015
                and
                m.panic <= 0
                and
                not self.fx_mode
            ):
                m.rest = (
                    self.rng.uniform(
                        .4,
                        1.8,
                    )
                )

            if m.rest > 0:
                m.rest -= dt
                m.vx *= .82
                m.vy *= .82

            else:
                gain = (
                    2.2
                    if m.panic > 0
                    else 1.0
                )

                m.vx = (
                    m.vx
                    + ax
                    * dt
                    * gain
                ) * .985

                m.vy = (
                    m.vy
                    + ay
                    * dt
                    * gain
                ) * .985

            speed = (
                math.hypot(
                    m.vx,
                    m.vy,
                )
            )

            max_speed = (
                13
                if m.panic > 0
                else 9
            )

            if speed > max_speed:
                m.vx *= (
                    max_speed
                    / speed
                )

                m.vy *= (
                    max_speed
                    / speed
                )

            m.x = clamp(
                m.x
                + m.vx * dt,
                1,
                stage.w - 2,
            )

            m.y = clamp(
                m.y
                + m.vy * dt,
                1,
                stage.h - 2,
            )

            alive.append(
                m
            )

        self.moths = (
            alive[
                -self.max_moths:
            ]
        )

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
            "*",
            "+",
        )

        palettes = (
            (
                244,
                250,
                229,
                223,
                217,
                211,
            ),

            (
                45,
                51,
                87,
                123,
                159,
                195,
            ),

            (
                201,
                207,
                213,
                219,
                225,
                231,
            ),

            (
                82,
                118,
                154,
                190,
                226,
                220,
            ),
        )

        pal = (
            palettes[
                (
                    self.palette_phase
                    // 4
                )
                % len(
                    palettes
                )
            ]
        )

        for i, m in enumerate(
            self.moths
        ):
            rate = (
                22
                if m.panic > 0
                else 14
            )

            frame = int(
                now * rate
                + i * 1.7
                + m.phase
            ) % len(
                glyphs
            )

            fg = (
                pal[
                    (
                        frame
                        + self.palette_phase
                    )
                    % len(
                        pal
                    )
                ]
            )

            c.put(
                int(
                    round(
                        m.x
                    )
                ),
                int(
                    round(
                        m.y
                    )
                ),
                glyphs[
                    frame
                ],
                fg,
                frame
                in (
                    1,
                    4,
                ),
            )

        if self.fx_mode:
            bx = int(
                self.beacon_x
            )

            by = int(
                self.beacon_y
            )

            spin = int(
                now * 10
            ) % 4

            arms = (
                (
                    "-",
                    "|",
                ),
                (
                    "/",
                    "\\",
                ),
                (
                    "|",
                    "-",
                ),
                (
                    "\\",
                    "/",
                ),
            )[spin]

            c.put(
                bx,
                by,
                "@",
                195,
                True,
            )

            c.put(
                bx - 2,
                by,
                arms[0],
                159,
                True,
            )

            c.put(
                bx + 2,
                by,
                arms[0],
                159,
                True,
            )

            c.put(
                bx,
                by - 1,
                arms[1],
                159,
                True,
            )

            c.put(
                bx,
                by + 1,
                arms[1],
                159,
                True,
            )

            s = (
                " MOTH FX :: "
                f"formation={self.formations[self.formation_i]:<7} "
                f"turbulence={self.turbulence[self.turbulence_i]:<7} "
                f"target={self.target_population:03d}  "
                "[ ] formation "
                "V turbulence "
                "P palette "
                "+/- population "
                "Space burst "
                "R random "
                "Esc "
            )

            c.text(
                2,
                max(
                    1,
                    c.h - 4,
                ),
                s[
                    :max(
                        0,
                        c.w - 4,
                    )
                ],
                219,
                True,
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

        self.tail: Deque[
            Coord
        ] = deque(
            maxlen=24
        )

        self.trail: Dict[
            Coord,
            float,
        ] = {}

        self.echoes: List[
            Tuple[
                Coord,
                float,
            ]
        ] = []

        self.hops = 0

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

        start = (
            self.rng.choice(
                stage.graph_list
            )
        )

        goal = (
            stage.far_node(
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

        self.echoes = []

        self.hops = (
            self.rng.randint(
                4,
                7,
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

        goal = stage.far_node(
            self.rng,
            start,
            max(
                12,
                stage.w // 4,
            ),
        )

        self.route = stage.path(
            start,
            goal,
        )

        self.i = 0
        self.acc = 0.0

    def update(
        self,
        dt: float,
        stage: Stage,
        achars: ACharField,
        lichen: "SignalLichen",
    ) -> None:
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

        self.echoes = [
            (
                p,
                ttl - dt,
            )
            for p, ttl
            in self.echoes
            if ttl - dt > 0
        ]

        if (
            not self.active
            or
            not self.route
        ):
            return

        self.acc += (
            dt * 22
        )

        while (
            self.acc >= 1
            and
            self.active
        ):
            self.acc -= 1

            p = self.route[
                self.i
            ]

            self.tail.appendleft(
                p
            )

            self.trail[p] = (
                self.rng.uniform(
                    .4,
                    1.6,
                )
            )

            lichen.stimulate(
                p,
                .1,
            )

            if p in stage.gaps:
                stage.mark_repaired(
                    p,
                    self.rng.uniform(
                        5,
                        12,
                    ),
                )

                achars.spawn_spark(
                    p[0],
                    p[1],
                    self.rng.randint(
                        2,
                        5,
                    ),
                )

            elif (
                self.rng.random()
                < .055
            ):
                achars.spawn_spark(
                    p[0],
                    p[1],
                    1,
                )

            if (
                p in stage.junctions
                and
                self.rng.random()
                < .075
            ):
                self.echoes.append(
                    (
                        p,
                        .9,
                    )
                )

            if (
                self.i
                < len(
                    self.route
                )
                - 1
            ):
                self.i += 1

            elif self.hops > 0:
                self.hops -= 1

                self._continue(
                    stage
                )

            else:
                self.active = False

    def render(
        self,
        c: Canvas,
        now: float,
    ) -> None:
        for p, ttl in (
            self.trail.items()
        ):
            c.put(
                p[0],
                p[1],
                ".",
                (
                    22
                    if ttl < .6
                    else 28
                ),
            )

        for p, ttl in (
            self.echoes
        ):
            c.put(
                p[0],
                p[1],
                (
                    "*"
                    if int(
                        now * 18
                    )
                    & 1
                    else "+"
                ),
                (
                    40
                    if ttl > .4
                    else 34
                ),
                True,
            )

        if not self.active:
            return

        for j, (
            x,
            y,
        ) in enumerate(
            reversed(
                list(
                    self.tail
                )[:18]
            )
        ):
            c.put(
                x,
                y,
                (
                    "="
                    if j % 3
                    else "~"
                ),
                22
                + min(
                    6,
                    j // 3,
                ),
            )

        c.put(
            self.pos[0],
            self.pos[1],
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
        "b+",
    ]

    def __init__(
        self,
        rng: random.Random,
    ) -> None:
        self.rng = rng

        self.state = "hidden"

        self.y = 0.0
        self.target = 0.0

        self.stops: List[
            int
        ] = []

        self.timer = 0.0

        self.cargo = "[]"

        self.caption = (
            "NO PERMIT"
        )

        self.call_flash = 0.0

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
        candidates = sorted(
            set(
                (
                    stage.hlines[0]
                    + 2,

                    stage.hlines[1],

                    stage.hlines[2],

                    max(
                        stage.hlines[0]
                        + 2,
                        stage.h - 5,
                    ),
                )
            )
        )

        if self.active:
            self.stops.append(
                self.rng.choice(
                    candidates
                )
            )

            self.call_flash = 1.4
            return

        count = self.rng.randint(
            2,
            min(
                4,
                len(
                    candidates
                ),
            ),
        )

        self.stops = self.rng.sample(
            candidates,
            count,
        )

        self.y = float(
            stage.h - 3
        )

        self.target = float(
            self.stops.pop(
                0
            )
        )

        self.cargo = (
            self.rng.choice(
                self.CARGO
            )
        )

        if (
            gremlin.collected
            and
            self.rng.random()
            < .35
        ):
            self.cargo = "b+"

        self.caption = (
            self.rng.choice(
                (
                    "NO PERMIT",
                    "SERVICE?",
                    "B13 LIFT",
                    "NOT LISTED",
                    "FREIGHT?",
                )
            )
        )

        self.state = "moving"
        self.timer = 0.0

        self.call_flash = 1.0

    def update(
        self,
        dt: float,
        stage: Stage,
        achars: ACharField,
    ) -> None:
        self.call_flash = max(
            0.0,
            self.call_flash
            - dt,
        )

        if self.state == "hidden":
            return

        self.timer += dt

        if self.state in (
            "moving",
            "depart",
        ):
            dy = (
                self.target
                - self.y
            )

            speed = (
                9
                if self.state
                == "moving"
                else 11
            )

            step = (
                sign(
                    dy
                )
                * speed
                * dt
            )

            if (
                abs(
                    step
                )
                >= abs(
                    dy
                )
            ):
                self.y = (
                    self.target
                )

                if self.state == "depart":
                    self.state = "hidden"
                    self.timer = 0.0

                else:
                    self.state = "opening"
                    self.timer = 0.0
                    self.call_flash = .8

            else:
                self.y += step

            return

        if (
            self.state == "opening"
            and
            self.timer >= .6
        ):
            self.state = "dwell"
            self.timer = 0.0

        elif (
            self.state == "dwell"
            and
            self.timer >= 2.0
        ):
            if (
                self.cargo == "b+"
                and
                self.rng.random()
                < .32
            ):
                achars.spill(
                    stage
                )

                self.cargo = "--"

            self.state = "closing"
            self.timer = 0.0

        elif (
            self.state == "closing"
            and
            self.timer >= .6
        ):
            self.timer = 0.0

            if self.stops:
                self.target = float(
                    self.stops.pop(
                        0
                    )
                )

                self.state = "moving"

            else:
                self.target = float(
                    stage.h - 3
                )

                self.state = "depart"

    def render(
        self,
        c: Canvas,
        stage: Stage,
        now: float,
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
                    / .2
                ),
            )

            if self.state == "closing":
                phase = (
                    2 - phase
                )

        elif self.state == "dwell":
            phase = 2

        doors = (
            "[||]",
            "[  ]",
            "<  >",
        )[phase]

        flash = (
            int(
                now * 12
            )
            & 1
        )

        c.text(
            x - 2,
            y - 1,
            "+---+",
            (
                208
                if flash
                else 214
            ),
            True,
        )

        c.text(
            x - 2,
            y,
            doors.ljust(
                5
            ),
            (
                214
                if flash
                else 208
            ),
            True,
        )

        c.text(
            x - 2,
            y + 1,
            "+---+",
            (
                208
                if flash
                else 214
            ),
            True,
        )

        if self.state == "dwell":
            c.text(
                x - 1,
                y,
                self.cargo[
                    :2
                ],
                229,
                True,
            )

        if self.call_flash > 0:
            c.put(
                (
                    x + 3
                    if x + 3
                    < c.w
                    else x - 3
                ),
                max(
                    1,
                    y - 1,
                ),
                "*",
                226,
                True,
            )

        c.text(
            max(
                1,
                x
                - len(
                    self.caption
                )
                // 2,
            ),
            max(
                1,
                y - 2,
            ),
            self.caption,
            179,
        )


class GhostOperator:
    def __init__(
        self,
        rng: random.Random,
    ) -> None:
        self.rng = rng

        self.active = False

        self.pos: Coord = (
            2,
            2,
        )

        self.target: Coord = (
            2,
            2,
        )

        self.timer = 0.0

        self.path: List[
            Coord
        ] = []

        self.i = 0

        self.after: Deque[
            Tuple[
                Coord,
                float,
            ]
        ] = deque(
            maxlen=20
        )

        self.click = 0.0

        self.visits = 0

    def trigger(
        self,
        stage: Stage,
    ) -> None:
        if not stage.control_nodes:
            return

        self.active = True

        self.timer = 0.0

        self.visits = self.rng.randint(
            5,
            11,
        )

        self.pos = (
            self.rng.choice(
                stage.control_nodes
            )
        )

        self._pick(
            stage
        )

    def _pick(
        self,
        stage: Stage,
    ) -> None:
        self.target = (
            self.rng.choice(
                stage.control_nodes
            )
        )

        x0, y0 = self.pos
        x1, y1 = self.target

        n = max(
            abs(
                x1 - x0
            ),
            abs(
                y1 - y0
            ),
            1,
        )

        self.path = [
            (
                round(
                    x0
                    + (
                        x1 - x0
                    )
                    * t
                    / n
                ),

                round(
                    y0
                    + (
                        y1 - y0
                    )
                    * t
                    / n
                ),
            )
            for t in range(
                n + 1
            )
        ]

        self.i = 0

    def update(
        self,
        dt: float,
        stage: Stage,
        achars: ACharField,
    ) -> None:
        self.after = deque(
            (
                (
                    p,
                    ttl - dt,
                )
                for p, ttl
                in self.after
                if ttl - dt > 0
            ),
            maxlen=20,
        )

        self.click = max(
            0,
            self.click - dt,
        )

        if not self.active:
            return

        self.timer += dt

        steps = int(
            self.timer
            * 20
        )

        if steps:
            self.timer -= (
                steps / 20
            )

        for _ in range(
            steps
        ):
            if (
                self.i
                < len(
                    self.path
                )
                - 1
            ):
                self.i += 1

                self.pos = (
                    self.path[
                        self.i
                    ]
                )

                self.after.appendleft(
                    (
                        self.pos,
                        .9,
                    )
                )

            else:
                self.click = .24

                achars.charge_near(
                    *self.pos,
                    4,
                    .3,
                )

                self.visits -= 1

                if self.visits <= 0:
                    self.active = False
                    break

                self._pick(
                    stage
                )

    def render(
        self,
        c: Canvas,
        now: float,
    ) -> None:
        for p, ttl in self.after:
            c.put(
                p[0],
                p[1],
                ".",
                (
                    54
                    if ttl < .45
                    else 60
                ),
            )

        if not self.active:
            return

        x, y = self.pos

        glyph = (
            "+"
            if os.name == "nt"
            else "◆"
        )

        pulse = (
            int(
                now * 14
            )
            & 1
        )

        c.put(
            x,
            y,
            glyph,
            (
                195
                if pulse
                else 159
            ),
            True,
        )

        if self.click > 0:
            for dx, dy, ch in (
                (
                    1,
                    0,
                    "!",
                ),
                (
                    -1,
                    0,
                    "!",
                ),
                (
                    0,
                    1,
                    "*",
                ),
                (
                    0,
                    -1,
                    "*",
                ),
            ):
                c.put(
                    x + dx,
                    y + dy,
                    ch,
                    225,
                    True,
                )


class SignalLichen:
    def __init__(
        self,
        rng: random.Random,
    ) -> None:
        self.rng = rng

        self.cover: Dict[
            Coord,
            float,
        ] = {}

        self.active = False

        self.growth_acc = 0.0

    def trigger(
        self,
        stage: Stage,
    ) -> None:
        self.active = True

        if not stage.graph_list:
            return

        count = min(
            len(
                stage.graph_list
            ),
            self.rng.randint(
                8,
                20,
            ),
        )

        for p in self.rng.sample(
            stage.graph_list,
            count,
        ):
            self.cover[p] = max(
                self.cover.get(
                    p,
                    0,
                ),
                self.rng.uniform(
                    .3,
                    .8,
                ),
            )

    def stimulate(
        self,
        p: Coord,
        amount: float = .1,
    ) -> None:
        if p in self.cover:
            self.cover[p] = clamp(
                self.cover[p]
                + amount,
                0,
                1,
            )

        elif (
            self.rng.random()
            < amount * 2
        ):
            self.cover[p] = (
                amount
            )

    def burn_near(
        self,
        x: float,
        y: float,
        radius: float = 5,
    ) -> None:
        r2 = (
            radius
            * radius
        )

        for p in list(
            self.cover
        ):
            if (
                (
                    p[0] - x
                )
                ** 2
                +
                (
                    p[1] - y
                )
                ** 2
                <= r2
            ):
                self.cover[p] -= .75

                if self.cover[p] <= 0:
                    self.cover.pop(
                        p,
                        None,
                    )

    def update(
        self,
        dt: float,
        stage: Stage,
        crawler: CableCrawler,
        coolant: "PrismaticCoolant",
    ) -> None:
        if (
            not self.cover
            and
            not self.active
        ):
            return

        self.growth_acc += (
            dt
            * (
                4.5
                if self.active
                else 1.0
            )
        )

        while self.growth_acc >= 1:
            self.growth_acc -= 1

            if (
                not self.cover
                and
                stage.graph_list
            ):
                self.cover[
                    self.rng.choice(
                        stage.graph_list
                    )
                ] = .3

                continue

            if not self.cover:
                break

            p = (
                self.rng.choice(
                    list(
                        self.cover
                    )
                )
            )

            self.cover[p] = clamp(
                self.cover[p]
                + self.rng.uniform(
                    .02,
                    .08,
                ),
                0,
                1,
            )

            ns = list(
                stage.neighbors(
                    p
                )
            )

            if (
                ns
                and
                self.rng.random()
                < .62
            ):
                q = self.rng.choice(
                    ns
                )

                self.cover[q] = max(
                    self.cover.get(
                        q,
                        0,
                    ),
                    self.rng.uniform(
                        .08,
                        .3,
                    ),
                )

            if (
                coolant.active
                and
                self.rng.random()
                < .2
            ):
                self.cover[p] = min(
                    1,
                    self.cover[p]
                    + .12,
                )

            if (
                self.rng.random()
                < .08
            ):
                q = (
                    self.rng.choice(
                        list(
                            self.cover
                        )
                    )
                )

                self.cover[q] -= .08

                if self.cover[q] <= 0:
                    self.cover.pop(
                        q,
                        None,
                    )

            limit = min(
                480,
                max(
                    140,
                    len(
                        stage.graph
                    )
                    // 2,
                ),
            )

            if (
                len(
                    self.cover
                )
                > limit
            ):
                self.active = False

    def render(
        self,
        c: Canvas,
        now: float,
    ) -> None:
        glyphs = (
            ".",
            ":",
            "*",
            "#",
            "%",
        )

        for i, (
            p,
            v,
        ) in enumerate(
            self.cover.items()
        ):
            level = min(
                4,
                int(
                    v * 5
                ),
            )

            fg = (
                22,
                28,
                34,
                40,
                46,
            )[level]

            if (
                v > .7
                and
                int(
                    now * 5
                    + i
                )
                % 6
                == 0
            ):
                fg = (
                    82,
                    118,
                    154,
                    190,
                )[
                    i % 4
                ]

            c.put(
                p[0],
                p[1],
                glyphs[
                    level
                ],
                fg,
                level >= 2,
            )


@dataclass
class Arc:
    a: Coord
    b: Coord

    ttl: float

    age: float = 0.0


class ArcStorm:
    def __init__(
        self,
        rng: random.Random,
    ) -> None:
        self.rng = rng

        self.arcs: List[
            Arc
        ] = []

        self.timer = 0.0
        self.active_for = 0.0

    @property
    def active(self) -> bool:
        return (
            self.active_for > 0
            or
            bool(
                self.arcs
            )
        )

    def trigger(
        self,
        stage: Stage,
    ) -> None:
        self.active_for = max(
            self.active_for,
            self.rng.uniform(
                4,
                8,
            ),
        )

        self.timer = 0

        self._spawn(
            stage
        )

    def _spawn(
        self,
        stage: Stage,
    ) -> None:
        nodes = (
            list(
                stage.lamps
            )
            +
            stage.junctions
        )

        if len(nodes) < 2:
            return

        a = (
            self.rng.choice(
                nodes
            )
        )

        far = [
            p
            for p in nodes
            if manhattan(
                p,
                a,
            )
            >= 6
        ]

        b = self.rng.choice(
            far
            or nodes
        )

        self.arcs.append(
            Arc(
                a,
                b,
                self.rng.uniform(
                    .18,
                    .46,
                ),
            )
        )

    def update(
        self,
        dt: float,
        stage: Stage,
        achars: ACharField,
        moths: RelayMoths,
        lichen: SignalLichen,
        drone: "MaintenanceDrone",
    ) -> None:
        self.active_for = max(
            0,
            self.active_for
            - dt,
        )

        self.timer += dt

        if (
            self.active_for > 0
            and
            self.timer
            >= self.rng.uniform(
                .16,
                .44,
            )
        ):
            self.timer = 0
            self._spawn(
                stage
            )

        alive = []

        for arc in self.arcs:
            arc.age += dt

            if arc.age >= arc.ttl:
                continue

            alive.append(
                arc
            )

            t = clamp(
                arc.age / arc.ttl,
                0,
                1,
            )

            x = (
                arc.a[0]
                +
                (
                    arc.b[0]
                    - arc.a[0]
                )
                * t
            )

            y = (
                arc.a[1]
                +
                (
                    arc.b[1]
                    - arc.a[1]
                )
                * t
            )

            achars.charge_near(
                x,
                y,
                6,
                .9,
            )

            moths.panic_near(
                x,
                y,
                8,
            )

            lichen.burn_near(
                x,
                y,
                3.5,
            )

            if (
                drone.active
                and
                (
                    drone.x - x
                )
                ** 2
                +
                (
                    drone.y - y
                )
                ** 2
                < 36
            ):
                drone.charge = min(
                    1.5,
                    drone.charge
                    + .08,
                )

        self.arcs = alive

    def points(self) -> List[
        Coord
    ]:
        out = []

        for a in self.arcs:
            t = clamp(
                a.age / a.ttl,
                0,
                1,
            )

            out.append(
                (
                    round(
                        a.a[0]
                        +
                        (
                            a.b[0]
                            - a.a[0]
                        )
                        * t
                    ),

                    round(
                        a.a[1]
                        +
                        (
                            a.b[1]
                            - a.a[1]
                        )
                        * t
                    ),
                )
            )

        return out

    def _line(
        self,
        a: Coord,
        b: Coord,
        now: float,
    ) -> List[
        Coord
    ]:
        x0, y0 = a
        x1, y1 = b

        n = max(
            abs(
                x1 - x0
            ),
            abs(
                y1 - y0
            ),
            1,
        )

        out = []

        for i in range(
            n + 1
        ):
            t = i / n

            x = round(
                x0
                + (
                    x1 - x0
                )
                * t
            )

            y = round(
                y0
                + (
                    y1 - y0
                )
                * t
                +
                math.sin(
                    t
                    * math.pi
                    * 7
                    + now * 18
                )
                * .65
            )

            out.append(
                (
                    x,
                    y,
                )
            )

        return out

    def render(
        self,
        c: Canvas,
        now: float,
    ) -> None:
        for j, a in enumerate(
            self.arcs
        ):
            for i, p in enumerate(
                self._line(
                    a.a,
                    a.b,
                    now,
                )
            ):
                ch = (
                    ".",
                    "*",
                    "+",
                    "~",
                    "#",
                )[
                    (
                        i
                        + int(
                            now * 30
                        )
                        + j
                    )
                    % 5
                ]

                fg = (
                    51,
                    87,
                    123,
                    159,
                    195,
                    201,
                    207,
                )[
                    (
                        i + j
                    )
                    % 7
                ]

                c.put(
                    p[0],
                    p[1],
                    ch,
                    fg,
                    True,
                )


# ---------------------------------------------------------------------------
# NEW EFFECT #10
# ARROW-CONTROLLED MAINTENANCE DRONE
# ---------------------------------------------------------------------------

@dataclass
class DroneParticle:
    x: float
    y: float

    vx: float
    vy: float

    ttl: float

    age: float = 0.0

    kind: int = 0


class MaintenanceDrone:
    """
    Directly steerable using arrow keys.

    D:
        deploy / recall

    arrows:
        directional thrust

    Space:
        radial boost / EMP-like visual pulse

    H:
        autopilot toggle
    """

    def __init__(
        self,
        rng: random.Random,
    ) -> None:
        self.rng = rng

        self.active = False

        self.x = 10.0
        self.y = 10.0

        self.vx = 0.0
        self.vy = 0.0

        self.heading = (
            1.0,
            0.0,
        )

        self.particles: List[
            DroneParticle
        ] = []

        self.trail: Deque[
            Coord
        ] = deque(
            maxlen=24
        )

        self.boost = 0.0
        self.charge = 0.0

        self.autopilot = False

        self.target: Optional[
            Coord
        ] = None

        self.flash = 0.0

    def trigger(
        self,
        stage: Stage,
    ) -> None:
        if self.active:
            self.active = False
            return

        self.active = True

        self.x = stage.w / 2
        self.y = stage.h / 2

        self.vx = 0.0
        self.vy = 0.0

        self.autopilot = False
        self.target = None

        self.flash = .5

    def thrust(
        self,
        dx: int,
        dy: int,
    ) -> None:
        if not self.active:
            return

        power = (
            15
            * (
                1.6
                if self.boost > 0
                else 1
            )
        )

        self.vx += (
            dx
            * power
        )

        self.vy += (
            dy
            * power
            * .55
        )

        if dx or dy:
            self.heading = (
                float(
                    dx
                ),
                float(
                    dy
                ),
            )

        self.autopilot = False

    def pulse(
        self,
        achars: ACharField,
        moths: RelayMoths,
    ) -> None:
        if not self.active:
            return

        self.boost = .65
        self.flash = .35

        achars.charge_near(
            self.x,
            self.y,
            8,
            1.0,
        )

        moths.panic_near(
            self.x,
            self.y,
            9,
        )

        for i in range(
            28
        ):
            a = (
                i / 28
                * math.tau
            )

            sp = (
                self.rng.uniform(
                    3,
                    10,
                )
            )

            self.particles.append(
                DroneParticle(
                    self.x,
                    self.y,

                    math.cos(
                        a
                    )
                    * sp,

                    math.sin(
                        a
                    )
                    * sp
                    * .5,

                    self.rng.uniform(
                        .35,
                        .8,
                    ),

                    kind=1,
                )
            )

    def toggle_autopilot(
        self,
        stage: Stage,
    ) -> None:
        if not self.active:
            return

        self.autopilot = (
            not self.autopilot
        )

        self.target = (
            self.rng.choice(
                stage.control_nodes
                or
                [
                    (
                        int(
                            stage.w / 2
                        ),
                        int(
                            stage.h / 2
                        ),
                    )
                ]
            )
            if self.autopilot
            else None
        )

    def update(
        self,
        dt: float,
        stage: Stage,
        achars: ACharField,
        moths: RelayMoths,
        lichen: SignalLichen,
    ) -> None:
        self.boost = max(
            0,
            self.boost - dt,
        )

        self.charge = max(
            0,
            self.charge
            - dt * .25,
        )

        self.flash = max(
            0,
            self.flash - dt,
        )

        new = []

        for p in self.particles:
            p.age += dt

            if p.age >= p.ttl:
                continue

            p.x += (
                p.vx * dt
            )

            p.y += (
                p.vy * dt
            )

            p.vx *= .96
            p.vy *= .96

            new.append(
                p
            )

        self.particles = (
            new[
                -180:
            ]
        )

        if not self.active:
            return

        if self.autopilot:
            if not self.target:
                self.target = (
                    self.rng.choice(
                        stage.control_nodes
                        or
                        [
                            (
                                int(
                                    stage.w / 2
                                ),
                                int(
                                    stage.h / 2
                                ),
                            )
                        ]
                    )
                )

            dx = (
                self.target[0]
                - self.x
            )

            dy = (
                self.target[1]
                - self.y
            )

            d = (
                math.hypot(
                    dx,
                    dy,
                )
                + .001
            )

            self.vx += (
                dx / d
                * 7
                * dt
            )

            self.vy += (
                dy / d
                * 4
                * dt
            )

            if d < 2.5:
                self.target = (
                    self.rng.choice(
                        stage.control_nodes
                        or
                        [
                            self.target
                        ]
                    )
                )

        self.vx *= .965
        self.vy *= .965

        speed = (
            math.hypot(
                self.vx,
                self.vy,
            )
        )

        if speed > 18:
            self.vx *= (
                18 / speed
            )

            self.vy *= (
                18 / speed
            )

        self.x += (
            self.vx * dt
        )

        self.y += (
            self.vy * dt
        )

        if (
            self.x < 2
            or
            self.x
            > stage.w - 3
        ):
            self.x = clamp(
                self.x,
                2,
                stage.w - 3,
            )

            self.vx = (
                -self.vx
                * .65
            )

        if (
            self.y < 2
            or
            self.y
            > stage.h - 3
        ):
            self.y = clamp(
                self.y,
                2,
                stage.h - 3,
            )

            self.vy = (
                -self.vy
                * .65
            )

        self.trail.appendleft(
            (
                int(
                    round(
                        self.x
                    )
                ),
                int(
                    round(
                        self.y
                    )
                ),
            )
        )

        if (
            self.rng.random()
            < .75
        ):
            hvx, hvy = (
                self.heading
            )

            self.particles.append(
                DroneParticle(
                    self.x
                    - hvx * 2,

                    self.y
                    - hvy,

                    self.rng.uniform(
                        -1,
                        1,
                    )
                    - hvx * 5,

                    self.rng.uniform(
                        -.5,
                        .5,
                    )
                    - hvy * 2.5,

                    self.rng.uniform(
                        .35,
                        .9,
                    ),

                    kind=0,
                )
            )

        # Drone wash interacts with the shared world.
        moths.panic_near(
            self.x,
            self.y,
            5,
        )

        achars.charge_near(
            self.x,
            self.y,
            3,
            .12
            + self.charge * .2,
        )

        lichen.burn_near(
            self.x,
            self.y,
            1.4,
        )

    def render(
        self,
        c: Canvas,
        now: float,
    ) -> None:
        for p in self.particles:
            t = (
                p.age / p.ttl
            )

            if p.kind == 0:
                fg = (
                    51,
                    87,
                    123,
                    159,
                    195,
                    201,
                    207,
                )[
                    int(
                        (
                            1 - t
                        )
                        * 6
                    )
                    % 7
                ]

            else:
                fg = (
                    226,
                    220,
                    214,
                    208,
                )[
                    int(
                        (
                            1 - t
                        )
                        * 3
                    )
                    % 4
                ]

            c.put(
                int(
                    round(
                        p.x
                    )
                ),
                int(
                    round(
                        p.y
                    )
                ),
                (
                    "*"
                    if p.kind
                    else "."
                ),
                fg,
                p.kind == 1,
            )

        if not self.active:
            return

        for j, (
            x,
            y,
        ) in enumerate(
            list(
                self.trail
            )[2:14]
        ):
            c.put(
                x,
                y,
                (
                    "."
                    if j % 2
                    else ":"
                ),
                54
                + min(
                    6,
                    j // 2,
                ),
            )

        x = int(
            round(
                self.x
            )
        )

        y = int(
            round(
                self.y
            )
        )

        pulse = (
            int(
                now * 12
            )
            & 1
        )

        body = (
            "<O>",
            "<@>",
        )[pulse]

        fg = (
            231
            if self.flash > 0
            else
            195
            if self.charge > 0
            else 159
        )

        c.text(
            x - 1,
            y,
            body,
            fg,
            True,
        )

        c.put(
            x,
            y - 1,
            "^",
            123,
            True,
        )

        c.put(
            x,
            y + 1,
            "v",
            123,
            True,
        )

        label = (
            "AUTO"
            if self.autopilot
            else "ARROWS"
        )

        c.text(
            max(
                1,
                x - 2,
            ),
            max(
                1,
                y - 2,
            ),
            label,
            87,
        )


# ---------------------------------------------------------------------------
# NEW EFFECT #11
# PRISMATIC COOLANT LEAK
# ---------------------------------------------------------------------------

@dataclass
class CoolDrop:
    x: float
    y: float

    vx: float
    vy: float

    ttl: float

    phase: float

    age: float = 0.0

    split: int = 0


class PrismaticCoolant:
    """
    Highly coloured animated leak.

    Behaviour includes:
        falling streams
        side shear
        vortex mode
        panel collisions
        splitting
        persistent wet trails
    """

    def __init__(
        self,
        rng: random.Random,
    ) -> None:
        self.rng = rng

        self.active_for = 0.0

        self.drops: List[
            CoolDrop
        ] = []

        self.acc = 0.0

        self.source = (
            10.0,
            2.0,
        )

        self.mode = 0

        self.trails: Dict[
            Coord,
            Tuple[
                float,
                int,
            ]
        ] = {}

    @property
    def active(self) -> bool:
        return (
            self.active_for > 0
            or
            bool(
                self.drops
            )
        )

    def trigger(
        self,
        stage: Stage,
    ) -> None:
        self.active_for = max(
            self.active_for,
            self.rng.uniform(
                8,
                15,
            ),
        )

        self.mode = (
            self.mode + 1
        ) % 3

        self.source = (
            self.rng.uniform(
                4,
                stage.w - 5,
            ),
            self.rng.uniform(
                2,
                max(
                    3,
                    stage.hlines[0]
                    - 1,
                ),
            ),
        )

        for _ in range(
            20
        ):
            self._spawn(
                stage
            )

    def _spawn(
        self,
        stage: Stage,
        x: Optional[float] = None,
        y: Optional[float] = None,
        split: int = 0,
    ) -> None:
        if x is None:
            sx, sy = (
                self.source
            )

        else:
            sx = x

            sy = (
                y
                if y is not None
                else self.source[1]
            )

        angle = self.rng.uniform(
            -.45,
            .45,
        )

        speed = self.rng.uniform(
            2,
            7,
        )

        self.drops.append(
            CoolDrop(
                sx,
                sy,

                math.sin(
                    angle
                )
                * speed,

                math.cos(
                    angle
                )
                * speed
                * .7,

                self.rng.uniform(
                    5,
                    12,
                ),

                self.rng.random()
                * math.tau,

                split=split,
            )
        )

        self.drops = (
            self.drops[
                -260:
            ]
        )

    def update(
        self,
        dt: float,
        now: float,
        stage: Stage,
        achars: ACharField,
        moths: RelayMoths,
    ) -> None:
        self.active_for = max(
            0,
            self.active_for
            - dt,
        )

        if self.active_for > 0:
            self.acc += (
                dt * 18
            )

            while self.acc >= 1:
                self.acc -= 1

                self._spawn(
                    stage
                )

        for p in list(
            self.trails
        ):
            ttl, ph = (
                self.trails[p]
            )

            ttl -= dt

            if ttl <= 0:
                self.trails.pop(
                    p,
                    None,
                )

            else:
                self.trails[p] = (
                    ttl,
                    ph,
                )

        alive = []

        for d in self.drops:
            d.age += dt

            if d.age >= d.ttl:
                continue

            if self.mode == 0:
                d.vy += (
                    5 * dt
                )

                d.vx += (
                    math.sin(
                        now * 2
                        + d.phase
                    )
                    * .9
                    * dt
                )

            elif self.mode == 1:
                d.vx += (
                    math.sin(
                        d.y * .4
                        + now * 3
                    )
                    * 2
                    * dt
                )

                d.vy += (
                    2.5 * dt
                )

            else:
                cx = stage.w / 2
                cy = stage.h / 2

                dx = d.x - cx
                dy = (
                    d.y - cy
                ) * 2

                r = (
                    math.hypot(
                        dx,
                        dy,
                    )
                    + .001
                )

                d.vx += (
                    -dy / r
                    * 4
                    * dt
                )

                d.vy += (
                    dx / r
                    * 2
                    * dt
                    + 1.3
                    * dt
                )

            oy = d.y

            d.x += (
                d.vx * dt
            )

            d.y += (
                d.vy * dt
            )

            d.vx *= .994
            d.vy *= .995

            p = (
                int(
                    round(
                        d.x
                    )
                ),
                int(
                    round(
                        d.y
                    )
                ),
            )

            self.trails[p] = (
                self.rng.uniform(
                    .4,
                    1.4,
                ),
                int(
                    d.phase * 10
                ),
            )

            for level in (
                stage.hlines
                +
                [
                    stage.h - 2
                ]
            ):
                if oy < level <= d.y:
                    d.y = (
                        level - 1
                    )

                    d.vy = (
                        -abs(
                            d.vy
                        )
                        * self.rng.uniform(
                            .15,
                            .4,
                        )
                    )

                    d.vx += (
                        self.rng.uniform(
                            -3,
                            3,
                        )
                    )

                    achars.spawn_spark(
                        d.x,
                        d.y,
                        1,
                    )

                    moths.panic_near(
                        d.x,
                        d.y,
                        3,
                    )

                    if (
                        d.split < 1
                        and
                        self.rng.random()
                        < .22
                    ):
                        self._spawn(
                            stage,
                            d.x,
                            d.y,
                            d.split + 1,
                        )

                    break

            if (
                d.x < 1
                or
                d.x
                > stage.w - 2
            ):
                d.x = clamp(
                    d.x,
                    1,
                    stage.w - 2,
                )

                d.vx = (
                    -d.vx
                    * .7
                )

            if d.y < 1:
                d.y = 1
                d.vy = abs(
                    d.vy
                )

            if d.y > stage.h - 2:
                continue

            alive.append(
                d
            )

        self.drops = alive

    def render(
        self,
        c: Canvas,
        now: float,
    ) -> None:
        palette = (
            33,
            39,
            45,
            51,
            87,
            123,
            159,
            195,
            201,
            207,
            213,
            219,
        )

        for (
            x,
            y,
        ), (
            ttl,
            ph,
        ) in self.trails.items():
            c.put(
                x,
                y,
                (
                    "."
                    if ttl < .8
                    else ":"
                ),
                palette[
                    (
                        ph
                        + int(
                            now * 8
                        )
                    )
                    % len(
                        palette
                    )
                ],
            )

        for i, d in enumerate(
            self.drops
        ):
            frame = int(
                now * 14
                + d.phase
                + i
            ) % 4

            glyph = (
                ".",
                "o",
                "O",
                "*",
            )[frame]

            fg = palette[
                (
                    int(
                        d.phase * 7
                    )
                    + frame
                    + int(
                        now * 5
                    )
                )
                % len(
                    palette
                )
            ]

            c.put(
                int(
                    round(
                        d.x
                    )
                ),
                int(
                    round(
                        d.y
                    )
                ),
                glyph,
                fg,
                frame >= 2,
            )

        if self.active:
            sx = int(
                self.source[0]
            )

            sy = int(
                self.source[1]
            )

            c.put(
                sx,
                sy,
                "V",
                219,
                True,
            )

            c.put(
                sx,
                sy + 1,
                "|",
                213,
                True,
            )


# ---------------------------------------------------------------------------
# NEW EFFECT #12
# DIAGNOSTIC AURORA / SCANNER STORM
# ---------------------------------------------------------------------------

@dataclass
class AuroraSpark:
    x: float
    y: float

    vx: float
    vy: float

    ttl: float

    phase: float

    age: float = 0.0


class DiagnosticAurora:
    """
    Large full-screen animated scan waves, coloured ribbons,
    harmonics and spark constellations.
    """

    def __init__(
        self,
        rng: random.Random,
    ) -> None:
        self.rng = rng

        self.active_for = 0.0

        self.phase = 0.0

        self.band_count = 3

        self.sparks: List[
            AuroraSpark
        ] = []

        self.mode = 0

    @property
    def active(self) -> bool:
        return (
            self.active_for > 0
            or
            bool(
                self.sparks
            )
        )

    def trigger(
        self,
        stage: Stage,
    ) -> None:
        self.active_for = max(
            self.active_for,
            self.rng.uniform(
                7,
                14,
            ),
        )

        self.mode = (
            self.mode + 1
        ) % 4

        self.band_count = (
            self.rng.randint(
                2,
                6,
            )
        )

        for _ in range(
            50
        ):
            self.sparks.append(
                AuroraSpark(
                    self.rng.uniform(
                        1,
                        stage.w - 2,
                    ),

                    self.rng.uniform(
                        1,
                        stage.h - 2,
                    ),

                    self.rng.uniform(
                        -2,
                        2,
                    ),

                    self.rng.uniform(
                        -1,
                        1,
                    ),

                    self.rng.uniform(
                        2,
                        6,
                    ),

                    self.rng.random()
                    * math.tau,
                )
            )

    def wave_y(
        self,
        x: float,
        stage: Stage,
        offset: float = 0.0,
    ) -> float:
        if self.mode == 0:
            return (
                stage.h / 2
                +
                math.sin(
                    x * .09
                    + self.phase
                    + offset
                )
                * stage.h
                * .22
            )

        if self.mode == 1:
            return (
                stage.h / 2
                +
                math.sin(
                    x * .17
                    - self.phase * 1.3
                    + offset
                )
                * 4
                +
                math.sin(
                    x * .05
                    + self.phase
                )
                * 5
            )

        if self.mode == 2:
            return (
                stage.h / 2
                +
                math.sin(
                    (
                        x
                        - stage.w / 2
                    )
                    * .12
                    +
                    self.phase
                    +
                    offset
                )
                *
                (
                    3
                    +
                    abs(
                        x
                        - stage.w / 2
                    )
                    * .04
                )
            )

        return (
            stage.h / 2
            +
            math.sin(
                x * .06
                + self.phase
                + offset
            )
            * stage.h
            * .3
            +
            math.sin(
                x * .21
                - self.phase * 2
            )
            * 2
        )

    def update(
        self,
        dt: float,
        stage: Stage,
        achars: ACharField,
        moths: RelayMoths,
        drone: MaintenanceDrone,
    ) -> None:
        self.active_for = max(
            0,
            self.active_for
            - dt,
        )

        self.phase += (
            dt * 2.4
        )

        if (
            self.active_for > 0
            and
            self.rng.random()
            < dt * 12
        ):
            x = self.rng.uniform(
                1,
                stage.w - 2,
            )

            y = self.wave_y(
                x,
                stage,
                self.rng.uniform(
                    -2,
                    2,
                ),
            )

            self.sparks.append(
                AuroraSpark(
                    x,
                    y,

                    self.rng.uniform(
                        -3,
                        3,
                    ),

                    self.rng.uniform(
                        -1.5,
                        1.5,
                    ),

                    self.rng.uniform(
                        1.5,
                        4,
                    ),

                    self.rng.random()
                    * math.tau,
                )
            )

        alive = []

        for s in self.sparks:
            s.age += dt

            if s.age >= s.ttl:
                continue

            target = self.wave_y(
                s.x,
                stage,
                s.phase * .2,
            )

            s.vy += (
                (
                    target
                    - s.y
                )
                * .4
                * dt
            )

            s.vx += (
                math.sin(
                    self.phase
                    + s.phase
                )
                * .3
                * dt
            )

            s.x += (
                s.vx * dt
            )

            s.y += (
                s.vy * dt
            )

            s.vx *= .995
            s.vy *= .99

            if s.x < 1:
                s.x = (
                    stage.w - 2
                )

            elif s.x > stage.w - 2:
                s.x = 1

            s.y = clamp(
                s.y,
                1,
                stage.h - 2,
            )

            alive.append(
                s
            )

        self.sparks = (
            alive[
                -220:
            ]
        )

        if self.active_for > 0:
            if (
                self.rng.random()
                < dt * 5
            ):
                x = self.rng.uniform(
                    1,
                    stage.w - 2,
                )

                y = self.wave_y(
                    x,
                    stage,
                )

                achars.charge_near(
                    x,
                    y,
                    4,
                    .25,
                )

                moths.panic_near(
                    x,
                    y,
                    2.5,
                )

            if drone.active:
                drone.charge = min(
                    1.5,
                    drone.charge
                    + dt * .08,
                )

    def render(
        self,
        c: Canvas,
        stage: Stage,
        now: float,
    ) -> None:
        if not self.active:
            return

        palette = (
            17,
            18,
            19,
            20,
            21,
            27,
            33,
            39,
            45,
            51,
            87,
            123,
            159,
            195,
            201,
            207,
            213,
            219,
        )

        for band in range(
            self.band_count
        ):
            off = (
                band * 1.3
            )

            for x in range(
                1,
                c.w - 1,
            ):
                y = int(
                    round(
                        self.wave_y(
                            x,
                            stage,
                            off,
                        )
                    )
                )

                if (
                    1
                    <= y
                    < c.h - 1
                ):
                    phase = (
                        x
                        + band * 7
                        + int(
                            now * 15
                        )
                    ) % len(
                        palette
                    )

                    ch = (
                        ".",
                        "~",
                        "=",
                        "*",
                        "+",
                    )[
                        (
                            x
                            + band
                            + int(
                                now * 10
                            )
                        )
                        % 5
                    ]

                    c.put(
                        x,
                        y,
                        ch,
                        palette[
                            phase
                        ],
                        ch
                        in (
                            "*",
                            "+",
                        ),
                    )

                    if (
                        band % 2 == 0
                        and
                        y + 1 < c.h - 1
                        and
                        x % 3 == 0
                    ):
                        c.put(
                            x,
                            y + 1,
                            ".",
                            palette[
                                (
                                    phase + 5
                                )
                                % len(
                                    palette
                                )
                            ],
                        )

        for i, s in enumerate(
            self.sparks
        ):
            fg = palette[
                (
                    int(
                        s.phase * 5
                    )
                    + i
                    + int(
                        now * 12
                    )
                )
                % len(
                    palette
                )
            ]

            ch = (
                ".",
                "*",
                "+",
                "o",
            )[
                (
                    i
                    + int(
                        now * 16
                    )
                )
                % 4
            ]

            c.put(
                int(
                    round(
                        s.x
                    )
                ),
                int(
                    round(
                        s.y
                    )
                ),
                ch,
                fg,
                ch
                in (
                    "*",
                    "+",
                ),
            )

        label = (
            " DIAGNOSTIC AURORA "
            "// DISPLAY CALIBRATION ESCALATED INTO WEATHER "
        )

        c.text(
            max(
                1,
                (
                    c.w
                    - len(
                        label
                    )
                )
                // 2,
            ),
            1,
            label[
                :max(
                    0,
                    c.w - 2,
                )
            ],
            123,
            True,
        )


class AmbientScheduler:
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

        self.reset(
            time.monotonic(),
            True,
        )

    def reset(
        self,
        now: float,
        soon: bool = False,
    ) -> None:
        ranges = {
            "g": (
                22,
                70,
            ),
            "b": (
                15,
                50,
            ),
            "t": (
                35,
                95,
            ),
            "m": (
                20,
                65,
            ),
            "c": (
                28,
                75,
            ),
            "l": (
                45,
                130,
            ),
            "o": (
                32,
                90,
            ),
            "f": (
                55,
                160,
            ),
            "x": (
                50,
                150,
            ),
            "d": (
                55,
                150,
            ),
            "v": (
                45,
                120,
            ),
            "z": (
                65,
                180,
            ),
        }

        for k, (
            lo,
            hi,
        ) in ranges.items():
            if soon:
                lo = max(
                    5,
                    lo * .22,
                )

                hi = max(
                    8,
                    hi * .22,
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
    ) -> List[
        str
    ]:
        if not self.enabled:
            return []

        out = []

        ranges = {
            "g": (
                35,
                100,
            ),
            "b": (
                25,
                75,
            ),
            "t": (
                50,
                130,
            ),
            "m": (
                35,
                90,
            ),
            "c": (
                40,
                100,
            ),
            "l": (
                60,
                170,
            ),
            "o": (
                50,
                125,
            ),
            "f": (
                85,
                220,
            ),
            "x": (
                80,
                210,
            ),
            "d": (
                80,
                220,
            ),
            "v": (
                70,
                190,
            ),
            "z": (
                95,
                250,
            ),
        }

        for k, when in list(
            self.next.items()
        ):
            if now >= when:
                out.append(
                    k
                )

                lo, hi = (
                    ranges[
                        k
                    ]
                )

                self.next[k] = (
                    now
                    + self.rng.uniform(
                        lo,
                        hi,
                    )
                )

        return out


class App:
    FPS = 24.0

    def __init__(self) -> None:
        self.rng = random.Random(
            time.time_ns()
            ^ os.getpid()
        )

        size = shutil.get_terminal_size(
            (
                120,
                38,
            )
        )

        self.w = max(
            30,
            size.columns,
        )

        self.h = max(
            16,
            size.lines,
        )

        self.stage = Stage(
            self.w,
            self.h,
        )

        self.input = InputReader()

        self.help = False
        self.running = True

        self.achars = ACharField(
            self.rng
        )

        self.lift = MaintenanceLift(
            self.rng
        )

        self.gremlin = Gremlin(
            self.rng
        )

        self.phantom = PhantomTransmission(
            self.rng
        )

        self.moths = RelayMoths(
            self.rng
        )

        self.crawler = CableCrawler(
            self.rng
        )

        self.ghost = GhostOperator(
            self.rng
        )

        self.lichen = SignalLichen(
            self.rng
        )

        self.arc = ArcStorm(
            self.rng
        )

        self.drone = MaintenanceDrone(
            self.rng
        )

        self.coolant = PrismaticCoolant(
            self.rng
        )

        self.aurora = DiagnosticAurora(
            self.rng
        )

        self.ambient = AmbientScheduler(
            self.rng
        )

        self.last_size = (
            self.w,
            self.h,
        )

    def context(self) -> Dict[
        str,
        bool,
    ]:
        return {
            "gremlin":
                self.gremlin.active,

            "hardware":
                any(
                    a.hardware
                    for a
                    in self.achars.items
                ),

            "moths":
                self.moths.active,

            "crawler":
                self.crawler.active,

            "lift":
                self.lift.active,

            "ghost":
                self.ghost.active,

            "lichen":
                bool(
                    self.lichen.cover
                ),

            "arc":
                self.arc.active,

            "drone":
                self.drone.active,

            "coolant":
                self.coolant.active,

            "aurora":
                self.aurora.active,
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
            self.achars.spill(
                self.stage
            )

        elif key == "t":
            self.phantom.trigger(
                self.context(),
                self.stage,
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

        elif key == "o":
            self.ghost.trigger(
                self.stage
            )

        elif key == "f":
            self.lichen.trigger(
                self.stage
            )

        elif key == "x":
            self.arc.trigger(
                self.stage
            )

        elif key == "d":
            self.drone.trigger(
                self.stage
            )

        elif key == "v":
            self.coolant.trigger(
                self.stage
            )

        elif key == "z":
            self.aurora.trigger(
                self.stage
            )

    def handle_key(
        self,
        key: str,
    ) -> None:
        # Dedicated FX layers.
        if key == "\x18":
            # Ctrl-X
            self.achars.toggle_fx()
            return

        if key == "\x19":
            # Ctrl-Y
            self.moths.toggle_fx(
                self.stage
            )
            return

        if self.achars.handle_fx_key(
            key,
            self.stage,
        ):
            return

        if self.moths.handle_fx_key(
            key,
            self.stage,
        ):
            return

        # Arrow-controlled drone.
        if (
            key
            in (
                "UP",
                "DOWN",
                "LEFT",
                "RIGHT",
            )
            and
            self.drone.active
        ):
            dx, dy = {
                "UP": (
                    0,
                    -1,
                ),
                "DOWN": (
                    0,
                    1,
                ),
                "LEFT": (
                    -1,
                    0,
                ),
                "RIGHT": (
                    1,
                    0,
                ),
            }[
                key
            ]

            self.drone.thrust(
                dx,
                dy,
            )

            return

        if (
            key == " "
            and
            self.drone.active
        ):
            self.drone.pulse(
                self.achars,
                self.moths,
            )

            return

        k = (
            key.lower()
            if len(key) == 1
            else key
        )

        if k == "q":
            self.running = False

        elif key == "?":
            self.help = (
                not self.help
            )

        elif k == "a":
            self.ambient.enabled = (
                not self.ambient.enabled
            )

        elif k == "r":
            self.trigger(
                self.rng.choice(
                    list(
                        "gbtmclofxdvz"
                    )
                )
            )

        elif (
            k == "h"
            and
            self.drone.active
        ):
            self.drone.toggle_autopilot(
                self.stage
            )

        elif k in "gbtmclofxdvz":
            self.trigger(
                k
            )

    def resize(self) -> None:
        size = shutil.get_terminal_size(
            (
                120,
                38,
            )
        )

        w = max(
            30,
            size.columns,
        )

        h = max(
            16,
            size.lines,
        )

        if (
            (
                w,
                h,
            )
            == self.last_size
        ):
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

        self.gremlin.state = "hidden"
        self.crawler.active = False
        self.lift.state = "hidden"
        self.ghost.active = False

        self.arc.arcs = []
        self.arc.active_for = 0

        self.drone.active = False

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

        self.lichen.cover = {
            p: v
            for p, v
            in self.lichen.cover.items()
            if p in self.stage.graph
        }

    def update(
        self,
        dt: float,
        now: float,
    ) -> None:
        for key in self.ambient.due(
            now
        ):
            self.trigger(
                key
            )

        self.achars.update(
            dt,
            self.stage,
            now,
        )

        self.lift.update(
            dt,
            self.stage,
            self.achars,
        )

        self.drone.update(
            dt,
            self.stage,
            self.achars,
            self.moths,
            self.lichen,
        )

        self.gremlin.update(
            dt,
            self.stage,
            self.achars,
            self.lift,
            self.drone,
        )

        self.phantom.update(
            dt
        )

        self.coolant.update(
            dt,
            now,
            self.stage,
            self.achars,
            self.moths,
        )

        self.lichen.update(
            dt,
            self.stage,
            self.crawler,
            self.coolant,
        )

        self.crawler.update(
            dt,
            self.stage,
            self.achars,
            self.lichen,
        )

        self.ghost.update(
            dt,
            self.stage,
            self.achars,
        )

        self.arc.update(
            dt,
            self.stage,
            self.achars,
            self.moths,
            self.lichen,
            self.drone,
        )

        self.aurora.update(
            dt,
            self.stage,
            self.achars,
            self.moths,
            self.drone,
        )

        self.moths.update(
            dt,
            now,
            self.stage,
            self.gremlin,
            self.achars,
            self.phantom,
            self.arc.points(),
            self.drone,
            self.aurora,
        )

    def help_overlay(
        self,
        c: Canvas,
    ) -> None:
        width = min(
            c.w - 6,
            92,
        )

        height = min(
            c.h - 6,
            28,
        )

        x = max(
            2,
            (
                c.w
                - width
            )
            // 2,
        )

        y = max(
            2,
            (
                c.h
                - height
            )
            // 2,
        )

        c.box(
            x,
            y,
            width,
            height,
            159,
        )

        lines = [
            "MAINTENANCE ECOSYSTEM V3 // OVERDRIVE // CHEAT SHEET",

            "",

            "G gremlin        B loose hardware       T phantom radio",

            "M relay moths    C cable crawler        L unauthorized lift",

            "O ghost operator F signal lichen        X arc storm",

            "D DRONE          V prismatic coolant    Z diagnostic aurora",

            "",

            "DRONE: D deploy/recall | ARROWS thrust | Space boost pulse | H autopilot/hold",

            "",

            "Ctrl-X  aChar FX layer",

            "  Space burst | +/- rate | [/] family | D emitter | V field | K collision | P palette | R random",

            "",

            "Ctrl-Y  MOTH FX layer",

            "  Space swarm burst | +/- population | [/] formation | V turbulence | P palette | R random",

            "",

            "V3 interaction highlights:",

            "  drone wash scatters moths, charges nearby aChars and scrapes lichen",

            "  coolant splashes from console rails and fluoresces lichen",

            "  aurora scan-fronts excite aChars, moths and the drone across the whole terminal",

            "  moth FX formations: orbit / ribbon / vortex / lattice / comet / pulse",

            "  gremlin still hunts bolts, climbs the topology and can ride the lift",

            "  crawler repairs divider gaps and stimulates lichen; arcs burn it back",

            "",

            "A ambient on/off   R random event   ? close help   Q quit",
        ]

        for i, line in enumerate(
            lines[
                :height - 2
            ]
        ):
            c.text(
                x + 2,
                y + 1 + i,
                line,
                (
                    159
                    if i == 0
                    else 250
                ),
                i == 0,
                width - 4,
            )

    def draw(
        self,
        now: float,
    ) -> str:
        c = Canvas(
            self.w,
            self.h,
        )

        self.stage.render(
            c,
            now,
            self.ambient.enabled,
        )

        # Low / background visual layers.
        self.aurora.render(
            c,
            self.stage,
            now,
        )

        self.lichen.render(
            c,
            now,
        )

        self.coolant.render(
            c,
            now,
        )

        self.crawler.render(
            c,
            now,
        )

        self.achars.render(
            c
        )

        self.moths.render(
            c,
            now,
        )

        # Creature / foreground layers.
        self.lift.render(
            c,
            self.stage,
            now,
        )

        self.gremlin.render(
            c,
            self.stage,
            now,
        )

        self.drone.render(
            c,
            now,
        )

        self.ghost.render(
            c,
            now,
        )

        self.arc.render(
            c,
            now,
        )

        self.phantom.render(
            c,
            self.stage,
        )

        if self.help:
            self.help_overlay(
                c
            )

        return c.render()

    def run(self) -> None:
        frame_time = (
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

        last = time.monotonic()

        try:
            while self.running:
                start = (
                    time.monotonic()
                )

                self.resize()

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
                    .1,
                    max(
                        0,
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

                if elapsed < frame_time:
                    time.sleep(
                        frame_time
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

        raise SystemExit(
            2
        )

    App().run()


if __name__ == "__main__":
    main()
   