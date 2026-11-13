"""A small NumPy sphere-tracing renderer for the concept phone.

The phone is a signed distance field (all units in millimetres):
  * body: rounded-rectangle plan, flat titanium sides with rounded edges
  * camera plateau on the back, three protruding lenses with recessed glass
  * side buttons
Shading is analytic: a studio environment of soft boxes plus an animated
"sweep" light, titanium metal with Fresnel, frosted back glass, glossy front
glass with a textured, emissive screen, and lens glass that can glow.
"""
import math

import numpy as np

from common import H, W, ORANGE, CYAN, TI_BLUE, TI_BLUE_HI, smoothstep

f32 = np.float32

# ----------------------------------------------------------------------------- geometry
HX, HY, HZ = 77.6 / 2, 163.0 / 2, 8.25 / 2
CR = 12.2          # plan corner radius
ER = 1.55          # edge rounding of the titanium band
BS = 19.2          # camera plateau half size
BR = 9.4           # plateau corner radius
BH = 1.7           # plateau height above the back glass
BCX, BCY = HX - 4.0 - BS, HY - 4.0 - BS
LR = 7.1           # lens outer (metal ring) radius
LRIN = LR - 1.05   # lens glass radius
LH = 1.25          # lens protrusion above plateau
ZB = -HZ - BH      # plateau top plane
ZL = ZB - LH       # lens ring top plane
ZG = ZL + 0.55     # recessed glass plane
LENSES = np.array([(BCX + 8.5, BCY + 9.2), (BCX + 8.5, BCY - 9.2), (BCX - 8.7, BCY)], f32)
FLASH = (BCX - 10.4, BCY + 12.4, 2.5)
LIDAR = (BCX - 10.4, BCY - 12.4, 2.25)
MIC = (BCX - 1.0, BCY + 15.6, 0.55)

# (side sign, y centre, half length, half depth z)
BUTTONS = [(-1, 52.0, 4.6, 1.5), (-1, 34.5, 7.4, 1.5), (-1, 17.0, 7.4, 1.5),
           (+1, 36.0, 11.0, 1.5), (+1, -25.0, 9.0, 1.7)]
BTN_OUT = 0.45     # protrusion of buttons beyond the band

AABB_MIN = np.array([-HX - 1.0, -HY - 0.5, ZL - 0.3], f32)
AABB_MAX = np.array([HX + 1.0, HY + 0.5, HZ + 0.3], f32)


def _rrect2(x, y, hx, hy, r):
    qx = np.abs(x) - (hx - r)
    qy = np.abs(y) - (hy - r)
    ox = np.maximum(qx, 0)
    oy = np.maximum(qy, 0)
    return np.sqrt(ox * ox + oy * oy) + np.minimum(np.maximum(qx, qy), 0) - r


def _extrude(d2, z, zc, hz, er):
    wx = d2 + er
    wy = np.abs(z - zc) - (hz - er)
    ox = np.maximum(wx, 0)
    oy = np.maximum(wy, 0)
    return np.minimum(np.maximum(wx, wy), 0) + np.sqrt(ox * ox + oy * oy) - er


def _box(x, y, z, hx, hy, hz):
    qx, qy, qz = np.abs(x) - hx, np.abs(y) - hy, np.abs(z) - hz
    ox, oy, oz = np.maximum(qx, 0), np.maximum(qy, 0), np.maximum(qz, 0)
    return np.sqrt(ox * ox + oy * oy + oz * oz) + np.minimum(np.maximum(qx, np.maximum(qy, qz)), 0)


def _smin(a, b, k):
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0, 1)
    return b + (a - b) * h - k * h * (1 - h)


def _lens_d2(x, y):
    d = None
    for cx, cy in LENSES:
        di = np.sqrt((x - cx) ** 2 + (y - cy) ** 2)
        d = di if d is None else np.minimum(d, di)
    return d


_REG_ZC = (ZL - 0.4 + (-HZ + 1.0)) / 2
_REG_HZ = ((-HZ + 1.0) - (ZL - 0.4)) / 2


def _bump_detail(x, y, z, dbody):
    d2 = _rrect2(x - BCX, y - BCY, BS, BS, BR)
    zc, hz = (ZB + (-HZ + 1.0)) / 2, ((-HZ + 1.0) - ZB) / 2
    d = _smin(dbody, _extrude(d2, z, zc, hz, 0.55), 1.0)
    rl = _lens_d2(x, y)
    zc, hz = (ZL + ZB + 0.5) / 2, (ZB + 0.5 - ZL) / 2
    d = _smin(d, _extrude(rl - LR, z, zc, hz, 0.42), 0.45)
    # recess the glass: subtract a cylinder of radius LRIN from the glass plane outwards
    zc, hz = (ZL - 2.0 + ZG) / 2, (ZG - ZL + 2.0) / 2
    drec = _extrude(rl - LRIN, z, zc, hz, 0.0)
    d = -_smin(-d, drec, 0.22)
    return d


def sdf(x, y, z):
    db = _extrude(_rrect2(x, y, HX, HY, CR), z, 0.0, HZ, ER)
    # camera plateau + lenses live inside this box; its distance is a safe lower bound
    bb = _box(x - BCX, y - BCY, z - _REG_ZC, BS + 1.2, BS + 1.2, _REG_HZ)
    d = np.minimum(db, bb)
    near = np.nonzero(bb < 0.5)[0]
    if near.size:
        d[near] = _bump_detail(x[near], y[near], z[near], db[near])
    # buttons
    nb = np.nonzero((np.abs(x) > HX - 2.5) & (np.abs(z) < 2.5))[0]
    if nb.size:
        xs, ys, zs, dd = x[nb], y[nb], z[nb], d[nb]
        for side, yc, hl, hz in BUTTONS:
            bx = xs - side * (HX + BTN_OUT - 0.9)
            dd = np.minimum(dd, _box(bx, ys - yc, zs, 0.55, hl - 0.35, hz - 0.35) - 0.35)
        d[nb] = dd
    return d


def sdf_p(p):
    return sdf(p[0], p[1], p[2])


_TETRA = np.array([[1, -1, -1], [-1, -1, 1], [-1, 1, -1], [1, 1, 1]], f32)


def normals(p, h=0.004):
    n = np.zeros_like(p)
    for k in _TETRA:
        d = sdf_p(p + (k * h)[:, None])
        n += k[:, None] * d[None, :]
    n /= np.maximum(np.linalg.norm(n, axis=0, keepdims=True), 1e-8)
    return n


# ----------------------------------------------------------------------------- pose / camera
def rot(yaw=0.0, pitch=0.0, roll=0.0):
    a, b, c = (math.radians(v) for v in (yaw, pitch, roll))
    ry = np.array([[math.cos(a), 0, math.sin(a)], [0, 1, 0], [-math.sin(a), 0, math.cos(a)]], f32)
    rx = np.array([[1, 0, 0], [0, math.cos(b), -math.sin(b)], [0, math.sin(b), math.cos(b)]], f32)
    rz = np.array([[math.cos(c), -math.sin(c), 0], [math.sin(c), math.cos(c), 0], [0, 0, 1]], f32)
    return (rz @ rx @ ry).astype(f32)


def _norm(v):
    v = np.asarray(v, f32)
    return v / np.linalg.norm(v)


class Camera:
    def __init__(self, pos, target=(0, 0, 0), fov=22.0, up=(0, 1, 0), shift=(0.0, 0.0)):
        self.pos = np.asarray(pos, f32)
        fwd = _norm(np.asarray(target, f32) - self.pos)
        right = _norm(np.cross(fwd, np.asarray(up, f32)))
        upv = np.cross(right, fwd)
        self.fwd, self.right, self.up = fwd, right, upv
        self.f = (H / 2) / math.tan(math.radians(fov) / 2)
        self.shift = shift

    def project(self, pw):
        d = pw - self.pos
        z = d @ self.fwd
        x = (d @ self.right) / z * self.f + W / 2 + self.shift[0]
        y = -(d @ self.up) / z * self.f + H / 2 + self.shift[1]
        return x, y, z

    def rays(self, xs, ys):
        cx = (xs - W / 2 - self.shift[0]) / self.f
        cy = (H / 2 + self.shift[1] - ys) / self.f
        d = (self.fwd[:, None] + self.right[:, None] * cx[None] + self.up[:, None] * cy[None])
        return d / np.linalg.norm(d, axis=0, keepdims=True)


# ----------------------------------------------------------------------------- lights
class SoftBox:
    def __init__(self, direction, su, sv, color, intensity, angle=0.0, soft=0.04):
        self.d = _norm(direction)
        u = _norm(np.cross(np.array([0, 1, 0], f32), self.d)) if abs(self.d[1]) < 0.95 else np.array([1, 0, 0], f32)
        v = np.cross(self.d, u)
        a = math.radians(angle)
        self.u = (u * math.cos(a) + v * math.sin(a)).astype(f32)
        self.v = (-u * math.sin(a) + v * math.cos(a)).astype(f32)
        self.su, self.sv, self.soft = su, sv, soft
        self.c = np.asarray(color, f32) * intensity
        self.area = 4 * su * sv


def studio_rig(key=1.0, rim_warm=1.0, rim_cool=1.0, front=1.0, top=1.0, side=1.0):
    """Product-shot lighting: big soft key, strip lights where flat faces reflect, warm/cool rims."""
    rig = []
    if key:
        rig.append(SoftBox((-0.55, 0.45, 0.70), 0.34, 0.70, (1.0, 0.97, 0.94), 2.4 * key, soft=0.16))
    if front:
        rig.append(SoftBox((0.16, 0.28, 1.0), 0.07, 1.3, (0.85, 0.9, 1.0), 0.9 * front, angle=-36, soft=0.06))
    if side:
        rig.append(SoftBox((0.78, 0.08, 0.62), 0.09, 1.1, (1.0, 0.93, 0.86), 1.7 * side, soft=0.07))
        rig.append(SoftBox((-0.80, 0.05, 0.60), 0.07, 1.1, (0.80, 0.88, 1.0), 1.2 * side, soft=0.06))
    if rim_warm:
        rig.append(SoftBox((0.92, 0.18, -0.40), 0.12, 0.95, (1.0, 0.50, 0.20), 3.6 * rim_warm))
    if rim_cool:
        rig.append(SoftBox((-0.92, 0.22, -0.38), 0.12, 0.95, (0.30, 0.50, 1.0), 3.2 * rim_cool))
    if top:
        rig.append(SoftBox((0.0, 1.0, 0.12), 0.7, 0.35, (0.9, 0.93, 1.0), 0.6 * top, soft=0.2))
    return rig


def silhouette_rig(level=1.0):
    """Only the rims: reads as a dark silhouette with lit edges."""
    return [SoftBox((0.95, 0.12, -0.30), 0.12, 0.95, (1.0, 0.52, 0.22), 4.0 * level),
            SoftBox((-0.95, 0.20, -0.30), 0.12, 0.95, (0.32, 0.52, 1.0), 3.6 * level),
            SoftBox((0.0, 1.0, -0.2), 0.6, 0.12, (0.6, 0.7, 1.0), 1.0 * level, soft=0.1)]


def env(r, rough, rig, sweep, ambient):
    """Radiance arriving from direction r (3, N) for a reflection lobe of given roughness."""
    out = np.empty_like(r)
    out[:] = np.asarray(ambient, f32)[:, None]
    for L in rig:
        c = L.d @ r
        cc = np.maximum(c, 0.08)
        u = np.abs((L.u @ r) / cc)
        v = np.abs((L.v @ r) / cc)
        s = L.soft + rough
        m = smoothstep(L.su + s, L.su - s * 0.5, u) * smoothstep(L.sv + s, L.sv - s * 0.5, v)
        m *= smoothstep(0.02, 0.2, c)
        k = (L.su * L.sv) / ((L.su + rough) * (L.sv + rough))
        out += L.c[:, None] * (m * k)[None]
    if sweep is not None and sweep.get("I", 0) > 0:
        phi = np.arctan2(r[0], r[2])
        dphi = (phi - sweep["phi"] + np.pi) % (2 * np.pi) - np.pi
        w = sweep.get("w", 0.05) + rough * 0.7
        b = np.exp(-(dphi / w) ** 2) * smoothstep(0.98, 0.55, np.abs(r[1] - sweep.get("y", 0.1)))
        out += (np.asarray(sweep.get("c", (0.9, 0.95, 1.0)), f32) * sweep["I"] * sweep.get("w", 0.05) / w)[:, None] * b[None]
    return out


def diffuse(n, rig, ambient):
    out = np.empty_like(n)
    out[:] = np.asarray(ambient, f32)[:, None] * 3.0
    for L in rig:
        out += L.c[:, None] * (np.maximum(L.d @ n, 0) * L.area / math.pi)[None]
    return out


def fresnel(cos, f0):
    return f0 + (1 - f0) * (1 - cos) ** 5


# ----------------------------------------------------------------------------- texture sampling
def sample_bilinear(tex, u, v):
    """tex (h, w, 3); u, v in texel coordinates (N,). Returns (3, N)."""
    h, w = tex.shape[:2]
    u = np.clip(u - 0.5, 0, w - 1.001)
    v = np.clip(v - 0.5, 0, h - 1.001)
    x0 = u.astype(np.int32)
    y0 = v.astype(np.int32)
    fx = (u - x0)[:, None]
    fy = (v - y0)[:, None]
    a = tex[y0, x0]
    b = tex[y0, x0 + 1]
    c = tex[y0 + 1, x0]
    d = tex[y0 + 1, x0 + 1]
    out = (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy
    return out.T


SCREEN_MIN_BEZEL = 1.25  # texture covers the screen at the thinnest bezel


def screen_uv(px, py, tex_shape):
    th, tw = tex_shape[:2]
    sx, sy = HX - SCREEN_MIN_BEZEL, HY - SCREEN_MIN_BEZEL
    return (px + sx) / (2 * sx) * tw, (sy - py) / (2 * sy) * th


# ----------------------------------------------------------------------------- shading
TI_F0 = np.array([0.36, 0.46, 0.64], f32)


def shade(p, n_l, rd_l, t, R, st, pix):
    """Return linear RGB (3, N) and emissive-only component (3, N)."""
    N = p.shape[1]
    px, py, pz = p
    n_w = R @ n_l
    rd_w = R @ rd_l
    cos = np.clip(-(rd_w * n_w).sum(0), 0, 1)
    r_w = rd_w + 2 * cos[None] * n_w
    rig, sweep, amb = st["rig"], st.get("sweep"), st.get("ambient", (0.004, 0.006, 0.012))
    fp = t * pix  # mm per (supersampled) pixel

    col = np.zeros((3, N), f32)
    emis = np.zeros((3, N), f32)
    nz = n_l[2]
    face = smoothstep(0.86, 0.985, np.abs(nz))

    # --- titanium (everything that is not a flat face)
    k = np.nonzero(face < 1)[0]
    if k.size:
        F = fresnel(cos[k], TI_F0[:, None])
        metal = F * env(r_w[:, k], 0.10, rig, sweep, amb) * st.get("metal_gain", 1.0) \
            + TI_BLUE[:, None] * 0.04 * diffuse(n_w[:, k], rig, amb)
        gl = st.get("glide")
        if gl is not None and gl.get("I", 0) > 0:
            band = np.exp(-((py[k] - gl["y"]) / gl.get("w", 6.0)) ** 2) * (0.45 + 0.55 * (1 - cos[k]))
            metal += np.asarray(gl.get("c", (1.0, 0.86, 0.70)), f32)[:, None] * (band * gl["I"])[None]
        col[:, k] += metal * (1 - face[k])[None]

    for side, fn in ((nz < 0, _shade_back), (nz > 0, _shade_front)):
        k = np.nonzero(side & (face > 0))[0]
        if k.size:
            c, e = fn(px[k], py[k], pz[k], n_w[:, k], r_w[:, k], cos[k], fp[k], st)
            col[:, k] += c * face[k][None]
            emis[:, k] += e * face[k][None]
    return col + emis, emis


def _shade_back(x, y, z, n_w, r_w, cos, fp, st):
    rig, sweep, amb = st["rig"], st.get("sweep"), st.get("ambient", (0.004, 0.006, 0.012))
    N = x.shape[0]
    emis = np.zeros((3, N), f32)
    Fg = fresnel(cos, 0.04)[None]
    base = (TI_BLUE * st.get("back_albedo", 0.9))[:, None]
    dif = diffuse(n_w, rig, amb)
    # frosted back glass
    tint = np.array([0.62, 0.78, 1.0], f32)[:, None]
    col = base * dif * 0.75 + Fg * env(r_w, 0.30, rig, sweep, amb) * 0.38 * tint
    # plateau top: same glass, a touch glossier
    on_plate = smoothstep(ZB + 0.35, ZB + 0.12, z)
    k = np.nonzero(on_plate > 0)[0]
    if k.size:
        plate = base * 0.8 * dif[:, k] * 0.5 + Fg[:, k] * env(r_w[:, k], 0.14, rig, sweep, amb) * 0.8 * tint
        w = on_plate[k][None]
        col[:, k] = col[:, k] * (1 - w) + plate * w

    # flash / lidar / mic on the plateau
    for (cx, cy, rr), kind in ((FLASH, 0), (LIDAR, 1), (MIC, 2)):
        d = np.sqrt((x - cx) ** 2 + (y - cy) ** 2)
        inside = smoothstep(rr + fp, rr - fp, d) * on_plate
        k = np.nonzero(inside > 0)[0]
        if not k.size:
            continue
        dk, Fk, rk = d[k], Fg[:, k], r_w[:, k]
        if kind == 0:
            ring = 0.5 + 0.5 * np.cos(dk / rr * 18.0)
            c = np.array([0.32, 0.27, 0.18], f32)[:, None] * (0.25 + 0.15 * ring)[None] * dif[:, k] * 0.5 \
                + Fk * env(rk, 0.05, rig, sweep, amb)
        elif kind == 1:
            c = np.array([0.006, 0.004, 0.012], f32)[:, None] + Fk * env(rk, 0.03, rig, sweep, amb) * 1.2
        else:
            c = np.zeros((3, k.size), f32) + 0.002
        w = inside[k][None]
        col[:, k] = col[:, k] * (1 - w) + c * w
        if kind == 0 and st.get("flash", 0) > 0:
            emis[:, k] += np.array([1.0, 0.85, 0.6], f32)[:, None] * (w * st["flash"] * 6)

    # lenses
    rl = li = lx = ly = None
    for i, (cx, cy) in enumerate(LENSES):
        di = np.sqrt((x - cx) ** 2 + (y - cy) ** 2)
        if rl is None:
            rl, li, lx, ly = di, np.zeros(N, np.int32), x - cx, y - cy
        else:
            m = di < rl
            rl = np.where(m, di, rl)
            li = np.where(m, i, li)
            lx = np.where(m, x - cx, lx)
            ly = np.where(m, y - cy, ly)
    in_lens = smoothstep(ZB - 0.15, ZB - 0.35, z) * smoothstep(LR + 0.2, LR - 0.1, rl)
    k = np.nonzero(in_lens > 0)[0]
    if k.size:
        cl, el = _shade_lens(rl[k], lx[k], ly[k], z[k], li[k], n_w[:, k], r_w[:, k], cos[k], fp[k], st)
        w = in_lens[k][None]
        col[:, k] = col[:, k] * (1 - w) + cl * w
        emis[:, k] += el * w
    return col, emis


def _shade_lens(r, lx, ly, z, li, n_w, r_w, cos, fp, st):
    rig, sweep, amb = st["rig"], st.get("sweep"), st.get("ambient", (0.004, 0.006, 0.012))
    N = r.shape[0]
    Fg = fresnel(cos, 0.05)[None]
    # metal ring on top of the lens barrel
    ring = TI_F0[:, None] * 1.15 * env(r_w, 0.05, rig, sweep, amb)
    # glass
    rn = r / LRIN
    ang = np.arctan2(ly, lx)
    glass = np.zeros((3, N), f32) + 0.0025
    glass += Fg * env(r_w, 0.02, rig, sweep, amb) * 0.45 * np.array([0.75, 0.7, 1.0], f32)[:, None]
    coat = (0.5 + 0.5 * np.sin(3 * ang + 7 * rn))
    glass += (np.array([0.10, 0.03, 0.22], f32)[:, None] * coat[None]
              + np.array([0.02, 0.12, 0.10], f32)[:, None] * (1 - coat)[None]) * (0.08 * (1 - rn ** 2))[None]
    for c0, amp in ((0.84, 0.05), (0.64, 0.035), (0.44, 0.03), (0.27, 0.02)):
        wdt = np.maximum(0.012, fp / LRIN)
        glass += np.array([0.35, 0.45, 0.6], f32)[:, None] * (amp * np.exp(-((rn - c0) / wdt) ** 2))[None]
    glass *= (0.35 + 0.65 * smoothstep(0.12, 0.24, rn))[None]
    # fake specular glint (reflection of the key light inside the optics)
    gl = np.exp(-(((lx / LRIN) + 0.33) ** 2 + ((ly / LRIN) - 0.36) ** 2) / 0.006)
    glass += np.array([0.9, 0.95, 1.0], f32)[:, None] * (gl * 0.5 * st.get("glint", 1.0))[None]
    # dark gasket between ring and glass
    gasket = smoothstep(LRIN - 0.05 - fp, LRIN - 0.05, r) * smoothstep(LRIN + 0.3 + fp, LRIN + 0.3, r)
    on_glass = smoothstep(LRIN + fp, LRIN - fp, r)
    col = ring * (1 - on_glass)[None] + glass * on_glass[None]
    col *= (1 - 0.85 * gasket)[None]

    emis = np.zeros((3, N), f32)
    glow = np.asarray(st.get("lens_glow", (0, 0, 0)), f32)
    if glow.max() > 0:
        g = glow[li]
        pulse = 1.0
        e = (CYAN[:, None] * (1.15 * np.exp(-((rn - 0.68) / 0.08) ** 2))[None]
             + TI_BLUE_HI[:, None] * (0.75 * np.exp(-((rn - 0.44) / 0.10) ** 2))[None]
             + ORANGE[:, None] * (1.5 * np.exp(-(rn / 0.15) ** 2))[None]
             + TI_BLUE_HI[:, None] * 0.12 * (1 - rn ** 2)[None])
        emis = e * (g * pulse * on_glass)[None]
    return col, emis


def _shade_front(x, y, z, n_w, r_w, cos, fp, st):
    rig, sweep, amb = st["rig"], st.get("sweep"), st.get("ambient", (0.004, 0.006, 0.012))
    N = x.shape[0]
    Fg = fresnel(cos, 0.04)[None]
    refl = Fg * env(r_w, 0.02, rig, sweep, amb) * st.get("front_refl", 1.0)
    col = np.zeros((3, N), f32) + 0.0015
    emis = np.zeros((3, N), f32)
    scr = st.get("screen")
    if scr is not None and scr.get("bright", 0) > 0:
        bez = scr["bezel"]
        ds = _rrect2(x, y, HX - bez, HY - bez, CR - bez * 0.9)
        m = smoothstep(fp * 0.7, -fp * 0.7, ds)
        # dynamic island
        iy = HY - bez - 1.15 - 2.85
        di = _rrect2(x, y - iy, 9.4, 2.85, 2.85)
        m *= smoothstep(-fp * 0.7, fp * 0.7, di)
        k = np.nonzero(m > 0)[0]
        if k.size:
            u, v = screen_uv(x[k], y[k], scr["tex"].shape)
            emis[:, k] = sample_bilinear(scr["tex"], u, v) * (scr["bright"] * m[k])[None]
        refl *= (1 - 0.45 * m * min(1.0, scr["bright"]))[None]
    return col + refl, emis


# ----------------------------------------------------------------------------- driver
def _ray_box(ro, rd):
    inv = 1.0 / np.where(np.abs(rd) < 1e-9, 1e-9, rd)
    t0 = (AABB_MIN[:, None] - ro[:, None]) * inv
    t1 = (AABB_MAX[:, None] - ro[:, None]) * inv
    tn = np.minimum(t0, t1).max(0)
    tf = np.maximum(t0, t1).min(0)
    return np.maximum(tn, 0), tf


def _march(ro, rd, pix, max_iter=110):
    tmin, tmax = _ray_box(ro, rd)
    t = tmin.copy()
    hit = np.zeros(rd.shape[1], bool)
    active = np.nonzero(tmin < tmax)[0]
    for _ in range(max_iter):
        if active.size == 0:
            break
        ta = t[active]
        p = ro[:, None] + rd[:, active] * ta[None]
        d = sdf_p(p)
        eps = ta * pix * 0.25
        h = d < eps
        hit[active[h]] = True
        ta = ta + np.where(h, 0, d)
        t[active] = ta
        alive = (~h) & (ta < tmax[active])
        active = active[alive]
    return t, hit


def screen_rect(cam, R, P, margin=6):
    corners = np.array([[x, y, z] for x in (AABB_MIN[0], AABB_MAX[0])
                        for y in (AABB_MIN[1], AABB_MAX[1]) for z in (AABB_MIN[2], AABB_MAX[2])], f32)
    pw = corners @ R.T + P
    x, y, z = cam.project(pw)
    if (z <= 1).any():
        return 0, 0, W, H
    x0 = int(max(0, math.floor(x.min()) - margin))
    x1 = int(min(W, math.ceil(x.max()) + margin))
    y0 = int(max(0, math.floor(y.min()) - margin))
    y1 = int(min(H, math.ceil(y.max()) + margin))
    return x0, y0, x1, y1


def render(cam, R, P, st, ss=2, chunk=450_000):
    """Render the phone. Returns premultiplied rgb (H,W,3), alpha (H,W), emissive (H,W,3), depth (H,W)."""
    R = np.asarray(R, f32)
    P = np.asarray(P, f32)
    rgb = np.zeros((H, W, 3), f32)
    alpha = np.zeros((H, W), f32)
    emis_img = np.zeros((H, W, 3), f32)
    depth = np.full((H, W), 1e6, f32)
    x0, y0, x1, y1 = screen_rect(cam, R, P)
    if x1 <= x0 or y1 <= y0:
        return rgb, alpha, emis_img, depth
    w, h = x1 - x0, y1 - y0
    sw, sh = w * ss, h * ss
    pix = 1.0 / (cam.f * ss)
    ro_l = R.T @ (cam.pos - P)
    out_c = np.zeros((3, sh * sw), f32)
    out_e = np.zeros((3, sh * sw), f32)
    out_a = np.zeros(sh * sw, f32)
    out_t = np.full(sh * sw, 1e6, f32)
    rows_per = max(1, chunk // sw)
    for r0 in range(0, sh, rows_per):
        r1 = min(sh, r0 + rows_per)
        ys = y0 + (np.arange(r0, r1, dtype=f32) + 0.5) / ss
        xs = x0 + (np.arange(sw, dtype=f32) + 0.5) / ss
        gx, gy = np.meshgrid(xs, ys)
        rd_w = cam.rays(gx.ravel(), gy.ravel())
        rd_l = R.T @ rd_w
        t, hit = _march(ro_l, rd_l, pix)
        k = np.nonzero(hit)[0]
        if k.size == 0:
            continue
        p = ro_l[:, None] + rd_l[:, k] * t[k][None]
        n = normals(p, h=max(0.002, float(np.median(t[k])) * pix * 0.5))
        c, e = shade(p, n, rd_l[:, k], t[k], R, st, pix)
        base = r0 * sw
        out_c[:, base + k] = c
        out_e[:, base + k] = e
        out_a[base + k] = 1.0
        out_t[base + k] = t[k]
    c = out_c.reshape(3, sh, sw).transpose(1, 2, 0)
    e = out_e.reshape(3, sh, sw).transpose(1, 2, 0)
    a = out_a.reshape(sh, sw)
    tt = out_t.reshape(sh, sw)
    if ss > 1:
        c = c.reshape(h, ss, w, ss, 3).mean((1, 3))
        e = e.reshape(h, ss, w, ss, 3).mean((1, 3))
        a = a.reshape(h, ss, w, ss).mean((1, 3))
        tt = tt.reshape(h, ss, w, ss).min((1, 3))
    rgb[y0:y1, x0:x1] = c
    emis_img[y0:y1, x0:x1] = e
    alpha[y0:y1, x0:x1] = a
    depth[y0:y1, x0:x1] = tt
    return rgb, alpha, emis_img, depth
