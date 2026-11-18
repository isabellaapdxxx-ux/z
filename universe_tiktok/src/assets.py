"""Procedural assets: starfield, nebula, planet textures, galaxies, cosmic web,
Hubble deep field and the Voyager-style probe. Everything is seeded so a
re-render is identical."""
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy import ndimage

import gfx as G
from config import BUILD, H, W

TAU = 2 * np.pi


# ======================================================================= starfield
class Starfield:
    """Three parallax layers of stars in 3D, camera flies along z.
    camz(t) / camx(t) / camy(t) are callables giving the camera position."""

    LAYERS = [  # n, zmin, zmax, brightness, spread
        (2600, 2.6, 7.0, 0.55, 0.0),
        (900, 1.2, 2.6, 0.85, 0.25),
        (200, 0.35, 1.2, 1.25, 0.55),
    ]
    F = 900.0

    def __init__(self, camz, camx, camy, seed=7):
        self.camz, self.camx, self.camy = camz, camx, camy
        rng = np.random.default_rng(seed)
        self.layers = []
        palette = np.array([[1.0, 1.0, 1.0], [0.75, 0.85, 1.0], [1.0, 0.9, 0.75],
                            [0.85, 0.9, 1.0], [1.0, 0.8, 0.7]], np.float32)
        for n, z0, z1, b, spread in self.LAYERS:
            X = (W / 2) * z1 / self.F * 1.25
            Y = (H / 2) * z1 / self.F * 1.25
            x = rng.uniform(-X, X, n).astype(np.float32)
            y = rng.uniform(-Y, Y, n).astype(np.float32)
            z = rng.uniform(0, z1 - z0, n).astype(np.float32)
            mag = rng.power(0.35, n).astype(np.float32)  # many dim, few bright
            col = palette[rng.integers(0, len(palette), n)] * (0.25 + 1.1 * mag)[:, None]
            tw = rng.uniform(0, TAU, n).astype(np.float32)
            self.layers.append(dict(x=x, y=y, z=z, X=X, Y=Y, z0=z0, z1=z1, b=b,
                                    spread=spread, col=col, tw=tw))

    def project(self, L, t, zoom2d=1.0, center=(W / 2, H / 2)):
        cz, cx, cy = self.camz(t), self.camx(t), self.camy(t)
        rng_z = L["z1"] - L["z0"]
        zr = L["z0"] + np.mod(L["z"] - cz, rng_z)
        xr = np.mod(L["x"] - cx + L["X"], 2 * L["X"]) - L["X"]
        yr = np.mod(L["y"] - cy + L["Y"], 2 * L["Y"]) - L["Y"]
        sx = W / 2 + self.F * xr / zr
        sy = H / 2 + self.F * yr / zr
        if zoom2d != 1.0:
            sx = center[0] + (sx - center[0]) * zoom2d
            sy = center[1] + (sy - center[1]) * zoom2d
        fade = G.smoothstep(0, 0.18, (zr - L["z0"]) / rng_z) * G.smoothstep(0, 0.25, (L["z1"] - zr) / rng_z)
        bright = L["b"] * (L["z0"] / zr) ** 0.6 * fade
        return sx, sy, bright.astype(np.float32)

    def render(self, img, t, intensity=1.0, streak=1.0, zoom2d=1.0, zoom2d_prev=None,
               center=(W / 2, H / 2)):
        if intensity <= 0.01:
            return
        dt = 1.0 / 30
        for L in self.layers:
            # shutter: sample a few sub-frame positions so fast motion streaks
            sx0, sy0, b0 = self.project(L, t, zoom2d, center)
            if streak > 0:
                zp = zoom2d_prev if zoom2d_prev is not None else zoom2d
                sx1, sy1, _ = self.project(L, t - dt * streak, zp, center)
                move = np.hypot(sx0 - sx1, sy0 - sy1)
                n = int(np.clip(np.percentile(move, 98) / 1.5, 1, 14))
            else:
                n = 1
            tw = 0.85 + 0.15 * np.sin(L["tw"] + t * 3.1)
            base = L["col"] * (b0 * tw * intensity)[:, None]
            if n == 1:
                G.splat(img, sx0, sy0, base, L["spread"])
                continue
            xs, ys, ws = [], [], []
            for j in range(n):
                f = j / (n - 1)
                xs.append(sx0 + (sx1 - sx0) * f)
                ys.append(sy0 + (sy1 - sy0) * f)
                ws.append(base * (1.6 / n) * (1 - 0.6 * f))
            G.splat(img, np.concatenate(xs), np.concatenate(ys), np.concatenate(ws), L["spread"])


# ======================================================================= nebula
@lru_cache(maxsize=1)
def nebula_tex():
    h, w = H // 4, W // 4
    n1 = G.value_noise(h, w, 6, seed=11, base=3)
    n2 = G.value_noise(h, w, 6, seed=12, base=3)
    n3 = G.value_noise(h, w, 5, seed=13, base=5)
    purple = np.array([0.42, 0.12, 0.55], np.float32)
    blue = np.array([0.08, 0.2, 0.55], np.float32)
    teal = np.array([0.05, 0.35, 0.45], np.float32)
    a = G.smoothstep(0.45, 0.95, n1)[..., None]
    b = G.smoothstep(0.5, 1.0, n2)[..., None]
    c = G.smoothstep(0.6, 1.0, n3)[..., None]
    tex = (a * purple + b * blue + c * teal * 0.6).astype(np.float32)
    return tex


def draw_nebula(img, t, k=0.25, zoom=1.0, drift=(6.0, -3.0)):
    if k <= 0.005:
        return
    tex = nebula_tex()
    h, w = tex.shape[:2]
    z = 1.0 / zoom
    off = np.array([h / 2 - z * h / 2 + drift[1] * t / 4, w / 2 - z * w / 2 + drift[0] * t / 4])
    out = np.empty_like(tex)
    for c in range(3):
        out[..., c] = ndimage.affine_transform(tex[..., c], [z, z], offset=off, order=1, mode="grid-wrap")
    img += k * G.upsample(out, 4)


# ======================================================================= planets
@lru_cache(maxsize=1)
def earth_tex():
    h, w = 256, 512
    n = G.value_noise(h, w, 6, seed=3, base=3)
    cl = G.value_noise(h, w, 6, seed=4, base=4)
    lat = np.linspace(90, -90, h)[:, None] * np.ones((1, w))
    land = n > 0.56
    tex = np.zeros((h, w, 3), np.float32)
    deep = np.array([0.02, 0.10, 0.35]); shallow = np.array([0.05, 0.30, 0.65])
    tex[:] = deep + (shallow - deep) * G.smoothstep(0.3, 0.56, n)[..., None]
    green = np.array([0.12, 0.42, 0.15]); brown = np.array([0.55, 0.45, 0.25])
    lc = green + (brown - green) * G.smoothstep(0.6, 0.8, n)[..., None]
    tex[land] = lc[land]
    ice = np.abs(lat) > 72
    tex[ice] = [0.9, 0.95, 1.0]
    cloud = G.smoothstep(0.55, 0.8, cl)[..., None]
    tex = tex * (1 - 0.85 * cloud) + 0.95 * cloud
    return tex.astype(np.float32)


@lru_cache(maxsize=1)
def moon_tex():
    h, w = 256, 512
    rng = np.random.default_rng(5)
    base = 0.45 + 0.25 * G.value_noise(h, w, 6, seed=6, base=4)
    maria = G.smoothstep(0.55, 0.7, G.value_noise(h, w, 4, seed=8, base=2))
    base = base * (1 - 0.35 * maria)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    for _ in range(140):
        cx, cy = rng.uniform(0, w), rng.uniform(0, h)
        r = rng.uniform(2, 16) * (1 if rng.random() > 0.1 else 2)
        dx = np.minimum(np.abs(xx - cx), w - np.abs(xx - cx))
        d = np.sqrt(dx ** 2 + (yy - cy) ** 2) / r
        base = base - 0.16 * (d < 1) * (1 - d ** 2) + 0.10 * np.exp(-((d - 1.05) / 0.12) ** 2)
    tex = np.clip(base, 0, 1)[..., None] * np.array([1.0, 0.98, 0.95])
    return tex.astype(np.float32)


def draw_planet(img, cx, cy, r, tex, rot=0.0, light=(-0.6, -0.45, 0.65), atmo=None,
                ambient=0.06, spec=0.0, alpha=1.0):
    ext = r + 2
    x0, x1, y0, y1 = G.box(cx, cy, ext)
    if x0 >= x1 or y0 >= y1 or r < 0.5:
        return
    a, xx, yy = G.disc_alpha(cx, cy, r, x0, x1, y0, y1)
    nx = (xx - cx) / r
    ny = (yy - cy) / r
    nz = np.sqrt(np.clip(1 - nx ** 2 - ny ** 2, 0, 1))
    lon = np.arctan2(nx, nz) + rot
    lat = np.arcsin(np.clip(-ny, -1, 1))
    th, tw_ = tex.shape[:2]
    u = ((lon / TAU) % 1.0 * tw_).astype(np.int32) % tw_
    v = np.clip(((0.5 - lat / np.pi) * th).astype(np.int32), 0, th - 1)
    col = tex[v, u]
    L = np.array(light, np.float32); L /= np.linalg.norm(L)
    lam = np.clip(nx * L[0] + ny * L[1] + nz * L[2], 0, 1)
    shade = ambient + (1 - ambient) * lam
    rgb = col * shade[..., None]
    if spec:
        hz = L + np.array([0, 0, 1.0]); hz /= np.linalg.norm(hz)
        s = np.clip(nx * hz[0] + ny * hz[1] + nz * hz[2], 0, 1) ** 40
        rgb += spec * s[..., None]
    if atmo is not None:
        rim = (1 - nz) ** 2.5 * (0.3 + 0.7 * lam)
        rgb += rim[..., None] * np.asarray(atmo, np.float32) * 1.2
    G.over(img, rgb.astype(np.float32), a * alpha, x0, y0)
    if atmo is not None:
        # outer atmosphere halo
        e = r * 1.35
        x0, x1, y0, y1 = G.box(cx, cy, e)
        yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
        d = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
        hal = np.exp(-np.maximum(d - r, 0) / (r * 0.06)) * (d >= r - 1) * 0.8
        img[y0:y1, x0:x1] += (hal * alpha)[..., None] * np.asarray(atmo, np.float32)


@lru_cache(maxsize=1)
def sun_noise():
    return G.value_noise(256, 256, 6, seed=21, base=8)


@lru_cache(maxsize=1)
def ray_noise():
    rng = np.random.default_rng(22)
    a = rng.random(64)
    a = np.concatenate([a, a[:1]])
    return a


def draw_sun(img, cx, cy, r, t, k=1.0, rays=True):
    # corona / halo
    G.add_glow(img, cx, cy, r * 0.9, (1.0, 0.55, 0.15), 0.9 * k, halo=0.55 * k, halo_r=r * 1.1,
               extent=r * 3.2)
    if rays:
        e = r * 2.4
        x0, x1, y0, y1 = G.box(cx, cy, e)
        yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
        ang = np.arctan2(yy - cy, xx - cx)
        d = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) / r
        rn = ray_noise()
        u = ((ang / TAU + 0.5) * 64 + t * 0.6) % 64
        i0 = u.astype(np.int32)
        f = u - i0
        ray = rn[i0] * (1 - f) + rn[i0 + 1] * f
        u2 = ((ang / TAU + 0.5) * 64 * 1.7 - t * 0.9) % 64
        j0 = u2.astype(np.int32)
        ray2 = rn[j0] * (1 - (u2 - j0)) + rn[j0 + 1] * (u2 - j0)
        rv = (0.5 * ray + 0.5 * ray2) ** 3
        val = rv * np.exp(-(d - 1) * 2.2) * (d > 0.98) * 0.7 * k
        img[y0:y1, x0:x1] += val[..., None] * np.array([1.0, 0.6, 0.2], np.float32)
    # photosphere
    x0, x1, y0, y1 = G.box(cx, cy, r + 2)
    a, xx, yy = G.disc_alpha(cx, cy, r, x0, x1, y0, y1)
    nx = (xx - cx) / r
    ny = (yy - cy) / r
    nz = np.sqrt(np.clip(1 - nx ** 2 - ny ** 2, 0, 1))
    tex = sun_noise()
    uu = ((nx * 0.5 + 0.5) * 255 + t * 6).astype(np.int32) % 256
    vv = ((ny * 0.5 + 0.5) * 255 + t * 2).astype(np.int32) % 256
    gran = 0.85 + 0.3 * tex[vv, uu]
    limb = 0.45 + 0.55 * nz ** 0.6
    core = np.array([1.6, 1.35, 0.85], np.float32)
    edge = np.array([1.3, 0.55, 0.12], np.float32)
    mix = (nz ** 0.8)[..., None]
    rgb = (edge + (core - edge) * mix) * (limb * gran)[..., None] * k
    G.over(img, rgb.astype(np.float32), a, x0, y0)


# ======================================================================= galaxies
@lru_cache(maxsize=None)
def galaxy_particles(seed=1, n=90000, arms=2, b=0.30, bulge=0.16, arm_sigma=0.20,
                     blue=(0.62, 0.78, 1.0)):
    rng = np.random.default_rng(seed)
    nb = int(n * bulge)
    nd = n - nb
    # bulge
    rb = np.abs(rng.normal(0, 0.09, nb)) + 0.005
    tb = rng.uniform(0, TAU, nb)
    xb, yb = rb * np.cos(tb), rb * np.sin(tb) * 0.85
    cb = np.array([1.0, 0.82, 0.55]) * rng.uniform(0.6, 1.2, (nb, 1))
    wb = np.full(nb, 0.075)
    # disk
    r = rng.exponential(0.28, nd) + 0.04
    far = r > 1.0
    r[far] = rng.uniform(0.15, 1.0, far.sum())  # no pile-up ring at the rim
    in_arm = rng.random(nd) < 0.72
    k = rng.integers(0, arms, nd)
    theta_arm = np.log(r / 0.05) / b + TAU * k / arms
    spread = rng.normal(0, arm_sigma, nd) * (0.6 + 0.6 * r)
    theta = np.where(in_arm, theta_arm + spread, rng.uniform(0, TAU, nd))
    xd, yd = r * np.cos(theta), r * np.sin(theta)
    cd = np.where(in_arm[:, None], np.array(blue), np.array([1.0, 0.9, 0.75]))
    cd = cd * rng.uniform(0.5, 1.3, (nd, 1))
    wd = np.where(in_arm, 0.13, 0.07) * np.exp(-r * 0.8) * (0.3 + 0.7 * G.smoothstep(0.04, 0.35, r))
    # pink star-forming knots
    hii = in_arm & (rng.random(nd) < 0.03) & (r > 0.2)
    cd[hii] = [1.0, 0.4, 0.75]
    wd[hii] *= 2.5
    xy = np.concatenate([np.stack([xb, yb], 1), np.stack([xd, yd], 1)]).astype(np.float32)
    rgb = (np.concatenate([cb, cd]) * np.concatenate([wb, wd])[:, None]).astype(np.float32)
    perm = rng.permutation(n)
    return xy[perm], rgb[perm]


def draw_galaxy(img, P, cx, cy, R, angle, tilt=0.8, pa=0.0, alpha=1.0, glow=1.0, R0=400.0):
    xy, rgb = P
    if R < 2 or alpha <= 0.01:
        return
    frac = float(np.clip((R / R0) ** 1.2, 0.08, 1.0))
    m = max(2000, int(len(xy) * frac))
    xy, rgb = xy[:m], rgb[:m] / (m / len(xy))
    ca, sa = np.cos(angle), np.sin(angle)
    x = xy[:, 0] * ca - xy[:, 1] * sa
    y = (xy[:, 0] * sa + xy[:, 1] * ca) * tilt
    cp, sp = np.cos(pa), np.sin(pa)
    X = x * cp - y * sp
    Y = x * sp + y * cp
    sx, sy = cx + R * X, cy + R * Y
    # keep surface brightness roughly constant: total light ~ visible area
    lum = float(np.clip((R / R0) ** 1.9 * (tilt / 0.78), 0.015, 1.3)) * alpha
    w = rgb * lum
    G.splat(img, sx, sy, w * 0.9)
    buf = G.splat_buffer(sx, sy, w, 4)
    g = ndimage.gaussian_filter(buf, (1.2, 1.2, 0)) * 0.6 + ndimage.gaussian_filter(buf, (5, 5, 0)) * 0.8
    img += glow * G.upsample(g, 4)
    # bright core
    G.add_glow(img, cx, cy, max(1.5, R * 0.05), (1.0, 0.85, 0.6), 0.45 * lum ** 0.5 * alpha,
               halo=0.12 * lum ** 0.5 * alpha, halo_r=R * 0.12, extent=R * 0.6)


# ======================================================================= cosmic web
@lru_cache(maxsize=1)
def cosmic_web(seed=31):
    rng = np.random.default_rng(seed)
    X, Y, Lz = 2.9, 5.0, 2.6
    nn = 170
    nodes = np.stack([rng.uniform(-X, X, nn), rng.uniform(-Y, Y, nn), rng.uniform(0, Lz, nn)], 1)
    pts, cols, ws = [], [], []
    edges = set()
    for i in range(nn):
        d = nodes - nodes[i]
        d[:, 2] = (d[:, 2] + Lz / 2) % Lz - Lz / 2
        dist = np.linalg.norm(d, axis=1)
        dist[i] = 1e9
        for j in np.argsort(dist)[:3]:
            if dist[j] < 2.2:
                edges.add((min(i, j), max(i, j)))
    for i, j in edges:
        a = nodes[i]
        d = nodes[j] - a
        d[2] = (d[2] + Lz / 2) % Lz - Lz / 2
        L = np.linalg.norm(d)
        n = int(420 * L)
        s = rng.random(n)
        thick = 0.012 + 0.018 * np.sin(np.pi * s)
        p = a + s[:, None] * d + rng.normal(0, 1, (n, 3)) * thick[:, None]
        pts.append(p)
        c = np.where(rng.random(n)[:, None] < 0.5, [0.55, 0.35, 1.0], [0.3, 0.5, 1.0])
        cols.append(c)
        ws.append(np.full(n, 0.16))
    for i in range(nn):
        n = int(rng.uniform(80, 260))
        p = nodes[i] + rng.normal(0, 0.04, (n, 3))
        pts.append(p)
        cols.append(np.tile([1.0, 0.7, 0.95], (n, 1)))
        ws.append(np.full(n, 0.34))
    n = 5000
    pts.append(np.stack([rng.uniform(-X, X, n), rng.uniform(-Y, Y, n), rng.uniform(0, Lz, n)], 1))
    cols.append(np.tile([0.4, 0.4, 0.8], (n, 1)))
    ws.append(np.full(n, 0.06))
    P = np.concatenate(pts).astype(np.float32)
    P[:, 2] %= Lz
    C = (np.concatenate(cols) * np.concatenate(ws)[:, None]).astype(np.float32)
    return P, C, Lz


# ======================================================================= Hubble deep field
HDF_SIZE = 2200


def hdf_texture():
    path = BUILD / "hdf.png"
    if path.exists():
        return Image.open(path).convert("RGB")
    S = HDF_SIZE
    rng = np.random.default_rng(41)
    img = np.zeros((S, S, 3), np.float32)
    bg = G.value_noise(S // 8, S // 8, 4, seed=42, base=4)
    bg = ndimage.zoom(bg, 8, order=1)[:S, :S]
    img += (0.012 + 0.02 * bg)[..., None] * np.array([0.3, 0.35, 0.8], np.float32)
    n = 3600
    sizes = np.clip(rng.lognormal(0.9, 0.75, n), 0.7, 40)
    order = np.argsort(sizes)
    for k in order:
        s = sizes[k]
        cx, cy = rng.uniform(0, S), rng.uniform(0, S)
        e = rng.uniform(0.35, 1.0)
        ang = rng.uniform(0, np.pi)
        kind = rng.choice(["ell", "spiral", "blue", "red"], p=[0.3, 0.3, 0.25, 0.15])
        if s < 3:
            kind = rng.choice(["blue", "red", "ell"], p=[0.4, 0.35, 0.25])
        col = {"ell": np.array([1.0, 0.78, 0.45]), "spiral": np.array([0.85, 0.85, 1.0]),
               "blue": np.array([0.45, 0.6, 1.0]), "red": np.array([1.0, 0.35, 0.25])}[kind]
        col = col * rng.uniform(0.7, 1.2, 3)
        ext = s * 4
        x0, x1 = int(max(0, cx - ext)), int(min(S, cx + ext + 1))
        y0, y1 = int(max(0, cy - ext)), int(min(S, cy + ext + 1))
        if x1 <= x0 or y1 <= y0:
            continue
        yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
        dx, dy = xx - cx, yy - cy
        u = dx * np.cos(ang) + dy * np.sin(ang)
        v = (-dx * np.sin(ang) + dy * np.cos(ang)) / e
        rr = np.sqrt(u * u + v * v) / s
        val = np.exp(-rr ** 2 * 1.5) * 1.2
        if kind == "spiral" and s > 5:
            th = np.arctan2(v, u)
            arms = 0.5 + 0.5 * np.cos(2 * (th - 2.2 * np.log(rr + 0.2)))
            val = np.exp(-rr * 1.6) * (0.35 + 0.9 * arms) * 0.9 + np.exp(-rr ** 2 * 12) * 1.2
            core = np.exp(-rr ** 2 * 10)[..., None] * np.array([1.0, 0.85, 0.6])
            img[y0:y1, x0:x1] += core * 0.8
        if kind == "ell":
            val = np.exp(-rr ** 0.7 * 2.4) * 1.6
        bright = rng.uniform(0.4, 1.0) * (1.0 if s > 2 else 1.6)
        img[y0:y1, x0:x1] += val[..., None] * col * bright
    # a few foreground stars with diffraction spikes
    for _ in range(9):
        cx, cy = rng.uniform(100, S - 100), rng.uniform(100, S - 100)
        L = rng.uniform(25, 70)
        x0, x1, y0, y1 = int(cx - L), int(cx + L), int(cy - L), int(cy + L)
        yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
        dx, dy = np.abs(xx - cx), np.abs(yy - cy)
        spike = np.exp(-dy / 1.2) * np.exp(-dx / (L * 0.35)) + np.exp(-dx / 1.2) * np.exp(-dy / (L * 0.35))
        core = np.exp(-(dx ** 2 + dy ** 2) / 6)
        img[y0:y1, x0:x1] += (spike * 0.8 + core * 2.0)[..., None] * np.array([1.0, 0.95, 0.9])
    img = G.tonemap(img)
    im = Image.fromarray(G.to_u8(img))
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path)
    return im


# ======================================================================= probe
@lru_cache(maxsize=1)
def probe_sprite():
    S = 3
    im = Image.new("RGBA", (300 * S, 300 * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)

    def P(*pts):
        return [(x * S, y * S) for x, y in pts]

    grey, dark, gold = (200, 204, 212, 255), (90, 92, 100, 255), (176, 140, 70, 255)
    # magnetometer boom (long, thin) to upper right
    d.line(P((160, 140), (292, 18)), fill=(170, 175, 185, 255), width=2 * S)
    # RTG boom to lower left with 3 generators
    d.line(P((150, 160), (40, 250)), fill=grey, width=3 * S)
    for k in range(3):
        cx, cy = 58 + k * 13, 235 - k * 10.5
        d.ellipse(P((cx - 7, cy - 7), (cx + 7, cy + 7)), fill=dark, outline=grey, width=S)
    # science boom to lower right with scan platform
    d.line(P((165, 165), (240, 225)), fill=grey, width=3 * S)
    d.rectangle(P((232, 215), (258, 238)), fill=(120, 110, 90, 255), outline=grey, width=S)
    d.ellipse(P((250, 230), (264, 244)), fill=dark, outline=grey, width=S)
    # plasma antennas
    d.line(P((150, 170), (95, 290)), fill=(160, 160, 170, 255), width=S)
    d.line(P((156, 172), (140, 296)), fill=(160, 160, 170, 255), width=S)
    # bus (decagon)
    cx, cy, r = 158, 158, 28
    pts = [(cx + r * np.cos(a), cy + r * np.sin(a)) for a in np.linspace(0, TAU, 11)[:-1]]
    d.polygon(P(*pts), fill=gold, outline=(220, 190, 110, 255))
    # dish (seen at an angle) facing left/up toward the Sun
    d.ellipse(P((60, 60), (150, 210)), fill=(232, 234, 240, 255), outline=(150, 152, 160, 255), width=2 * S)
    d.ellipse(P((76, 82), (138, 190)), outline=(190, 192, 200, 255), width=S)
    d.ellipse(P((92, 106), (124, 166)), outline=(185, 188, 196, 255), width=S)
    # feed struts and sub-reflector
    for (x, y) in ((70, 100), (70, 170), (140, 135)):
        d.line(P((x, y), (82, 135)), fill=(140, 140, 150, 255), width=S)
    d.ellipse(P((76, 128), (88, 142)), fill=(240, 240, 245, 255))
    im = im.resize((300, 300), Image.LANCZOS)
    return im
