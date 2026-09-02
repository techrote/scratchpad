#!/usr/bin/env python3
"""
MAINTENANCE ECOSYSTEM MK II
===========================

Nine interacting terminal-only easter-eggs/effects.
No PlasmaRack functionality.

Dependency-free.
Windows Terminal first-class.
POSIX terminals are also supported.

MAIN KEYS
---------
G  Gremlin MK II
B  Loose hardware / aChar spill
T  Phantom maintenance transmission
M  Relay moth swarm
C  Cable crawler
L  Unauthorized maintenance lift

O  Ghost operator cursor          [NEW]
F  Signal lichen bloom            [NEW]
X  Arc-storm / relay discharge    [NEW]

R  Random effect
A  Toggle ambient automatic events

Ctrl-X
   Toggle aChar FX layer

?
   Help

Q
   Quit


ACHAR FX LAYER
--------------
Space
    burst

+/-
    spawn rate

[/]
    previous/next aChar family

D
    emitter geometry

V
    velocity field

K
    collision mode

P
    palette phase

R
    randomize FX setup

Esc
    close FX layer


ORIGINAL SIX: MK II IMPROVEMENTS
--------------------------------

1. GREMLIN
   - genuinely follows divider/cable topology
   - hunts settled bolts and washers
   - collects loose hardware
   - multiple traversal moods
   - climbing / walking / sleeping poses
   - longer autonomous excursions
   - can hitch-hike the maintenance lift
   - returns through the hatch
   - reacts to changing maintenance world

2. aCHAR / LOOSE HARDWARE SYSTEM
   - 10 character families
   - hundreds of simultaneous aChars
   - horizontal, vertical, radial, ring and line emitters
   - configurable vector/velocity fields
   - wrap / reflect / damp collision modes
   - animated LUT colour
   - charge state from electrical events
   - persistent trails
   - multi-origin hardware showers
   - original loose-bolt joke remains available with B

3. PHANTOM MAINTENANCE TRANSMISSION
   - carrier-acquisition phase
   - signal-strength drift
   - type-on reception
   - multiple fragments / replies
   - contextual messages based on other active effects
   - radio beacon can attract relay moths
   - controlled corruption at poor signal strength
   - fades back into ordinary telemetry

4. RELAY MOTHS
   - larger swarms
   - lamp attraction
   - crude orbital/flocking motion
   - resting / roosting
   - panic state
   - flee gremlin
   - react to nearby aChars
   - attracted toward active phantom-radio beacon
   - violently flee arc discharges

5. CABLE CRAWLER
   - longer multi-hop journeys
   - graph-topology traversal
   - persistent phosphor tail
   - junction echoes
   - emits sparks
   - repairs broken divider cells temporarily
   - stimulates signal lichen while passing

6. UNAUTHORIZED MAINTENANCE LIFT
   - multi-stop trips
   - extra calls can be queued while moving
   - animated doors
   - call lamp
   - random cargo
   - contextual cargo from gremlin's bolt collection
   - can accidentally release hardware
   - gremlin can ride it
   - still has absolutely no permit


NEW EFFECTS
-----------

7. GHOST OPERATOR
   An impossible second operator cursor appears,
   traverses the panel, selects decorative nodes,
   leaves phosphor afterimages and energizes nearby
   aChars when it "clicks".

8. SIGNAL LICHEN
   Glyph colonies spread along actual console
   divider topology. The crawler stimulates it.
   Arc storms burn it back. It grows, thickens,
   fluoresces and eventually becomes self-limiting.

9. ARC STORM
   Electrical discharges jump between lamps and
   graph junctions. They charge nearby aChars,
   panic moths, burn signal lichen and create a
   much more alarming-looking machine.


All systems are cosmetic/presentation-only.
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
from typing import (
    Deque,
    Dict,
    Iterable,
    List,
    Optional,
    Sequence,
    Set,
    Tuple,
)


# ---------------------------------------------------------------------------
# ANSI
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def clamp(
    v: float,
    lo: float,
    hi: float,
) -> float:
    return (
        lo
        if v < lo
        else hi
        if v > hi
        else v
    )


def sign(
    v: float,
) -> int:
    return (
        (v > 0)
        - (v < 0)
    )


def manhattan(
    a: Coord,
    b: Coord,
) -> int:
    return (
        abs(a[0] - b[0])
        + abs(a[1] - b[1])
    )


# ---------------------------------------------------------------------------
# INPUT
# ---------------------------------------------------------------------------

class InputReader:
    """
    Non-blocking keyboard input.

    Windows:
        msvcrt

    POSIX:
        cbreak terminal + select
    """

    def __init__(
        self,
    ) -> None:
        self.is_windows = (
            os.name == "nt"
        )

        self._old_term = None

        if self.is_windows:
            self._enable_vt()

        else:
            import termios
            import tty

            self._termios = termios
            self._tty = tty

            if sys.stdin.isatty():
                self._old_term = (
                    termios.tcgetattr(
                        sys.stdin.fileno()
                    )
                )

                tty.setcbreak(
                    sys.stdin.fileno()
                )

    def _enable_vt(
        self,
    ) -> None:
        try:
            import ctypes
            from ctypes import wintypes

            k32 = (
                ctypes.windll.kernel32
            )

            handle = (
                k32.GetStdHandle(
                    -11
                )
            )

            mode = (
                wintypes.DWORD()
            )

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

    def read_keys(
        self,
    ) -> List[str]:
        out: List[str] = []

        if self.is_windows:
            import msvcrt

            while msvcrt.kbhit():
                ch = (
                    msvcrt.getwch()
                )

                if ch in (
                    "\x00",
                    "\xe0",
                ):
                    if msvcrt.kbhit():
                        msvcrt.getwch()

                    continue

                out.append(
                    ch
                )

            return out

        import select

        while True:
            ready, _, _ = (
                select.select(
                    [sys.stdin],
                    [],
                    [],
                    0,
                )
            )

            if not ready:
                break

            ch = sys.stdin.read(
                1
            )

            if not ch:
                break

            out.append(
                ch
            )

        return out

    def close(
        self,
    ) -> None:
        if (
            not self.is_windows
            and self._old_term
            is not None
        ):
            try:
                self._termios.tcsetattr(
                    sys.stdin.fileno(),
                    self._termios.TCSADRAIN,
                    self._old_term,
                )

            except Exception:
                pass


# ---------------------------------------------------------------------------
# CANVAS
# ---------------------------------------------------------------------------

class Canvas:
    """
    Simple terminal-cell framebuffer.

    Stores:
        character
        256-colour foreground
        bold state

    Then emits one synchronized terminal frame.
    """

    def __init__(
        self,
        w: int,
        h: int,
    ) -> None:
        self.w = w
        self.h = h

        n = (
            w * h
        )

        self.chars = (
            [" "] * n
        )

        self.fg: List[
            Optional[int]
        ] = (
            [None] * n
        )

        self.bold = (
            [False] * n
        )

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

            self.chars[i] = (
                ch[0]
            )

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
            or h < 2
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

    def render(
        self,
    ) -> str:
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

                fg = (
                    self.fg[i]
                )

                bold = (
                    self.bold[i]
                )

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

            if (
                y
                != self.h - 1
            ):
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


# ---------------------------------------------------------------------------
# SHARED INDUSTRIAL STAGE / TOPOLOGY
# ---------------------------------------------------------------------------

class Stage:
    """
    Shared industrial geometry.

    Several inhabitants use the same real terminal-cell graph:

        Gremlin
        Cable Crawler
        Signal Lichen
        Arc Storm junction selection

    Thus the apparent scenery is also the world's navigation topology.
    """

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

        # Main horizontal rails.
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

        # Main vertical rails.
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

        # Internal branch.
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

        # Two short auxiliary rails.
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
                        x1 - 7,
                    ),
                    min(
                        w - 2,
                        x1 + 8,
                    ),
                ):
                    self.graph.add(
                        (
                            x,
                            y,
                        )
                    )

        # Deliberately broken divider/wire cells.
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

        if not self.junctions:
            stride = max(
                1,
                len(
                    self.graph_list
                )
                // 12,
            )

            self.junctions = list(
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

        # Targets for the ghost operator.
        self.control_nodes = []

        for x, y in self.lamps:
            self.control_nodes.extend(
                [
                    (
                        x,
                        y,
                    ),
                    (
                        x + 2
                        if x + 2
                        < w - 2
                        else x - 2,
                        y,
                    ),
                ]
            )

        stride = max(
            1,
            len(
                self.junctions
            )
            // 8,
        )

        self.control_nodes.extend(
            self.junctions[
                ::stride
            ]
        )

        self.control_nodes = [
            p
            for p
            in self.control_nodes
            if (
                1
                <= p[0]
                < w - 1
                and
                1
                <= p[1]
                < h - 1
            )
        ]

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

        queue: Deque[
            Coord
        ] = deque(
            [
                start
            ]
        )

        previous: Dict[
            Coord,
            Optional[Coord],
        ] = {
            start: None
        }

        while queue:
            p = (
                queue.popleft()
            )

            if p == goal:
                break

            for n in self.neighbors(
                p
            ):
                if (
                    n
                    not in previous
                ):
                    previous[n] = p

                    queue.append(
                        n
                    )

        if (
            goal
            not in previous
        ):
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

            p = previous[p]

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
            or [start]
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

        title = (
            " MAINTENANCE ECOSYSTEM MK II "
            "// NINE THINGS WRONG WITH ONE CONSOLE "
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
            self.hlines[1]
            + 4,
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
                "AUX MAINT // PRESENTATION LAYER ONLY",
            ),
            (
                self.vlines[0] + 2,
                2,
                "BAY 13 EXISTS WHEN OBSERVED",
            ),
            (
                self.vlines[1] + 2,
                2,
                "LIFT AUTHORITY: NONE",
            ),
            (
                2,
                self.hlines[0] + 2,
                "loose hardware expected",
            ),
            (
                self.vlines[0] + 2,
                self.hlines[0] + 2,
                "relay moth load: nonzero",
            ),
            (
                self.vlines[1] + 2,
                self.hlines[0] + 2,
                "ghost cursor not billable",
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
                    2.0
                    + i * 0.17
                )
            ) % 5

            fg = (
                82,
                83,
                119,
                120,
                156,
            )[pulse]

            c.put(
                x,
                y,
                "o",
                fg,
                pulse == 4,
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
            f"{'ON' if ambient else 'OFF'}"
            "  G/B/T/M/C/L/O/F/X effects"
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


# ---------------------------------------------------------------------------
# ACHAR ENGINE
# ---------------------------------------------------------------------------

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
            maxlen=10
        )
    )


class ACharField:
    """
    Generalized character-particle engine.

    The original falling bolt is now simply one preset of this system.
    """

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
        ]

        self.items: List[
            AChar
        ] = []

        self.fx_mode = False

        self.spawn_rate = 6.0
        self.spawn_acc = 0.0

        self.selected_kind = 4
        self.direction_i = 4
        self.field_i = 0
        self.collision_i = 0

        self.palette_phase = 0

        self.max_items = 260

        self.directions = [
            "DOWN",
            "UP",
            "LEFT",
            "RIGHT",
            "MIXED",
            "RADIAL",
            "RING",
            "LINE",
        ]

        self.fields = [
            "NONE",
            "SWIRL",
            "SHEAR",
            "WAVE",
            "ATTRACT",
            "REPEL",
        ]

        self.collisions = [
            "WRAP",
            "REFLECT",
            "DAMP",
        ]

    def toggle_fx(
        self,
    ) -> None:
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
                    x=x,
                    y=y,

                    vx=self.rng.uniform(
                        -6,
                        6,
                    ),

                    vy=self.rng.uniform(
                        -5,
                        1,
                    ),

                    kind=3,

                    ttl=self.rng.uniform(
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
        """
        Original Easter Egg #2, heavily expanded.

        Multiple hardware origins produce a genuine little debris shower.
        """

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
                8,
                18,
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
                    x=clamp(
                        x,
                        2,
                        stage.w - 3,
                    ),

                    y=self.rng.uniform(
                        1,
                        max(
                            2,
                            stage.hlines[0]
                            - 1,
                        ),
                    ),

                    vx=self.rng.uniform(
                        -4.2,
                        4.2,
                    ),

                    vy=self.rng.uniform(
                        -2.5,
                        2.0,
                    ),

                    kind=kind,

                    ttl=self.rng.uniform(
                        10,
                        24,
                    ),

                    phase=(
                        self.rng.random()
                        * 8
                    ),

                    hardware=(
                        kind in (
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

        speed = (
            self.rng.uniform(
                4.0,
                13.0,
            )
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
            y = (
                stage.h - 3
            )

            vy = -speed

        elif mode == "LEFT":
            x = (
                stage.w - 3
            )

            vx = -speed

        elif mode == "RIGHT":
            x = 2
            vx = speed

        elif mode == "RADIAL":
            x = (
                stage.w / 2
            )

            y = (
                stage.h / 2
            )

            angle = (
                self.rng.random()
                * math.tau
            )

            vx = (
                math.cos(
                    angle
                )
                * speed
            )

            vy = (
                math.sin(
                    angle
                )
                * speed
                * .55
            )

        elif mode == "RING":
            angle = (
                self.rng.random()
                * math.tau
            )

            radius = (
                min(
                    stage.w,
                    stage.h * 2,
                )
                * .28
            )

            x = (
                stage.w / 2
                + math.cos(
                    angle
                )
                * radius
            )

            y = (
                stage.h / 2
                + math.sin(
                    angle
                )
                * radius
                * .5
            )

            vx = (
                -math.sin(
                    angle
                )
                * speed
            )

            vy = (
                math.cos(
                    angle
                )
                * speed
                * .45
            )

        elif mode == "LINE":
            y = (
                self.rng.choice(
                    stage.hlines
                )
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

        else:
            angle = (
                self.rng.random()
                * math.tau
            )

            vx = (
                math.cos(
                    angle
                )
                * speed
            )

            vy = (
                math.sin(
                    angle
                )
                * speed
                * .55
            )

        self.add(
            AChar(
                x=x,
                y=y,

                vx=vx,
                vy=vy,

                kind=self.selected_kind,

                ttl=self.rng.uniform(
                    6,
                    16,
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
        count: int = 30,
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

        k = key.lower()

        if key == " ":
            self.burst(
                stage
            )

        elif key in (
            "+",
            "=",
        ):
            self.spawn_rate = min(
                60.0,
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
            ) % 64

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
                    2,
                    28,
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

    def charge_near(
        self,
        x: float,
        y: float,
        radius: float = 7.0,
        amount: float = 1.0,
    ) -> None:
        radius_sq = (
            radius * radius
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
                <= radius_sq
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
        keep = []
        collected = 0

        for a in self.items:
            if (
                a.hardware
                and
                a.settled
                and
                (
                    abs(
                        a.x - x
                    )
                    +
                    abs(
                        a.y - y
                    )
                    <= radius
                )
            ):
                collected += 1

            else:
                keep.append(
                    a
                )

        self.items = keep

        return collected

    def nearest_settled_hardware(
        self,
        p: Coord,
        max_d: int = 40,
    ) -> Optional[
        Coord
    ]:
        best: Optional[
            Coord
        ] = None

        best_distance = (
            max_d + 1
        )

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

            if d < best_distance:
                best_distance = d
                best = q

        return best

    def disturbance_near(
        self,
        x: float,
        y: float,
        radius: float = 5.0,
    ) -> float:
        radius_sq = (
            radius * radius
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
                    <= radius_sq
                )
            )
        )

    def _apply_field(
        self,
        a: AChar,
        dt: float,
        stage: Stage,
    ) -> None:
        mode = (
            self.fields[
                self.field_i
            ]
        )

        cx = (
            stage.w / 2
        )

        cy = (
            stage.h / 2
        )

        dx = (
            a.x - cx
        )

        dy = (
            a.y - cy
        ) * 1.8

        radius = (
            math.hypot(
                dx,
                dy,
            )
            + .001
        )

        now = (
            time.monotonic()
        )

        if mode == "SWIRL":
            a.vx += (
                -dy
                / radius
                * 4.0
                * dt
            )

            a.vy += (
                dx
                / radius
                * 2.0
                * dt
            )

        elif mode == "SHEAR":
            a.vx += (
                math.sin(
                    a.y * .23
                    + now * 1.2
                )
                * 3.0
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
                -dx
                / radius
                * 4.5
                * dt
            )

            a.vy += (
                -dy
                / radius
                * 2.2
                * dt
            )

        elif mode == "REPEL":
            a.vx += (
                dx
                / radius
                * 4.5
                * dt
            )

            a.vy += (
                dy
                / radius
                * 2.2
                * dt
            )

    def update(
        self,
        dt: float,
        stage: Stage,
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
            )

            a.vy += (
                kind.gravity
                * dt
            )

            a.vx *= (
                kind.drag
            )

            a.vy *= (
                kind.drag
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

            # Physical hardware collides with panel rails.
            if (
                a.hardware
                and
                a.vy > 0
            ):
                levels = (
                    list(
                        stage.hlines
                    )
                    +
                    [
                        stage.h - 2
                    ]
                )

                for level in levels:
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
                                .24,
                                .48,
                            )
                        )

                        a.vx *= .72

                        a.bounces += 1

                        if (
                            abs(
                                a.vy
                            )
                            < 1.0
                            or
                            a.bounces
                            >= 4
                        ):
                            a.settled = True

                            a.vx = 0.0
                            a.vy = 0.0

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
                    damping = (
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
                            * damping
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
                            * damping
                        )

            else:
                a.x = clamp(
                    a.x,
                    1,
                    stage.w - 2,
                )

                if (
                    a.y
                    > stage.h - 2
                ):
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
                )[1:6],
                start=1,
            ):
                if not a.settled:
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
                )[
                    int(
                        a.charge
                        * 7
                    )
                    % 5
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
                    a.charge > .4
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
                f"emit={self.directions[self.direction_i]:<6} "
                f"field={self.fields[self.field_i]:<7} "
                f"coll={self.collisions[self.collision_i]:<7} "
                f"rate={self.spawn_rate:04.1f}/s  "
                "[ ] type  "
                "D emit  "
                "V field  "
                "K collide  "
                "P palette  "
                "+/- rate  "
                "Space burst  "
                "R random  "
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


# ---------------------------------------------------------------------------
# GREMLIN MK II
# ---------------------------------------------------------------------------

class Gremlin:
    """
    Robot gremlin MK II.

    Improvements:
        - actual topology traversal
        - hardware hunting
        - collecting
        - mood states
        - sleeping
        - climbing poses
        - lift hitch-hiking
    """

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
    def active(
        self,
    ) -> bool:
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
                    )
                )
            )

            return

        self.state = "opening"
        self.timer = 0.0

        self.pos = (
            stage.hatch
        )

        self.journeys = (
            self.rng.randint(
                3,
                6,
            )
        )

        self.mood = (
            self.rng.choice(
                (
                    "curious",
                    "busy",
                    "suspicious",
                )
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

        if (
            goal
            not in stage.graph
            and
            stage.graph_list
        ):
            goal = min(
                stage.graph_list,
                key=lambda p: manhattan(
                    p,
                    goal,
                ),
            )

        self.route = (
            stage.path(
                start,
                goal,
            )
            or
            [start]
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
                self.pos,
                45,
            )
        )

        if (
            hardware
            and
            self.rng.random()
            < .72
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
    ) -> None:
        if (
            self.state
            == "hidden"
        ):
            return

        self.timer += dt

        if (
            self.state
            == "opening"
        ):
            if (
                self.timer
                >= .8
            ):
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

        if (
            self.state
            == "closing"
        ):
            if (
                self.timer
                >= .7
            ):
                self.state = (
                    "hidden"
                )

                self.timer = 0.0

            return

        if (
            self.state
            == "nap"
        ):
            if (
                self.timer
                >= self.rng.uniform(
                    .6,
                    1.4,
                )
            ):
                self.timer = 0.0

                if (
                    self.journeys
                    > 0
                ):
                    self.journeys -= 1

                    self.state = (
                        "explore"
                    )

                    self._route_to(
                        stage,
                        self._choose_goal(
                            stage,
                            achars,
                        ),
                    )

                else:
                    self.state = (
                        "return"
                    )

                    self._route_to(
                        stage,
                        stage.hatch,
                    )

            return

        # The gremlin may board the lift while their paths cross.
        if (
            lift.active
            and
            self.state
            == "explore"
        ):
            lx = (
                stage.shaft_x
            )

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
                self.state = (
                    "riding"
                )

                self.ride_offset = (
                    self.pos[1]
                    - ly
                )

                self.mood = (
                    "commuting"
                )

                return

        if (
            self.state
            == "riding"
        ):
            if not lift.active:
                self.state = (
                    "explore"
                )

                if stage.graph_list:
                    self.pos = min(
                        stage.graph_list,
                        key=lambda p: manhattan(
                            p,
                            self.pos,
                        ),
                    )

                else:
                    self.pos = (
                        stage.hatch
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
                lift.state
                == "dwell"
                and
                self.rng.random()
                < .035
            ):
                self.state = (
                    "explore"
                )

                if stage.graph_list:
                    self.pos = min(
                        stage.graph_list,
                        key=lambda p: manhattan(
                            p,
                            self.pos,
                        ),
                    )

                else:
                    self.pos = (
                        stage.hatch
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
                stage.hatch
                if self.state
                == "return"
                else self._choose_goal(
                    stage,
                    achars,
                ),
            )

        self.acc += (
            dt * 10.5
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

            if dx > 0:
                self.facing = (
                    "right"
                )

            elif dx < 0:
                self.facing = (
                    "left"
                )

            elif dy:
                self.facing = (
                    "climb"
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
                self.state
                == "return"
                and
                self.pos
                == stage.hatch
            ):
                self.state = (
                    "closing"
                )

                self.timer = 0.0

            else:
                self.state = (
                    "nap"
                )

                self.timer = 0.0

    def render(
        self,
        c: Canvas,
        stage: Stage,
        now: float,
    ) -> None:
        hx, hy = (
            stage.hatch
        )

        if (
            self.state
            == "hidden"
        ):
            return

        if self.state in (
            "opening",
            "closing",
        ):
            sequence = [
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

            if (
                self.state
                == "closing"
            ):
                phase = (
                    3 - phase
                )

            c.text(
                max(
                    1,
                    hx - 3,
                ),
                hy,
                sequence[
                    phase
                ],
                220,
                True,
            )

            if (
                self.state
                == "opening"
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
                now * 7
            )
            & 1
        )

        if (
            self.state
            == "nap"
        ):
            sprite = (
                (
                    " z ",
                    "_o_",
                    "/|\\",
                )
                if bob
                else
                (
                    " Z ",
                    "_o_",
                    "/|\\",
                )
            )

        elif (
            self.facing
            == "climb"
        ):
            sprite = (
                (
                    " o ",
                    "/|\\",
                    "^ ^",
                )
                if bob
                else
                (
                    " o ",
                    "\\|/",
                    "v v",
                )
            )

        elif (
            self.facing
            == "left"
        ):
            sprite = (
                (
                    "_o ",
                    "<|>",
                    "/ \\",
                )
                if bob
                else
                (
                    " o_",
                    "<|>",
                    "/ \\",
                )
            )

        else:
            sprite = (
                (
                    " o_",
                    "<|>",
                    "/ \\",
                )
                if bob
                else
                (
                    "_o ",
                    "<|>",
                    "/ \\",
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
            self.mood
            and
            int(
                now * 2
            )
            % 9
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
                    :12
                ],
                179,
            )


# ---------------------------------------------------------------------------
# PHANTOM TRANSMISSION MK II
# ---------------------------------------------------------------------------

class PhantomTransmission:
    BASE = [
        "GROUND WAS OPTIONAL, APPARENTLY.",
        "THE FUTURE FAILED ITS CONTINUITY TEST.",
        "NO FAULT FOUND. MORALE REPLACED.",
        "THE MACHINE DENIES KNOWING YOU.",
        "BAY 13 REQUESTS A BETTER BAY 13.",
        "PLEASE STOP NAMING THE FAULTS. THEY RESPOND TO IT.",
        "WE HAVE ISOLATED THE PROBLEM TO EVERYTHING AFTER TUESDAY.",
        "CHANNEL CLEAR. SITUATION LESS SO.",
        "DO NOT TRUST A CONNECTOR THAT LOOKS CONFIDENT.",
        "THE NIGHT SHIFT LEFT US A NOTE. IT JUST SAYS 'NO'.",
        "AUX POWER REPORTS IT IS DOING ITS BEST.",
        "THE CORRIDOR MAP HAS FILED FOR INDEPENDENCE.",
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
    def active(
        self,
    ) -> bool:
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

        if context.get(
            "gremlin"
        ):
            contextual.append(
                "SMALL UNIT OUT OF HATCH AGAIN. DO NOT ENCOURAGE IT."
            )

        if context.get(
            "hardware"
        ):
            contextual.append(
                "STORES: SEND BOLTS. APPARENTLY ALL OF THEM."
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

        if context.get(
            "ghost"
        ):
            contextual.append(
                "WE CAN SEE THE CURSOR. THERE IS NO OPERATOR LOGGED IN."
            )

        if context.get(
            "lichen"
        ):
            contextual.append(
                "GREEN GROWTH ON BUS 4. BUS 4 CLAIMS IT IS DECORATIVE."
            )

        if context.get(
            "arc"
        ):
            contextual.append(
                "DISCHARGE EVENT CLOSED AS WEATHER. THIS IS INDOORS."
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
            < .58
        ):
            self.fragments.append(
                self.rng.choice(
                    self.REPLIES
                )
            )

        if (
            self.rng.random()
            < .25
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

        self.state = (
            "acquire"
        )

        self.timer = 0.0

    def update(
        self,
        dt: float,
    ) -> None:
        if (
            self.state
            == "idle"
        ):
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
            self.state
            == "acquire"
            and
            self.timer
            >= 1.0
        ):
            self.state = (
                "identify"
            )

            self.timer = 0.0

        elif (
            self.state
            == "identify"
            and
            self.timer
            >= 1.0
        ):
            self.state = (
                "message"
            )

            self.timer = 0.0

        elif (
            self.state
            == "message"
            and
            self.timer
            >= 4.4
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
                self.state = (
                    "fade"
                )

                self.timer = 0.0

        elif (
            self.state
            == "fade"
            and
            self.timer
            >= 1.4
        ):
            self.state = (
                "idle"
            )

            self.timer = 0.0

    def _corrupt(
        self,
        s: str,
        intensity: float,
    ) -> str:
        local = (
            random.Random(
                int(
                    self.timer
                    * 9
                )
                +
                self.frag_i
                * 1009
                +
                len(
                    s
                )
                * 31
            )
        )

        replacements = (
            "#?./:-_"
        )

        return "".join(
            local.choice(
                replacements
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
        if (
            self.state
            == "idle"
        ):
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
            y + 5
            >= c.h
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

        if (
            self.state
            == "acquire"
        ):
            dots = (
                "."
                * (
                    1
                    + int(
                        self.timer
                        * 6
                    )
                    % 7
                )
            )

            c.text(
                x + 2,
                y + 1,
                self._corrupt(
                    "carrier search // wrong wire"
                    + dots,
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

        if (
            self.state
            == "identify"
        ):
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
            if self.state
            == "fade"
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

        shown = self._corrupt(
            message[
                :reveal
            ],
            (
                1
                - self.strength
            )
            * .12,
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


# ---------------------------------------------------------------------------
# RELAY MOTHS MK II
# ---------------------------------------------------------------------------

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


class RelayMoths:
    def __init__(
        self,
        rng: random.Random,
    ) -> None:
        self.rng = rng

        self.moths: List[
            Moth
        ] = []

        self.max_moths = 90

    @property
    def active(
        self,
    ) -> bool:
        return bool(
            self.moths
        )

    def trigger(
        self,
        stage: Stage,
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

        for _ in range(
            self.rng.randint(
                18,
                36,
            )
        ):
            angle = (
                self.rng.random()
                * math.tau
            )

            radius = (
                self.rng.uniform(
                    1,
                    9,
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
                        * .5
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

                    age=0.0,

                    ttl=self.rng.uniform(
                        16,
                        36,
                    ),
                )
            )

        self.moths = (
            self.moths[
                -self.max_moths:
            ]
        )

    def panic_near(
        self,
        x: float,
        y: float,
        radius: float = 9.0,
    ) -> None:
        radius_sq = (
            radius * radius
        )

        for moth in self.moths:
            if (
                (
                    moth.x - x
                )
                ** 2
                +
                (
                    moth.y - y
                )
                ** 2
                <= radius_sq
            ):
                moth.panic = 1.6

    def update(
        self,
        dt: float,
        stage: Stage,
        gremlin: Gremlin,
        achars: ACharField,
        phantom: PhantomTransmission,
        arc_points: Sequence[
            Coord
        ],
    ) -> None:
        alive = []

        for moth in self.moths:
            moth.age += dt

            moth.panic = max(
                0.0,
                moth.panic - dt,
            )

            if (
                moth.age
                >= moth.ttl
            ):
                continue

            if (
                moth.target
                >= len(
                    stage.lamps
                )
            ):
                moth.target = 0

            tx, ty = (
                stage.lamps[
                    moth.target
                ]
            )

            # Active radio signals occasionally become the dominant light.
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

            dx = (
                tx - moth.x
            )

            dy = (
                ty - moth.y
            )

            distance = (
                math.hypot(
                    dx,
                    dy,
                )
                + .001
            )

            # Lamp attraction plus tangential orbit.
            ax = (
                dx
                / distance
                * 5
                +
                (
                    -dy
                    / distance
                )
                * 2.2
            )

            ay = (
                dy
                / distance
                * 3
                +
                (
                    dx
                    / distance
                )
                * 1.2
            )

            # Gremlin avoidance.
            if gremlin.active:
                gx, gy = (
                    gremlin.pos
                )

                rx = (
                    moth.x - gx
                )

                ry = (
                    moth.y - gy
                )

                gd = (
                    math.hypot(
                        rx,
                        ry,
                    )
                    + .001
                )

                if gd < 10:
                    ax += (
                        rx
                        / gd
                        * (
                            28 / gd
                        )
                    )

                    ay += (
                        ry
                        / gd
                        * (
                            18 / gd
                        )
                    )

                    moth.panic = max(
                        moth.panic,
                        .6,
                    )

            # Arc avoidance.
            for px, py in arc_points:
                rx = (
                    moth.x - px
                )

                ry = (
                    moth.y - py
                )

                rd = (
                    math.hypot(
                        rx,
                        ry,
                    )
                    + .001
                )

                if rd < 8:
                    ax += (
                        rx
                        / rd
                        * (
                            35 / rd
                        )
                    )

                    ay += (
                        ry
                        / rd
                        * (
                            22 / rd
                        )
                    )

                    moth.panic = max(
                        moth.panic,
                        1.0,
                    )

            disturbance = (
                achars.disturbance_near(
                    moth.x,
                    moth.y,
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

            # Resting / roosting.
            if (
                distance < 1.5
                and
                self.rng.random()
                < .018
                and
                moth.panic <= 0
            ):
                moth.rest = (
                    self.rng.uniform(
                        .4,
                        1.8,
                    )
                )

            if (
                moth.rest > 0
            ):
                moth.rest -= dt

                moth.vx *= .82
                moth.vy *= .82

            else:
                gain = (
                    2.0
                    if moth.panic > 0
                    else 1.0
                )

                moth.vx = (
                    moth.vx
                    + ax * dt * gain
                    + self.rng.uniform(
                        -.8,
                        .8,
                    )
                    * dt
                ) * .985

                moth.vy = (
                    moth.vy
                    + ay * dt * gain
                    + self.rng.uniform(
                        -.5,
                        .5,
                    )
                    * dt
                ) * .985

                if (
                    distance < 2
                    and
                    self.rng.random()
                    < .01
                    and
                    stage.lamps
                ):
                    moth.target = (
                        self.rng.randrange(
                            len(
                                stage.lamps
                            )
                        )
                    )

            speed = (
                math.hypot(
                    moth.vx,
                    moth.vy,
                )
            )

            max_speed = (
                11
                if moth.panic > 0
                else 8
            )

            if (
                speed > max_speed
            ):
                moth.vx *= (
                    max_speed
                    / speed
                )

                moth.vy *= (
                    max_speed
                    / speed
                )

            moth.x = clamp(
                moth.x
                + moth.vx * dt,
                1,
                stage.w - 2,
            )

            moth.y = clamp(
                moth.y
                + moth.vy * dt,
                1,
                stage.h - 2,
            )

            alive.append(
                moth
            )

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

        for i, moth in enumerate(
            self.moths
        ):
            frame = int(
                now
                * (
                    18
                    if moth.panic > 0
                    else 12
                )
                +
                i * 1.7
            ) % 4

            fg = (
                (
                    244,
                    250,
                    229,
                    223,
                )[frame]
                if moth.panic <= 0
                else
                (
                    208,
                    214,
                    220,
                    226,
                )[frame]
            )

            c.put(
                int(
                    round(
                        moth.x
                    )
                ),
                int(
                    round(
                        moth.y
                    )
                ),
                glyphs[
                    frame
                ],
                fg,
                frame == 1,
            )


# ---------------------------------------------------------------------------
# CABLE CRAWLER MK II
# ---------------------------------------------------------------------------

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
            maxlen=22
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
    def pos(
        self,
    ) -> Coord:
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
                3,
                6,
            )
        )

        self.active = bool(
            self.route
        )

    def _continue(
        self,
        stage: Stage,
    ) -> None:
        start = (
            self.pos
        )

        goal = (
            stage.far_node(
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
            if (
                ttl - dt
                > 0
            )
        ]

        if (
            not self.active
            or
            not self.route
        ):
            return

        self.acc += (
            dt * 20
        )

        while (
            self.acc >= 1
            and
            self.active
        ):
            self.acc -= 1

            p = (
                self.route[
                    self.i
                ]
            )

            self.tail.appendleft(
                p
            )

            self.trail[p] = (
                self.rng.uniform(
                    .4,
                    1.5,
                )
            )

            # Lichen likes the crawler's energy leakage.
            lichen.stimulate(
                p,
                .08,
            )

            if p in stage.gaps:
                stage.mark_repaired(
                    p,
                    self.rng.uniform(
                        5,
                        11,
                    ),
                )

                achars.spawn_spark(
                    p[0],
                    p[1],
                    self.rng.randint(
                        2,
                        4,
                    ),
                )

            elif (
                self.rng.random()
                < .05
            ):
                achars.spawn_spark(
                    p[0],
                    p[1],
                    1,
                )

            if (
                self.rng.random()
                < .06
                and
                p in stage.junctions
            ):
                self.echoes.append(
                    (
                        p,
                        .8,
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

            elif (
                self.hops > 0
            ):
                self.hops -= 1

                self._continue(
                    stage
                )

            else:
                self.active = False

    def render(
        self,
        c: Canvas,
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
                "+",
                (
                    34
                    if ttl < .4
                    else 40
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
                )[:16]
            )
        ):
            c.put(
                x,
                y,
                "=",
                22
                + min(
                    5,
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


# ---------------------------------------------------------------------------
# MAINTENANCE LIFT MK II
# ---------------------------------------------------------------------------

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
    def active(
        self,
    ) -> bool:
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

        # Pressing L again while active calls another stop.
        if self.active:
            self.stops.append(
                self.rng.choice(
                    candidates
                )
            )

            self.call_flash = 1.4

            return

        count = (
            self.rng.randint(
                2,
                min(
                    4,
                    len(
                        candidates
                    ),
                ),
            )
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

        self.state = (
            "moving"
        )

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

        if (
            self.state
            == "hidden"
        ):
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
                8.5
                if self.state
                == "moving"
                else 10
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

                if (
                    self.state
                    == "depart"
                ):
                    self.state = (
                        "hidden"
                    )

                    self.timer = 0.0

                else:
                    self.state = (
                        "opening"
                    )

                    self.timer = 0.0

                    self.call_flash = .8

            else:
                self.y += step

            return

        if (
            self.state
            == "opening"
            and
            self.timer
            >= .65
        ):
            self.state = (
                "dwell"
            )

            self.timer = 0.0

        elif (
            self.state
            == "dwell"
            and
            self.timer
            >= 2.1
        ):
            # One mysterious cargo item is literally a sack of bolts.
            if (
                self.cargo
                == "b+"
                and
                self.rng.random()
                < .28
            ):
                achars.spill(
                    stage
                )

                self.cargo = "--"

            self.state = (
                "closing"
            )

            self.timer = 0.0

        elif (
            self.state
            == "closing"
            and
            self.timer
            >= .65
        ):
            self.timer = 0.0

            if self.stops:
                self.target = float(
                    self.stops.pop(
                        0
                    )
                )

                self.state = (
                    "moving"
                )

            else:
                self.target = float(
                    stage.h - 3
                )

                self.state = (
                    "depart"
                )

    def render(
        self,
        c: Canvas,
        stage: Stage,
    ) -> None:
        if (
            self.state
            == "hidden"
        ):
            return

        x = (
            stage.shaft_x
        )

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
                    / .22
                ),
            )

            if (
                self.state
                == "closing"
            ):
                phase = (
                    2 - phase
                )

        elif (
            self.state
            == "dwell"
        ):
            phase = 2

        doors = (
            "[||]",
            "[  ]",
            "<  >",
        )[phase]

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
            doors.ljust(
                5
            ),
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

        if (
            self.state
            == "dwell"
        ):
            c.text(
                x - 1,
                y,
                self.cargo[
                    :2
                ],
                229,
                True,
            )

        if (
            self.call_flash
            > 0
        ):
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


# ---------------------------------------------------------------------------
# NEW EFFECT #7 - GHOST OPERATOR
# ---------------------------------------------------------------------------

class GhostOperator:
    """
    A cursor with no operator.

    It ignores physical divider topology and traverses directly between
    decorative interaction nodes.

    On arrival it appears to "click" a control, producing a local charge
    pulse in the aChar system.
    """

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
            maxlen=16
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

        self.visits = (
            self.rng.randint(
                4,
                9,
            )
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
        if not stage.control_nodes:
            return

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

        # Straight-line cell interpolation.
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
                if (
                    ttl - dt
                    > 0
                )
            ),
            maxlen=16,
        )

        self.click = max(
            0.0,
            self.click
            - dt,
        )

        if not self.active:
            return

        self.timer += dt

        steps = int(
            self.timer
            * 18
        )

        if steps:
            self.timer -= (
                steps / 18
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
                        .8,
                    )
                )

            else:
                self.click = .22

                achars.charge_near(
                    self.pos[0],
                    self.pos[1],
                    4,
                    .25,
                )

                self.visits -= 1

                if (
                    self.visits <= 0
                ):
                    self.active = False
                    break

                self._pick(
                    stage
                )

    def render(
        self,
        c: Canvas,
    ) -> None:
        for p, ttl in (
            self.after
        ):
            c.put(
                p[0],
                p[1],
                ".",
                (
                    54
                    if ttl < .4
                    else 60
                ),
            )

        if not self.active:
            return

        x, y = self.pos

        # ASCII on Windows to avoid font-width surprises.
        glyph = (
            "+"
            if os.name == "nt"
            else "◆"
        )

        c.put(
            x,
            y,
            glyph,
            159,
            True,
        )

        if (
            self.click > 0
        ):
            c.put(
                (
                    x + 1
                    if x + 1
                    < c.w
                    else x - 1
                ),
                y,
                "!",
                195,
                True,
            )


# ---------------------------------------------------------------------------
# NEW EFFECT #8 - SIGNAL LICHEN
# ---------------------------------------------------------------------------

class SignalLichen:
    """
    A cellular glyph colony constrained to actual panel topology.

    Growth:
        graph-neighbour propagation

    Crawler:
        stimulates growth

    Arc Storm:
        burns colonies away

    The growth rate eventually self-limits.
    """

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
                6,
                16,
            ),
        )

        seeds = (
            self.rng.sample(
                stage.graph_list,
                count,
            )
        )

        for p in seeds:
            self.cover[p] = max(
                self.cover.get(
                    p,
                    0.0,
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

    def burn_near(
        self,
        x: float,
        y: float,
        radius: float = 5.0,
    ) -> None:
        radius_sq = (
            radius * radius
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
                <= radius_sq
            ):
                self.cover[p] -= .7

                if (
                    self.cover[p]
                    <= 0
                ):
                    self.cover.pop(
                        p,
                        None,
                    )

    def update(
        self,
        dt: float,
        stage: Stage,
        crawler: CableCrawler,
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
                4.0
                if self.active
                else 1.0
            )
        )

        while (
            self.growth_acc
            >= 1
        ):
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

            neighbors = list(
                stage.neighbors(
                    p
                )
            )

            if (
                neighbors
                and
                self.rng.random()
                < .6
            ):
                q = (
                    self.rng.choice(
                        neighbors
                    )
                )

                self.cover[q] = max(
                    self.cover.get(
                        q,
                        0.0,
                    ),
                    self.rng.uniform(
                        .08,
                        .28,
                    ),
                )

            # Natural dieback prevents permanent total coverage.
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

                if (
                    self.cover[q]
                    <= 0
                ):
                    self.cover.pop(
                        q,
                        None,
                    )

            limit = min(
                420,
                max(
                    120,
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
        )

        for i, (
            p,
            value,
        ) in enumerate(
            self.cover.items()
        ):
            level = min(
                3,
                int(
                    value
                    * 4
                ),
            )

            glyph = (
                glyphs[
                    level
                ]
            )

            fg = (
                22,
                28,
                34,
                40,
            )[level]

            if (
                value > .75
                and
                int(
                    now * 3
                    + i
                )
                % 7
                == 0
            ):
                fg = 46

            c.put(
                p[0],
                p[1],
                glyph,
                fg,
                level >= 2,
            )


# ---------------------------------------------------------------------------
# NEW EFFECT #9 - ARC STORM
# ---------------------------------------------------------------------------

@dataclass
class Arc:
    a: Coord
    b: Coord

    ttl: float
    age: float = 0.0


class ArcStorm:
    """
    Electrical storm travelling between stage lamps/junctions.

    Interaction:
        charge aChars
        panic moths
        burn lichen
    """

    def __init__(
        self,
        rng: random.Random,
    ) -> None:
        self.rng = rng

        self.arcs: List[
            Arc
        ] = []

        self.timer = 0.0

        self.bursts = 0

        self.active_for = 0.0

    @property
    def active(
        self,
    ) -> bool:
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
                3.5,
                7.0,
            ),
        )

        self.timer = 0.0
        self.bursts += 1

        self._spawn_arc(
            stage
        )

    def _spawn_arc(
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

        if (
            len(
                nodes
            )
            < 2
        ):
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

        b = (
            self.rng.choice(
                far
                or nodes
            )
        )

        self.arcs.append(
            Arc(
                a=a,
                b=b,

                ttl=self.rng.uniform(
                    .18,
                    .42,
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
    ) -> None:
        self.active_for = max(
            0.0,
            self.active_for
            - dt,
        )

        self.timer += dt

        if (
            self.active_for > 0
            and
            self.timer
            >= self.rng.uniform(
                .18,
                .5,
            )
        ):
            self.timer = 0.0

            self._spawn_arc(
                stage
            )

        alive = []

        for arc in self.arcs:
            arc.age += dt

            if (
                arc.age
                >= arc.ttl
            ):
                continue

            alive.append(
                arc
            )

            t = clamp(
                arc.age
                / arc.ttl,
                0,
                1,
            )

            x = (
                arc.a[0]
                + (
                    arc.b[0]
                    - arc.a[0]
                )
                * t
            )

            y = (
                arc.a[1]
                + (
                    arc.b[1]
                    - arc.a[1]
                )
                * t
            )

            achars.charge_near(
                x,
                y,
                6,
                .8,
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

        self.arcs = alive

    def points(
        self,
    ) -> List[
        Coord
    ]:
        points = []

        for arc in self.arcs:
            t = clamp(
                arc.age
                / arc.ttl,
                0,
                1,
            )

            points.append(
                (
                    round(
                        arc.a[0]
                        +
                        (
                            arc.b[0]
                            - arc.a[0]
                        )
                        * t
                    ),
                    round(
                        arc.a[1]
                        +
                        (
                            arc.b[1]
                            - arc.a[1]
                        )
                        * t
                    ),
                )
            )

        return points

    def _line_points(
        self,
        a: Coord,
        b: Coord,
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
            t = (
                i / n
            )

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
                    * 6
                )
                * .6
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
        for j, arc in enumerate(
            self.arcs
        ):
            points = (
                self._line_points(
                    arc.a,
                    arc.b,
                )
            )

            for i, p in enumerate(
                points
            ):
                glyph = (
                    ".",
                    "*",
                    "+",
                    "~",
                )[
                    (
                        i
                        + int(
                            now * 30
                        )
                        + j
                    )
                    % 4
                ]

                fg = (
                    51,
                    87,
                    123,
                    159,
                    195,
                )[
                    (
                        i + j
                    )
                    % 5
                ]

                c.put(
                    p[0],
                    p[1],
                    glyph,
                    fg,
                    True,
                )


# ---------------------------------------------------------------------------
# AMBIENT EVENT SCHEDULER
# ---------------------------------------------------------------------------

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
        }

        for key, (
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

            self.next[key] = (
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
        }

        for key, when in list(
            self.next.items()
        ):
            if now >= when:
                out.append(
                    key
                )

                lo, hi = (
                    ranges[
                        key
                    ]
                )

                self.next[key] = (
                    now
                    + self.rng.uniform(
                        lo,
                        hi,
                    )
                )

        return out


# ---------------------------------------------------------------------------
# APPLICATION
# ---------------------------------------------------------------------------

class App:
    FPS = 22.0

    def __init__(
        self,
    ) -> None:
        self.rng = (
            random.Random(
                time.time_ns()
                ^ os.getpid()
            )
        )

        size = (
            shutil.get_terminal_size(
                (
                    120,
                    38,
                )
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

        self.input = (
            InputReader()
        )

        self.help = False
        self.running = True

        # Original six.
        self.achars = (
            ACharField(
                self.rng
            )
        )

        self.lift = (
            MaintenanceLift(
                self.rng
            )
        )

        self.gremlin = (
            Gremlin(
                self.rng
            )
        )

        self.phantom = (
            PhantomTransmission(
                self.rng
            )
        )

        self.moths = (
            RelayMoths(
                self.rng
            )
        )

        self.crawler = (
            CableCrawler(
                self.rng
            )
        )

        # New three.
        self.ghost = (
            GhostOperator(
                self.rng
            )
        )

        self.lichen = (
            SignalLichen(
                self.rng
            )
        )

        self.arc = (
            ArcStorm(
                self.rng
            )
        )

        self.ambient = (
            AmbientScheduler(
                self.rng
            )
        )

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

            "ghost": (
                self.ghost.active
            ),

            "lichen": bool(
                self.lichen.cover
            ),

            "arc": (
                self.arc.active
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

    def handle_key(
        self,
        key: str,
    ) -> None:
        # Ctrl-X owns global entry into the dedicated aChar layer.
        if key == "\x18":
            self.achars.toggle_fx()
            return

        # Once open, aChar-layer bindings have priority.
        if self.achars.handle_fx_key(
            key,
            self.stage,
        ):
            return

        k = key.lower()

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
                        "gbtmclofx"
                    )
                )
            )

        elif k in (
            "gbtmclofx"
        ):
            self.trigger(
                k
            )

    def resize(
        self,
    ) -> None:
        size = (
            shutil.get_terminal_size(
                (
                    120,
                    38,
                )
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

        # Geometry-bound actors restart safely.
        self.gremlin.state = (
            "hidden"
        )

        self.crawler.active = False
        self.lift.state = "hidden"

        self.ghost.active = False

        self.arc.arcs = []
        self.arc.active_for = 0

        # Free-space particle effects survive resizing.
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

        for moth in self.moths.moths:
            moth.x = clamp(
                moth.x,
                1,
                w - 2,
            )

            moth.y = clamp(
                moth.y,
                1,
                h - 2,
            )

        self.lichen.cover = {
            p: value
            for p, value
            in self.lichen.cover.items()
            if p in self.stage.graph
        }

    def update(
        self,
        dt: float,
        now: float,
    ) -> None:
        # Ambient autonomous events.
        for key in self.ambient.due(
            now
        ):
            self.trigger(
                key
            )

        # Update order deliberately creates interactions.
        self.achars.update(
            dt,
            self.stage,
        )

        self.lift.update(
            dt,
            self.stage,
            self.achars,
        )

        self.gremlin.update(
            dt,
            self.stage,
            self.achars,
            self.lift,
        )

        self.phantom.update(
            dt
        )

        self.lichen.update(
            dt,
            self.stage,
            self.crawler,
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
        )

        self.moths.update(
            dt,
            self.stage,
            self.gremlin,
            self.achars,
            self.phantom,
            self.arc.points(),
        )

    def help_overlay(
        self,
        c: Canvas,
    ) -> None:
        width = min(
            c.w - 6,
            84,
        )

        height = min(
            c.h - 6,
            24,
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
            "MAINTENANCE ECOSYSTEM MK II // CHEAT SHEET",
            "",

            "G gremlin MK II       B loose hardware / aChar spill",
            "T phantom radio       M relay moths",
            "C cable crawler       L unauthorized lift",
            "O ghost operator      F signal lichen       X arc storm",
            "R random event        A ambient auto-events on/off",

            "",

            "Ctrl-X  aChar FX layer",

            " Space burst   +/- rate   [/] family   D emitter geometry",

            " V velocity field   K collision   P palette   R randomize   Esc close",

            "",

            "MK II interactions:",

            " gremlin hunts bolts and can hitch-hike the lift",

            " moths react to gremlin, aChars, radio beacons and electrical arcs",

            " crawler repairs broken divider cells and stimulates lichen",

            " arc storm charges aChars, panics moths and burns lichen",

            " ghost operator clicks decorative controls and energizes nearby aChars",

            " phantom transmissions can mention whatever is currently happening",

            "",

            "? close help      Q quit",
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

        # Lowest to highest visual layers.
        self.stage.render(
            c,
            now,
            self.ambient.enabled,
        )

        self.lichen.render(
            c,
            now,
        )

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

        self.ghost.render(
            c
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

    def run(
        self,
    ) -> None:
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

        last = (
            time.monotonic()
        )

        try:
            while self.running:
                frame_start = (
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
                    - frame_start
                )

                if (
                    elapsed
                    < frame_time
                ):
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


# ---------------------------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------------------------

def main(
) -> None:
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