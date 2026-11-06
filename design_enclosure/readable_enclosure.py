"""Readable enclosure: parametric CAD (CadQuery).

A two-part pebble-shaped shell (front + back) built around the real component
models in this folder, plus printed button caps.

    pip install cadquery
    python3 design_enclosure/readable_enclosure.py          # build, check, export
    python3 design_enclosure/readable_enclosure.py --no-check

Coordinates (mm): X = length, Y = width, Z = thickness.
Z = 0 is the BACK face (camera side, faces the page); Z = T is the FRONT face
(big Scan button, speaker, status LED). The user holds the device flat over
the page, like the renderings.

Layout, back to front:
  back shell (z 0..SPLIT): camera + illumination LED, PowerBoost, CM5 (SoC
      facing the vents), screw counterbores
  middle: CM5-NANO-B carrier, LiPo cell (over camera/PowerBoost)
  front shell (SPLIT..T): Scan button over the cell, speaker over the carrier,
      4 side buttons on the +Y wall, USB-C charge port and power switch on the
      -Y wall, lanyard post at the -X end

Every part position is a parameter below. Run with checks after any change:
the script reports interference between parts and the shell.

Fasteners: 5 x M2.5 x 10 screws from the back into M2.5 heat-set inserts
(OD 3.5-4.0 mm, 4-5 mm long) in the front shell.
"""
import argparse
import math
import os
import sys

import cadquery as cq

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")

# ----------------------------------------------------------------- shell
L, W, T = 128.0, 84.0, 30.0      # outer size
N_SUPER = 3.0                    # superellipse exponent (2 = ellipse, higher = squarer)
R_EDGE = 11.0                    # rounding of front/back edges (the pebble look)
WALL = 2.2
SPLIT = 10.5                     # z of the front/back parting line
LIP_H, LIP_T, LIP_GAP = 1.5, 1.2, 0.5    # gap clears the back shell's inner curve

# --------------------------------------------------------- components
BOARD_X0 = -2.0                  # CM5-NANO-B board origin (x), centred in y
BOARD_PCB_TOP = 9.8              # z of carrier PCB top surface
CM5_STACK_GAP = 0.4              # carrier underside to CM5 connector face
CAM_X0, CAM_Y0, CAM_Z = -33.0, 0.6, 8.1   # camera STEP origin; lens tip ~0.4 above back face
PB_X0, PB_Y0, PB_Z = -46.0, -24.0, 3.7    # PowerBoost 1000C origin (bottom of PCB)
BATT = dict(x0=-54.0, y0=-25.0, z0=11.0, lx=50.0, ly=50.0, lz=9.0)   # LiPo, set to your cell
SPK = dict(x=28.0, y=0.0, d=40.0, h=6.0)                             # 40 mm 3 W speaker
AMP = dict(x0=-8.0, y0=-34.0, lx=17.8, ly=19.3, z0=22.0, lz=4.0)     # MAX98357A breakout
SCAN = dict(x=-29.0, y=0.0, cap_d=30.0, sw=12.0, sw_h=4.3)           # 12x12x4.3 tactile
STATUS_LED = dict(x=-6.0, y=-9.0, d=3.0)
ILLUM_LED = dict(x=-6.0, y=13.0, d=5.0)
# Camera island: charcoal bezel over the lens + illumination LED, with a clear
# acrylic window (laser-cut 0.8 mm). Sits in a pocket in the back face.
ISLAND = dict(r=7.5, depth=1.0, proud=0.6, window_t=0.8, window_margin=2.3)
SIDE_Z = 17.0                    # height of the side buttons
SIDE_BUTTONS = [                 # on the +Y wall; shape = tactile cue for blind users
    dict(name="repeat", x=-38.0, shape="round"),
    dict(name="vol_up", x=-8.0, shape="dot"),
    dict(name="vol_down", x=6.0, shape="bar"),
    dict(name="lang", x=28.0, shape="square"),
]
USBC = dict(x=-20.0, z=16.0)     # USB-C panel breakout on the -Y wall
POWER_SW = dict(x=2.0, z=16.0)   # mini slide switch (SS12D00) on the -Y wall
BOSSES = [(-22.0, 29.0), (44.0, 27.0), (-40.0, -28.5), (20.0, -28.0), (44.0, -27.0)]
CM5_HOLES = [(3.5, 3.5), (51.5, 3.5), (3.5, 36.5), (51.5, 36.5)]
CAM_HOLES = [(2.0, 2.0), (2.0, 23.0), (14.5, 2.0), (14.5, 23.0)]
PB_HOLES = [(2.5, 2.5), (2.5, 20.3), (33.9, 5.2), (33.9, 18.3)]
VENT_XS = [8.0, 15.0, 22.0, 29.0, 36.0, 43.0]

STEP = {
    "carrier": "CM5-NANO-B.step",
    "cm5": "CM5R5-3dsteps.step",
    "camera": "Camera_module_3_std_model_simple.stp",
    "powerboost": "PowerBoost_1000C.step",
}


# =============================================================== helpers
def superellipse_pts(a, b, n=N_SUPER, count=64):
    pts = []
    for i in range(count):
        t = 2 * math.pi * i / count
        c, s = math.cos(t), math.sin(t)
        x = a * math.copysign(abs(c) ** (2 / n), c)
        y = b * math.copysign(abs(s) ** (2 / n), s)
        pts.append((x, y))
    return pts


def outline_wire(offset=0.0):
    pts = superellipse_pts(L / 2, W / 2)
    wire = cq.Workplane("XY").spline(pts, periodic=True, includeCurrent=False).close().wires().val()
    if offset:
        wire = wire.offset2D(offset, "arc")[0]
    return wire


def pebble(offset, z0, height, radius):
    """Extruded outline with rounded top and bottom edges."""
    face = cq.Face.makeFromWires(outline_wire(offset))
    solid = cq.Solid.extrudeLinear(face, cq.Vector(0, 0, height)).translate((0, 0, z0))
    wp = cq.Workplane("XY").add(solid)
    if radius > 0:
        wp = wp.edges("not |Z").fillet(radius)
    return wp.val()


def inner_half_width(x):
    """Half-width (y) of the inner wall at x, in the straight band."""
    a, b = L / 2 - WALL, W / 2 - WALL
    r = 1 - (abs(x) / a) ** N_SUPER
    return b * (r ** (1 / N_SUPER)) if r > 0 else 0.0


def side_ref(x, half=6.0):
    """Y of a side button's inner reference plane (flange back face): 1.7 mm
    inside the wall at its innermost point across the button, so the 1 mm
    flange clears the wall where it curves towards the ends (in plan) and
    towards the front face (the front fillet starts at z = 19)."""
    return min(inner_half_width(x - half), inner_half_width(x), inner_half_width(x + half)) - 1.7


def box(x0, y0, z0, lx, ly, lz):
    return cq.Workplane("XY").box(lx, ly, lz, centered=False).translate((x0, y0, z0)).val()


def cyl_z(x, y, z0, d, h):
    return cq.Workplane("XY").circle(d / 2).extrude(h).translate((x, y, z0)).val()


def cyl_y(x, y0, z, d, h):
    return cq.Workplane("XZ").circle(d / 2).extrude(-h).translate((x, y0, z)).val()


def load_step(name):
    return cq.importers.importStep(os.path.join(HERE, STEP[name])).val()


# ============================================================ components
def components():
    """Return {name: solid} in device coordinates."""
    c = {}
    carrier = load_step("carrier")  # PCB top at z=0, 56 x 41
    c["carrier"] = carrier.translate((BOARD_X0, -20.5, BOARD_PCB_TOP))
    cm5 = load_step("cm5")          # 55 x 40, PCB z 0..1.1, SoC on +z, connectors on -z
    carrier_bottom = BOARD_PCB_TOP - 1.25
    flipped = cm5.rotate((0, 0, 0), (1, 0, 0), 180)  # y -> -y, z -> -z
    c["cm5"] = flipped.translate((BOARD_X0, 19.5, carrier_bottom - CM5_STACK_GAP - 1.1))
    c["camera"] = load_step("camera").translate((CAM_X0, CAM_Y0, CAM_Z))
    c["powerboost"] = load_step("powerboost").translate((PB_X0, PB_Y0, PB_Z))
    c["battery"] = box(BATT["x0"], BATT["y0"], BATT["z0"], BATT["lx"], BATT["ly"], BATT["lz"])
    spk_z0 = T - WALL - 0.2 - SPK["h"]
    c["speaker"] = cyl_z(SPK["x"], SPK["y"], spk_z0, SPK["d"], SPK["h"])
    c["amp"] = box(AMP["x0"], AMP["y0"], AMP["z0"], AMP["lx"], AMP["ly"], AMP["lz"])
    sw = SCAN["sw"]
    c["scan_switch"] = box(SCAN["x"] - sw / 2, SCAN["y"] - sw / 2, scan_switch_z(), sw, sw, SCAN["sw_h"])
    for b in SIDE_BUTTONS:
        yr = side_ref(b["x"])
        c[f"sw_{b['name']}"] = box(b["x"] - 3, yr - 0.2 - 5.0, SIDE_Z - 3, 6, 5.0, 6)
    yw = -min(inner_half_width(USBC["x"] - 6), inner_half_width(USBC["x"] + 6))
    c["usbc_breakout"] = box(USBC["x"] - 6, yw + 0.3, USBC["z"] - 2.5, 12, 12, 5)
    yw = -inner_half_width(POWER_SW["x"])
    c["power_switch"] = box(POWER_SW["x"] - 4.3, yw + 0.3, POWER_SW["z"] - 1.8, 8.6, 3.6, 3.6)
    c["status_led"] = cyl_z(STATUS_LED["x"], STATUS_LED["y"], T - WALL - 4.5, STATUS_LED["d"], 4.5)
    c["illum_led"] = cyl_z(ILLUM_LED["x"], ILLUM_LED["y"], WALL, ILLUM_LED["d"], 8.6)
    return c


def scan_switch_z():
    # under the cap: flange (1.0) + 0.2 clearance, 0.6 plunger, 0.1 gap to the switch
    return T - WALL - 1.2 - 0.7 - SCAN["sw_h"]


# ================================================================= shell
def shell_solids():
    outer = pebble(0, 0, T, R_EDGE)
    inner = pebble(-WALL, WALL, T - 2 * WALL, R_EDGE - WALL)
    return outer, inner


def boss_column(x, y, z0, z1, d=7.0):
    """Screw column plus a rib to the nearest long wall."""
    col = cyl_z(x, y, z0, d, z1 - z0)
    yw = inner_half_width(x) * (1 if y > 0 else -1)
    y0, y1 = sorted((y, yw + (1.0 if y > 0 else -1.0)))
    rib = box(x - 1.5, y0, z0, 3.0, y1 - y0, z1 - z0)
    return col.fuse(rib)


def build():
    """Front and back shells. Features are collected and applied in one fuse and
    one cut per shell: booleans on the filleted pebble are slow, so batching
    keeps a full rebuild to about a minute."""
    outer, inner = shell_solids()
    shell = outer.cut(inner)
    big = 400
    front = shell.intersect(box(-big / 2, -big / 2, SPLIT, big, big, T))
    back = shell.intersect(box(-big / 2, -big / 2, -1, big, big, SPLIT + 1))
    f_add, f_cut, b_add, b_cut = [], [], [], []
    top_inner = T - WALL

    # ---- alignment lip on the front shell
    def ring(off_out, off_in, z0, h):
        o = cq.Solid.extrudeLinear(cq.Face.makeFromWires(outline_wire(off_out)), cq.Vector(0, 0, h))
        i = cq.Solid.extrudeLinear(cq.Face.makeFromWires(outline_wire(off_in)), cq.Vector(0, 0, h))
        return o.cut(i).translate((0, 0, z0))
    lip = ring(-WALL - LIP_GAP, -WALL - LIP_GAP - LIP_T, SPLIT - LIP_H, LIP_H)       # tongue
    lip = lip.fuse(ring(-WALL + 0.6, -WALL - LIP_GAP - LIP_T, SPLIT, 2.0))         # root into the wall
    lip = lip.cut(*[boss_column(x, y, SPLIT - LIP_H - 1, SPLIT + 1, d=8.0) for (x, y) in BOSSES])
    f_add.append(lip)

    # ---- screw bosses: back = counterbored column, front = insert column
    for (x, y) in BOSSES:
        b_add.append(boss_column(x, y, WALL - 0.5, SPLIT))
        f_add.append(boss_column(x, y, SPLIT, T - WALL + 0.5))
        b_cut.append(cyl_z(x, y, -1, 5.4, 1 + 6.5))           # screw head counterbore
        b_cut.append(cyl_z(x, y, 0, 2.8, SPLIT + 0.1))         # clearance
        f_cut.append(cyl_z(x, y, SPLIT - 0.1, 3.6, 6.1))       # heat-set insert

    # ---- back shell: camera window, illumination LED, vents, standoffs
    lx, ly = lens_center()
    # the 8.5 mm lens housing passes through the wall: square opening + outer chamfer
    b_cut.append(box(lx - 4.55, ly - 4.55, -1, 9.1, 9.1, WALL + 2))
    b_cut.append(island_outline(0.2, -1.0, ISLAND["depth"] + 1.0))   # pocket for the camera island
    b_cut.append(cyl_z(ILLUM_LED["x"], ILLUM_LED["y"], -1, ILLUM_LED["d"] + 0.15, WALL + 2))
    for vx in VENT_XS:
        b_cut.append(cq.Workplane("XY").slot2D(22, 2.2, 90).extrude(WALL + 2).translate((vx, 0, -1)).val())
    cam_pcb_bottom = CAM_Z - 0.74
    for hx, hy in CAM_HOLES:
        x, y = CAM_X0 + hx, CAM_Y0 + hy
        b_add.append(cyl_z(x, y, WALL - 0.3, 4.5, cam_pcb_bottom - WALL + 0.3))
        b_cut.append(cyl_z(x, y, 1.0, 1.8, cam_pcb_bottom))
    for hx, hy in PB_HOLES:
        x, y = PB_X0 + hx, PB_Y0 + hy
        b_add.append(cyl_z(x, y, WALL - 0.3, 4.5, PB_Z - WALL + 0.3))
        b_cut.append(cyl_z(x, y, 1.0, 2.0, PB_Z))
    for hx, hy in CM5_HOLES:
        x, y = BOARD_X0 + hx, 19.5 - hy
        b_add.append(cyl_z(x, y, WALL - 0.3, 5.0, cm5_pcb_bottom() - WALL + 0.3))
        b_cut.append(cyl_z(x, y, 1.0, 2.2, cm5_pcb_bottom()))

    # ---- front shell: scan button
    f_cut.append(cyl_z(SCAN["x"], SCAN["y"], top_inner - 0.5, SCAN["cap_d"] + 0.8, WALL + 2))
    z_sw = scan_switch_z()
    tube = cyl_z(SCAN["x"], SCAN["y"], z_sw - 1.2, 42, top_inner - z_sw + 1.7)
    tube = tube.cut(cyl_z(SCAN["x"], SCAN["y"], z_sw, 37, 30))
    tube = tube.cut(box(SCAN["x"] - 2, SCAN["y"] - 22, z_sw - 2, 4, 10, 3))   # wire slot
    f_add.append(tube)

    # speaker: locating ring + grille
    ring = cyl_z(SPK["x"], SPK["y"], top_inner - 2.5, SPK["d"] + 3.6, 2.6)
    ring = ring.cut(cyl_z(SPK["x"], SPK["y"], top_inner - 3, SPK["d"] + 0.6, 4))
    f_add.append(ring)
    for (gx, gy) in grille_points(SPK["x"], SPK["y"], 32.0, 3.2):
        f_cut.append(cyl_z(gx, gy, top_inner - 1, 1.6, WALL + 3))

    # status LED: light hole + holder tube for a 3 mm LED
    sx, sy = STATUS_LED["x"], STATUS_LED["y"]
    f_add.append(cyl_z(sx, sy, top_inner - 5, 5.6, 5.2).cut(cyl_z(sx, sy, top_inner - 6, 3.1, 7)))
    f_cut.append(cyl_z(sx, sy, top_inner - 1, 2.0, WALL + 3))

    # side buttons (+Y wall): hole + holder box for a 6x6 tactile switch
    lip_clear = []
    for b in SIDE_BUTTONS:
        yw = inner_half_width(b["x"])
        yr = side_ref(b["x"])
        plate = yr - 0.2 - 5.0                      # switch back face
        hb = box(b["x"] - 6.3, plate - 1.4, SIDE_Z - 6.3, 12.6, yw + 1.0 - (plate - 1.4), 12.6)
        hb = hb.cut(box(b["x"] - 5.3, plate, SIDE_Z - 5.3, 10.6, yw + 2.0 - plate, 10.6))  # flange + switch cavity
        hb = hb.cut(box(b["x"] - 1.5, plate - 3, SIDE_Z - 4, 3.0, 3.5, 8))                # wire slot
        f_add.append(hb)
        lip_clear.append(box(b["x"] - 5.4, plate, SIDE_Z - 6.0, 10.8, yw + 3.0 - plate, 12.0))
        if b["shape"] == "square":
            f_cut.append(box(b["x"] - 3.7, yr, SIDE_Z - 3.7, 7.4, WALL + 8, 7.4))
        else:
            f_cut.append(cyl_y(b["x"], yr, SIDE_Z, 8.0, WALL + 8))

    f_add[0] = f_add[0].cut(*lip_clear)   # the lip must not run under the cap flanges

    # USB-C port and power-switch slot (-Y wall), with cradles
    yw = -inner_half_width(USBC["x"])
    f_cut.append(cq.Workplane("XZ").slot2D(9.6, 3.9).extrude(-(WALL + 6))
                 .translate((USBC["x"], yw - WALL - 3, USBC["z"])).val())
    yw = -inner_half_width(POWER_SW["x"])
    f_cut.append(box(POWER_SW["x"] - 2.6, yw - WALL - 3, POWER_SW["z"] - 1.1, 5.2, WALL + 4, 2.2))
    for (cx, cz, wdt, hgt, dep) in [(USBC["x"], USBC["z"], 14.0, 7.0, 13.6),
                                    (POWER_SW["x"], POWER_SW["z"], 10.8, 5.8, 5.0)]:
        yw = -min(inner_half_width(cx - wdt / 2), inner_half_width(cx + wdt / 2))
        # starts 2 mm inside the wall so it is always joined to it; back end is the stop
        cr = box(cx - wdt / 2, yw - 2.0, cz - hgt / 2, wdt, dep + 2.0, hgt)
        cr = cr.cut(box(cx - wdt / 2 + 0.8, yw - 1, cz - hgt / 2 + 0.8, wdt - 1.6, dep, hgt - 1.6))
        f_add.append(cr)

    # lanyard: slot through the -X end and a post to loop the cord around
    end_x = -(L / 2)
    f_cut.append(box(end_x - 1, -1.4, 12.5, WALL + 4, 2.8, 7.0))
    f_add.append(cyl_z(end_x + WALL + 3.6, 0, SPLIT, 4.0, T - WALL - SPLIT))

    # battery corner guides (front shell, reach 4 mm down the cell sides)
    bx0, by0, blx, bly = BATT["x0"], BATT["y0"], BATT["lx"], BATT["ly"]
    btop = BATT["z0"] + BATT["lz"]
    for gx in (bx0, bx0 + blx):
        for gy in (by0, by0 + bly):
            left, low = gx == bx0, gy == by0
            if not left and low:
                continue   # this corner is under the amplifier
            gx0 = gx - 2.0 if left else gx
            gy0 = gy - 2.0 if low else gy
            arm_x = box(gx if left else gx - 6.0, gy0, btop - 4, 6.0, 2.0, T - btop + 4)
            arm_y = box(gx0, gy if low else gy - 6.0, btop - 4, 2.0, 6.0, T - btop + 4)
            f_add.append(arm_x.fuse(arm_y))

    # ---- apply: adds are clipped to the outer skin, then everything is cut
    front_add = cq.Compound.makeCompound(f_add).intersect(outer)
    back_add = cq.Compound.makeCompound(b_add).intersect(outer)
    front = front.fuse(front_add).clean().cut(*f_cut)
    back = back.fuse(back_add).clean().cut(*b_cut)
    front = _largest_solid(front)
    back = _largest_solid(back)
    return dict(front=front, back=back), cap_solids()


def _largest_solid(shape):
    solids = shape.Solids()
    if len(solids) == 1:
        return solids[0]
    for s in sorted(solids, key=lambda s: -s.Volume())[1:]:
        bb = s.BoundingBox()
        print(f"  note: dropping loose piece {s.Volume():.0f} mm3 at "
              f"x[{bb.xmin:.1f},{bb.xmax:.1f}] y[{bb.ymin:.1f},{bb.ymax:.1f}] z[{bb.zmin:.1f},{bb.zmax:.1f}]")
    return max(solids, key=lambda s: s.Volume())


def cm5_pcb_bottom():
    return BOARD_PCB_TOP - 1.25 - CM5_STACK_GAP - 1.1 - 1.11


def lens_center():
    # Camera Module 3 lens housing (8.5 mm square) centre in the STEP file,
    # offset by the camera placement.
    return CAM_X0 + 14.4, CAM_Y0 + 12.5


def grille_points(cx, cy, dia, pitch):
    pts = []
    rows = int(dia / pitch) + 2
    for r in range(-rows, rows + 1):
        y = r * pitch * math.sqrt(3) / 2
        off = (pitch / 2) if r % 2 else 0
        for k in range(-rows, rows + 1):
            x = k * pitch + off
            if x * x + y * y <= (dia / 2) ** 2:
                pts.append((cx + x, cy + y))
    return pts


# ================================================================== caps
def island_geom():
    """Centre, length and angle of the camera island (lens to LED)."""
    lx, ly = lens_center()
    ex, ey = ILLUM_LED["x"], ILLUM_LED["y"]
    cx, cy = (lx + ex) / 2, (ly + ey) / 2
    span = math.hypot(ex - lx, ey - ly)
    ang = math.degrees(math.atan2(ey - ly, ex - lx))
    return cx, cy, span, ang


def island_outline(grow, z0, h, r=None):
    """Stadium (slot) shape around lens and LED, grown by `grow`."""
    cx, cy, span, ang = island_geom()
    r = (ISLAND["r"] if r is None else r) + grow
    return (cq.Workplane("XY").slot2D(span + 2 * r, 2 * r, ang).extrude(h)
            .translate((cx, cy, z0)).val())


def island_parts():
    """Charcoal bezel + clear window. The bezel fills the 1 mm pocket and stands
    0.6 mm proud; the window sits flush in its outer face."""
    z_out = -ISLAND["proud"]
    t = ISLAND["proud"] + ISLAND["depth"]
    bezel = island_outline(0.0, z_out, t)
    try:
        bezel = cq.Workplane("XY").add(bezel).faces("<Z").edges().fillet(0.5).val()
    except Exception:
        pass
    win_r = ISLAND["r"] - ISLAND["window_margin"]
    window = island_outline(0.0, z_out, ISLAND["window_t"], r=win_r)
    bezel = bezel.cut(island_outline(0.1, z_out - 0.1, ISLAND["window_t"] + 0.1, r=win_r))  # window seat
    lx, ly = lens_center()
    bezel = bezel.cut(box(lx - 4.55, ly - 4.55, z_out, 9.1, 9.1, t + 1))                       # lens
    bezel = bezel.cut(cyl_z(ILLUM_LED["x"], ILLUM_LED["y"], z_out, ILLUM_LED["d"] + 0.4, t + 1))  # LED
    return bezel, window.translate((0, 0, 0))


def cap_solids():
    """Button caps, printed in TPU (Shore 85A-95A): soft rubber to the touch,
    and the flange doubles as a dust seal against the inside of the shell."""
    caps = {}
    top_inner = T - WALL
    sx, sy, d = SCAN["x"], SCAN["y"], SCAN["cap_d"]
    # Scan: gently domed rubber disc (0.3 mm proud at the rim, 1.5 mm at the centre),
    # raised ring + centre dot so it is found by touch
    rs = ((d / 2) ** 2 + 1.2 ** 2) / 2.4
    sphere_c = cq.Vector(sx, sy, T + 1.5 - rs)
    body = cyl_z(sx, sy, top_inner - 0.2, d, WALL + 4).intersect(cq.Solid.makeSphere(rs).translate(sphere_c))
    ring = cyl_z(sx, sy, top_inner, d - 6, 6).cut(cyl_z(sx, sy, top_inner - 1, d - 9, 8))
    ring = ring.intersect(cq.Solid.makeSphere(rs + 0.6).translate(sphere_c))
    dot = cq.Solid.makeSphere(1.6).translate((sx, sy, T + 1.5))
    flange = cyl_z(sx, sy, top_inner - 1.2, d + 5.0, 1.0)
    plunger = cyl_z(sx, sy, scan_switch_z() + SCAN["sw_h"] + 0.1, 5.0,
                    top_inner - 1.2 - (scan_switch_z() + SCAN["sw_h"] + 0.1))
    caps["cap_scan"] = body.fuse(ring).fuse(dot).fuse(flange).fuse(plunger)

    for b in SIDE_BUTTONS:
        yw = inner_half_width(b["x"])
        y_in = side_ref(b["x"])  # flange back face
        length = (yw + WALL + 1.0) - y_in     # tip 1 mm proud of the outer wall
        if b["shape"] == "square":
            shaft = box(b["x"] - 3.5, y_in, SIDE_Z - 3.5, 7.0, length, 7.0)
        else:
            shaft = cyl_y(b["x"], y_in, SIDE_Z, 7.6, length)
        try:   # soft rounded rubber edge on the outer face
            shaft = cq.Workplane("XY").add(shaft).faces(">Y").edges().fillet(1.2).val()
        except Exception:
            pass
        flange = cyl_y(b["x"], y_in, SIDE_Z, 10.0, 1.0)
        plunger = cyl_y(b["x"], y_in - 0.2, SIDE_Z, 3.0, 0.2)
        cap = shaft.fuse(flange).fuse(plunger)
        tip_y = yw + WALL + 1.0
        if b["shape"] == "dot":
            cap = cap.fuse(cq.Solid.makeSphere(1.2).translate((b["x"], tip_y, SIDE_Z)))
        elif b["shape"] == "bar":
            cap = cap.fuse(box(b["x"] - 2.5, tip_y - 0.4, SIDE_Z - 0.7, 5.0, 1.0, 1.4))
        caps[f"cap_{b['name']}"] = cap

    bezel, window = island_parts()
    caps["camera_bezel"] = bezel
    caps["camera_window"] = window
    return caps


# ================================================================ checks
PRIMITIVES = {"battery", "speaker", "amp", "scan_switch", "usbc_breakout", "power_switch",
              "status_led", "illum_led"}


def _mesh(shape, tol=0.3):
    import trimesh
    vs, fs = shape.tessellate(tol, 0.3)
    return trimesh.Trimesh([(v.x, v.y, v.z) for v in vs], fs, process=True)


def check(parts, caps, comps, tol=0.5):
    """Interference report.

    - shell/cap vs simple parts (cell, speaker, switches...): exact OCC volume
    - shell/cap vs STEP models (carrier, CM5, camera, PowerBoost): surface
      points of the model that fall inside the shell mesh
    - front vs back shell, and component vs component: exact or bounding box
    """
    problems = []
    rigid = {**parts, **caps}
    meshes = {k: _mesh(v) for k, v in rigid.items()}
    comp_names = [k for k in comps if not k.startswith("sw_")] + [k for k in comps if k.startswith("sw_")]
    for cname in comp_names:
        c = comps[cname]
        cb = c.BoundingBox()
        if cname in PRIMITIVES or cname.startswith("sw_"):
            for pname, p in rigid.items():
                pb = p.BoundingBox()
                if _bb_apart(cb, pb):
                    continue
                v = c.intersect(p).Volume()
                if v > tol:
                    problems.append((pname, cname, f"{v:.1f} mm3"))
        else:
            import trimesh
            cm = _mesh(c, tol=1.0)
            pts = cm.sample(5000) if len(cm.faces) else cm.vertices
            for pname, m in meshes.items():
                inside = m.contains(pts)
                n = int(inside.sum())
                if n > 20:
                    sel = pts[inside]
                    problems.append((pname, cname, f"{n} pts, e.g. x{sel[:,0].min():.1f}..{sel[:,0].max():.1f} "
                                     f"y{sel[:,1].min():.1f}..{sel[:,1].max():.1f} z{sel[:,2].min():.1f}..{sel[:,2].max():.1f}"))
    for a, b in (("front", "back"), ("back", "front")):
        pts = meshes[a].sample(20000)
        pts = pts[abs(pts[:, 2] - SPLIT) > 0.05]   # skip the shared parting plane
        n = int(meshes[b].contains(pts).sum())
        if n > 20:
            sel = pts[meshes[b].contains(pts)]
            problems.append((a, b, f"{n} surface points of {a} inside {b}, x{sel[:,0].min():.1f}..{sel[:,0].max():.1f} "
                             f"y{sel[:,1].min():.1f}..{sel[:,1].max():.1f} z{sel[:,2].min():.1f}..{sel[:,2].max():.1f}"))
    for cname, cap in caps.items():                 # printed/inserted parts vs shells (exact)
        for pname, part in parts.items():
            if _bb_apart(cap.BoundingBox(), part.BoundingBox()):
                continue
            if cap.distance(part) > 1e-3:
                continue                            # clear
            v = sum(sol.Volume() for sol in cap.intersect(part).Solids())
            if v > tol:                             # contact alone (seated parts) is fine
                problems.append((pname, cname, f"{v:.1f} mm3"))
    names = list(comps)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if {a, b} == {"carrier", "cm5"}:
                continue
            ba, bb = comps[a].BoundingBox(), comps[b].BoundingBox()
            if _bb_apart(ba, bb):
                continue
            if a in PRIMITIVES or b in PRIMITIVES or a.startswith("sw_") or b.startswith("sw_"):
                prim, other = (comps[a], comps[b]) if (a in PRIMITIVES or a.startswith("sw_")) else (comps[b], comps[a])
                pb = prim.BoundingBox()
                v = sum(prim.intersect(s).Volume() for s in other.Solids() if not _bb_apart(pb, s.BoundingBox()))
                if v > tol:
                    problems.append((a, b, f"{v:.1f} mm3"))
            else:
                problems.append((a, b, "bounding boxes overlap"))
    return problems


def _bb_apart(a, b, margin=0.0):
    return (a.xmax < b.xmin - margin or b.xmax < a.xmin - margin or a.ymax < b.ymin - margin
            or b.ymax < a.ymin - margin or a.zmax < b.zmin - margin or b.zmax < a.zmin - margin)


def export(parts, caps, comps):
    os.makedirs(OUT, exist_ok=True)
    for name, solid in {**parts, **caps}.items():
        cq.exporters.export(solid, os.path.join(OUT, f"{name}.step"))
        cq.exporters.export(solid, os.path.join(OUT, f"{name}.stl"), tolerance=0.05, angularTolerance=0.1)
    assy = cq.Assembly(name="readable")
    colors = dict(front=(0.93, 0.70, 0.68), back=(0.93, 0.70, 0.68))
    for name, solid in parts.items():
        assy.add(solid, name=name, color=cq.Color(*colors[name], 1.0))
    cap_colors = dict(camera_bezel=(0.18, 0.18, 0.19, 1.0), camera_window=(0.85, 0.9, 0.95, 0.4))
    for name, solid in caps.items():
        assy.add(solid, name=name, color=cq.Color(*cap_colors.get(name, (0.97, 0.96, 0.93, 1.0))))
    # The vendor STEP models (carrier, CM5, camera, PowerBoost) are left out:
    # with them the file is ~500 MB. They sit in this folder; components()
    # shows where each one goes.
    for name, solid in comps.items():
        if name in STEP:
            continue
        assy.add(solid, name=name, color=cq.Color(0.2, 0.45, 0.25, 1.0))
    assy.export(os.path.join(OUT, "readable_assembly.step"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-check", action="store_true")
    ap.add_argument("--no-export", action="store_true")
    args = ap.parse_args()
    parts, caps = build()
    comps = components()
    for name, s in {**parts, **caps}.items():
        bb = s.BoundingBox()
        print(f"{name:14s} {bb.xlen:6.1f} x {bb.ylen:5.1f} x {bb.zlen:5.1f} mm  {s.Volume() / 1000:6.1f} cm3  valid={s.isValid()}")
    if not args.no_check:
        problems = check(parts, caps, comps)
        if problems:
            print("\nINTERFERENCE:")
            for a, b, v in problems:
                print(f"  {a:16s} x {b:16s} {v}")
        else:
            print("\nNo interference.")
    if not args.no_export:
        export(parts, caps, comps)
        print(f"\nExported to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
