# builds the other zooms from the generated zoom 9 tiles, then lays the archived artwork over them
#   python pyramid.py      writes zooms 0-10 to tiles/generated, and the combined set to tiles/merged
# without tiles/archive, the merged set is the generated tiles alone
import os, shutil
import numpy as np
from PIL import Image
from common import ARCHIVE, MERGED, GENERATED as GEN

BASE, TOP = 9, 10


def tiles(root, z):
    d = os.path.join(root, str(z))
    if not os.path.isdir(d):
        return set()
    return {(int(x), int(f[:-4])) for x in os.listdir(d) for f in os.listdir(os.path.join(d, x)) if f.endswith('.png')}


def load(root, z, x, y):
    p = os.path.join(root, str(z), str(x), f'{y}.png')
    if not os.path.exists(p):
        return None
    return np.asarray(Image.open(p).convert('RGBA')).astype(np.float32)


def save(root, z, x, y, a):
    p = os.path.join(root, str(z), str(x), f'{y}.png')
    os.makedirs(os.path.dirname(p), exist_ok=True)
    img = Image.fromarray(np.clip(np.round(a), 0, 255).astype(np.uint8), 'RGBA')
    if img.getextrema()[3][0] == 255:
        img = img.convert('RGB')
    img.save(p)


# up: zoom 10 is the zoom 9 art blown up, as the original's zoom 10 is
base = tiles(GEN, BASE)
n = 2 ** BASE
for x, y in base:
    ctx = np.zeros((768, 768, 4), np.float32)
    center = load(GEN, BASE, x, y)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            t = load(GEN, BASE, (x + dx) % n, y + dy) if 0 <= y + dy < n else None
            ctx[(dy + 1) * 256:(dy + 2) * 256, (dx + 1) * 256:(dx + 2) * 256] = t if t is not None else center
    big = np.asarray(Image.fromarray(ctx.astype(np.uint8), 'RGBA').resize((1536, 1536), Image.BICUBIC)).astype(np.float32)
    for qx in (0, 1):
        for qy in (0, 1):
            save(GEN, TOP, 2 * x + qx, 2 * y + qy, big[512 + qy * 256:768 + qy * 256, 512 + qx * 256:768 + qx * 256])
print(f'z{TOP}: {len(base) * 4} tiles')

# down: each tile is its four children averaged, with see-through where there are none
for z in range(BASE - 1, -1, -1):
    parents = {(x // 2, y // 2) for x, y in tiles(GEN, z + 1)}
    for x, y in parents:
        quad = np.zeros((512, 512, 4), np.float32)
        for qx in (0, 1):
            for qy in (0, 1):
                t = load(GEN, z + 1, 2 * x + qx, 2 * y + qy)
                if t is not None:
                    quad[qy * 256:(qy + 1) * 256, qx * 256:(qx + 1) * 256] = t
        a = quad[..., 3:] / 255
        pre = (quad[..., :3] * a).reshape(256, 2, 256, 2, 3).mean(axis=(1, 3))
        alpha = a.reshape(256, 2, 256, 2, 1).mean(axis=(1, 3))
        rgb = np.where(alpha > 0, pre / np.maximum(alpha, 1e-6), 0)
        save(GEN, z, x, y, np.concatenate([rgb, alpha * 255], -1))
    print(f'z{z}: {len(parents)} tiles')

# merge: the archived artwork wins wherever it has paint
if os.path.isdir(MERGED):
    shutil.rmtree(MERGED)
for z in range(0, TOP + 1):
    arch, gen = tiles(ARCHIVE, z), tiles(GEN, z)
    for x, y in arch | gen:
        src = None if (x, y) in gen else os.path.join(ARCHIVE, str(z), str(x), f'{y}.png')
        if (x, y) not in arch:
            src = os.path.join(GEN, str(z), str(x), f'{y}.png')
        if src:
            p = os.path.join(MERGED, str(z), str(x), f'{y}.png')
            os.makedirs(os.path.dirname(p), exist_ok=True)
            shutil.copyfile(src, p)
            continue
        top, bottom = load(ARCHIVE, z, x, y), load(GEN, z, x, y)
        ta, ba = top[..., 3:] / 255, bottom[..., 3:] / 255
        oa = ta + ba * (1 - ta)
        rgb = np.where(oa > 0, (top[..., :3] * ta + bottom[..., :3] * ba * (1 - ta)) / np.maximum(oa, 1e-6), 0)
        save(MERGED, z, x, y, np.concatenate([rgb, oa * 255], -1))
    print(f'merged z{z}: {len(arch | gen)} tiles ({len(arch & gen)} combined)')
