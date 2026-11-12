"""Tiny software 3D renderer for blocky (box-built) scenes.

Painter's algorithm over boxes / textured quads, flat per-face lighting with
directional, point and spot lights plus distance fog. Everything is drawn with
Pillow polygons, textures are mapped with perspective transforms.
"""
import math
import numpy as np
from PIL import Image, ImageDraw

# ---------------------------------------------------------------- matrices

def T(x, y, z):
    m = np.eye(4)
    m[:3, 3] = (x, y, z)
    return m


def S(x, y=None, z=None):
    if y is None:
        y = z = x
    return np.diag([x, y, z, 1.0])


def RX(a):
    c, s = math.cos(a), math.sin(a)
    m = np.eye(4)
    m[1, 1], m[1, 2], m[2, 1], m[2, 2] = c, -s, s, c
    return m


def RY(a):
    c, s = math.cos(a), math.sin(a)
    m = np.eye(4)
    m[0, 0], m[0, 2], m[2, 0], m[2, 2] = c, s, -s, c
    return m


def RZ(a):
    c, s = math.cos(a), math.sin(a)
    m = np.eye(4)
    m[0, 0], m[0, 1], m[1, 0], m[1, 1] = c, -s, s, c
    return m


def rad(d):
    return d * math.pi / 180.0


# unit cube corners
_C = np.array([[x, y, z] for x in (-.5, .5) for y in (-.5, .5) for z in (-.5, .5)])


def _ci(x, y, z):
    return (0 if x < 0 else 4) + (0 if y < 0 else 2) + (0 if z < 0 else 1)


# faces: name -> (corner idx TL,TR,BR,BL as seen from outside, local normal)
FACES = {
    'front': ([_ci(-1, 1, 1), _ci(1, 1, 1), _ci(1, -1, 1), _ci(-1, -1, 1)], (0, 0, 1)),
    'back': ([_ci(1, 1, -1), _ci(-1, 1, -1), _ci(-1, -1, -1), _ci(1, -1, -1)], (0, 0, -1)),
    'right': ([_ci(1, 1, 1), _ci(1, 1, -1), _ci(1, -1, -1), _ci(1, -1, 1)], (1, 0, 0)),
    'left': ([_ci(-1, 1, -1), _ci(-1, 1, 1), _ci(-1, -1, 1), _ci(-1, -1, -1)], (-1, 0, 0)),
    'top': ([_ci(-1, 1, -1), _ci(1, 1, -1), _ci(1, 1, 1), _ci(-1, 1, 1)], (0, 1, 0)),
    'bottom': ([_ci(-1, -1, 1), _ci(1, -1, 1), _ci(1, -1, -1), _ci(-1, -1, -1)], (0, -1, 0)),
}
FACE_ITEMS = list(FACES.items())


class Box:
    __slots__ = ('M', 'color', 'decals', 'layer', 'bias', 'emissive', 'outline', 'hide')

    def __init__(self, M, color, decals=None, layer=1, bias=0.0, emissive=0.0,
                 outline=None, hide=()):
        self.M = M
        self.color = np.asarray(color, float)
        self.decals = decals or {}
        self.layer = layer
        self.bias = bias
        self.emissive = emissive
        self.outline = outline
        self.hide = hide


def box(center, size, color, rot=None, **kw):
    """Axis box given world center & size, optional 4x4 rotation about center."""
    M = T(*center)
    if rot is not None:
        M = M @ rot
    return Box(M @ S(*size), color, **kw)


class Quad:
    """Textured quad: corners TL,TR,BR,BL (world), RGBA image."""
    __slots__ = ('P', 'img', 'layer', 'bias', 'lit', 'two_sided', 'emissive')

    def __init__(self, P, img, layer=1, bias=0.0, lit=True, two_sided=False, emissive=0.0):
        self.P = np.asarray(P, float)
        self.img = img
        self.layer = layer
        self.bias = bias
        self.lit = lit
        self.two_sided = two_sided
        self.emissive = emissive


class Light:
    def __init__(self, pos, color, intensity=1.0, radius=6.0, spot_dir=None,
                 spot_cos=0.9, spot_soft=0.08):
        self.pos = np.asarray(pos, float)
        self.color = np.asarray(color, float) / 255.0
        self.intensity = intensity
        self.radius = radius
        self.spot_dir = None if spot_dir is None else np.asarray(spot_dir, float) / np.linalg.norm(spot_dir)
        self.spot_cos = spot_cos
        self.spot_soft = spot_soft


class Camera:
    def __init__(self, pos, target, fov=55, roll=0.0):
        self.pos = np.asarray(pos, float)
        f = np.asarray(target, float) - self.pos
        f /= np.linalg.norm(f)
        up = np.array([0, 1.0, 0])
        r = np.cross(f, up)
        r /= np.linalg.norm(r)
        u = np.cross(r, f)
        if roll:
            c, s = math.cos(roll), math.sin(roll)
            r, u = r * c + u * s, -r * s + u * c
        self.R = np.stack([r, u, f])  # rows
        self.fov = fov


class Scene:
    def __init__(self):
        self.boxes = []
        self.quads = []
        self.lights = []
        self.ambient = np.array([0.35, 0.35, 0.35])
        self.sun_dir = np.array([0.4, 0.8, 0.45])
        self.sun_dir = self.sun_dir / np.linalg.norm(self.sun_dir)
        self.sun = np.array([0.7, 0.7, 0.7])
        self.fog_color = np.array([0, 0, 0], float)
        self.fog_density = 0.0
        self.background = None  # PIL image or color
        self.floor_shadows = []  # list of (polygon world pts Nx3, alpha)
        self.cast = []  # (boxes, light_pos, alpha) planar shadows onto y=0

    def add(self, *items):
        for it in items:
            if isinstance(it, (list, tuple)):
                self.add(*it)
            elif isinstance(it, Box):
                self.boxes.append(it)
            elif isinstance(it, Quad):
                self.quads.append(it)
            elif isinstance(it, Light):
                self.lights.append(it)
        return self


# ---------------------------------------------------------------- helpers

def homography(src, dst):
    """Coefficients for PIL PERSPECTIVE mapping dst(output) -> src(input)."""
    A = []
    b = []
    for (x, y), (u, v) in zip(dst, src):
        A.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        A.append([0, 0, 0, x, y, 1, -v * x, -v * y])
        b += [u, v]
    try:
        return np.linalg.solve(np.array(A, float), np.array(b, float))
    except np.linalg.LinAlgError:
        return None


def clip_near(pts, near):
    out = []
    n = len(pts)
    for i in range(n):
        a = pts[i]
        b = pts[(i + 1) % n]
        ain = a[2] >= near
        bin_ = b[2] >= near
        if ain:
            out.append(a)
        if ain != bin_:
            t = (near - a[2]) / (b[2] - a[2])
            out.append(a + (b - a) * t)
    return out


class Renderer:
    def __init__(self, W, H, ss=2):
        self.W, self.H, self.ss = W, H, ss
        self.w, self.h = W * ss, H * ss

    def shade(self, scene, p, n, base, emissive=0.0):
        col = scene.ambient.copy()
        d = float(np.dot(n, scene.sun_dir))
        if d > 0:
            col = col + scene.sun * d
        for L in scene.lights:
            v = L.pos - p
            dist2 = float(v @ v)
            dist = math.sqrt(dist2) + 1e-6
            v = v / dist
            nd = float(n @ v)
            if nd <= 0:
                nd = 0.08  # a bit of wrap so backsides aren't pitch black
            att = L.intensity / (1.0 + dist2 / (L.radius * L.radius))
            if L.spot_dir is not None:
                c = float(-v @ L.spot_dir)
                k = (c - L.spot_cos) / L.spot_soft
                if k <= 0:
                    continue
                att *= min(1.0, k)
            col = col + L.color * (att * nd)
        rgb = base * col + emissive * base
        return rgb

    def fog(self, scene, rgb, dist):
        if scene.fog_density > 0:
            f = 1.0 - math.exp(-dist * scene.fog_density)
            rgb = rgb * (1 - f) + scene.fog_color * f
        return rgb

    def render(self, scene, cam):
        w, h = self.w, self.h
        if isinstance(scene.background, Image.Image):
            img = scene.background.resize((w, h)) if scene.background.size != (w, h) else scene.background.copy()
        else:
            bg = scene.background if scene.background is not None else (0, 0, 0)
            img = Image.new('RGB', (w, h), tuple(int(c) for c in bg))
        draw = ImageDraw.Draw(img, 'RGBA')
        f = (h / 2) / math.tan(math.radians(cam.fov) / 2)
        cx, cy = w / 2, h / 2
        near = 0.05
        R, cpos = cam.R, cam.pos

        def to_cam(P):
            return (P - cpos) @ R.T

        def project(Pc):
            return [(cx + f * p[0] / p[2], cy - f * p[1] / p[2]) for p in Pc]

        items = []  # (layer, key, kind, payload)
        for b in scene.boxes:
            M = b.M
            V = _C @ M[:3, :3].T + M[:3, 3]
            ctr = M[:3, 3]
            dist = float(np.linalg.norm(ctr - cpos))
            items.append((b.layer, -dist + b.bias, 0, (b, V)))
        for q in scene.quads:
            ctr = q.P.mean(0)
            dist = float(np.linalg.norm(ctr - cpos))
            items.append((q.layer, -dist + q.bias, 1, q))
        items.sort(key=lambda it: (it[0], it[1]))

        shadows_done = False
        for layer, key, kind, payload in items:
            if layer >= 1 and not shadows_done:
                self._shadows(scene, img, draw, to_cam, project, near)
                shadows_done = True
            if kind == 0:
                b, V = payload
                Vc = to_cam(V)
                if (Vc[:, 2] < near).all():
                    continue
                M3 = b.M[:3, :3]
                for name, (idx, nl) in FACE_ITEMS:
                    if name in b.hide:
                        continue
                    n = M3 @ np.array(nl, float)
                    nn = np.linalg.norm(n)
                    if nn == 0:
                        continue
                    n = n / nn
                    P = V[idx]
                    pc = P.mean(0)
                    if float(n @ (cpos - pc)) <= 0:
                        continue
                    Pc = Vc[idx]
                    if (Pc[:, 2] < near).any():
                        poly = clip_near(list(Pc), near)
                        if len(poly) < 3:
                            continue
                        pts = project(poly)
                        full = False
                    else:
                        pts = project(Pc)
                        full = True
                    rgb = self.shade(scene, pc, n, b.color, b.emissive)
                    rgb = self.fog(scene, rgb, float(np.linalg.norm(pc - cpos)))
                    col = tuple(int(max(0, min(255, c))) for c in rgb)
                    if b.outline is not None:
                        oc = tuple(int(c * b.outline) for c in col)
                        draw.polygon(pts, fill=col, outline=oc, width=max(1, self.ss))
                    else:
                        draw.polygon(pts, fill=col)
                    dec = b.decals.get(name)
                    if dec is not None and full:
                        fac = rgb / np.maximum(b.color, 1)
                        self._texture(img, dec, pts, fac)
            else:
                q = payload
                Pc = to_cam(q.P)
                if (Pc[:, 2] < near).any():
                    continue
                pts = project(Pc)
                n = np.cross(q.P[3] - q.P[0], q.P[1] - q.P[0])
                n = n / (np.linalg.norm(n) + 1e-9)
                pc = q.P.mean(0)
                facing = float(n @ (cpos - pc))
                if facing <= 0 and not q.two_sided:
                    continue
                if facing <= 0:
                    n = -n
                if q.lit:
                    rgb = self.shade(scene, pc, n, np.array([255.0, 255, 255]), q.emissive)
                    rgb = self.fog(scene, rgb, float(np.linalg.norm(pc - cpos)))
                    fac = rgb / 255.0
                else:
                    fac = None
                self._texture(img, q.img, pts, fac)
        if not shadows_done:
            self._shadows(scene, img, draw, to_cam, project, near)
        return img

    def _poly_world(self, P, to_cam, project, near):
        Pc = to_cam(np.asarray(P, float))
        if (Pc[:, 2] < near).any():
            poly = clip_near(list(Pc), near)
            if len(poly) < 3:
                return None
            return project(poly)
        return project(Pc)

    def _shadows(self, scene, img, draw, to_cam, project, near):
        for P, alpha in scene.floor_shadows:
            pts = self._poly_world(P, to_cam, project, near)
            if pts:
                draw.polygon(pts, fill=(0, 0, 0, int(alpha)))
        if scene.cast:
            mask = Image.new('L', img.size, 0)
            md = ImageDraw.Draw(mask)
            alpha_max = 0
            for boxes, lpos, alpha in scene.cast:
                alpha_max = max(alpha_max, alpha)
                L = np.asarray(lpos, float)
                for b in boxes:
                    V = _C @ b.M[:3, :3].T + b.M[:3, 3]
                    hy = L[1] - V[:, 1]
                    hy = np.maximum(hy, 0.05)
                    t = (L[1] - 0.02) / hy
                    G = L + (V - L) * t[:, None]
                    hull = _hull2d(G[:, [0, 2]])
                    P = np.array([[x, 0.02, z] for x, z in hull])
                    pts = self._poly_world(P, to_cam, project, near)
                    if pts:
                        md.polygon(pts, fill=255)
            dark = Image.new('RGB', img.size, (0, 0, 0))
            mask = mask.point(lambda v: int(v * alpha_max / 255))
            img.paste(dark, (0, 0), mask)

    def _texture(self, img, tex, pts, fac):
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        x0, y0 = int(math.floor(min(xs))), int(math.floor(min(ys)))
        x1, y1 = int(math.ceil(max(xs))), int(math.ceil(max(ys)))
        W, H = img.size
        if x1 < 0 or y1 < 0 or x0 >= W or y0 >= H:
            return
        # limit to the screen (keeps transforms cheap when very close)
        cx0, cy0 = max(x0, 0), max(y0, 0)
        cx1, cy1 = min(x1, W), min(y1, H)
        bw, bh = cx1 - cx0, cy1 - cy0
        if bw < 2 or bh < 2:
            return
        tw, th = tex.size
        dst = [(p[0] - cx0, p[1] - cy0) for p in pts]
        co = homography([(0, 0), (tw, 0), (tw, th), (0, th)], dst)
        if co is None:
            return
        t = tex.transform((bw, bh), Image.PERSPECTIVE, tuple(co), Image.BILINEAR)
        if fac is not None:
            r, g, b, a = t.split()
            fr, fg, fb = (float(min(3.0, max(0.0, v))) for v in fac)
            r = r.point(lambda v, k=fr: min(255, int(v * k)))
            g = g.point(lambda v, k=fg: min(255, int(v * k)))
            b = b.point(lambda v, k=fb: min(255, int(v * k)))
            t = Image.merge('RGBA', (r, g, b, a))
        img.paste(t.convert('RGB'), (cx0, cy0), t.split()[3])


def _hull2d(pts):
    pts = sorted(set((round(float(x), 4), round(float(y), 4)) for x, y in pts))
    if len(pts) <= 2:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def disc(center, radius, n=20, y=0.02):
    cx, cz = center
    return np.array([[cx + radius * math.cos(2 * math.pi * i / n), y,
                      cz + radius * 0.8 * math.sin(2 * math.pi * i / n)] for i in range(n)])
