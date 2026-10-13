# stitches a block of tiles into one picture to look over (missing tiles show magenta)
#   python preview.py <folder> <z> <x0> <x1> <y0> <y1> <out.png>
#   e.g. python preview.py tiles/merged 4 0 5 3 7 preview.png      (Alaska, Hawaii and the lower 48)
import sys, os
from PIL import Image

root, z, x0, x1, y0, y1, out = sys.argv[1], *map(int, sys.argv[2:7]), sys.argv[7]
im = Image.new('RGBA', ((x1 - x0 + 1) * 256, (y1 - y0 + 1) * 256), (255, 0, 255, 255))
for x in range(x0, x1 + 1):
    for y in range(y0, y1 + 1):
        p = os.path.join(root, str(z), str(x), f'{y}.png')
        if os.path.exists(p):
            t = Image.open(p).convert('RGBA')
            im.paste(t, ((x - x0) * 256, (y - y0) * 256), t)
im.save(out)
print(f'{out}: {im.size[0]}x{im.size[1]}')
