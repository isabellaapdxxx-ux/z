"""Contact sheet of rendered stills: python tools/contact_sheet.py <frames dir> <out.jpg> [cols] [thumb_w]"""
import glob, os, sys
from PIL import Image, ImageDraw, ImageFont
d, out = sys.argv[1], sys.argv[2]
cols = int(sys.argv[3]) if len(sys.argv) > 3 else 6
tw = int(sys.argv[4]) if len(sys.argv) > 4 else 300
files = sorted(glob.glob(os.path.join(d, 'f_*.jpg')))
th = tw * 16 // 9
rows = (len(files) + cols - 1) // cols
sheet = Image.new('RGB', (cols * (tw + 6), rows * (th + 30)), (30, 30, 30))
font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 18)
for i, f in enumerate(files):
    im = Image.open(f).convert('RGB').resize((tw, th))
    x, y = (i % cols) * (tw + 6), (i // cols) * (th + 30)
    sheet.paste(im, (x, y + 26))
    fr = int(os.path.basename(f)[2:7])
    ImageDraw.Draw(sheet).text((x + 4, y + 3), f'{fr / 30:.2f}s', fill=(255, 255, 0), font=font)
sheet.save(out, quality=88)
print(out, sheet.size)
