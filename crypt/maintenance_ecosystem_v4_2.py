"""
MAINTENANCE ECOSYSTEM V4.2
==========================
Standalone ANSI terminal toy. No PlasmaRack functionality.
Dependency-free. Windows Terminal first-class; POSIX terminals also supported.

MAIN EFFECTS
------------
G  robot gremlin
B  loose hardware / aChar spill
T  phantom maintenance transmission
M  relay moth swarm
C  cable crawler
L  unauthorized maintenance lift
O  ghost operator
F  signal lichen
X  arc storm
D  lunar-service drone
V  prismatic coolant leak
Z  diagnostic aurora

GLOBAL
------
E       Effects / Ambient popup
A       ambient master on/off
R       random effect
Ctrl-X  aChar FX layer
Ctrl-Y  Moth FX layer
?       help
Q       quit

DRONE
-----
D            deploy / recall
LEFT/RIGHT   rotate
SPACE        main engine
DOWN         damping / retro
UP           AUTO <-> MANUAL

EFFECTS / AMBIENT PANEL
-----------------------
E / ESC            close
UP/DOWN or W/S     select effect
LEFT/RIGHT         chance -/+ 5%
- / +              chance -/+ 5%
ENTER / SPACE      enable/disable selected effect
T                  trigger selected effect immediately
A                  ambient master on/off
R                  restore default chances
0                  set selected chance to 0%
1                  set selected chance to 100%

While the popup is open it owns ALL keyboard input, so the lander and FX
layers cannot steal arrow keys or Space.
"""
from __future__ import annotations
import math
import os
import random
import shutil
import sys
import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, Iterable, List, Optional, Set, Tuple
ESC = '\x1b'
SYNC_BEGIN = ESC + '[?2026h'
SYNC_END = ESC + '[?2026l'
ALT_ON = ESC + '[?1049h'
ALT_OFF = ESC + '[?1049l'
HIDE_CURSOR = ESC + '[?25l'
SHOW_CURSOR = ESC + '[?25h'
RESET = ESC + '[0m'
HOME = ESC + '[H'
CLEAR = ESC + '[2J'
Coord = Tuple[int, int]

def clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v

def sign(v: float) -> int:
    return (v > 0) - (v < 0)

def manhattan(a: Coord, b: Coord) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])

class InputReader:
    """Nonblocking input with Windows/POSIX arrow-key decoding."""

    def __init__(self) -> None:
        self.is_windows = os.name == 'nt'
        self._old_term = None
        self._buf = ''
        if self.is_windows:
            self._enable_windows_vt()
        else:
            import termios
            import tty
            self._termios = termios
            if sys.stdin.isatty():
                self._old_term = termios.tcgetattr(sys.stdin.fileno())
                tty.setcbreak(sys.stdin.fileno())

    def _enable_windows_vt(self) -> None:
        try:
            import ctypes
            from ctypes import wintypes
            k32 = ctypes.windll.kernel32
            handle = k32.GetStdHandle(-11)
            mode = wintypes.DWORD()
            if k32.GetConsoleMode(handle, ctypes.byref(mode)):
                k32.SetConsoleMode(handle, mode.value | 4)
        except Exception:
            pass

    def read_keys(self) -> List[str]:
        if self.is_windows:
            import msvcrt
            out: List[str] = []
            arrows = {'H': 'UP', 'P': 'DOWN', 'K': 'LEFT', 'M': 'RIGHT'}
            while msvcrt.kbhit():
                ch = msvcrt.getwch()
                if ch in ('\x00', 'à'):
                    if msvcrt.kbhit():
                        mapped = arrows.get(msvcrt.getwch())
                        if mapped:
                            out.append(mapped)
                    continue
                out.append(ch)
            return out
        import select
        fd = sys.stdin.fileno()
        while True:
            ready, _, _ = select.select([sys.stdin], [], [], 0)
            if not ready:
                break
            try:
                data = os.read(fd, 64)
            except OSError:
                break
            if not data:
                break
            self._buf += data.decode('utf-8', 'ignore')
        out: List[str] = []
        arrows = {'\x1b[A': 'UP', '\x1b[B': 'DOWN', '\x1b[C': 'RIGHT', '\x1b[D': 'LEFT'}
        while self._buf:
            matched = False
            for seq, name in arrows.items():
                if self._buf.startswith(seq):
                    out.append(name)
                    self._buf = self._buf[len(seq):]
                    matched = True
                    break
            if matched:
                continue
            if self._buf.startswith('\x1b[') and len(self._buf) < 3:
                break
            out.append(self._buf[0])
            self._buf = self._buf[1:]
        return out

    def close(self) -> None:
        if not self.is_windows and self._old_term is not None:
            try:
                self._termios.tcsetattr(sys.stdin.fileno(), self._termios.TCSADRAIN, self._old_term)
            except Exception:
                pass

class Canvas:

    def __init__(self, w: int, h: int) -> None:
        self.w = w
        self.h = h
        n = w * h
        self.chars = [' '] * n
        self.fg: List[Optional[int]] = [None] * n
        self.bold = [False] * n

    def _i(self, x: int, y: int) -> int:
        return y * self.w + x

    def put(self, x: int, y: int, ch: str, fg: Optional[int]=None, bold: bool=False) -> None:
        if 0 <= x < self.w and 0 <= y < self.h and ch:
            i = self._i(x, y)
            self.chars[i] = ch[0]
            self.fg[i] = fg
            self.bold[i] = bold

    def text(self, x: int, y: int, s: str, fg: Optional[int]=None, bold: bool=False, max_width: Optional[int]=None) -> None:
        if not 0 <= y < self.h:
            return
        if max_width is not None:
            s = s[:max(0, max_width)]
        for j, ch in enumerate(s):
            self.put(x + j, y, ch, fg, bold)

    def hline(self, x1: int, x2: int, y: int, ch: str='-', fg: int=240) -> None:
        if x2 < x1:
            x1, x2 = (x2, x1)
        for x in range(max(0, x1), min(self.w - 1, x2) + 1):
            self.put(x, y, ch, fg)

    def vline(self, x: int, y1: int, y2: int, ch: str='|', fg: int=240) -> None:
        if y2 < y1:
            y1, y2 = (y2, y1)
        for y in range(max(0, y1), min(self.h - 1, y2) + 1):
            self.put(x, y, ch, fg)

    def box(self, x: int, y: int, w: int, h: int, fg: int=240) -> None:
        if w < 2 or h < 2:
            return
        self.hline(x + 1, x + w - 2, y, '-', fg)
        self.hline(x + 1, x + w - 2, y + h - 1, '-', fg)
        self.vline(x, y + 1, y + h - 2, '|', fg)
        self.vline(x + w - 1, y + 1, y + h - 2, '|', fg)
        for px, py in ((x, y), (x + w - 1, y), (x, y + h - 1), (x + w - 1, y + h - 1)):
            self.put(px, py, '+', fg)

    def render(self) -> str:
        out = [SYNC_BEGIN, HOME]
        current_fg: Optional[int] = None
        current_bold = False
        for y in range(self.h):
            for x in range(self.w):
                i = self._i(x, y)
                fg = self.fg[i]
                bold = self.bold[i]
                if fg != current_fg or bold != current_bold:
                    if fg is None and (not bold):
                        out.append(RESET)
                    else:
                        codes = []
                        if bold:
                            codes.append('1')
                        if fg is not None:
                            codes.append(f'38;5;{fg}')
                        out.append(ESC + '[' + ';'.join(codes) + 'm')
                    current_fg = fg
                    current_bold = bold
                out.append(self.chars[i])
            if y != self.h - 1:
                out.append('\n')
        out.extend((RESET, SYNC_END))
        return ''.join(out)

class Stage:

    def __init__(self, w: int, h: int) -> None:
        self.w = w
        self.h = h
        self.graph: Set[Coord] = set()
        self.graph_list: List[Coord] = []
        self.junctions: List[Coord] = []
        self.control_nodes: List[Coord] = []
        self.gaps: Set[Coord] = set()
        self.repaired_until: Dict[Coord, float] = {}
        self.lamps: List[Coord] = []
        self.vlines: List[int] = []
        self.hlines: List[int] = []
        self.hatch: Coord = (5, 5)
        self.shaft_x = 10
        self.rebuild(w, h)

    def rebuild(self, w: int, h: int) -> None:
        self.w = w
        self.h = h
        self.graph.clear()
        self.repaired_until.clear()
        top = max(5, min(7, h - 10))
        bottom = max(top + 8, h - 8)
        mid = (top + bottom) // 2
        self.hlines = sorted(set((top, mid, bottom)))
        x1 = max(18, w // 3)
        x2 = min(w - 18, 2 * w // 3)
        if x2 <= x1 + 8:
            x1 = max(12, w // 2 - 10)
            x2 = min(w - 12, w // 2 + 10)
        self.vlines = [x1, x2]
        self.shaft_x = x2
        self.hatch = (min(max(7, w // 10), max(7, x1 - 6)), top)
        for y in self.hlines:
            for x in range(1, w - 1):
                self.graph.add((x, y))
        for x in self.vlines:
            for y in range(top, h - 1):
                self.graph.add((x, y))
        branch_y = min(h - 3, mid + 4)
        branch_x = min(x2 - 2, x1 + 5)
        for x in range(x1, x2 + 1):
            self.graph.add((x, branch_y))
        for y in range(top, branch_y + 1):
            self.graph.add((branch_x, y))
        loop_left = max(3, x1 - 12)
        loop_right = min(w - 4, x2 + 12)
        loop_y = min(h - 4, bottom + 3)
        if loop_y > bottom:
            for x in range(loop_left, loop_right + 1):
                self.graph.add((x, loop_y))
            for y in range(bottom, loop_y + 1):
                self.graph.add((loop_left, y))
                self.graph.add((loop_right, y))
        candidates = [(min(w - 3, x1 + 7), mid), (max(2, x2 - 9), bottom), (x2, min(h - 3, mid + 3)), (max(2, x1 - 4), top)]
        self.gaps = {p for p in candidates if p in self.graph}
        self.graph_list = sorted(self.graph)
        self.junctions = [p for p in self.graph_list if sum((1 for _ in self.neighbors(p))) >= 3]
        if not self.junctions and self.graph_list:
            stride = max(1, len(self.graph_list) // 12)
            self.junctions = self.graph_list[::stride]
        self.lamps = [(max(3, x1 - 5), max(2, top - 3)), (min(w - 4, x1 + 8), max(2, top - 3)), (min(w - 4, x2 + 7), max(2, top - 3)), (max(3, x1 - 6), min(h - 3, bottom + 3)), (min(w - 4, x2 + 8), min(h - 3, bottom + 3))]
        self.control_nodes = list(self.lamps)
        if self.junctions:
            stride = max(1, len(self.junctions) // 10)
            self.control_nodes += self.junctions[::stride]

    def neighbors(self, p: Coord) -> Iterable[Coord]:
        x, y = p
        for q in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if q in self.graph:
                yield q

    def path(self, start: Coord, goal: Coord) -> List[Coord]:
        if start not in self.graph or goal not in self.graph:
            return []
        q: Deque[Coord] = deque([start])
        prev: Dict[Coord, Optional[Coord]] = {start: None}
        while q:
            p = q.popleft()
            if p == goal:
                break
            for n in self.neighbors(p):
                if n not in prev:
                    prev[n] = p
                    q.append(n)
        if goal not in prev:
            return []
        out = []
        p: Optional[Coord] = goal
        while p is not None:
            out.append(p)
            p = prev[p]
        out.reverse()
        return out

    def far_node(self, rng: random.Random, start: Coord, min_dist: int=16) -> Coord:
        far = [p for p in self.graph_list if manhattan(p, start) >= min_dist]
        return rng.choice(far or self.graph_list or [start])

    def nearest_graph(self, p: Coord) -> Coord:
        if not self.graph_list:
            return p
        return min(self.graph_list, key=lambda q: manhattan(p, q))

    def mark_repaired(self, p: Coord, seconds: float=7.0) -> None:
        if p in self.gaps:
            self.repaired_until[p] = time.monotonic() + seconds

    def is_repaired(self, p: Coord, now: float) -> bool:
        until = self.repaired_until.get(p, 0.0)
        if until <= now:
            self.repaired_until.pop(p, None)
            return False
        return True

    def render(self, c: Canvas, now: float, ambient: bool) -> None:
        c.box(0, 0, self.w, self.h, 238)
        c.text(2, 0, ' MAINTENANCE ECOSYSTEM V4.2 // LUNAR SERVICE // E = EFFECTS / AMBIENT '[:max(0, self.w - 4)], 244, True)
        for y in self.hlines:
            c.hline(1, self.w - 2, y, '-', 239)
        for x in self.vlines:
            c.vline(x, self.hlines[0], self.h - 2, '|', 239)
        for x in self.vlines:
            for y in self.hlines:
                c.put(x, y, '+', 245)
        branch_y = min(self.h - 3, self.hlines[1] + 4)
        branch_x = min(self.vlines[1] - 2, self.vlines[0] + 5)
        c.hline(self.vlines[0], self.vlines[1], branch_y, '-', 237)
        c.vline(branch_x, self.hlines[0], branch_y, '|', 237)
        for p in self.gaps:
            repaired = self.is_repaired(p, now)
            c.put(p[0], p[1], '#' if repaired else ' ', 154 if repaired else None, repaired)
        labels = [(2, 2, 'AUX MAINT // ALL FAILURES COSMETIC'), (self.vlines[0] + 2, 2, 'BAY 13 // E OPENS EFFECTS MENU'), (self.vlines[1] + 2, 2, 'LANDER: SPACE THRUST'), (2, self.hlines[0] + 2, 'UP = AUTO / MANUAL'), (self.vlines[0] + 2, self.hlines[0] + 2, 'CTRL-Y MOTH FX'), (self.vlines[1] + 2, self.hlines[0] + 2, 'WASD WORK IN MENU')]
        for x, y, s in labels:
            c.text(x, y, s, 242, max_width=max(0, self.w - x - 2))
        for i, (x, y) in enumerate(self.lamps):
            pulse = int(now * (2.3 + i * 0.2)) % 6
            fg = (82, 83, 119, 120, 156, 229)[pulse]
            glyph = ('o', 'o', 'O', 'o', '*', 'o')[pulse]
            c.put(x, y, glyph, fg, pulse in (2, 4))
        hx, hy = self.hatch
        c.text(max(1, hx - 3), hy, '[==]', 245, True)
        for y in range(self.hlines[0] + 1, self.h - 2, 3):
            c.put(self.shaft_x, y, ':', 244)
        c.text(2, self.h - 1, f" A ambient:{('ON' if ambient else 'OFF')}  E menu  D lander  UP mode  LEFT/RIGHT rotate  SPACE thrust  Ctrl-X/Y FX  ? help  Q quit "[:max(0, self.w - 4)], 244)

@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    ttl: float
    age: float = 0.0
    glyph: str = '.'
    palette: Tuple[int, ...] = (244,)

class ACharField:

    def __init__(self, rng: random.Random) -> None:
        self.rng = rng
        self.items: List[Particle] = []
        self.hardware: List[Tuple[float, float, float, float, float, bool]] = []
        self.fx_mode = False
        self.rate = 8.0
        self.acc = 0.0
        self.mode = 0
        self.palette_phase = 0
        self.max_items = 360
        self.palettes = [(45, 51, 87, 123, 159, 195), (201, 207, 213, 219, 225, 231), (82, 118, 154, 190, 226, 220), (33, 39, 45, 51, 87, 123)]

    def toggle_fx(self) -> None:
        self.fx_mode = not self.fx_mode

    def _add(self, p: Particle) -> None:
        self.items.append(p)
        self.items = self.items[-self.max_items:]

    def spark(self, x: float, y: float, n: int=2) -> None:
        for _ in range(n):
            self._add(Particle(x=x, y=y, vx=self.rng.uniform(-7, 7), vy=self.rng.uniform(-5, 2), ttl=self.rng.uniform(0.4, 1.2), glyph=self.rng.choice('.*+'), palette=(226, 220, 214, 208)))

    def spill(self, stage: Stage) -> None:
        for _ in range(self.rng.randint(10, 22)):
            x = self.rng.choice([stage.vlines[0], stage.vlines[1], self.rng.randint(4, stage.w - 5)]) + self.rng.uniform(-4, 4)
            self.hardware.append((clamp(x, 2, stage.w - 3), self.rng.uniform(1, max(2, stage.hlines[0] - 1)), self.rng.uniform(-4, 4), self.rng.uniform(-2, 2), self.rng.uniform(12, 26), False))

    def charge_near(self, x: float, y: float, r: float=6, amount: float=0.5) -> None:
        r2 = r * r
        for p in self.items:
            if (p.x - x) ** 2 + (p.y - y) ** 2 <= r2:
                p.vx += self.rng.uniform(-3, 3) * amount
                p.vy += self.rng.uniform(-2, 2) * amount

    def collect_near(self, x: int, y: int, radius: int=2) -> int:
        kept = []
        n = 0
        for h in self.hardware:
            hx, hy, vx, vy, ttl, settled = h
            if settled and abs(hx - x) + abs(hy - y) <= radius:
                n += 1
            else:
                kept.append(h)
        self.hardware = kept
        return n

    def nearest_hardware(self, p: Coord) -> Optional[Coord]:
        best = None
        best_d = 99999
        for hx, hy, vx, vy, ttl, settled in self.hardware:
            if not settled:
                continue
            q = (round(hx), round(hy))
            d = manhattan(p, q)
            if d < best_d:
                best_d = d
                best = q
        return best

    def disturbance_near(self, x: float, y: float, r: float=5) -> float:
        r2 = r * r
        return float(sum((1 for p in self.items if (p.x - x) ** 2 + (p.y - y) ** 2 <= r2)))

    def burst(self, stage: Stage, n: int=40) -> None:
        for _ in range(n):
            angle = self.rng.random() * math.tau
            if self.mode == 0:
                x = stage.w / 2
                y = stage.h / 2
            elif self.mode == 1:
                x = self.rng.uniform(2, stage.w - 3)
                y = 2
            else:
                x, y = self.rng.choice([(2, 2), (stage.w - 3, 2), (2, stage.h - 3), (stage.w - 3, stage.h - 3)])
            speed = self.rng.uniform(4, 14)
            self._add(Particle(x=x, y=y, vx=math.cos(angle) * speed, vy=math.sin(angle) * speed * 0.55, ttl=self.rng.uniform(5, 14), glyph=self.rng.choice('.*+ox~'), palette=self.rng.choice(self.palettes)))

    def handle_fx_key(self, key: str, stage: Stage) -> bool:
        if not self.fx_mode:
            return False
        if key == '\x1b':
            self.fx_mode = False
            return True
        if key == ' ':
            self.burst(stage)
        elif key in ('+', '='):
            self.rate = min(80, self.rate + 1)
        elif key == '-':
            self.rate = max(0, self.rate - 1)
        elif key in ('[', ']'):
            self.mode = (self.mode + (-1 if key == '[' else 1)) % 3
        elif key.lower() == 'p':
            self.palette_phase = (self.palette_phase + 1) % 64
        elif key.lower() == 'r':
            self.mode = self.rng.randrange(3)
            self.rate = self.rng.uniform(3, 35)
            self.palette_phase = self.rng.randrange(64)
        else:
            return False
        return True

    def update(self, dt: float, stage: Stage) -> None:
        if self.fx_mode:
            self.acc += dt * self.rate
            while self.acc >= 1:
                self.acc -= 1
                self.burst(stage, 1)
        alive = []
        for p in self.items:
            p.age += dt
            if p.age >= p.ttl:
                continue
            p.x += p.vx * dt
            p.y += p.vy * dt
            p.vx *= 0.995
            p.vy *= 0.995
            if p.x < 1:
                p.x = stage.w - 2
            elif p.x > stage.w - 2:
                p.x = 1
            if p.y < 1:
                p.y = stage.h - 2
            elif p.y > stage.h - 2:
                p.y = 1
            alive.append(p)
        self.items = alive
        hardware = []
        for hx, hy, vx, vy, ttl, settled in self.hardware:
            ttl -= dt
            if ttl <= 0:
                continue
            if settled:
                hardware.append((hx, hy, 0, 0, ttl, True))
                continue
            old_y = hy
            vy += 10 * dt
            hx += vx * dt
            hy += vy * dt
            vx *= 0.995
            for level in stage.hlines + [stage.h - 2]:
                if old_y < level <= hy:
                    hy = level - 1
                    vy = -abs(vy) * self.rng.uniform(0.18, 0.42)
                    vx *= 0.7
                    if abs(vy) < 1:
                        settled = True
                        vx = 0
                        vy = 0
                    break
            hx = clamp(hx, 1, stage.w - 2)
            hardware.append((hx, hy, vx, vy, ttl, settled))
        self.hardware = hardware

    def render(self, c: Canvas, now: float) -> None:
        for i, p in enumerate(self.items):
            fg = p.palette[(i + int(now * 10) + self.palette_phase) % len(p.palette)]
            c.put(round(p.x), round(p.y), p.glyph, fg, p.glyph in '*+')
        for i, (x, y, vx, vy, ttl, settled) in enumerate(self.hardware):
            c.put(round(x), round(y), ('|', '/', '-', '\\')[int(now * 12 + i) % 4] if not settled else 'o', 250, settled)
        if self.fx_mode:
            c.text(2, max(1, c.h - 3), f' aCHAR FX :: mode={self.mode} rate={self.rate:04.1f}/s  [ ] mode  +/- rate  P palette  Space burst  R random  Esc '[:max(0, c.w - 4)], 159, True)

class Gremlin:

    def __init__(self, rng: random.Random) -> None:
        self.rng = rng
        self.state = 'hidden'
        self.timer = 0.0
        self.pos: Coord = (0, 0)
        self.route: List[Coord] = []
        self.i = 0
        self.acc = 0.0
        self.journeys = 0
        self.collected = 0
        self.facing = 'right'

    @property
    def active(self) -> bool:
        return self.state != 'hidden'

    def trigger(self, stage: Stage) -> None:
        if self.active:
            self.journeys += 1
            return
        self.state = 'opening'
        self.timer = 0.0
        self.pos = stage.hatch
        self.journeys = self.rng.randint(4, 8)

    def _go(self, stage: Stage, goal: Coord) -> None:
        start = self.pos if self.pos in stage.graph else stage.hatch
        if goal not in stage.graph:
            goal = stage.nearest_graph(goal)
        self.route = stage.path(start, goal) or [start]
        self.i = 0
        self.acc = 0.0

    def update(self, dt: float, stage: Stage, achars: ACharField) -> None:
        if self.state == 'hidden':
            return
        self.timer += dt
        if self.state == 'opening' and self.timer > 0.7:
            self.state = 'walk'
            self.timer = 0
            self._go(stage, stage.far_node(self.rng, self.pos, 15))
            return
        if self.state == 'closing' and self.timer > 0.6:
            self.state = 'hidden'
            return
        if self.state == 'nap' and self.timer > self.rng.uniform(0.5, 1.2):
            self.timer = 0
            if self.journeys > 0:
                self.journeys -= 1
                self.state = 'walk'
                target = achars.nearest_hardware(self.pos) if self.rng.random() < 0.7 else None
                self._go(stage, target or stage.far_node(self.rng, self.pos, 12))
            else:
                self.state = 'return'
                self._go(stage, stage.hatch)
            return
        if self.state not in ('walk', 'return'):
            return
        self.acc += dt * 11
        while self.acc >= 1 and self.i < len(self.route) - 1:
            self.acc -= 1
            old = self.route[self.i]
            self.i += 1
            self.pos = self.route[self.i]
            dx = self.pos[0] - old[0]
            dy = self.pos[1] - old[1]
            self.facing = 'right' if dx > 0 else 'left' if dx < 0 else 'climb' if dy else self.facing
            self.collected += achars.collect_near(*self.pos, 2)
        if self.i >= len(self.route) - 1:
            if self.state == 'return' and self.pos == stage.hatch:
                self.state = 'closing'
                self.timer = 0
            else:
                self.state = 'nap'
                self.timer = 0

    def render(self, c: Canvas, stage: Stage, now: float) -> None:
        if self.state == 'hidden':
            return
        hx, hy = stage.hatch
        if self.state in ('opening', 'closing'):
            seq = ['[==]', '[--]', '[  ]', '<  >']
            phase = min(3, int(self.timer / 0.17))
            if self.state == 'closing':
                phase = 3 - phase
            c.text(max(1, hx - 3), hy, seq[phase], 220, True)
            return
        x, y = self.pos
        bob = int(now * 8) & 1
        if self.state == 'nap':
            sprite = ((' z ', '_o_', '/|\\'), (' Z ', '_o_', '/|\\'))[bob]
        elif self.facing == 'climb':
            sprite = ((' o ', '/|\\', '^ ^'), (' o ', '\\|/', 'v v'))[bob]
        elif self.facing == 'left':
            sprite = (('_o ', '<|>', '/ \\'), (' o_', '<|>', '/ \\'))[bob]
        else:
            sprite = ((' o_', '<|>', '/ \\'), ('_o ', '<|>', '/ \\'))[bob]
        for sy, row in enumerate(sprite):
            c.text(x - 1, y - 1 + sy, row, 220, True)

class Phantom:
    MESSAGES = ['GROUND WAS OPTIONAL, APPARENTLY.', 'THE MACHINE DENIES KNOWING YOU.', 'BAY 13 REQUESTS A BETTER BAY 13.', 'UPLINK REPORTS OPERATOR MAY BE A DRONE.', 'AUTOPILOT DENIES RESPONSIBILITY.', 'THE COLOUR OF THE COOLANT IS NOT IN THE MANUAL.', 'DIAGNOSTIC WEATHER REMAINS INDOORS.']

    def __init__(self, rng: random.Random) -> None:
        self.rng = rng
        self.active_for = 0.0
        self.msg = ''
        self.channel = ''
        self.strength = 0.7

    @property
    def active(self) -> bool:
        return self.active_for > 0

    def trigger(self, context: Dict[str, bool], stage: Stage) -> None:
        extra = []
        if context.get('drone'):
            extra.append('LANDER ACTIVE. LANDING PAD HAS NOT BEEN CONSULTED.')
        if context.get('moths'):
            extra.append('RELAY MOTHS HAVE FORMED A COMMITTEE.')
        if context.get('coolant'):
            extra.append('COOLANT LEAK NOW TECHNICALLY A LIGHTING FEATURE.')
        self.msg = self.rng.choice(self.MESSAGES + extra * 2)
        self.channel = self.rng.choice(['BAY 13', 'AUX RADIO', 'MAINT CH-0?', 'SERVICE RETURN'])
        self.strength = self.rng.uniform(0.4, 0.98)
        self.active_for = 6.0

    def update(self, dt: float) -> None:
        self.active_for = max(0, self.active_for - dt)

    def render(self, c: Canvas, stage: Stage, now: float) -> None:
        if not self.active:
            return
        x = stage.vlines[1] + 2
        y = stage.hlines[1] + 1
        w = max(18, c.w - x - 3)
        if w < 22 or y + 4 >= c.h:
            x = 2
            y = 2
            w = max(22, c.w - 4)
        c.box(x, y, w, 4, 53)
        c.text(x + 2, y + 1, f'{self.channel} // RX {int(self.strength * 100):02d}%', 51, True, w - 4)
        reveal = min(len(self.msg), int((6 - self.active_for) * 24))
        c.text(x + 2, y + 2, self.msg[:reveal], 51, max_width=w - 4)

@dataclass
class Moth:
    x: float
    y: float
    vx: float
    vy: float
    phase: float
    ttl: float
    age: float = 0.0
    panic: float = 0.0

class RelayMoths:

    def __init__(self, rng: random.Random) -> None:
        self.rng = rng
        self.moths: List[Moth] = []
        self.fx_mode = False
        self.population = 55
        self.form = 0
        self.palette = 0
        self.max_moths = 170
        self.forms = ['ORBIT', 'RIBBON', 'VORTEX', 'LATTICE', 'COMET', 'PULSE']

    @property
    def active(self) -> bool:
        return bool(self.moths)

    def toggle_fx(self, stage: Stage) -> None:
        self.fx_mode = not self.fx_mode

    def trigger(self, stage: Stage, n: Optional[int]=None) -> None:
        n = n or self.rng.randint(20, 42)
        cx, cy = self.rng.choice(stage.lamps) if stage.lamps else (stage.w / 2, stage.h / 2)
        for _ in range(n):
            angle = self.rng.random() * math.tau
            radius = self.rng.uniform(1, 9)
            self.moths.append(Moth(x=cx + math.cos(angle) * radius, y=cy + math.sin(angle) * radius * 0.5, vx=self.rng.uniform(-2, 2), vy=self.rng.uniform(-1, 1), phase=self.rng.random() * math.tau, ttl=self.rng.uniform(18, 40)))
        self.moths = self.moths[-self.max_moths:]

    def handle_fx_key(self, key: str, stage: Stage) -> bool:
        if not self.fx_mode:
            return False
        if key == '\x1b':
            self.fx_mode = False
            return True
        if key == ' ':
            self.trigger(stage, 35)
        elif key in ('+', '='):
            self.population = min(160, self.population + 5)
        elif key == '-':
            self.population = max(5, self.population - 5)
        elif key in ('[', ']'):
            self.form = (self.form + (-1 if key == '[' else 1)) % len(self.forms)
        elif key.lower() == 'p':
            self.palette = (self.palette + 1) % 4
        elif key.lower() == 'r':
            self.form = self.rng.randrange(len(self.forms))
            self.population = self.rng.randint(20, 140)
            self.palette = self.rng.randrange(4)
        else:
            return False
        return True

    def panic_near(self, x: float, y: float, r: float=8) -> None:
        r2 = r * r
        for m in self.moths:
            if (m.x - x) ** 2 + (m.y - y) ** 2 <= r2:
                m.panic = 1.2

    def _target(self, m: Moth, i: int, now: float, stage: Stage) -> Tuple[float, float]:
        cx = stage.w / 2
        cy = stage.h / 2
        phase = now * 1.7 + m.phase + i * 0.18
        form = self.forms[self.form]
        if form == 'RIBBON':
            return (cx + math.sin(phase * 0.7) * stage.w * 0.32, cy + math.sin(phase * 2.2) * 5)
        if form == 'VORTEX':
            r = 2 + i % 26 * 0.45
            return (cx + math.cos(phase) * r, cy + math.sin(phase) * r * 0.45)
        if form == 'LATTICE':
            cols = max(3, int(math.sqrt(max(1, self.population))))
            gx = i % cols - cols / 2
            gy = i // cols % cols - cols / 2
            return (cx + gx * 3, cy + gy * 1.2)
        if form == 'COMET':
            return (cx + math.cos(now * 0.9) * stage.w * 0.25 - i % 40 * 0.5, cy + math.sin(now * 1.2) * stage.h * 0.2 + math.sin(i * 0.7 + now * 3) * 2)
        if form == 'PULSE':
            r = 4 + (math.sin(now * 3 + m.phase) + 1) * 8
            return (cx + math.cos(m.phase + i * 0.3) * r, cy + math.sin(m.phase + i * 0.3) * r * 0.45)
        r = 4 + i % 20 * 0.5
        return (cx + math.cos(phase) * r, cy + math.sin(phase) * r * 0.5)

    def update(self, dt: float, now: float, stage: Stage, gremlin: Gremlin, achars: ACharField, drone: 'LanderDrone') -> None:
        if self.fx_mode and len(self.moths) < self.population and (self.rng.random() < dt * 18):
            self.trigger(stage, min(6, self.population - len(self.moths)))
        alive = []
        for i, m in enumerate(self.moths):
            m.age += dt
            m.panic = max(0, m.panic - dt)
            if m.age >= m.ttl and (not self.fx_mode):
                continue
            if self.fx_mode:
                m.ttl = max(m.ttl, m.age + 8)
                tx, ty = self._target(m, i, now, stage)
            else:
                tx, ty = self.rng.choice(stage.lamps) if stage.lamps else (stage.w / 2, stage.h / 2)
            dx = tx - m.x
            dy = ty - m.y
            d = math.hypot(dx, dy) + 0.001
            ax = dx / d * 5 - dy / d * 2
            ay = dy / d * 3 + dx / d * 1.1
            if gremlin.active:
                gx, gy = gremlin.pos
                rx = m.x - gx
                ry = m.y - gy
                gd = math.hypot(rx, ry) + 0.001
                if gd < 9:
                    ax += rx / gd * (25 / gd)
                    ay += ry / gd * (16 / gd)
                    m.panic = max(m.panic, 0.6)
            if drone.active:
                rx = m.x - drone.x
                ry = m.y - drone.y
                dd = math.hypot(rx, ry) + 0.001
                if dd < 10:
                    ax += rx / dd * (32 / dd)
                    ay += ry / dd * (18 / dd)
                    m.panic = max(m.panic, 0.6)
            disturbance = achars.disturbance_near(m.x, m.y, 4)
            ax += self.rng.uniform(-0.6, 0.6) * (1 + disturbance)
            ay += self.rng.uniform(-0.4, 0.4) * (1 + disturbance)
            gain = 2 if m.panic else 1
            m.vx = (m.vx + ax * dt * gain) * 0.985
            m.vy = (m.vy + ay * dt * gain) * 0.985
            speed = math.hypot(m.vx, m.vy)
            max_speed = 12 if m.panic else 9
            if speed > max_speed:
                m.vx *= max_speed / speed
                m.vy *= max_speed / speed
            m.x = clamp(m.x + m.vx * dt, 1, stage.w - 2)
            m.y = clamp(m.y + m.vy * dt, 1, stage.h - 2)
            alive.append(m)
        self.moths = alive[-self.max_moths:]

    def render(self, c: Canvas, now: float) -> None:
        palettes = [(244, 250, 229, 223, 217, 211), (45, 51, 87, 123, 159, 195), (201, 207, 213, 219, 225, 231), (82, 118, 154, 190, 226, 220)]
        palette = palettes[self.palette]
        glyphs = ".^'v*+"
        for i, m in enumerate(self.moths):
            frame = int(now * (20 if m.panic else 14) + i * 1.7 + m.phase) % len(glyphs)
            c.put(round(m.x), round(m.y), glyphs[frame], palette[(frame + i) % len(palette)], frame in (1, 4))
        if self.fx_mode:
            c.text(2, max(1, c.h - 4), f' MOTH FX :: {self.forms[self.form]} target={self.population:03d}  [ ] formation  +/- population  P palette  Space burst  R random  Esc '[:max(0, c.w - 4)], 219, True)

class CableCrawler:

    def __init__(self, rng: random.Random) -> None:
        self.rng = rng
        self.active = False
        self.route: List[Coord] = []
        self.i = 0
        self.acc = 0.0
        self.hops = 0
        self.tail: Deque[Coord] = deque(maxlen=22)

    def trigger(self, stage: Stage) -> None:
        if not stage.graph_list:
            return
        start = self.rng.choice(stage.graph_list)
        goal = stage.far_node(self.rng, start, 15)
        self.route = stage.path(start, goal)
        self.i = 0
        self.acc = 0
        self.hops = self.rng.randint(4, 7)
        self.active = bool(self.route)

    @property
    def pos(self) -> Coord:
        if self.route:
            return self.route[min(self.i, len(self.route) - 1)]
        return (0, 0)

    def update(self, dt: float, stage: Stage, achars: ACharField, lichen: 'Lichen') -> None:
        if not self.active or not self.route:
            return
        self.acc += dt * 21
        while self.acc >= 1 and self.active:
            self.acc -= 1
            p = self.route[self.i]
            self.tail.appendleft(p)
            lichen.stimulate(p, 0.1)
            if p in stage.gaps:
                stage.mark_repaired(p, self.rng.uniform(5, 11))
                achars.spark(*p, 3)
            if self.i < len(self.route) - 1:
                self.i += 1
            elif self.hops > 0:
                self.hops -= 1
                start = self.pos
                goal = stage.far_node(self.rng, start, 12)
                self.route = stage.path(start, goal)
                self.i = 0
            else:
                self.active = False

    def render(self, c: Canvas, now: float) -> None:
        for j, (x, y) in enumerate(reversed(list(self.tail))):
            c.put(x, y, '=' if j % 3 else '~', 22 + min(6, j // 3))
        if self.active:
            c.put(*self.pos, '@', 46, True)

class Lift:

    def __init__(self, rng: random.Random) -> None:
        self.rng = rng
        self.state = 'hidden'
        self.y = 0.0
        self.target = 0.0
        self.stops: List[int] = []
        self.timer = 0.0

    @property
    def active(self) -> bool:
        return self.state != 'hidden'

    def trigger(self, stage: Stage, gremlin: Gremlin) -> None:
        choices = sorted(set((stage.hlines[0] + 2, stage.hlines[1], stage.hlines[2], max(stage.hlines[0] + 2, stage.h - 5))))
        if self.active:
            self.stops.append(self.rng.choice(choices))
            return
        self.stops = self.rng.sample(choices, self.rng.randint(2, min(4, len(choices))))
        self.y = float(stage.h - 3)
        self.target = float(self.stops.pop(0))
        self.state = 'move'
        self.timer = 0

    def update(self, dt: float, stage: Stage) -> None:
        if self.state == 'hidden':
            return
        self.timer += dt
        if self.state in ('move', 'depart'):
            dy = self.target - self.y
            step = sign(dy) * (9 if self.state == 'move' else 11) * dt
            if abs(step) >= abs(dy):
                self.y = self.target
                self.state = 'hidden' if self.state == 'depart' else 'open'
                self.timer = 0
            else:
                self.y += step
        elif self.state == 'open' and self.timer > 0.5:
            self.state = 'dwell'
            self.timer = 0
        elif self.state == 'dwell' and self.timer > 1.8:
            self.state = 'close'
            self.timer = 0
        elif self.state == 'close' and self.timer > 0.5:
            if self.stops:
                self.target = float(self.stops.pop(0))
                self.state = 'move'
            else:
                self.target = float(stage.h - 3)
                self.state = 'depart'
            self.timer = 0

    def render(self, c: Canvas, stage: Stage, now: float) -> None:
        if not self.active:
            return
        x = stage.shaft_x
        y = round(self.y)
        doors = '<  >' if self.state == 'dwell' else '[  ]' if self.state in ('open', 'close') else '[||]'
        c.text(x - 2, y - 1, '+---+', 208, True)
        c.text(x - 2, y, doors, 214, True)
        c.text(x - 2, y + 1, '+---+', 208, True)

class Ghost:

    def __init__(self, rng: random.Random) -> None:
        self.rng = rng
        self.active = False
        self.pos = (2, 2)
        self.target = (2, 2)
        self.visits = 0

    def trigger(self, stage: Stage) -> None:
        if not stage.control_nodes:
            return
        self.active = True
        self.pos = self.rng.choice(stage.control_nodes)
        self.target = self.rng.choice(stage.control_nodes)
        self.visits = self.rng.randint(5, 10)

    def update(self, dt: float, stage: Stage, achars: ACharField) -> None:
        if not self.active:
            return
        x, y = self.pos
        tx, ty = self.target
        dx = tx - x
        dy = ty - y
        if abs(dx) + abs(dy) <= 1:
            achars.charge_near(x, y, 4, 0.4)
            self.visits -= 1
            if self.visits <= 0:
                self.active = False
                return
            self.target = self.rng.choice(stage.control_nodes)
            return
        self.pos = (x + sign(dx), y + sign(dy))

    def render(self, c: Canvas, now: float) -> None:
        if self.active:
            c.put(*self.pos, '+', 195 if int(now * 12) & 1 else 159, True)

class Lichen:

    def __init__(self, rng: random.Random) -> None:
        self.rng = rng
        self.cover: Dict[Coord, float] = {}
        self.active = False
        self.acc = 0.0

    def trigger(self, stage: Stage) -> None:
        self.active = True
        if stage.graph_list:
            for p in self.rng.sample(stage.graph_list, min(len(stage.graph_list), self.rng.randint(8, 18))):
                self.cover[p] = self.rng.uniform(0.3, 0.8)

    def stimulate(self, p: Coord, amount: float=0.1) -> None:
        if p in self.cover:
            self.cover[p] = clamp(self.cover[p] + amount, 0, 1)
        elif self.rng.random() < amount * 2:
            self.cover[p] = amount

    def burn_near(self, x: float, y: float, r: float=4) -> None:
        r2 = r * r
        for p in list(self.cover):
            if (p[0] - x) ** 2 + (p[1] - y) ** 2 <= r2:
                self.cover[p] -= 0.7
                if self.cover[p] <= 0:
                    self.cover.pop(p, None)

    def update(self, dt: float, stage: Stage) -> None:
        self.acc += dt * (4 if self.active else 1)
        while self.acc >= 1 and self.cover:
            self.acc -= 1
            p = self.rng.choice(list(self.cover))
            self.cover[p] = clamp(self.cover[p] + self.rng.uniform(0.02, 0.08), 0, 1)
            neighbors = list(stage.neighbors(p))
            if neighbors and self.rng.random() < 0.6:
                q = self.rng.choice(neighbors)
                self.cover[q] = max(self.cover.get(q, 0), self.rng.uniform(0.08, 0.28))
            if len(self.cover) > 450:
                self.active = False

    def render(self, c: Canvas, now: float) -> None:
        glyphs = '.:*#%'
        palette = (22, 28, 34, 40, 46)
        for i, (p, v) in enumerate(self.cover.items()):
            level = min(4, int(v * 5))
            fg = palette[level]
            if v > 0.7 and int(now * 5 + i) % 6 == 0:
                fg = (82, 118, 154, 190)[i % 4]
            c.put(*p, glyphs[level], fg, level >= 2)

@dataclass
class ArcSeg:
    a: Coord
    b: Coord
    ttl: float
    age: float = 0.0

class ArcStorm:

    def __init__(self, rng: random.Random) -> None:
        self.rng = rng
        self.active_for = 0.0
        self.arcs: List[ArcSeg] = []
        self.acc = 0.0

    @property
    def active(self) -> bool:
        return self.active_for > 0 or bool(self.arcs)

    def trigger(self, stage: Stage) -> None:
        self.active_for = max(self.active_for, self.rng.uniform(4, 8))
        self._spawn(stage)

    def _spawn(self, stage: Stage) -> None:
        nodes = stage.lamps + stage.junctions
        if len(nodes) < 2:
            return
        a = self.rng.choice(nodes)
        far = [p for p in nodes if manhattan(p, a) >= 6]
        b = self.rng.choice(far or nodes)
        self.arcs.append(ArcSeg(a=a, b=b, ttl=self.rng.uniform(0.18, 0.45)))

    def update(self, dt: float, stage: Stage, achars: ACharField, moths: RelayMoths, lichen: Lichen, drone: 'LanderDrone') -> None:
        self.active_for = max(0, self.active_for - dt)
        self.acc += dt
        if self.active_for > 0 and self.acc > 0.25:
            self.acc = 0
            self._spawn(stage)
        alive = []
        for arc in self.arcs:
            arc.age += dt
            if arc.age >= arc.ttl:
                continue
            alive.append(arc)
            t = clamp(arc.age / arc.ttl, 0, 1)
            x = arc.a[0] + (arc.b[0] - arc.a[0]) * t
            y = arc.a[1] + (arc.b[1] - arc.a[1]) * t
            achars.charge_near(x, y, 6, 0.8)
            moths.panic_near(x, y, 8)
            lichen.burn_near(x, y, 3.5)
            if drone.active and (drone.x - x) ** 2 + (drone.y - y) ** 2 < 36:
                drone.electrical = min(1.5, drone.electrical + 0.1)
        self.arcs = alive

    def render(self, c: Canvas, now: float) -> None:
        for j, arc in enumerate(self.arcs):
            x0, y0 = arc.a
            x1, y1 = arc.b
            n = max(abs(x1 - x0), abs(y1 - y0), 1)
            for i in range(n + 1):
                t = i / n
                x = round(x0 + (x1 - x0) * t)
                y = round(y0 + (y1 - y0) * t + math.sin(t * math.pi * 7 + now * 18) * 0.6)
                c.put(x, y, '.*+~#'[(i + int(now * 30) + j) % 5], (51, 87, 123, 159, 195, 201, 207)[(i + j) % 7], True)

@dataclass
class Exhaust:
    x: float
    y: float
    vx: float
    vy: float
    ttl: float
    age: float = 0.0

class LanderDrone:
    GRAVITY = 3.0
    MAIN_THRUST = 7.6
    ROTATE_RATE = 2.35
    MAX_SPEED = 24.0
    CONTROL_HOLD = 0.16
    MODE_DEBOUNCE = 0.38
    SOFT_VY = 1.45
    SOFT_VX = 1.2
    SOFT_ANGLE = math.radians(20)
    HARD_VY = 2.7
    HARD_VX = 2.1
    HARD_ANGLE = math.radians(38)
    PAD_HALF_WIDTH = 5

    def __init__(self, rng: random.Random) -> None:
        self.rng = rng
        self.active = False
        self.x = 10.0
        self.y = 5.0
        self.vx = 0.0
        self.vy = 0.0
        self.angle = 0.0
        self.mode = 'MANUAL'
        self.fuel = 100.0
        self.electrical = 0.0
        self.landed = False
        self.crashed = False
        self.status = 'STOWED'
        self.pad_x = 10.0
        self.ground_y = 20.0
        self.last_mode_toggle = -999.0
        self.left_hold = 0.0
        self.right_hold = 0.0
        self.thrust_hold = 0.0
        self.retro_hold = 0.0
        self.exhaust: List[Exhaust] = []
        self.trail: Deque[Coord] = deque(maxlen=28)
        self.crash_flash = 0.0

    def _normalise_angle(self, angle: float) -> float:
        return (angle + math.pi) % (math.pi * 2) - math.pi

    def _choose_pad(self, stage: Stage) -> None:
        self.ground_y = float(stage.h - 3)
        margin = max(8, self.PAD_HALF_WIDTH + 3)
        if stage.w > margin * 2:
            self.pad_x = float(self.rng.randint(margin, stage.w - margin - 1))
        else:
            self.pad_x = stage.w / 2

    def _reset_flight(self, stage: Stage) -> None:
        self._choose_pad(stage)
        self.x = stage.w / 2
        self.y = 3.0
        self.vx = self.rng.uniform(-1.0, 1.0)
        self.vy = self.rng.uniform(-0.1, 0.3)
        self.angle = self.rng.uniform(-0.12, 0.12)
        self.fuel = 100.0
        self.landed = False
        self.crashed = False
        self.left_hold = 0.0
        self.right_hold = 0.0
        self.thrust_hold = 0.0
        self.retro_hold = 0.0
        self.trail.clear()
        self.crash_flash = 0.0
        self.status = self.mode

    def trigger(self, stage: Stage) -> None:
        if self.active:
            self.active = False
            self.status = 'STOWED'
            return
        self.active = True
        self.mode = 'MANUAL'
        self._reset_flight(stage)

    def toggle_mode(self, stage: Stage, now: Optional[float]=None) -> bool:
        if not self.active:
            return False
        if now is None:
            now = time.monotonic()
        if now - self.last_mode_toggle < self.MODE_DEBOUNCE:
            return False
        self.last_mode_toggle = now
        self.mode = 'AUTO' if self.mode == 'MANUAL' else 'MANUAL'
        self.status = self.mode
        self.left_hold = 0.0
        self.right_hold = 0.0
        self.thrust_hold = 0.0
        self.retro_hold = 0.0
        return True

    def press_left(self) -> None:
        if self.active and self.mode == 'MANUAL' and (not self.crashed):
            self.left_hold = max(self.left_hold, self.CONTROL_HOLD)
            if self.landed:
                self.landed = False

    def press_right(self) -> None:
        if self.active and self.mode == 'MANUAL' and (not self.crashed):
            self.right_hold = max(self.right_hold, self.CONTROL_HOLD)
            if self.landed:
                self.landed = False

    def press_thrust(self) -> None:
        if self.active and self.mode == 'MANUAL' and (not self.crashed) and (self.fuel > 0):
            self.thrust_hold = max(self.thrust_hold, self.CONTROL_HOLD)
            self.landed = False

    def press_retro(self) -> None:
        if self.active and self.mode == 'MANUAL' and (not self.crashed):
            self.retro_hold = max(self.retro_hold, self.CONTROL_HOLD)
            self.landed = False

    def _emit_exhaust(self, power: float) -> None:
        nx = math.sin(self.angle)
        ny = -math.cos(self.angle)
        count = max(1, int(4 * power))
        for _ in range(count):
            self.exhaust.append(Exhaust(x=self.x - nx * 1.4, y=self.y - ny * 0.8, vx=-nx * self.rng.uniform(3.5, 8.5) + self.rng.uniform(-1.0, 1.0), vy=-ny * self.rng.uniform(2.0, 5.0) + self.rng.uniform(-0.5, 0.5), ttl=self.rng.uniform(0.28, 0.85)))
        self.exhaust = self.exhaust[-240:]

    def _engine(self, power: float, dt: float) -> None:
        if self.fuel <= 0:
            return
        power = clamp(power, 0.0, 1.0)
        ax = math.sin(self.angle) * self.MAIN_THRUST * power
        ay = -math.cos(self.angle) * self.MAIN_THRUST * power
        self.vx += ax * dt
        self.vy += ay * dt
        self.fuel = max(0.0, self.fuel - power * 7.0 * dt)
        self._emit_exhaust(power)

    def _manual_controls(self, dt: float) -> None:
        if self.left_hold > 0:
            self.angle -= self.ROTATE_RATE * dt
        if self.right_hold > 0:
            self.angle += self.ROTATE_RATE * dt
        if self.thrust_hold > 0:
            self._engine(1.0, dt)
        if self.retro_hold > 0 and self.fuel > 0:
            factor = max(0.0, 1.0 - dt * 2.7)
            self.vx *= factor
            self.vy *= factor
            self.angle *= max(0.0, 1.0 - dt * 2.0)
            self.fuel = max(0.0, self.fuel - dt * 2.0)
            self._emit_exhaust(0.25)

    def _autopilot(self, dt: float) -> None:
        dx = self.pad_x - self.x
        altitude = self.ground_y - self.y
        desired_angle = clamp(dx * 0.045 - self.vx * 0.09, -0.62, 0.62)
        if altitude < 7:
            desired_angle *= max(0, altitude / 7)
        angle_error = self._normalise_angle(desired_angle - self.angle)
        max_turn = self.ROTATE_RATE * dt
        self.angle += clamp(angle_error, -max_turn, max_turn)
        if altitude > 18:
            desired_vy = 2.4
        elif altitude > 10:
            desired_vy = 1.8
        elif altitude > 5:
            desired_vy = 1.15
        elif altitude > 2:
            desired_vy = 0.7
        else:
            desired_vy = 0.35
        error_vy = self.vy - desired_vy
        power = clamp(error_vy * 0.3, 0.0, 1.0)
        if abs(dx) > 4 and altitude > 3:
            power = max(power, 0.42)
        if altitude < 4:
            power = max(power, 0.46)
        if power > 0:
            self._engine(power, dt)
        self.status = 'AUTO FINAL' if altitude < 5 else 'AUTO SEEK'

    def _crash(self, achars: ACharField, moths: RelayMoths, lichen: Lichen) -> None:
        self.crashed = True
        self.landed = False
        self.status = 'IMPACT'
        self.crash_flash = 1.0
        self.vx = 0.0
        self.vy = 0.0
        achars.spark(self.x, self.y, 18)
        moths.panic_near(self.x, self.y, 13)
        lichen.burn_near(self.x, self.y, 4)

    def _ground_collision(self, achars: ACharField, moths: RelayMoths, lichen: Lichen) -> None:
        if self.y < self.ground_y:
            return
        self.y = self.ground_y
        impact_vx = abs(self.vx)
        impact_vy = abs(self.vy)
        angle_error = abs(self._normalise_angle(self.angle))
        on_pad = abs(self.x - self.pad_x) <= self.PAD_HALF_WIDTH
        if impact_vy <= self.SOFT_VY and impact_vx <= self.SOFT_VX and (angle_error <= self.SOFT_ANGLE) and on_pad:
            self.landed = True
            self.vx = 0.0
            self.vy = 0.0
            self.angle *= 0.2
            self.status = 'SOFT LAND'
            return
        if impact_vy <= self.HARD_VY and impact_vx <= self.HARD_VX and (angle_error <= self.HARD_ANGLE) and on_pad:
            self.landed = True
            self.vx = 0.0
            self.vy = 0.0
            self.angle *= 0.35
            self.status = 'HARD LAND'
            achars.spark(self.x, self.y, 4)
            return
        if impact_vy < 0.8 and impact_vx < 0.6 and (angle_error < self.SOFT_ANGLE):
            self.landed = True
            self.vx = 0.0
            self.vy = 0.0
            self.status = 'WRONG PAD'
            return
        self._crash(achars, moths, lichen)

    def update(self, dt: float, stage: Stage, achars: ACharField, moths: RelayMoths, lichen: Lichen) -> None:
        self.ground_y = float(stage.h - 3)
        self.crash_flash = max(0.0, self.crash_flash - dt)
        self.electrical = max(0.0, self.electrical - dt * 0.25)
        alive = []
        for e in self.exhaust:
            e.age += dt
            if e.age >= e.ttl:
                continue
            e.x += e.vx * dt
            e.y += e.vy * dt
            e.vx *= 0.96
            e.vy *= 0.96
            alive.append(e)
        self.exhaust = alive
        if not self.active:
            return
        self.left_hold = max(0.0, self.left_hold - dt)
        self.right_hold = max(0.0, self.right_hold - dt)
        self.thrust_hold = max(0.0, self.thrust_hold - dt)
        self.retro_hold = max(0.0, self.retro_hold - dt)
        if self.crashed:
            self.status = 'IMPACT // D RECALL'
            return
        if self.landed:
            self.status = 'LANDED ' + self.mode
            return
        if self.mode == 'AUTO':
            self._autopilot(dt)
        else:
            self._manual_controls(dt)
            self.status = 'MANUAL'
        self.vy += self.GRAVITY * dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.angle = self._normalise_angle(self.angle)
        speed = math.hypot(self.vx, self.vy)
        if speed > self.MAX_SPEED:
            self.vx *= self.MAX_SPEED / speed
            self.vy *= self.MAX_SPEED / speed
        if self.x < 2:
            self.x = 2
            self.vx = abs(self.vx) * 0.45
        elif self.x > stage.w - 3:
            self.x = float(stage.w - 3)
            self.vx = -abs(self.vx) * 0.45
        if self.y < 2:
            self.y = 2
            self.vy = abs(self.vy) * 0.25
        self.trail.appendleft((int(round(self.x)), int(round(self.y))))
        self._ground_collision(achars, moths, lichen)
        moths.panic_near(self.x, self.y, 5)
        achars.charge_near(self.x, self.y, 3, 0.1 + self.electrical * 0.2)
        lichen.burn_near(self.x, self.y, 1.2)

    def render(self, c: Canvas, stage: Stage, now: float) -> None:
        ground_y = int(self.ground_y + 1)
        if 1 <= ground_y < c.h - 1:
            for x in range(1, c.w - 1):
                c.put(x, ground_y, '_', 238)
        px = int(round(self.pad_x))
        py = int(round(self.ground_y + 1))
        c.text(px - self.PAD_HALF_WIDTH, py, '=' * (self.PAD_HALF_WIDTH * 2 + 1), 82, True)
        c.text(max(1, px - 3), min(c.h - 2, py + 1), 'PAD 13', 82, True)
        for e in self.exhaust:
            t = e.age / e.ttl
            fg = (226, 220, 214, 208, 202)[min(4, int(t * 5))]
            c.put(int(round(e.x)), int(round(e.y)), '*' if t < 0.25 else '.', fg, t < 0.25)
        if not self.active:
            return
        for i, (tx, ty) in enumerate(list(self.trail)[2:18]):
            c.put(tx, ty, ':' if i % 2 else '.', 54 + min(6, i // 3))
        x = int(round(self.x))
        y = int(round(self.y))
        orientation = int(round(self.angle / (math.pi / 4))) % 8
        nose = ('^', '/', '>', '\\', 'v', '/', '<', '\\')[orientation]
        wing = ('=', '/', '|', '\\', '=', '/', '|', '\\')[orientation]
        if self.crashed:
            nose = '#'
            wing = 'x'
        fg = 231 if self.crash_flash > 0 else 195 if self.electrical > 0 else 159 if self.mode == 'MANUAL' else 118
        c.put(x, y, nose, fg, True)
        c.put(x - 1, y, wing, fg, True)
        c.put(x + 1, y, wing, fg, True)
        c.put(x, y + 1, 'o', 87, True)
        altitude = max(0.0, self.ground_y - self.y)
        hud = f' {self.mode:<6} ALT {altitude:05.1f} ANG {math.degrees(self.angle):+04.0f} VX {self.vx:+05.1f} VY {self.vy:+05.1f} FUEL {self.fuel:05.1f} // {self.status} '
        c.text(2, 1, hud[:max(0, c.w - 4)], fg, True)

class Coolant:

    def __init__(self, rng: random.Random) -> None:
        self.rng = rng
        self.active_for = 0.0
        self.drops: List[Particle] = []
        self.source = (10.0, 2.0)
        self.acc = 0.0

    @property
    def active(self) -> bool:
        return self.active_for > 0 or bool(self.drops)

    def trigger(self, stage: Stage) -> None:
        self.active_for = max(self.active_for, self.rng.uniform(8, 14))
        self.source = (self.rng.uniform(4, stage.w - 5), self.rng.uniform(2, max(3, stage.hlines[0] - 1)))

    def update(self, dt: float, stage: Stage, achars: ACharField, moths: RelayMoths) -> None:
        self.active_for = max(0, self.active_for - dt)
        if self.active_for > 0:
            self.acc += dt * 18
            while self.acc >= 1:
                self.acc -= 1
                self.drops.append(Particle(x=self.source[0], y=self.source[1], vx=self.rng.uniform(-2, 2), vy=self.rng.uniform(1, 5), ttl=self.rng.uniform(5, 10), glyph=self.rng.choice('.oO*'), palette=(33, 39, 45, 51, 87, 123, 159, 195, 201, 207, 213, 219)))
        alive = []
        for p in self.drops:
            p.age += dt
            if p.age >= p.ttl:
                continue
            old_y = p.y
            p.vy += 5 * dt
            p.vx += math.sin(p.y * 0.3 + time.monotonic() * 2) * 0.7 * dt
            p.x += p.vx * dt
            p.y += p.vy * dt
            for level in stage.hlines + [stage.h - 2]:
                if old_y < level <= p.y:
                    p.y = level - 1
                    p.vy = -abs(p.vy) * 0.25
                    p.vx += self.rng.uniform(-3, 3)
                    achars.spark(p.x, p.y, 1)
                    moths.panic_near(p.x, p.y, 3)
                    break
            p.x = clamp(p.x, 1, stage.w - 2)
            if p.y < stage.h - 2:
                alive.append(p)
        self.drops = alive[-280:]

    def render(self, c: Canvas, now: float) -> None:
        for i, p in enumerate(self.drops):
            c.put(round(p.x), round(p.y), p.glyph, p.palette[(i + int(now * 8)) % len(p.palette)], p.glyph in 'O*')
        if self.active:
            c.put(round(self.source[0]), round(self.source[1]), 'V', 219, True)

class Aurora:

    def __init__(self, rng: random.Random) -> None:
        self.rng = rng
        self.active_for = 0.0
        self.phase = 0.0
        self.bands = 3
        self.mode = 0

    @property
    def active(self) -> bool:
        return self.active_for > 0

    def trigger(self, stage: Stage) -> None:
        self.active_for = max(self.active_for, self.rng.uniform(7, 14))
        self.bands = self.rng.randint(2, 6)
        self.mode = (self.mode + 1) % 4

    def wave_y(self, x: float, stage: Stage, offset: float=0) -> float:
        if self.mode == 0:
            return stage.h / 2 + math.sin(x * 0.09 + self.phase + offset) * stage.h * 0.22
        if self.mode == 1:
            return stage.h / 2 + math.sin(x * 0.17 - self.phase * 1.3 + offset) * 4 + math.sin(x * 0.05 + self.phase) * 5
        if self.mode == 2:
            return stage.h / 2 + math.sin((x - stage.w / 2) * 0.12 + self.phase + offset) * (3 + abs(x - stage.w / 2) * 0.04)
        return stage.h / 2 + math.sin(x * 0.06 + self.phase + offset) * stage.h * 0.3 + math.sin(x * 0.21 - self.phase * 2) * 2

    def update(self, dt: float) -> None:
        self.active_for = max(0, self.active_for - dt)
        self.phase += dt * 2.4

    def render(self, c: Canvas, stage: Stage, now: float) -> None:
        if not self.active:
            return
        palette = (17, 18, 19, 20, 21, 27, 33, 39, 45, 51, 87, 123, 159, 195, 201, 207, 213, 219)
        for band in range(self.bands):
            for x in range(1, c.w - 1):
                y = round(self.wave_y(x, stage, band * 1.3))
                if 1 <= y < c.h - 1:
                    c.put(x, y, '.~=*+'[(x + band + int(now * 10)) % 5], palette[(x + band * 7 + int(now * 15)) % len(palette)], (x + band) % 7 == 0)
EFFECTS = [('g', 'Robot Gremlin'), ('b', 'Loose Hardware / aChars'), ('t', 'Phantom Transmission'), ('m', 'Relay Moths'), ('c', 'Cable Crawler'), ('l', 'Unauthorized Lift'), ('o', 'Ghost Operator'), ('f', 'Signal Lichen'), ('x', 'Arc Storm'), ('d', 'Lunar-Service Drone'), ('v', 'Prismatic Coolant'), ('z', 'Diagnostic Aurora')]
DEFAULT_CHANCES = {'g': 0.55, 'b': 0.68, 't': 0.38, 'm': 0.62, 'c': 0.48, 'l': 0.28, 'o': 0.34, 'f': 0.26, 'x': 0.24, 'd': 0.18, 'v': 0.3, 'z': 0.16}
BASE_WINDOWS = {'g': (30, 90), 'b': (22, 65), 't': (45, 110), 'm': (28, 75), 'c': (35, 90), 'l': (55, 145), 'o': (45, 115), 'f': (70, 175), 'x': (65, 170), 'd': (75, 190), 'v': (55, 145), 'z': (85, 220)}

class AmbientScheduler:
    """
    Percentage directly scales event rate:

        100% -> normal cadence
         50% -> ~half frequency
         25% -> ~quarter frequency
          0% -> never

    Menu changes reschedule immediately.
    """

    def __init__(self, rng: random.Random) -> None:
        self.rng = rng
        self.enabled = True
        self.effect_enabled = {key: True for key, _ in EFFECTS}
        self.chance = dict(DEFAULT_CHANCES)
        self.next: Dict[str, float] = {}
        self.reschedule_all(time.monotonic(), soon=True)

    def _schedule(self, key: str, now: float, soon: bool=False) -> None:
        if not self.effect_enabled.get(key, True):
            self.next[key] = math.inf
            return
        chance = clamp(self.chance.get(key, 0.0), 0.0, 1.0)
        if chance <= 0:
            self.next[key] = math.inf
            return
        lo, hi = BASE_WINDOWS[key]
        if soon:
            lo = max(3.0, lo * 0.18)
            hi = max(6.0, hi * 0.18)
        base_delay = self.rng.uniform(lo, hi)
        self.next[key] = now + base_delay / chance

    def reschedule_all(self, now: Optional[float]=None, soon: bool=False) -> None:
        if now is None:
            now = time.monotonic()
        for key, _ in EFFECTS:
            self._schedule(key, now, soon)

    def toggle_master(self, now: Optional[float]=None) -> None:
        if now is None:
            now = time.monotonic()
        self.enabled = not self.enabled
        if self.enabled:
            self.reschedule_all(now, soon=False)

    def set_effect_enabled(self, key: str, enabled: bool, now: Optional[float]=None) -> None:
        if now is None:
            now = time.monotonic()
        self.effect_enabled[key] = bool(enabled)
        self._schedule(key, now)

    def toggle_effect(self, key: str, now: Optional[float]=None) -> None:
        self.set_effect_enabled(key, not self.effect_enabled.get(key, True), now)

    def set_chance(self, key: str, value: float, now: Optional[float]=None) -> None:
        if now is None:
            now = time.monotonic()
        self.chance[key] = clamp(value, 0.0, 1.0)
        self._schedule(key, now)

    def adjust_chance(self, key: str, delta: float, now: Optional[float]=None) -> None:
        self.set_chance(key, self.chance.get(key, 0.0) + delta, now)

    def reset_defaults(self, now: Optional[float]=None) -> None:
        if now is None:
            now = time.monotonic()
        self.chance = dict(DEFAULT_CHANCES)
        self.reschedule_all(now, soon=False)

    def next_in(self, key: str, now: Optional[float]=None) -> Optional[float]:
        if now is None:
            now = time.monotonic()
        when = self.next.get(key, math.inf)
        if not math.isfinite(when):
            return None
        return max(0.0, when - now)

    def due(self, now: float) -> List[str]:
        if not self.enabled:
            return []
        fired = []
        for key, _ in EFFECTS:
            if not self.effect_enabled.get(key, True) or self.chance.get(key, 0) <= 0:
                continue
            if now >= self.next.get(key, math.inf):
                fired.append(key)
                self._schedule(key, now)
        return fired

class EffectsPanel:
    """
    Fixed menu controls.

    Navigation:
        UP/DOWN
        W/S

    Chance:
        LEFT/RIGHT
        -/+

    Enable:
        ENTER
        SPACE

    Also:
        T = trigger selected immediately
        A = ambient master
        R = reset chances
        0 = selected chance 0%
        1 = selected chance 100%
        E / ESC = close

    This panel is modal. App.handle_key() gives it first refusal on every key.
    """

    def __init__(self) -> None:
        self.open = False
        self.selected = 0
        self.feedback = ''
        self.feedback_until = 0.0

    def toggle(self) -> None:
        self.open = not self.open

    def _selected_key(self) -> str:
        return EFFECTS[self.selected][0]

    def _flash(self, text: str, seconds: float=0.8) -> None:
        self.feedback = text
        self.feedback_until = time.monotonic() + seconds

    def handle(self, key: str, ambient: AmbientScheduler, trigger_callback, now: Optional[float]=None) -> bool:
        if not self.open:
            return False
        if now is None:
            now = time.monotonic()
        if key == '\x1b' or (len(key) == 1 and key.lower() == 'e'):
            self.open = False
            return True
        if key == 'UP' or (len(key) == 1 and key.lower() == 'w'):
            self.selected = (self.selected - 1) % len(EFFECTS)
            self._flash(EFFECTS[self.selected][1])
            return True
        if key == 'DOWN' or (len(key) == 1 and key.lower() == 's'):
            self.selected = (self.selected + 1) % len(EFFECTS)
            self._flash(EFFECTS[self.selected][1])
            return True
        effect_key = self._selected_key()
        if key == 'LEFT' or key == '-':
            ambient.adjust_chance(effect_key, -0.05, now)
            self._flash(f'{int(round(ambient.chance[effect_key] * 100))}%')
            return True
        if key == 'RIGHT' or key in ('+', '='):
            ambient.adjust_chance(effect_key, 0.05, now)
            self._flash(f'{int(round(ambient.chance[effect_key] * 100))}%')
            return True
        if key == '0':
            ambient.set_chance(effect_key, 0.0, now)
            self._flash('0%')
            return True
        if key == '1':
            ambient.set_chance(effect_key, 1.0, now)
            self._flash('100%')
            return True
        if key in ('\r', '\n', ' '):
            ambient.toggle_effect(effect_key, now)
            self._flash('ENABLED' if ambient.effect_enabled[effect_key] else 'DISABLED')
            return True
        if len(key) == 1 and key.lower() == 't':
            if ambient.effect_enabled.get(effect_key, True):
                trigger_callback(effect_key)
                self._flash('TRIGGERED')
            else:
                self._flash('DISABLED')
            return True
        if len(key) == 1 and key.lower() == 'a':
            ambient.toggle_master(now)
            self._flash('AMBIENT ON' if ambient.enabled else 'AMBIENT OFF')
            return True
        if len(key) == 1 and key.lower() == 'r':
            ambient.reset_defaults(now)
            self._flash('DEFAULTS')
            return True
        return True

    def render(self, c: Canvas, ambient: AmbientScheduler) -> None:
        if not self.open:
            return
        now = time.monotonic()
        w = min(c.w - 4, 88)
        h = min(c.h - 2, len(EFFECTS) + 10)
        x = max(1, (c.w - w) // 2)
        y = max(1, (c.h - h) // 2)
        c.box(x, y, w, h, 159)
        c.text(x + 2, y + 1, 'EFFECTS / AMBIENT', 195, True, w - 4)
        c.text(x + 2, y + 2, f"MASTER: {('ON' if ambient.enabled else 'OFF')}    UP/DOWN or W/S select    LEFT/RIGHT or -/+ chance", 250, False, w - 4)
        c.text(x + 2, y + 3, 'SPACE/ENTER enable   T trigger now   A master   R defaults   0=0%  1=100%   E/ESC close', 244, False, w - 4)
        c.text(x + 2, y + 4, 'Chance directly scales ambient frequency: 100%=normal cadence, 50%=~half, 0%=never', 240, False, w - 4)
        for i, (effect_key, name) in enumerate(EFFECTS):
            yy = y + 6 + i
            if yy >= y + h - 2:
                break
            selected = i == self.selected
            enabled = ambient.effect_enabled.get(effect_key, True)
            chance = clamp(ambient.chance.get(effect_key, 0.0), 0, 1)
            percent = int(round(chance * 100))
            bar_width = 20
            bar_count = int(round(chance * bar_width))
            bar = '#' * bar_count + '.' * (bar_width - bar_count)
            remaining = ambient.next_in(effect_key, now)
            if not enabled:
                countdown = 'DISABLED'
            elif chance <= 0:
                countdown = 'NEVER'
            elif remaining is None:
                countdown = '---'
            elif remaining < 60:
                countdown = f'{remaining:4.0f}s'
            else:
                countdown = f'{remaining / 60:4.1f}m'
            line = f"{('>' if selected else ' ')} [{('ON ' if enabled else 'OFF')}] {effect_key.upper()} {name:<24} {percent:3d}% [{bar}] {countdown:>8}"
            c.text(x + 2, yy, line[:w - 4], 231 if selected else 250, selected, w - 4)
        if self.feedback and now < self.feedback_until:
            msg = f' {self.feedback} '
            c.text(max(x + 2, x + w - len(msg) - 3), y + 1, msg, 226, True)

class App:
    FPS = 24.0

    def __init__(self) -> None:
        self.rng = random.Random(time.time_ns() ^ os.getpid())
        size = shutil.get_terminal_size((120, 38))
        self.w = max(30, size.columns)
        self.h = max(16, size.lines)
        self.stage = Stage(self.w, self.h)
        self.input = InputReader()
        self.running = True
        self.help = False
        self.achars = ACharField(self.rng)
        self.gremlin = Gremlin(self.rng)
        self.phantom = Phantom(self.rng)
        self.moths = RelayMoths(self.rng)
        self.crawler = CableCrawler(self.rng)
        self.lift = Lift(self.rng)
        self.ghost = Ghost(self.rng)
        self.lichen = Lichen(self.rng)
        self.arc = ArcStorm(self.rng)
        self.drone = LanderDrone(self.rng)
        self.coolant = Coolant(self.rng)
        self.aurora = Aurora(self.rng)
        self.ambient = AmbientScheduler(self.rng)
        self.panel = EffectsPanel()
        self.last_size = (self.w, self.h)

    def context(self) -> Dict[str, bool]:
        return {'gremlin': self.gremlin.active, 'moths': self.moths.active, 'drone': self.drone.active, 'coolant': self.coolant.active}

    def trigger(self, key: str, manual: bool=True) -> None:
        if not self.ambient.effect_enabled.get(key, True):
            return
        if key == 'g':
            self.gremlin.trigger(self.stage)
        elif key == 'b':
            self.achars.spill(self.stage)
        elif key == 't':
            self.phantom.trigger(self.context(), self.stage)
        elif key == 'm':
            self.moths.trigger(self.stage)
        elif key == 'c':
            self.crawler.trigger(self.stage)
        elif key == 'l':
            self.lift.trigger(self.stage, self.gremlin)
        elif key == 'o':
            self.ghost.trigger(self.stage)
        elif key == 'f':
            self.lichen.trigger(self.stage)
        elif key == 'x':
            self.arc.trigger(self.stage)
        elif key == 'd':
            self.drone.trigger(self.stage)
        elif key == 'v':
            self.coolant.trigger(self.stage)
        elif key == 'z':
            self.aurora.trigger(self.stage)

    def handle_key(self, key: str) -> None:
        now = time.monotonic()

        # Modal popup has absolute keyboard ownership.
        if self.panel.open:
            self.panel.handle(key, self.ambient, self.trigger, now)
            return

        if len(key) == 1 and key.lower() == 'e':
            self.panel.open = True
            return

        if key == '\x18':
            self.achars.toggle_fx()
            return

        if key == '\x19':
            self.moths.toggle_fx(self.stage)
            return

        if self.achars.handle_fx_key(key, self.stage):
            return

        if self.moths.handle_fx_key(key, self.stage):
            return

        if self.drone.active:
            if key == 'UP':
                self.drone.toggle_mode(self.stage, now)
                return
            if key == 'LEFT':
                self.drone.press_left()
                return
            if key == 'RIGHT':
                self.drone.press_right()
                return
            if key == 'DOWN':
                self.drone.press_retro()
                return
            if key == ' ':
                self.drone.press_thrust()
                return

        k = key.lower() if len(key) == 1 else key

        if k == 'q':
            self.running = False
        elif key == '?':
            self.help = not self.help
        elif k == 'a':
            self.ambient.toggle_master(now)
        elif k == 'r':
            choices = [effect_key for effect_key, _ in EFFECTS if self.ambient.effect_enabled.get(effect_key, True)]
            if choices:
                self.trigger(self.rng.choice(choices))
        elif k in dict(EFFECTS):
            self.trigger(k)

    def resize(self) -> None:
        size = shutil.get_terminal_size((120, 38))
        w = max(30, size.columns)
        h = max(16, size.lines)
        if (w, h) == self.last_size:
            return
        self.last_size = (w, h)
        self.w = w
        self.h = h
        self.stage.rebuild(w, h)
        self.gremlin.state = 'hidden'
        self.crawler.active = False
        self.lift.state = 'hidden'
        self.ghost.active = False
        self.arc.arcs = []
        self.arc.active_for = 0
        self.drone.active = False

    def update(self, dt: float, now: float) -> None:
        for key in self.ambient.due(now):
            self.trigger(key, manual=False)
        self.achars.update(dt, self.stage)
        self.lift.update(dt, self.stage)
        self.drone.update(dt, self.stage, self.achars, self.moths, self.lichen)
        self.gremlin.update(dt, self.stage, self.achars)
        self.phantom.update(dt)
        self.coolant.update(dt, self.stage, self.achars, self.moths)
        self.lichen.update(dt, self.stage)
        self.crawler.update(dt, self.stage, self.achars, self.lichen)
        self.ghost.update(dt, self.stage, self.achars)
        self.arc.update(dt, self.stage, self.achars, self.moths, self.lichen, self.drone)
        self.aurora.update(dt)
        self.moths.update(dt, now, self.stage, self.gremlin, self.achars, self.drone)

    def help_overlay(self, c: Canvas) -> None:
        w = min(c.w - 6, 88)
        h = min(c.h - 6, 24)
        x = max(2, (c.w - w) // 2)
        y = max(2, (c.h - h) // 2)
        c.box(x, y, w, h, 159)
        lines = [
            'V4.2 // CHEAT SHEET',
            '',
            'LANDER:',
            '  D deploy/recall',
            '  LEFT/RIGHT rotate',
            '  SPACE main engine',
            '  DOWN damping/retro',
            '  UP AUTO <-> MANUAL',
            '',
            'EFFECTS MENU:',
            '  E open',
            '  UP/DOWN or W/S select',
            '  LEFT/RIGHT or -/+ adjust ambient chance',
            '  SPACE/ENTER enable/disable',
            '  T trigger selected',
            '  A ambient master',
            '  R defaults',
            '  0=0%   1=100%   E/ESC close',
            '',
            'Ctrl-X aChar FX   Ctrl-Y Moth FX',
            'G/B/T/M/C/L/O/F/X/D/V/Z individual effects',
            'R random effect   A ambient master   Q quit',
        ]
        for i, line in enumerate(lines[:h - 2]):
            c.text(x + 2, y + 1 + i, line, 159 if i == 0 else 250, i == 0, w - 4)

    def draw(self, now: float) -> str:
        c = Canvas(self.w, self.h)
        self.stage.render(c, now, self.ambient.enabled)
        self.aurora.render(c, self.stage, now)
        self.lichen.render(c, now)
        self.coolant.render(c, now)
        self.crawler.render(c, now)
        self.achars.render(c, now)
        self.moths.render(c, now)
        self.lift.render(c, self.stage, now)
        self.gremlin.render(c, self.stage, now)
        self.drone.render(c, self.stage, now)
        self.ghost.render(c, now)
        self.arc.render(c, now)
        self.phantom.render(c, self.stage, now)
        if self.help:
            self.help_overlay(c)
        self.panel.render(c, self.ambient)
        return c.render()

    def run(self) -> None:
        frame = 1 / self.FPS
        sys.stdout.write(ALT_ON + HIDE_CURSOR + CLEAR + HOME)
        sys.stdout.flush()
        last = time.monotonic()
        try:
            while self.running:
                start = time.monotonic()
                self.resize()
                for key in self.input.read_keys():
                    self.handle_key(key)
                now = time.monotonic()
                dt = min(0.1, max(0, now - last))
                last = now
                self.update(dt, now)
                sys.stdout.write(self.draw(now))
                sys.stdout.flush()
                elapsed = time.monotonic() - start
                if elapsed < frame:
                    time.sleep(frame - elapsed)
        except KeyboardInterrupt:
            pass
        finally:
            self.input.close()
            sys.stdout.write(RESET + SHOW_CURSOR + ALT_OFF)
            sys.stdout.flush()

def main() -> None:
    if not sys.stdout.isatty():
        print('This program needs an interactive ANSI terminal.', file=sys.stderr)
        raise SystemExit(2)
    App().run()

if __name__ == '__main__':
    main()
