# -*- coding: utf-8 -*-
"""準備打包素材（品牌主題、字型）到 assets/

1. 複製 sv-ttk（Sun Valley）主題 → assets/svtheme/，把藍色強調色換成 Moksa Web 橘紅 #FF5A36，
   底色換成 #F7F5F0、文字色 #111113。
2. 下載 Space Grotesk Bold、JetBrains Mono Medium（SIL OFL 授權）→ assets/fonts/
用法：python scripts/prepare_assets.py（需要 pip install sv-ttk pillow）
"""
import colorsys
import re
import shutil
import urllib.request
from pathlib import Path

import sv_ttk
from PIL import Image

HERE = Path(__file__).parent
ASSETS = HERE.parent / "src" / "assets"
BRAND = "#FF5A36"
BRAND_DARK = "#BE381A"
BG = "#F7F5F0"
FG = "#111113"
SEL_BG = "#FFD9CC"

FONTS = {
    "SpaceGrotesk-Bold.ttf": "https://cdn.jsdelivr.net/fontsource/fonts/space-grotesk@5.1.1/latin-700-normal.ttf",
    "JetBrainsMono-Medium.ttf": "https://cdn.jsdelivr.net/fontsource/fonts/jetbrains-mono@5.1.1/latin-500-normal.ttf",
}


def hex2rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def recolor_sprites(src: Path, dst: Path):
    """藍色系像素 → 品牌橘紅（保留明暗層次與透明度）"""
    th, ts, tv = colorsys.rgb_to_hsv(*hex2rgb(BRAND))
    im = Image.open(src).convert("RGBA")
    px = im.load()
    n = 0
    for y in range(im.height):
        for x in range(im.width):
            r, g, b, a = px[x, y]
            if a == 0:
                continue
            h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
            if s > 0.18 and 0.50 < h < 0.72:  # 藍色範圍
                # 原強調色 #005fb8 的 V≈0.72 對應到品牌色 V=1.0
                nv = min(1.0, v / 0.72 * tv)
                ns = min(1.0, s * ts)
                nr, ng, nb = colorsys.hsv_to_rgb(th, ns, nv)
                px[x, y] = (round(nr * 255), round(ng * 255), round(nb * 255), a)
                n += 1
    im.save(dst)
    return n


def build_theme():
    src = Path(sv_ttk.__file__).parent
    dst = ASSETS / "svtheme"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.py", "py.typed"))
    n = recolor_sprites(src / "theme" / "spritesheet_light.png", dst / "theme" / "spritesheet_light.png")
    tcl = dst / "theme" / "light.tcl"
    t = tcl.read_text(encoding="utf-8")
    t = t.replace('-fg      "#1c1c1c"', f'-fg      "{FG.lower()}"')
    t = t.replace('-bg      "#fafafa"', f'-bg      "{BG.lower()}"')
    # 選取文字的反白：淡橘底＋深色字（不用深橘底白字，避免看起來像錯誤）
    t = t.replace('-selbg   "#2f60d8"', f'-selbg   "{SEL_BG.lower()}"')
    t = t.replace('-selfg   "#ffffff"', f'-selfg   "{FG.lower()}"')
    t = t.replace('-accent  "#005fb8"', f'-accent  "{BRAND_DARK.lower()}"')
    t = t.replace('"#c1d8ee"', '"#ffd9cf"')
    tcl.write_text(t, encoding="utf-8")
    left = re.findall(r"#(?:fafafa|2f60d8|005fb8|c1d8ee)", t)
    print(f"主題：重新上色 {n} 個像素，light.tcl 殘留舊色 {len(left)} 處 → {dst}")


def fix_font_names(f: Path, family: str, style: str):
    """fontsource 的 Space Grotesk 700 檔內名稱寫成「Space Grotesk Light」，Tk 會找不到 → 改回正確家族名"""
    from fontTools.ttLib import TTFont  # pip install fonttools
    t = TTFont(f)
    full, ps = f"{family} {style}", f"{family.replace(' ', '')}-{style}"
    for nid, val in ((1, family), (2, style), (4, full), (6, ps), (16, family), (17, style)):
        t["name"].setName(val, nid, 3, 1, 0x409)
        t["name"].setName(val, nid, 1, 0, 0)
    t.save(f)


def get_fonts():
    d = ASSETS / "fonts"
    d.mkdir(parents=True, exist_ok=True)
    for name, url in FONTS.items():
        f = d / name
        if f.exists() and f.stat().st_size > 10000:
            print(f"字型已存在：{name}")
            continue
        req = urllib.request.Request(url, headers={"User-Agent": "font-fetch/1.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            f.write_bytes(r.read())
        print(f"下載字型：{name}（{f.stat().st_size // 1024} KB）")
    fix_font_names(d / "SpaceGrotesk-Bold.ttf", "Space Grotesk", "Bold")
    (d / "LICENSE.txt").write_text(
        "Space Grotesk（Florian Karsten）與 JetBrains Mono（JetBrains）皆以 SIL Open Font License 1.1 授權。\n"
        "https://openfontlicense.org\n", encoding="utf-8")


if __name__ == "__main__":
    build_theme()
    get_fonts()
