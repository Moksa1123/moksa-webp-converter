# -*- coding: utf-8 -*-
"""Moksa Web WebP 圖片轉換工具（Windows／macOS）
© Moksa Web・台中的網站工程工作室  https://moksaweb.com/

點兩下即可開啟。批次把 JPG / PNG / GIF / BMP / TIFF / WebP 轉成 WebP、JPG 或 PNG。
選「類別 → 用途」即自動帶入格式、尺寸、品質、檔案上限、安全區與命名。
用途資料在 assets/presets.json（由 scripts/gen_presets.py 產生）；程式旁放一份 presets.json 可覆蓋。
可拖放檔案、即時預覽轉換結果（真實檔案大小）、顯示各平台安全區。
需求（原始碼執行時）：Python 3.9+、Pillow；選用：tkinterdnd2（拖放）
"""
import ctypes
import io
import json
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

try:
    from PIL import Image, ImageDraw, ImageOps, ImageSequence, ImageTk
except ImportError:
    tk.Tk().withdraw()
    messagebox.showerror("缺少套件", "找不到 Pillow，請先在命令列執行：\n\npip install pillow")
    sys.exit(1)

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD

    class RootBase(tk.Tk, TkinterDnD.DnDWrapper):
        """載入 tkdnd；原生拖放元件載不起來時視窗照常開啟，只是不能拖放"""
        def __init__(self):
            tk.Tk.__init__(self)
            self.dnd_error = ""
            try:
                self.TkdndVersion = TkinterDnD._require(self)
            except Exception as e:
                self.TkdndVersion, self.dnd_error = None, repr(e)
except Exception as _e:  # 沒有拖放套件也能用
    DND_FILES = None

    class RootBase(tk.Tk):
        TkdndVersion, dnd_error = None, ""

IS_WIN = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"

APP_NAME = "Moksa Web"
APP_TITLE = "Moksa Web WebP 圖片轉換工具"
APP_VERSION = "1.4.1"
APP_URL = "https://moksaweb.com/"
APP_ABOUT = ("台中的網站工程工作室。WordPress、WooCommerce、LINE 整合、n8n 與 AI 自動化、客製 ERP——"
             "從規劃、開發到上線維運，一個窗口負責到底。")
SUPPORTED = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tif", ".tiff", ".webp"}
if IS_MAC:
    SETTINGS_FILE = Path.home() / "Library" / "Application Support" / "Moksa Web" / "webp_converter_settings.json"
else:
    SETTINGS_FILE = Path(os.environ.get("APPDATA", Path.home())) / "webp_converter_settings.json"
WEBP_MAX = 16383
EXT = {"webp": ".webp", "jpg": ".jpg", "png": ".png"}
BAD_CHARS = '\\/:*?"<>|'

# Moksa Web 品牌色（官網 CSS 變數）
BRAND = "#FF5A36"        # 主色 橘紅
ACCENT = "#BE381A"       # 白底小字用（對比足夠）
INK = "#111113"
MUTED = "#56565E"
PAPER = "#F7F5F0"
CARD = "#FAFAFA"        # 卡片底色＝sun-valley 卡片圖的顏色，卡片裡的元件才不會有色差
LINE = "#DFDCD4"
DARK = "#0E0E10"
DARK2 = "#1B1B1F"
DARK_INK = "#EEECE6"
DARK_MUTED = "#A3A3AB"
DANGER = "#C81E1E"
OK = "#1F7A3A"
OK_BG = "#E6F4EA"
TINT = "#FFF1EC"       # 淡橘（選取列、拖曳經過）
SEG = "#F0EDE6"        # 分段按鈕底色
PANE = "#ECE9E2"       # 預覽底色
PAPER2 = "#FBFAF7"     # 底部列
SIM_SCREEN = None  # 介面測試用：模擬螢幕解析度 (寬, 高)
UI_FONT = "PingFang TC" if IS_MAC else "Microsoft JhengHei UI"
BRAND_FONT = "Space Grotesk"
MONO_FONT = "JetBrains Mono"


def fs(n: int) -> int:
    """字級：程式裡的數字以 Windows（96 dpi）為準；Mac 的 Tk 以 72 dpi 計，放大 4/3 才會一樣大"""
    return round(n * 4 / 3) if IS_MAC else n

BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
ASSETS = BASE_DIR / "assets"
APP_DIR = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent


def register_fonts():
    """把打包的字型註冊成本程式私用（不安裝到系統）"""
    fonts = list((ASSETS / "fonts").glob("*.ttf"))
    if IS_WIN:
        for f in fonts:
            try:
                ctypes.windll.gdi32.AddFontResourceExW(str(f), 0x10, 0)  # FR_PRIVATE
            except Exception:
                pass
    elif IS_MAC:
        try:
            cf = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
            ct = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreText.framework/CoreText")
            cf.CFURLCreateFromFileSystemRepresentation.restype = ctypes.c_void_p
            cf.CFURLCreateFromFileSystemRepresentation.argtypes = [ctypes.c_void_p, ctypes.c_char_p,
                                                                   ctypes.c_long, ctypes.c_bool]
            ct.CTFontManagerRegisterFontsForURL.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p]
            for f in fonts:
                b = str(f).encode("utf-8")
                url = cf.CFURLCreateFromFileSystemRepresentation(None, b, len(b), False)
                ct.CTFontManagerRegisterFontsForURL(url, 1, None)  # kCTFontManagerScopeProcess
        except Exception:
            pass


def open_folder(path):
    """用系統檔案管理員開啟資料夾"""
    try:
        if IS_WIN:
            os.startfile(path)
        elif IS_MAC:
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception:
        pass


CUSTOM_PRESETS = ([SETTINGS_FILE.parent / "presets.json"] if IS_MAC else []) + [APP_DIR / "presets.json"]

FALLBACK_PRESETS = [
    {"key": "custom_keep", "cat": "自訂", "label": "保留原檔名", "naming": "keep", "apply": False,
     "hint": "下方格式、品質、尺寸全部自己設定。"},
    {"key": "custom_serial", "cat": "自訂", "label": "名稱＋流水號", "naming": "serial", "apply": False,
     "hint": "檔名＝名稱＋符號＋號碼，例如 banner-01、banner-02。"},
]


def load_presets():
    """讀用途預設：自訂的 presets.json 優先，否則用內建的。
    Windows：放在 exe 旁邊；Mac：放在 ~/Library/Application Support/Moksa Web/（.app 裡面客戶放不進去）"""
    for f in (*CUSTOM_PRESETS, ASSETS / "presets.json"):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            ps = d["presets"]
            cats = [c for c in d.get("categories", []) if any(p["cat"] == c for p in ps)]
            cats += [p["cat"] for p in ps if p["cat"] not in cats]
            cats = list(dict.fromkeys(cats))
            if not any(p["key"] == "custom_keep" for p in ps):
                ps = ps + FALLBACK_PRESETS
                if "自訂" not in cats:
                    cats.append("自訂")
            return ps, cats, d.get("version", ""), f
        except Exception:
            continue
    return FALLBACK_PRESETS, ["自訂"], "", None


PRESETS, CATEGORIES, PRESETS_VERSION, PRESETS_FILE = load_presets()
PRESET_BY_KEY = {p["key"]: p for p in PRESETS}

RESIZE_MODES = [
    ("none", "不調整尺寸"),
    ("width", "指定寬度（高度等比）"),
    ("height", "指定高度（寬度等比）"),
    ("fit", "限制在 寬×高 之內（不裁切）"),
    ("pad", "縮放並補白邊成 寬×高"),
    ("cover", "裁成固定 寬×高（置中裁切）"),
    ("percent", "依百分比縮放"),
    ("exact", "強制拉成 寬×高（會變形）"),
]
RS_LABEL = dict(RESIZE_MODES)
RS_KEY = {t: k for k, t in RESIZE_MODES}

DEFAULTS = {
    "preset": "custom_keep",
    "fmt": "webp", "mode": "lossy", "quality": 82, "method": 6, "alpha_quality": 100, "limit_kb": 0,
    "resize_mode": "none", "rw": 2000, "rh": 2000, "rpct": 50, "upscale": False,
    "base": "", "start": 1, "digits": 2, "sep": "-", "rev": 0,
    "out_mode": "subfolder", "out_dir": "",
    "keep_exif": False, "overwrite": False, "skip_larger": False, "recursive": True, "show_safe": True,
}


# ======================= 影像處理 =======================
def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


def diff_text(old: int, new: int) -> str:
    if not old:
        return "—"
    pct = abs(1 - new / old) * 100
    return f"省 {pct:.0f}%" if new <= old else f"變大 {pct:.0f}%"


def clean_name(s: str) -> str:
    return "".join("_" if c in BAD_CHARS else c for c in s).strip().strip(".")


def load_settings() -> dict:
    s = dict(DEFAULTS)
    try:
        s.update(json.loads(SETTINGS_FILE.read_text(encoding="utf-8")))
    except Exception:
        pass
    if s.get("preset") not in PRESET_BY_KEY:
        s["preset"] = "custom_keep"
    return s


def save_settings(s: dict) -> None:
    try:
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)  # Mac 的 Application Support 資料夾可能還不存在
        SETTINGS_FILE.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def resize_img(img, rs):
    """回傳（新圖, 是否放大）"""
    m = rs.get("resize_mode", "none")
    W, H, pct = int(rs.get("rw", 0)), int(rs.get("rh", 0)), int(rs.get("rpct", 100))
    w, h = img.size
    if m == "none":
        return img, False
    if m in ("cover", "exact", "pad"):
        if not (W and H):
            return img, False
        if m == "cover":
            return ImageOps.fit(img, (W, H), Image.LANCZOS), (W > w or H > h)
        if m == "exact":
            return img.resize((W, H), Image.LANCZOS), (W > w or H > h)
        r = min(W / w, H / h)
        if r > 1 and not rs.get("upscale"):
            r = 1
        inner = img if r == 1 else img.resize((max(1, round(w * r)), max(1, round(h * r))), Image.LANCZOS)
        bg = (255, 255, 255, 0) if inner.mode == "RGBA" else (255, 255, 255)
        canvas = Image.new(inner.mode, (W, H), bg)
        canvas.paste(inner, ((W - inner.width) // 2, (H - inner.height) // 2))
        return canvas, r > 1
    if m == "width" and W:
        nw, nh = W, h * W / w
    elif m == "height" and H:
        nw, nh = w * H / h, H
    elif m == "fit" and W and H:
        r = min(W / w, H / h)
        nw, nh = w * r, h * r
    elif m == "percent" and pct:
        nw, nh = w * pct / 100, h * pct / 100
    else:
        return img, False
    nw, nh = max(1, round(nw)), max(1, round(nh))
    if (nw > w or nh > h) and not rs.get("upscale"):
        return img, False
    if (nw, nh) == (w, h):
        return img, False
    return img.resize((nw, nh), Image.LANCZOS), nw > w


def limit_webp(img):
    w, h = img.size
    if max(w, h) <= WEBP_MAX:
        return img
    r = WEBP_MAX / max(w, h)
    return img.resize((max(1, int(w * r)), max(1, int(h * r))), Image.LANCZOS)


def flatten(img):
    """JPG 不支援透明：透明處補白"""
    if img.mode in ("RGBA", "LA"):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.getchannel("A"))
        return bg
    return img.convert("RGB") if img.mode != "RGB" else img


def load_source(src: Path, keep_exif: bool):
    """讀取來源：回傳（frames, durations, loop, extras）"""
    with Image.open(src) as im:
        extras = {}
        if keep_exif and im.info.get("exif"):
            extras["exif"] = im.info["exif"]
        if im.info.get("icc_profile"):
            extras["icc_profile"] = im.info["icc_profile"]
        if getattr(im, "n_frames", 1) > 1:
            frames, durations = [], []
            for fr in ImageSequence.Iterator(im):
                durations.append(fr.info.get("duration", im.info.get("duration", 100)))
                frames.append(fr.convert("RGBA"))
            return frames, durations, im.info.get("loop", 0), extras
        img = ImageOps.exif_transpose(im)
        if img.mode not in ("RGB", "RGBA"):
            alpha = img.mode in ("LA", "PA") or (img.mode == "P" and "transparency" in img.info)
            img = img.convert("RGBA" if alpha else "RGB")
        else:
            img = img.copy()
        return [img], [], 0, extras


def render(frames, durations, loop, extras, rs, opt):
    """依尺寸與格式編碼。回傳（資料, 實際品質, 輸出第一格影像, 是否放大）"""
    fmt = opt["fmt"]
    if fmt != "webp":
        frames, durations = frames[:1], []
    out, up = [], False
    for f in frames:
        r, u = resize_img(f, rs)
        out.append(limit_webp(r) if fmt == "webp" else r)
        up = up or u
    if fmt == "jpg":
        out = [flatten(out[0])]
    can_lower = fmt == "jpg" or (fmt == "webp" and opt["mode"] != "lossless")

    def enc(imgs, q):
        buf = io.BytesIO()
        if fmt == "webp":
            p = dict(lossless=opt["mode"] == "lossless", quality=q, method=int(opt["method"]),
                     alpha_quality=int(opt["alpha_quality"]), **extras)
            if len(imgs) > 1:
                imgs[0].save(buf, "WEBP", save_all=True, append_images=imgs[1:],
                             duration=durations, loop=loop, **p)
            else:
                imgs[0].save(buf, "WEBP", **p)
        elif fmt == "jpg":
            imgs[0].save(buf, "JPEG", quality=q, optimize=True, progressive=True,
                         subsampling=0 if q >= 90 else 2, **extras)
        else:
            imgs[0].save(buf, "PNG", optimize=True,
                         **({"icc_profile": extras["icc_profile"]} if "icc_profile" in extras else {}))
        return buf.getvalue()

    q = int(opt["quality"])
    limit = int(opt["limit_kb"]) * 1024
    data = enc(out, q)
    scale = 1.0
    if limit and len(data) > limit:
        # 1) 先降品質到 60
        while can_lower and len(data) > limit and q > 60:
            q = max(60, q - 5)
            data = enc(out, q)
        # 2) 尺寸不固定的用途：每次縮 10%，最多縮到一半
        if rs.get("resize_mode", "none") in ("none", "width", "height", "fit", "percent"):
            base_imgs = out
            while len(data) > limit and scale > 0.55:
                scale *= 0.9
                out = [im.resize((max(1, round(im.width * scale)), max(1, round(im.height * scale))),
                                 Image.LANCZOS) for im in base_imgs]
                data = enc(out, q)
        # 3) 還是超過就繼續降品質到 40
        while can_lower and len(data) > limit and q > 40:
            q = max(40, q - 5)
            data = enc(out, q)
    out[0].info["shrink"] = scale
    return data, (q if can_lower else None), out[0], up


def slugify(s: str) -> str:
    """網站檔名規則：英文小寫、空白換連字號"""
    s = "-".join(s.lower().split())
    while "--" in s:
        s = s.replace("--", "-")
    return s


def make_targets(src: Path, idx: int, n: int, opt: dict):
    """這張圖要輸出哪些檔案：[(路徑, 尺寸設定, 說明)]"""
    nm = opt["naming"]
    base = clean_name(opt["base"])
    src_stem = src.stem
    if opt.get("slug"):
        base, src_stem = slugify(base), slugify(src_stem)
    rev = f"-{opt['rev']}" if int(opt["rev"]) > 0 else ""
    ext = EXT[opt["fmt"]]
    if opt["out_mode"] == "subfolder":
        folder = src.parent / "converted"
    elif opt["out_mode"] == "custom" and opt["out_dir"]:
        folder = Path(opt["out_dir"])
    else:
        folder = src.parent
    user_rs = {k: opt[k] for k in ("resize_mode", "rw", "rh", "rpct", "upscale")}
    multi = opt.get("multi")

    if nm == "slider":
        stem = base
    elif nm == "serial":
        num = str(int(opt["start"]) + idx).zfill(int(opt["digits"]))
        stem = f"{base}{opt['sep']}{num}" if base else num
    elif nm == "product":
        stem = f"{base}pic" if idx == 0 else f"{base}pic{idx}"
    elif nm == "feature":
        stem = f"{base}pic{int(opt['start']) + idx}"
    elif nm == "sale":
        stem = f"{base}sale{int(opt['start']) + idx}"
    elif nm in ("generic", "line"):
        stem = (base + (f"-{int(opt['start']) + idx}" if n > 1 else "")) if base else src_stem
    else:
        stem = src_stem

    if multi:
        res = []
        for suf, w, h in multi:
            name = f"{stem}{suf}" if nm == "slider" else f"{stem}-{w}x{h}"
            res.append((folder / f"{name}{rev}{ext}",
                        {"resize_mode": "cover", "rw": w, "rh": h, "upscale": True}, f"{w}×{h}"))
        return res
    return [(folder / f"{stem}{rev}{ext}", user_rs, "")]


def process(src: Path, targets, opt: dict, produced: set):
    """轉換一張來源圖。每個輸出 yield（dst, 狀態, 原大小, 新大小, 說明）"""
    old = src.stat().st_size
    frames, durations, loop, extras = load_source(src, opt["keep_exif"])
    src_size = f"{frames[0].width}×{frames[0].height}"
    for dst, rs, _ in targets:
        key = str(dst.resolve()).lower()
        if key == str(src.resolve()).lower():
            yield dst, "略過", old, 0, "輸出檔名與原檔相同，為保留原始檔不覆蓋"
            continue
        if key in produced:
            yield dst, "略過", old, 0, "這次轉換中檔名重複"
            continue
        if dst.exists() and not opt["overwrite"]:
            yield dst, "略過", old, 0, "檔案已存在（可在進階設定勾「覆蓋」）"
            continue
        data, used_q, out0, up = render(frames, durations, loop, extras, rs, opt)
        new = len(data)
        out_size = f"{out0.width}×{out0.height}"
        note = src_size if out_size == src_size else f"{src_size} → {out_size}"
        if up:
            note += "（原圖較小，已放大）"
        if opt["fmt"] == "webp" and WEBP_MAX in out0.size:
            note += "（超過 WebP 上限，已縮小）"
        if used_q is not None and used_q != int(opt["quality"]):
            note += f"（為符合 {opt['limit_kb']} KB，品質降到 {used_q}）"
        if out0.info.get("shrink", 1.0) < 0.999:
            note += f"（為符合 {opt['limit_kb']} KB，尺寸縮到 {out0.width}×{out0.height}）"
        if opt["limit_kb"] and new > int(opt["limit_kb"]) * 1024:
            note += f"（仍超過 {opt['limit_kb']} KB）"
        if opt["skip_larger"] and new >= old and len(targets) == 1 and opt["resize_mode"] == "none":
            yield dst, "略過", old, new, f"轉完比原檔大 {note}"
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_name(dst.name + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, dst)
        produced.add(key)
        yield dst, "完成", old, new, note


def probe(src: Path):
    try:
        with Image.open(src) as im:
            w, h = im.size
            o = (im.getexif() or {}).get(0x0112, 1)
            if o in (5, 6, 7, 8):
                w, h = h, w
            return f"{w}×{h}"
    except Exception:
        return "無法讀取"


# ======================= 介面元件（v1.4.0） =======================
def round_img(w: int, h: int, r: int, fill, outline=None, width: int = 1, ss: int = 3):
    """反鋸齒的圓角矩形圖（Tk 畫布本身沒有反鋸齒）"""
    w, h = max(2, int(w)), max(2, int(h))
    im = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, w * ss - 1, h * ss - 1), radius=max(1, r) * ss, fill=fill,
                        outline=outline, width=width * ss if outline else 0)
    return im.resize((w, h), Image.LANCZOS)


def draw_icon(name: str, px: int, color: str):
    """線條圖示（用 Pillow 畫，Windows／Mac 一致）"""
    ss = 4
    n = px * ss
    im = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    w = max(ss * 2, int(n * 0.09))
    c = color

    def arrow(x, up, top=0.18, bot=0.82, span=0.22):
        y1, y2 = (n * top, n * bot) if up else (n * bot, n * top)
        d.line([(x, y2), (x, y1)], fill=c, width=w)
        dy = n * span * (1 if up else -1)
        d.line([(x - n * span, y1 + dy), (x, y1), (x + n * span, y1 + dy)], fill=c, width=w, joint="curve")

    if name == "up":
        arrow(n / 2, True)
    elif name == "down":
        arrow(n / 2, False)
    elif name == "sort":
        arrow(n * 0.32, True, span=0.15)
        arrow(n * 0.68, False, span=0.15)
    elif name == "remove":
        d.line([(n * 0.25, n * 0.25), (n * 0.75, n * 0.75)], fill=c, width=w)
        d.line([(n * 0.75, n * 0.25), (n * 0.25, n * 0.75)], fill=c, width=w)
    elif name == "clear":
        d.line([(n * 0.18, n * 0.27), (n * 0.82, n * 0.27)], fill=c, width=w)
        d.line([(n * 0.4, n * 0.27), (n * 0.42, n * 0.15), (n * 0.58, n * 0.15), (n * 0.6, n * 0.27)], fill=c, width=w)
        d.line([(n * 0.27, n * 0.33), (n * 0.32, n * 0.86), (n * 0.68, n * 0.86), (n * 0.73, n * 0.33)],
               fill=c, width=w, joint="curve")
        d.line([(n * 0.5, n * 0.42), (n * 0.5, n * 0.75)], fill=c, width=w)
    elif name == "upload":
        arrow(n / 2, True, top=0.14, bot=0.64, span=0.2)
        d.line([(n * 0.16, n * 0.62), (n * 0.16, n * 0.84), (n * 0.84, n * 0.84), (n * 0.84, n * 0.62)],
               fill=c, width=w, joint="curve")
    return im.resize((px, px), Image.LANCZOS)


class Tooltip:
    """滑鼠停在按鈕上顯示說明"""

    def __init__(self, widget, text):
        self.w, self.text, self.tip, self.job = widget, text, None, None
        widget.bind("<Enter>", self._enter, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _enter(self, _):
        self.job = self.w.after(450, self._show)

    def _show(self):
        if self.tip:
            return
        self.tip = t = tk.Toplevel(self.w)
        t.wm_overrideredirect(True)
        tk.Label(t, text=self.text, bg=INK, fg="#FFFFFF", font=(UI_FONT, fs(9)), padx=8, pady=3).pack()
        t.update_idletasks()
        x = self.w.winfo_rootx() + self.w.winfo_width() // 2 - t.winfo_width() // 2
        t.wm_geometry(f"+{x}+{self.w.winfo_rooty() + self.w.winfo_height() + 4}")

    def _hide(self, _=None):
        if self.job:
            self.w.after_cancel(self.job)
            self.job = None
        if self.tip:
            self.tip.destroy()
            self.tip = None


class Pill(tk.Canvas):
    """圓角膠囊標籤（狀態、摘要、節省比例）"""

    def __init__(self, parent, text="", fill=SEG, fg=INK, bg=CARD, font=None, padx=8, pady=3):
        super().__init__(parent, bg=bg, highlightthickness=0, bd=0, width=1, height=1)
        self._font = tkfont.Font(font=font or (UI_FONT, fs(9)))
        self._pad = (padx, pady)
        self._ph = None
        self.set(text, fill, fg)

    def set(self, text=None, fill=None, fg=None):
        if text is not None:
            self.text = text
        if fill is not None:
            self.fill = fill
        if fg is not None:
            self.fg = fg
        self.delete("all")
        if not self.text:
            self.configure(width=1, height=1)
            return
        px, py = self._pad
        w = self._font.measure(self.text) + 2 * px
        h = self._font.metrics("linespace") + 2 * py
        self._ph = ImageTk.PhotoImage(round_img(w, h, h // 2, self.fill))
        self.create_image(0, 0, anchor="nw", image=self._ph)
        self.create_text(w // 2, h // 2, text=self.text, fill=self.fg, font=self._font)
        self.configure(width=w, height=h)


class Segmented(tk.Canvas):
    """分段按鈕（格式、輸出位置、預覽／紀錄切換）"""

    def __init__(self, parent, options, variable, command=None, bg=CARD, height=30, font=None, width=None):
        super().__init__(parent, bg=bg, highlightthickness=0, bd=0, height=height, cursor="hand2",
                         width=width or 120)
        self.options, self.var, self.command = options, variable, command
        self.enabled = True
        self._font = tkfont.Font(font=font or (UI_FONT, fs(9)))
        self._bold = tkfont.Font(font=font or (UI_FONT, fs(9)))
        self._bold.configure(weight="bold")
        self._imgs = []
        self.bind("<Configure>", lambda e: self.redraw())
        self.bind("<Button-1>", self._click)
        variable.trace_add("write", lambda *a: self.redraw())

    def state(self, spec=None):
        if spec:
            self.enabled = "disabled" not in spec
            self.configure(cursor="hand2" if self.enabled else "arrow")
            self.redraw()
        return [] if self.enabled else ["disabled"]

    def _click(self, e):
        if not self.enabled:
            return
        n = len(self.options)
        i = min(n - 1, max(0, int(e.x / max(1, self.winfo_width()) * n)))
        if self.var.get() != self.options[i][0]:
            self.var.set(self.options[i][0])
            if self.command:
                self.command()

    def redraw(self):
        self.delete("all")
        w, h = self.winfo_width(), int(self.cget("height"))
        if w < 20:
            return
        n = len(self.options)
        track = ImageTk.PhotoImage(round_img(w, h, 8, SEG))
        self._imgs = [track]
        self.create_image(0, 0, anchor="nw", image=track)
        sw = (w - 6) / n
        cur = self.var.get()
        for i, (val, label) in enumerate(self.options):
            x0 = 3 + i * sw
            on = val == cur
            if on:
                ph = ImageTk.PhotoImage(round_img(sw, h - 6, 6, "#FFFFFF", outline=LINE))
                self._imgs.append(ph)
                self.create_image(x0, 3, anchor="nw", image=ph)
            fg = (ACCENT if on else MUTED) if self.enabled else "#B8B6B0"
            self.create_text(x0 + sw / 2, h / 2, text=label, fill=fg, font=self._bold if on else self._font)


class RoundBox(tk.Canvas):
    """圓角底框，裡面放一般元件（深色摘要卡用）"""

    def __init__(self, parent, fill, bg, radius=12, pad=(14, 12)):
        super().__init__(parent, bg=bg, highlightthickness=0, bd=0, height=10)
        self.fill, self.radius, self.pad = fill, radius, pad
        self.inner = tk.Frame(self, bg=fill)
        self._win = self.create_window(pad[0], pad[1], window=self.inner, anchor="nw")
        self._ph = None
        self._size = None
        self.bind("<Configure>", self._layout)
        self.inner.bind("<Configure>", self._layout)

    def _layout(self, _=None):
        w = self.winfo_width()
        h = self.inner.winfo_reqheight() + 2 * self.pad[1]
        if int(self.cget("height")) != h:
            self.configure(height=h)
        self.itemconfigure(self._win, width=max(10, w - 2 * self.pad[0]))
        if w > 20 and (w, h) != self._size:
            self._size = (w, h)
            self.delete("bg")
            self._ph = ImageTk.PhotoImage(round_img(w, h, self.radius, self.fill))
            self.create_image(0, 0, anchor="nw", image=self._ph, tags="bg")
            self.tag_lower("bg")


class NumBadge(tk.Canvas):
    """步驟的圓形編號"""

    def __init__(self, parent, n, k, bg=CARD):
        d = int(22 * k)
        super().__init__(parent, bg=bg, highlightthickness=0, bd=0, width=d, height=d)
        self._ph = ImageTk.PhotoImage(round_img(d, d, d // 2, BRAND))
        self.create_image(0, 0, anchor="nw", image=self._ph)
        self.create_text(d / 2, d / 2, text=str(n), fill="#FFFFFF", font=(BRAND_FONT, fs(9), "bold"))


# ======================= 視窗 =======================
class App(RootBase):
    def __init__(self):
        super().__init__()
        self.withdraw()
        self.title(APP_TITLE)
        try:
            self._icon = ImageTk.PhotoImage(Image.open(ASSETS / "logo-512.png").resize((64, 64), Image.LANCZOS))
            self.iconphoto(True, self._icon)
        except Exception:
            pass
        self.k = max(1.0, self.winfo_fpixels("1i") / 96)
        k = self.k
        sw, sh = SIM_SCREEN or (self.winfo_screenwidth(), self.winfo_screenheight())
        W, H = min(int(1320 * k), int(sw * 0.94)), min(int(880 * k), int(sh * 0.88))
        self.geometry(f"{W}x{H}+{(sw - W) // 2}+{max(0, (sh - H) // 2 - 20)}")
        self.minsize(min(int(1100 * k), W), min(int(720 * k), H))
        self._W = W
        self.configure(bg=PAPER)

        self.s = load_settings()
        self.files: list[Path] = []
        self.info: dict[Path, str] = {}
        self.status: dict[Path, tuple] = {}     # 清單「狀態」欄：(文字, 標籤)
        self.thumbs: dict[Path, object] = {}    # 縮圖 PhotoImage
        self.q: queue.Queue = queue.Queue()
        self.stop_flag = threading.Event()
        self.busy = False
        self._pv_token = 0
        self._pv_job = None
        self._pv_imgs = [None, None]
        self._pv_last = None
        self._pv_ratio = None                   # 預覽算出的「輸出／原檔」比例，用來預估總大小
        self._run_t0 = 0.0
        self._out_dirs = []
        self._loading = True
        self.dnd_ok = False

        self._theme()
        self._build()
        self._load_into_ui()
        self._loading = False
        self._on_preset(apply=False)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        if DND_FILES and self.TkdndVersion:
            try:
                self.drop_target_register(DND_FILES)
                self.dnd_bind("<<DropEnter>>", self._drop_enter)
                self.dnd_bind("<<DropLeave>>", self._drop_leave)
                self.dnd_bind("<<Drop>>", self._drop)
                self.dnd_ok = True
            except Exception as e:
                self.dnd_error = repr(e)
        if not self.dnd_ok:  # 不能拖放時，提示改用按鈕
            self.lbl_drop_title.configure(text="按下面的按鈕加入圖片")
        self._refresh_list()
        self.after(100, self._poll)
        self.deiconify()

    # ---------- 外觀 ----------
    def _theme(self):
        self.themed = False
        tcl = ASSETS / "svtheme" / "sv.tcl"
        try:
            if tcl.exists():
                self.tk.call("source", str(tcl))
                ttk.Style(self).theme_use("sun-valley-light")
                self.themed = True
        except tk.TclError:
            self.themed = False
        fams = set(tkfont.families(self))

        def pick(*names):
            return next((n for n in names if n in fams), names[-1])
        # Windows 以字型檔的家族名稱註冊（JetBrains Mono Medium），Mac 以 typographic 家族名稱（JetBrains Mono）
        self.brand_font = pick(BRAND_FONT, "Helvetica Neue" if IS_MAC else "Segoe UI Semibold")
        self.mono_font = pick(MONO_FONT, MONO_FONT + " Medium", "Menlo" if IS_MAC else "Consolas")
        for name in tkfont.names():
            f = tkfont.nametofont(name)
            if name != "TkFixedFont":
                f.configure(family=UI_FONT)
        k = self.k
        st = ttk.Style(self)
        st.configure(".", font=(UI_FONT, fs(10)))
        st.configure("Muted.TLabel", foreground=MUTED)
        st.configure("Danger.TLabel", foreground=DANGER)
        st.configure("Big.Accent.TButton", font=(UI_FONT, fs(11), "bold"), padding=(int(26 * k), int(8 * k)))
        st.configure("Accent.TButton", font=(UI_FONT, fs(10), "bold"))
        st.configure("Icon.Toolbutton", padding=int(5 * k))
        # 白色卡片裡的元件（底色要跟卡片一樣，不然會有一塊色差）
        for base in ("TFrame", "TLabel", "TRadiobutton", "TCheckbutton", "TButton", "Switch.TCheckbutton",
                     "Toolbutton", "Accent.TButton"):
            st.configure(f"C.{base}", background=CARD)
        st.configure("CMuted.TLabel", background=CARD, foreground=MUTED, font=(UI_FONT, fs(9)))
        st.configure("CField.TLabel", background=CARD, foreground=MUTED)
        st.configure("CTitle.TLabel", background=CARD, foreground=INK, font=(UI_FONT, fs(11), "bold"))
        st.configure("CValue.TLabel", background=CARD, foreground=MUTED, font=(UI_FONT, fs(9)))
        st.configure("CHint.TLabel", background=CARD, foreground=ACCENT, font=(UI_FONT, fs(9)))
        st.configure("CDanger.TLabel", background=CARD, foreground=DANGER, font=(UI_FONT, fs(9)))
        st.configure("CBig.TButton", background=CARD, font=(UI_FONT, fs(11)), padding=(int(22 * k), int(8 * k)))
        st.configure("CBig.Accent.TButton", background=CARD, font=(UI_FONT, fs(11), "bold"),
                     padding=(int(26 * k), int(8 * k)))
        st.configure("Treeview", rowheight=int(48 * k))
        st.configure("Treeview.Heading", font=(UI_FONT, fs(9)), foreground=MUTED)
        st.map("Treeview", background=[("selected", TINT)], foreground=[("selected", INK)])
        self.bg = PAPER
        self.icons = {n: ImageTk.PhotoImage(draw_icon(n, int(16 * k), MUTED))
                      for n in ("up", "down", "sort", "remove", "clear")}

    def _step(self, parent, n, title, collapsible=False):
        """右側步驟卡片：圓形編號＋標題；可收合的卡片右邊顯示目前設定的摘要"""
        k = self.k
        card = ttk.Frame(parent, style="Card.TFrame", padding=(int(14 * k), int(10 * k)))
        card.pack(fill="x", pady=(0, int(10 * k)))
        hd = ttk.Frame(card, style="C.TFrame")
        hd.pack(fill="x")
        NumBadge(hd, n, k).pack(side="left")
        ttk.Label(hd, text=title, style="CTitle.TLabel").pack(side="left", padx=(int(8 * k), 0))
        body = ttk.Frame(card, style="C.TFrame")
        value = None
        if collapsible:
            arrow = ttk.Label(hd, text="▾", style="CValue.TLabel")
            arrow.pack(side="right")
            value = ttk.Label(hd, style="CValue.TLabel")
            value.pack(side="right", padx=(0, int(6 * k)))
            body._open = False

            def toggle(_=None):
                body._open = not body._open
                if body._open:
                    body.pack(fill="x", pady=(int(10 * k), 0))
                    arrow.configure(text="▴")
                else:
                    body.pack_forget()
                    arrow.configure(text="▾")
            for w_ in (hd, value, arrow):
                w_.bind("<Button-1>", toggle)
                w_.configure(cursor="hand2")
            body.toggle = toggle
        else:
            body.pack(fill="x", pady=(int(10 * k), 0))
        return body, value

    def _field(self, parent, text, pady=(0, 8)):
        """一列：左邊欄位名稱，右邊放元件"""
        r = ttk.Frame(parent, style="C.TFrame")
        r.pack(fill="x", pady=pady)
        lbl = ttk.Label(r, text=text, style="CField.TLabel", width=8 if not IS_MAC else 9)
        lbl.pack(side="left")
        return r, lbl

    def _build(self):
        k = self.k
        # 頁首
        head = tk.Frame(self, bg=DARK, padx=int(20 * k), pady=int(10 * k))
        head.pack(fill="x")
        try:
            lg = Image.open(ASSETS / "logo-512.png").resize((int(38 * k), int(38 * k)), Image.LANCZOS)
            self._logo = ImageTk.PhotoImage(lg)
            tk.Label(head, image=self._logo, bg=DARK).pack(side="left")
        except Exception:
            self._logo = None
        wm = tk.Frame(head, bg=DARK)
        wm.pack(side="left", padx=(int(10 * k), 0))
        brand = tk.Label(wm, text="Moksa Web", font=(self.brand_font, fs(16), "bold"), fg=DARK_INK, bg=DARK,
                         cursor="hand2")
        brand.pack(anchor="w")
        tk.Label(wm, text="S T U D I O  ·  台 中", font=(self.mono_font, fs(7)), fg=DARK_MUTED, bg=DARK).pack(anchor="w")
        brand.bind("<Button-1>", lambda e: webbrowser.open(APP_URL))
        tk.Frame(head, bg="#3a3a40", width=1, height=int(32 * k)).pack(side="left", padx=int(18 * k))
        tt = tk.Frame(head, bg=DARK)
        tt.pack(side="left")
        tk.Label(tt, text="WebP 圖片轉換工具", font=(UI_FONT, fs(13), "bold"), fg=DARK_INK, bg=DARK).pack(anchor="w")
        tk.Label(tt, text="批次轉檔 · 依用途自動套用尺寸與命名 · 即時預覽", font=(UI_FONT, fs(9)),
                 fg=DARK_MUTED, bg=DARK).pack(anchor="w")
        rt = tk.Frame(head, bg=DARK)
        rt.pack(side="right")
        about = tk.Label(rt, text="關於", font=(UI_FONT, fs(9)), fg=BRAND, bg=DARK, cursor="hand2")
        about.pack(side="right")
        about.bind("<Button-1>", lambda e: self.show_about())
        tk.Label(rt, text=f"v{APP_VERSION}   ", font=(self.mono_font, fs(8)), fg=DARK_MUTED, bg=DARK).pack(side="right")
        tk.Frame(self, bg=BRAND, height=max(2, int(3 * k))).pack(fill="x")

        # 底部列：閒置時顯示摘要，轉換中才出現進度條與「停止」
        foot = tk.Frame(self, bg=PAPER2, padx=int(20 * k), pady=int(10 * k))
        foot.pack(side="bottom", fill="x")
        tk.Frame(self, bg=LINE, height=1).pack(side="bottom", fill="x")
        self.btn_go = ttk.Button(foot, text="開始轉換", style="Big.Accent.TButton", command=self.start)
        self.btn_go.pack(side="right")
        self.btn_stop = ttk.Button(foot, text="停止", command=self.stop_flag.set)
        self.btn_open = ttk.Button(foot, text="開啟輸出資料夾", command=self.open_output)
        self.lbl_status = tk.Label(foot, bg=PAPER2, fg=MUTED, font=(UI_FONT, fs(10)), anchor="w")
        self.lbl_status.pack(side="left", fill="x", expand=True)
        self.prog = tk.Frame(foot, bg=PAPER2)
        self.lbl_prog = tk.Label(self.prog, bg=PAPER2, fg=INK, font=(UI_FONT, fs(10), "bold"))
        self.lbl_prog.pack(side="left")
        self.pb = ttk.Progressbar(self.prog, mode="determinate")
        self.pb.pack(side="left", fill="x", expand=True, padx=(int(12 * k), int(12 * k)))

        body = ttk.Frame(self, padding=(int(20 * k), int(14 * k), int(20 * k), int(10 * k)))
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)

        # ===== 右側設定 =====
        extra = 30 if IS_MAC else 0  # 蘋方字比較寬，Mac 右側欄加寬，「用途」名稱才放得下
        self.right_w = int((400 + extra) * k) if self._W >= int(1200 * k) else int((370 + extra) * k)
        right = ttk.Frame(body, width=self.right_w)
        right.grid(row=0, column=1, sticky="ns", padx=(int(16 * k), 0))
        right.grid_propagate(False)
        right.pack_propagate(False)
        self._build_settings(self._scroll_panel(right))

        # ===== 左側：空白狀態／清單＋預覽 =====
        self.left = left = ttk.Frame(body)
        left.grid(row=0, column=0, sticky="nsew")
        self._build_empty(left)
        self._build_loaded(left)
        self._paint_card_labels(self)

    def _paint_card_labels(self, w):
        """卡片裡的 ttk.Label（樣式 C 開頭）直接指定白底：sun-valley 主題的標籤不會套用樣式的底色"""
        for c in w.winfo_children():
            if c.winfo_class() == "TLabel" and str(c.cget("style")).startswith("C"):
                c.configure(background=CARD)
            self._paint_card_labels(c)

    def _build_empty(self, left):
        k = self.k
        c = self.view_empty = tk.Canvas(left, bg=PAPER, highlightthickness=0)
        box = tk.Frame(c, bg=CARD)
        d = int(84 * k)
        ic = Image.new("RGBA", (d, d), (0, 0, 0, 0))
        ic.alpha_composite(round_img(d, d, d // 2, TINT))
        up = draw_icon("upload", int(40 * k), BRAND)
        ic.alpha_composite(up, ((d - up.width) // 2, (d - up.height) // 2))
        self._ic_upload = ImageTk.PhotoImage(ic)
        tk.Label(box, image=self._ic_upload, bg=CARD).pack()
        self.lbl_drop_title = tk.Label(box, text="把圖片或資料夾拖到這裡", bg=CARD, fg=INK,
                                       font=(UI_FONT, fs(15), "bold"))
        self.lbl_drop_title.pack(pady=(int(14 * k), int(4 * k)))
        self.lbl_drop_sub = tk.Label(box, text="支援 JPG、PNG、GIF、BMP、TIFF、WebP\n一次可以放很多張", bg=CARD,
                                     fg=MUTED, font=(UI_FONT, fs(10)), justify="center")
        self.lbl_drop_sub.pack()
        row = tk.Frame(box, bg=CARD)
        row.pack(pady=(int(18 * k), 0))
        self.btn_empty_add = ttk.Button(row, text="＋ 加入檔案", style="CBig.Accent.TButton", command=self.add_files)
        self.btn_empty_add.pack(side="left")
        ttk.Button(row, text="選擇資料夾", style="CBig.TButton", command=self.add_folder).pack(side="left",
                                                                                          padx=(int(10 * k), 0))
        tips = self.empty_tips = tk.Frame(box, bg=CARD)
        tips.pack(pady=(int(28 * k), 0))
        for i, (t, d_) in enumerate((("① 加入圖片", "拖進來或按上面按鈕"), ("② 選用途", "右邊選類別與用途"),
                                     ("③ 開始轉換", "按右下角按鈕"))):
            f = tk.Frame(tips, bg=CARD)
            f.pack(side="left", padx=int(16 * k))
            tk.Label(f, text=t, bg=CARD, fg=INK, font=(UI_FONT, fs(10), "bold")).pack(anchor="w")
            tk.Label(f, text=d_, bg=CARD, fg=MUTED, font=(UI_FONT, fs(9))).pack(anchor="w")
        self._empty_win = c.create_window(0, 0, window=box)
        self._empty_hot = False
        self._empty_size = None
        c.bind("<Configure>", lambda e: self._draw_empty())

    def _draw_empty(self, force=False):
        c = self.view_empty
        w, h = c.winfo_width(), c.winfo_height()
        if w < 50 or h < 50:
            return
        key = (w, h, self._empty_hot)
        if key == self._empty_size and not force:
            return
        self._empty_size = key
        k = self.k
        c.delete("bg")
        hot = self._empty_hot
        r = int(16 * k)
        self._empty_ph = ImageTk.PhotoImage(round_img(w - 2, h - 2, r, CARD, ss=2))
        c.create_image(1, 1, anchor="nw", image=self._empty_ph, tags="bg")
        col, wd = (BRAND, 3) if hot else ("#D2CCC0", 2)
        dash = () if hot else (6, 5)
        x1, y1, x2, y2 = 2, 2, w - 3, h - 3
        for a in ((x1 + r, y1, x2 - r, y1), (x1 + r, y2, x2 - r, y2), (x1, y1 + r, x1, y2 - r), (x2, y1 + r, x2, y2 - r)):
            c.create_line(*a, fill=col, width=wd, dash=dash, tags="bg")
        for (ax, ay, st_) in ((x1, y1, 90), (x2 - 2 * r, y1, 0), (x1, y2 - 2 * r, 180), (x2 - 2 * r, y2 - 2 * r, 270)):
            c.create_arc(ax, ay, ax + 2 * r, ay + 2 * r, start=st_, extent=90, style="arc", outline=col,
                         width=wd, dash=dash, tags="bg")
        c.tag_lower("bg")
        c.coords(self._empty_win, w // 2, h // 2)
        # 窄視窗：說明文字換行、三步驟提示收起來
        narrow = w < int(620 * k)
        if narrow and self.empty_tips.winfo_manager():
            self.empty_tips.pack_forget()
        elif not narrow and not self.empty_tips.winfo_manager():
            self.empty_tips.pack(pady=(int(28 * k), 0))

    def _build_loaded(self, left):
        k = self.k
        f = self.view_list = ttk.Frame(left)
        f.columnconfigure(0, weight=1)
        f.rowconfigure(1, weight=2)
        f.rowconfigure(2, weight=3)

        bar = self.bar = ttk.Frame(f)
        bar.grid(row=0, column=0, sticky="ew", pady=(0, int(10 * k)))
        self.bar_items = [
            ttk.Button(bar, text="＋ 加入檔案", style="Accent.TButton", command=self.add_files),
            ttk.Button(bar, text="資料夾", command=self.add_folder),
        ]
        self.bar_items[0].pack(side="left")
        self.bar_items[1].pack(side="left", padx=(int(8 * k), 0))
        tools = ttk.Frame(bar, style="Card.TFrame", padding=int(2 * k))
        tools.pack(side="right")
        for name, tip, cmd in (("up", "上移", lambda: self.move(-1)), ("down", "下移", lambda: self.move(1)),
                               ("sort", "依檔名排序", self.sort_files), ("remove", "移除選取的圖片", self.remove_selected),
                               ("clear", "清空清單", self.clear_files)):
            b = ttk.Button(tools, image=self.icons[name], style="C.Toolbutton", command=cmd)
            b.pack(side="left")
            Tooltip(b, tip)
            self.bar_items.append(b)
        self.lbl_count = ttk.Label(bar, style="Muted.TLabel")
        self.lbl_count.pack(side="right", padx=(0, int(10 * k)))

        tf = self.tf = ttk.Frame(f)
        tf.grid(row=1, column=0, sticky="nsew")
        tf.rowconfigure(0, weight=1)
        tf.columnconfigure(0, weight=1)
        cols = ("name", "dim", "size", "out", "status")
        self.tree = ttk.Treeview(tf, columns=cols, show="tree headings", selectmode="extended", height=3)
        self.tree.heading("#0", text="")
        for c, t, anc in (("name", "原始檔名", "w"), ("dim", "尺寸", "center"), ("size", "大小", "center"),
                          ("out", "輸出檔名", "w"), ("status", "狀態", "w")):
            self.tree.heading(c, text=t, anchor=anc)
            self.tree.column(c, anchor=anc, stretch=c in ("name", "out"))
        self.thumb_col = int((86 if IS_MAC else 64) * k)  # Mac 的清單在圖片前多縮排約 20px
        self.tree.column("#0", width=self.thumb_col, stretch=False, anchor="center")
        self.tree.tag_configure("warn", foreground="#A15C07")
        self.tree.tag_configure("err", foreground=DANGER)
        self.tree.tag_configure("run", foreground=ACCENT)
        ysb = ttk.Scrollbar(tf, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=ysb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        ysb.grid(row=0, column=1, sticky="ns")
        self.tree.bind("<Configure>", lambda e: self._fit_columns(e.width), add="+")
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._schedule_preview())
        self.tree.bind("<Delete>", lambda e: self.remove_selected())
        self.tree.bind("<BackSpace>", lambda e: self.remove_selected())
        self.menu = tk.Menu(self, tearoff=0)
        for t, cmd in (("上移", lambda: self.move(-1)), ("下移", lambda: self.move(1)), ("依檔名排序", self.sort_files),
                       (None, None), ("移除選取的圖片", self.remove_selected), ("清空清單", self.clear_files)):
            if t:
                self.menu.add_command(label=t, command=cmd)
            else:
                self.menu.add_separator()
        for seq in (("<Button-2>", "<Control-Button-1>") if IS_MAC else ("<Button-3>",)):
            self.tree.bind(seq, self._context_menu)
        self.drop_overlay = tk.Label(tf, text="放開滑鼠，加入圖片", bg=TINT, fg=ACCENT,
                                     font=(UI_FONT, fs(15), "bold"), highlightthickness=3,
                                     highlightbackground=BRAND, highlightcolor=BRAND)

        # 預覽卡片
        pv = ttk.Frame(f, style="Card.TFrame", padding=(int(14 * k), int(10 * k)))
        pv.grid(row=2, column=0, sticky="nsew", pady=(int(12 * k), 0))
        pv.columnconfigure(0, weight=1)
        pv.rowconfigure(1, weight=1)
        hd = ttk.Frame(pv, style="C.TFrame")
        hd.grid(row=0, column=0, sticky="ew", pady=(0, int(8 * k)))
        ttk.Label(hd, text="預覽", style="CTitle.TLabel").pack(side="left")
        self.v_tab = tk.StringVar(value="pv")
        Segmented(hd, [("pv", "並排預覽"), ("log", "轉換紀錄")], self.v_tab, command=self._switch_tab,
                  height=int(28 * k), width=int(180 * k)).pack(side="left", padx=(int(12 * k), 0))
        self.v_safe = tk.BooleanVar()
        self.chk_safe = ttk.Checkbutton(hd, text="顯示安全區", variable=self.v_safe,
                                        style="C.Switch.TCheckbutton" if self.themed else "C.TCheckbutton",
                                        command=self._redraw_preview)
        self.chk_safe.pack(side="right")

        self.pv_area = ttk.Frame(pv, style="C.TFrame")
        self.pv_area.grid(row=1, column=0, sticky="nsew")
        self.pv_area.columnconfigure(0, weight=1, uniform="pv")
        self.pv_area.columnconfigure(1, weight=1, uniform="pv")
        self.pv_area.rowconfigure(0, weight=1)
        self.cv = []
        for i in range(2):
            c = tk.Canvas(self.pv_area, bg=PANE, highlightthickness=0, height=int(120 * k))
            c.grid(row=0, column=i, sticky="nsew", padx=(0, int(6 * k)) if i == 0 else (int(6 * k), 0))
            c.bind("<Configure>", lambda e: self._redraw_preview())
            c.bind("<Button-1>", lambda e, i=i: self._zoom(i))
            c.configure(cursor="hand2")
            self.cv.append(c)
        bd = ttk.Frame(self.pv_area, style="C.TFrame")
        bd.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(int(8 * k), 0))
        self.lbl_size = tk.Label(bd, bg=CARD, fg=INK, font=(self.mono_font, fs(11), "bold"))
        self.lbl_size.pack(side="left")
        self.pill_save = Pill(bd, font=(self.mono_font, fs(9), "bold"))
        self.pill_save.pack(side="left", padx=(int(10 * k), int(10 * k)))
        self.lbl_info_r = ttk.Label(bd, style="CMuted.TLabel")
        self.lbl_info_r.pack(side="left", fill="x", expand=True)
        self.lbl_notes = ttk.Label(self.pv_area, style="CHint.TLabel", wraplength=int(700 * k), justify="left")
        self.lbl_notes.grid(row=2, column=0, columnspan=2, sticky="w")

        self.log_area = ttk.Frame(pv, style="C.TFrame")
        self.log_area.rowconfigure(0, weight=1)
        self.log_area.columnconfigure(0, weight=1)
        self.log = tk.Text(self.log_area, height=6, state="disabled", font=(self.mono_font, fs(9)), relief="flat",
                           wrap="none", bg=CARD, fg=INK, padx=4, pady=4)
        lsb = ttk.Scrollbar(self.log_area, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=lsb.set)
        self.log.grid(row=0, column=0, sticky="nsew")
        lsb.grid(row=0, column=1, sticky="ns")
        self.log.tag_configure("ok", foreground=OK)
        self.log.tag_configure("warn", foreground="#A15C07")
        self.log.tag_configure("err", foreground=DANGER)
        self.log.tag_configure("head", foreground=ACCENT)

    def _switch_tab(self):
        if self.v_tab.get() == "log":
            self.pv_area.grid_remove()
            self.log_area.grid(row=1, column=0, sticky="nsew")
        else:
            self.log_area.grid_remove()
            self.pv_area.grid()

    def _context_menu(self, e):
        row = self.tree.identify_row(e.y)
        if row and row not in self.tree.selection():
            self.tree.selection_set(row)
        try:
            self.menu.tk_popup(e.x_root, e.y_root)
        finally:
            self.menu.grab_release()

    def _scroll_panel(self, outer):
        """可捲動的容器：內容比視窗高時出現捲軸（小螢幕仍看得到每個步驟）"""
        cv = tk.Canvas(outer, highlightthickness=0, bd=0, bg=PAPER)
        sb = ttk.Scrollbar(outer, orient="vertical", command=cv.yview)
        inner = ttk.Frame(cv, padding=(0, 0, int(8 * self.k), 0))
        win = cv.create_window(0, 0, window=inner, anchor="nw")
        cv.configure(yscrollcommand=sb.set)
        cv.pack(side="left", fill="both", expand=True)
        self.set_cv, self.set_sb = cv, sb

        def sync(_=None):
            cv.itemconfigure(win, width=cv.winfo_width())
            need = inner.winfo_reqheight() > cv.winfo_height() + 1
            cv.configure(scrollregion=(0, 0, cv.winfo_width(), max(inner.winfo_reqheight(), cv.winfo_height())))
            if need and not sb.winfo_ismapped():
                sb.pack(side="right", fill="y", before=cv)
            elif not need and sb.winfo_ismapped():
                sb.pack_forget()
                cv.yview_moveto(0)
        inner.bind("<Configure>", sync)
        cv.bind("<Configure>", sync)

        def on_wheel(e):
            # 滑鼠在設定欄上滾動 → 捲動設定欄
            w = self.winfo_containing(e.x_root, e.y_root)
            if w is None or not str(w).startswith(str(outer)) or not sb.winfo_ismapped():
                return None
            step = -e.delta if IS_MAC else -round(e.delta / 120) or (-1 if e.delta > 0 else 1)
            cv.yview_scroll(step, "units")
            return "break"
        self.bind_all("<MouseWheel>", on_wheel, add="+")
        # 數字欄與下拉選單預設會被滾輪改值，捲動設定欄時容易誤改 → 改成捲動設定欄
        for cls in ("TSpinbox", "TCombobox"):
            self.bind_class(cls, "<MouseWheel>", lambda e: (on_wheel(e), "break")[1])
        return inner

    def _fit_columns(self, width):
        """清單欄寬跟著視窗：固定欄不動，剩下的寬度 4:6 分給原始檔名與輸出檔名"""
        k = self.k
        fixed = {"#0": self.thumb_col, "dim": int(96 * k), "size": int(76 * k), "status": int(104 * k)}
        rest = max(int(200 * k), width - sum(fixed.values()) - 4)
        widths = dict(fixed, name=int(rest * 0.42), out=rest - int(rest * 0.42))
        for c, w in widths.items():
            self.tree.column(c, width=w, minwidth=int(30 * k))

    def _build_settings(self, right):
        k = self.k
        # 輸出摘要（深色卡）
        sm = RoundBox(right, fill=DARK, bg=PAPER, radius=int(12 * k), pad=(int(14 * k), int(12 * k)))
        sm.pack(fill="x", pady=(0, int(10 * k)))
        tk.Label(sm.inner, text="輸出摘要", bg=DARK, fg=DARK_MUTED, font=(UI_FONT, fs(8))).pack(anchor="w")
        self.sum_chips = tk.Frame(sm.inner, bg=DARK)
        self.sum_chips.pack(fill="x", pady=(int(6 * k), int(6 * k)))
        self.chips = [Pill(self.sum_chips, bg=DARK, fill="#2A2A30", fg=DARK_INK,
                           font=(self.mono_font, fs(8)), padx=int(7 * k), pady=int(2 * k)) for _ in range(4)]
        self.lbl_sum_name = tk.Label(sm.inner, bg=DARK, fg="#FFB59F", font=(self.mono_font, fs(9)), anchor="w",
                                     justify="left", wraplength=self.right_w - int(60 * k))
        self.lbl_sum_name.pack(fill="x")

        # ① 用途與檔名
        c, _ = self._step(right, 1, "用途與檔名")
        self.v_cat = tk.StringVar()
        self.v_preset = tk.StringVar()
        r, _ = self._field(c, "類別")
        self.cb_cat = ttk.Combobox(r, values=CATEGORIES, textvariable=self.v_cat, state="readonly",
                                   height=len(CATEGORIES))
        self.cb_cat.pack(side="left", fill="x", expand=True)
        self.cb_cat.bind("<<ComboboxSelected>>", lambda e: self._on_cat())
        r, _ = self._field(c, "用途", pady=(0, 4))
        self.cb_preset = ttk.Combobox(r, textvariable=self.v_preset, state="readonly", height=18)
        self.cb_preset.pack(side="left", fill="x", expand=True)
        self.cb_preset.bind("<<ComboboxSelected>>", lambda e: self._on_preset(apply=True))
        self.lbl_hint = ttk.Label(c, style="CMuted.TLabel", wraplength=self.right_w - int(70 * k), justify="left")
        self.lbl_hint.pack(fill="x", pady=(0, int(8 * k)))
        r, self.lbl_base = self._field(c, "SKU")
        self.v_base = tk.StringVar()
        self.w_base = ttk.Entry(r, textvariable=self.v_base)
        self.w_base.pack(side="left", fill="x", expand=True)
        r2 = self.r2 = ttk.Frame(c, style="C.TFrame")
        r2.pack(fill="x", pady=(0, 8))
        self.v_start, self.v_digits, self.v_rev = tk.IntVar(), tk.IntVar(), tk.IntVar()
        self.v_sep = tk.StringVar()
        self.w_start_l = ttk.Label(r2, text="起始號", style="CField.TLabel")
        self.w_start = ttk.Entry(r2, width=6, textvariable=self.v_start, justify="center")
        self.w_dig_l = ttk.Label(r2, text="位數", style="CField.TLabel")
        self.w_dig = ttk.Entry(r2, width=3, textvariable=self.v_digits, justify="center")
        self.w_sep_l = ttk.Label(r2, text="符號", style="CField.TLabel")
        self.w_sep = ttk.Combobox(r2, values=["-", "_", "（無）"], textvariable=self.v_sep, width=4, state="readonly")
        r3 = self.r3 = ttk.Frame(c, style="C.TFrame")
        r3.pack(fill="x")
        ttk.Label(r3, text="更換版本", style="CField.TLabel", width=8 if not IS_MAC else 9).pack(side="left")
        self.w_rev = ttk.Entry(r3, width=4, textvariable=self.v_rev, justify="center")
        self.w_rev.pack(side="left")
        ttk.Label(r3, text="0＝新圖；填 1 → 檔名加 -1", style="CMuted.TLabel").pack(side="left", padx=(int(8 * k), 0))

        # ② 格式與品質
        c, _ = self._step(right, 2, "格式與品質")
        self.v_fmt = tk.StringVar()
        r, _ = self._field(c, "格式")
        self.w_fmt = Segmented(r, [("webp", "WebP"), ("jpg", "JPG"), ("png", "PNG")], self.v_fmt,
                               command=self._on_change, height=int(30 * k))
        self.w_fmt.pack(side="left", fill="x", expand=True)
        self.v_quality, self.v_method, self.v_limit = tk.IntVar(), tk.IntVar(), tk.IntVar()
        self.lbl_q, self.w_q = self._scale_row(c, "品質", self.v_quality, 0, 100, pady=(0, 0))

        # ③ 尺寸（平常收起來，顯示摘要）
        c, self.lbl_rs_value = self._step(right, 3, "尺寸", collapsible=True)
        self.body_rs = c
        self.v_rs = tk.StringVar()
        self.w_rs = ttk.Combobox(c, values=[t for _, t in RESIZE_MODES], textvariable=self.v_rs, state="readonly")
        self.w_rs.pack(fill="x")
        self.w_rs.bind("<<ComboboxSelected>>", lambda e: self._on_change())
        r = self.rs_row = ttk.Frame(c, style="C.TFrame")
        r.pack(fill="x", pady=(6, 0))
        self.v_rw, self.v_rh, self.v_rpct = tk.IntVar(), tk.IntVar(), tk.IntVar()
        self.v_up = tk.BooleanVar()
        self.w_rw_l = ttk.Label(r, text="寬", style="CField.TLabel")
        self.w_rw = ttk.Entry(r, width=7, textvariable=self.v_rw, justify="center")
        self.w_rh_l = ttk.Label(r, text="高", style="CField.TLabel")
        self.w_rh = ttk.Entry(r, width=7, textvariable=self.v_rh, justify="center")
        self.w_pct_l = ttk.Label(r, text="%", style="CField.TLabel")
        self.w_pct = ttk.Entry(r, width=5, textvariable=self.v_rpct, justify="center")
        self.w_up = ttk.Checkbutton(c, text="允許放大小圖（會變糊）", variable=self.v_up, style="C.TCheckbutton",
                                    command=self._on_change)
        self.w_up.pack(anchor="w", pady=(6, 0))
        self.lbl_multi = ttk.Label(c, style="CHint.TLabel", wraplength=self.right_w - int(60 * k), justify="left")
        self.lbl_multi.pack(fill="x")

        # ④ 輸出位置（平常收起來，顯示摘要）
        c, self.lbl_out_value = self._step(right, 4, "輸出位置", collapsible=True)
        self.body_out = c
        self.v_out_mode = tk.StringVar()
        Segmented(c, [("subfolder", "converted 資料夾"), ("same", "原資料夾"), ("custom", "自訂")], self.v_out_mode,
                  command=self._on_change, height=int(30 * k)).pack(fill="x")
        r = ttk.Frame(c, style="C.TFrame")
        r.pack(fill="x", pady=(int(8 * k), 0))
        self.v_out_dir = tk.StringVar()
        ttk.Entry(r, textvariable=self.v_out_dir).pack(side="left", fill="x", expand=True)
        self.btn_out_browse = ttk.Button(r, text="瀏覽…", style="C.TButton", command=self.pick_out)
        self.btn_out_browse.pack(side="left", padx=(6, 0))
        ttk.Label(c, text="選「自訂」再按「瀏覽…」選資料夾；converted 資料夾會建在原圖旁邊。",
                  style="CMuted.TLabel", wraplength=self.right_w - int(60 * k), justify="left").pack(fill="x", pady=(6, 0))

        # 進階
        self.adv_open = tk.BooleanVar(value=False)
        ar = ttk.Frame(right)
        ar.pack(fill="x")
        self.btn_adv = ttk.Button(ar, text="▸ 進階設定", style="Toolbutton" if self.themed else "TButton",
                                  command=self._toggle_adv)
        self.btn_adv.pack(side="left")
        ttk.Label(ar, text="壓縮強度、檔案上限、無損…", style="Muted.TLabel",
                  font=(UI_FONT, fs(9))).pack(side="left", padx=(int(4 * k), 0))
        self.adv = ttk.Frame(right, style="Card.TFrame", padding=(int(14 * k), int(10 * k)))
        r, _ = self._field(self.adv, "壓縮方式")
        self.v_mode = tk.StringVar()
        self.w_mode = Segmented(r, [("lossy", "有損（建議）"), ("lossless", "無損")], self.v_mode,
                                command=self._on_change, height=int(28 * k))
        self.w_mode.pack(side="left", fill="x", expand=True)
        self.w_lossy = self.w_lossless = self.w_mode
        self.lbl_m, self.w_m = self._scale_row(self.adv, "壓縮強度", self.v_method, 0, 6)
        r, _ = self._field(self.adv, "檔案上限", pady=(0, 2))
        ttk.Entry(r, width=8, textvariable=self.v_limit, justify="center").pack(side="left")
        ttk.Label(r, text=" KB（0＝不限）", style="CMuted.TLabel").pack(side="left")
        ttk.Label(self.adv, text="超過上限會自動降品質；尺寸不固定的用途也會縮小尺寸。", style="CMuted.TLabel",
                  wraplength=self.right_w - int(60 * k), justify="left").pack(fill="x", pady=(0, 8))
        self.v_alpha = tk.IntVar()
        self._scale_row(self.adv, "透明度品質", self.v_alpha, 0, 100)
        self.v_exif, self.v_skip, self.v_over, self.v_rec = (tk.BooleanVar() for _ in range(4))
        for v, t in ((self.v_exif, "保留 EXIF（拍攝資訊）"), (self.v_skip, "轉完比原檔大就不保留"),
                     (self.v_over, "覆蓋已存在的輸出檔"), (self.v_rec, "加入資料夾時包含子資料夾")):
            ttk.Checkbutton(self.adv, text=t, variable=v, style="C.TCheckbutton",
                            command=self._on_change).pack(anchor="w", pady=1)

    def _scale_row(self, parent, text, var, lo, hi, pady=(0, 8)):
        r, lbl = self._field(parent, text, pady=pady)
        ent = ttk.Entry(r, width=4, textvariable=var, justify="center")
        ent.pack(side="right")
        sc = ttk.Scale(r, from_=lo, to=hi, variable=var, command=lambda e: var.set(round(float(e))))
        sc.pack(side="left", fill="x", expand=True, padx=(0, int(10 * self.k)))
        return lbl, (sc, ent)

    def _toggle_adv(self):
        if self.adv_open.get():
            self.adv.pack_forget()
            self.btn_adv.configure(text="▸ 進階設定")
        else:
            self.adv.pack(fill="x", pady=(int(4 * self.k), int(10 * self.k)))
            self.btn_adv.configure(text="▾ 進階設定")
        self.adv_open.set(not self.adv_open.get())

    # ---------- 設定 <-> 介面 ----------
    def _load_into_ui(self):
        s = self.s
        p0 = PRESET_BY_KEY.get(s["preset"], PRESET_BY_KEY["custom_keep"])
        self.v_cat.set(p0["cat"])
        self._fill_presets(p0["cat"])
        self.v_preset.set(p0["label"])
        self.v_base.set(s["base"]); self.v_start.set(s["start"]); self.v_digits.set(s["digits"])
        self.v_sep.set(s["sep"] or "（無）"); self.v_rev.set(s["rev"])
        self.v_fmt.set(s["fmt"]); self.v_mode.set(s["mode"])
        self.v_quality.set(s["quality"]); self.v_method.set(s["method"]); self.v_limit.set(s["limit_kb"])
        self.v_rs.set(RS_LABEL.get(s["resize_mode"], RS_LABEL["none"]))
        self.v_rw.set(s["rw"]); self.v_rh.set(s["rh"]); self.v_rpct.set(s["rpct"]); self.v_up.set(s["upscale"])
        self.v_out_mode.set(s["out_mode"]); self.v_out_dir.set(s["out_dir"])
        self.v_alpha.set(s["alpha_quality"]); self.v_exif.set(s["keep_exif"]); self.v_skip.set(s["skip_larger"])
        self.v_over.set(s["overwrite"]); self.v_rec.set(s["recursive"]); self.v_safe.set(s["show_safe"])
        for v in (self.v_base, self.v_start, self.v_digits, self.v_sep, self.v_rev, self.v_quality,
                  self.v_method, self.v_limit, self.v_rw, self.v_rh, self.v_rpct, self.v_out_dir, self.v_alpha):
            v.trace_add("write", lambda *a: self._on_change())

    @staticmethod
    def _int(var, lo, hi, dflt):
        try:
            return max(lo, min(hi, int(var.get())))
        except (tk.TclError, ValueError):
            return dflt

    def _cat_presets(self, cat):
        return [p for p in PRESETS if p["cat"] == cat]

    def _fill_presets(self, cat):
        self.cb_preset.configure(values=[p["label"] for p in self._cat_presets(cat)])

    def _on_cat(self):
        cat = self.v_cat.get()
        self._fill_presets(cat)
        ps = self._cat_presets(cat)
        if ps:
            self.v_preset.set(ps[0]["label"])
            self._on_preset(apply=True)

    def _preset(self):
        cat = self.v_cat.get()
        for p in PRESETS:
            if p["cat"] == cat and p["label"] == self.v_preset.get():
                return p
        return PRESET_BY_KEY["custom_keep"]

    def _collect(self, save=True) -> dict:
        p = self._preset()
        sep = self.v_sep.get()
        s = {
            "preset": p["key"], "naming": p["naming"], "multi": p.get("multi"), "slug": bool(p.get("slug")),
            "fmt": self.v_fmt.get() or "webp", "mode": self.v_mode.get() or "lossy",
            "quality": self._int(self.v_quality, 0, 100, 82), "method": self._int(self.v_method, 0, 6, 6),
            "alpha_quality": self._int(self.v_alpha, 0, 100, 100), "limit_kb": self._int(self.v_limit, 0, 10 ** 6, 0),
            "resize_mode": RS_KEY.get(self.v_rs.get(), "none"),
            "rw": self._int(self.v_rw, 1, 20000, 2000), "rh": self._int(self.v_rh, 1, 20000, 2000),
            "rpct": self._int(self.v_rpct, 1, 400, 50), "upscale": self.v_up.get(),
            "base": self.v_base.get().strip(), "start": self._int(self.v_start, 0, 99999, 1),
            "digits": self._int(self.v_digits, 1, 6, 2), "sep": "" if sep == "（無）" else sep,
            "rev": self._int(self.v_rev, 0, 99, 0),
            "out_mode": self.v_out_mode.get() or "subfolder", "out_dir": self.v_out_dir.get().strip(),
            "keep_exif": self.v_exif.get(), "overwrite": self.v_over.get(), "skip_larger": self.v_skip.get(),
            "recursive": self.v_rec.get(), "show_safe": self.v_safe.get(),
        }
        if save:
            self.s.update({k_: v for k_, v in s.items() if k_ in DEFAULTS})
            save_settings(self.s)
        return s

    def _on_preset(self, apply: bool):
        p = self._preset()
        if apply and p.get("apply", True):
            self._loading = True
            self.v_fmt.set(p.get("fmt", "webp")); self.v_mode.set("lossy")
            self.v_quality.set(p.get("quality", 82)); self.v_method.set(p.get("method", 6))
            self.v_limit.set(p.get("limit_kb", 0))
            if "resize" in p:
                m, w, h = p["resize"]
                self.v_rs.set(RS_LABEL[m])
                if w:
                    self.v_rw.set(w)
                if h:
                    self.v_rh.set(h)
                self.v_up.set(False)
            self.v_safe.set(bool(p.get("safe")))
            self._loading = False
        hint = p.get("hint", "")
        if p.get("slug"):
            hint += "（檔名自動轉英文小寫、空白換成連字號）"
        self.lbl_hint.configure(text=hint)
        # 「自訂」用途要自己設尺寸 → 自動展開「③ 尺寸」
        if (not p.get("apply", True)) != self.body_rs._open:
            self.body_rs.toggle()
        self._on_change()

    def _on_change(self):
        if self._loading:
            return
        p = self._preset()
        nm = p["naming"]
        multi = p.get("multi")
        fmt = self.v_fmt.get()
        self.lbl_base.configure(text={"serial": "名稱", "keep": "名稱", "line": "名稱", "generic": "名稱",
                                      "slider": "SKU／活動"}.get(nm, "SKU"))
        self._en(self.w_base, nm != "keep")
        self._en(self.w_rev, nm != "keep")
        num = nm in ("serial", "feature", "sale", "line", "generic")
        self._show_row(self.r2, [(self.w_start_l, num), (self.w_start, num), (self.w_dig_l, nm == "serial"),
                                 (self.w_dig, nm == "serial"), (self.w_sep_l, nm == "serial"),
                                 (self.w_sep, nm == "serial")], before=self.r3)
        # 格式
        self._en(self.w_mode, fmt == "webp")
        for w_ in self.w_q:
            self._en(w_, fmt != "png")
        for w_ in self.w_m:
            self._en(w_, fmt == "webp")
        self.lbl_q.configure(text="壓縮努力" if fmt == "webp" and self.v_mode.get() == "lossless" else "品質")
        # 尺寸
        m = "none" if multi else RS_KEY.get(self.v_rs.get(), "none")
        need_w, need_h = m in ("width", "fit", "pad", "cover", "exact"), m in ("height", "fit", "pad", "cover", "exact")
        for w_ in (self.w_rs, self.rs_row, self.w_up, self.lbl_multi):
            w_.pack_forget()
        if not multi:
            self.w_rs.pack(fill="x")
        self._show_row(self.rs_row, [(self.w_rw_l, need_w), (self.w_rw, need_w), (self.w_rh_l, need_h),
                                     (self.w_rh, need_h), (self.w_pct_l, m == "percent"),
                                     (self.w_pct, m == "percent")], before=None)
        if m in ("width", "height", "fit", "percent", "pad"):
            self.w_up.pack(anchor="w", pady=(6, 0))
        if multi:
            self.lbl_multi.pack(fill="x")
        self.lbl_multi.configure(text=("固定輸出：" + "、".join(f"{w}×{h}" for _, w, h in multi) + "（置中裁切）")
                                 if multi else "")
        self._update_summary()
        self._refresh_outnames()
        self._update_footer()
        self._schedule_preview()

    def _size_text(self, opt, short=False):
        """尺寸設定的白話說明"""
        if opt.get("multi"):
            return f"{len(opt['multi'])} 種尺寸" if short else "、".join(f"{w}×{h}" for _, w, h in opt["multi"])
        m, W, H = opt["resize_mode"], opt["rw"], opt["rh"]
        return {"none": "原尺寸", "width": f"寬 {W}", "height": f"高 {H}", "fit": f"{W}×{H} 內",
                "pad": f"{W}×{H} 補白邊", "cover": f"{W}×{H} 裁切", "percent": f"{opt['rpct']}%",
                "exact": f"{W}×{H} 拉伸"}.get(m, "")

    def _update_summary(self):
        """右上角輸出摘要、③④ 收合時的摘要文字"""
        opt = self._collect(save=False)
        fmt = opt["fmt"]
        q = "" if fmt == "png" else (("無損" if opt["mode"] == "lossless" and fmt == "webp" else "有損 ")
                                     + ("" if opt["mode"] == "lossless" and fmt == "webp" else str(opt["quality"])))
        chips = [(fmt.upper(), BRAND, "#FFFFFF"), (q, "#2A2A30", DARK_INK),
                 (self._size_text(opt, short=True), "#2A2A30", DARK_INK),
                 (f"上限 {opt['limit_kb']:,} KB" if opt["limit_kb"] else "大小不限", "#2A2A30", DARK_INK)]
        for pill, (t, f, c) in zip(self.chips, chips):
            pill.pack_forget()
            if t:
                pill.set(t, f, c)
                pill.pack(side="left", padx=(0, int(6 * self.k)))
        need_base = opt["naming"] not in ("keep", "serial", "line", "generic") and not opt["base"]
        if need_base:
            name = "→ 先填 SKU，就會顯示輸出檔名"
        else:
            src = self.files[0] if self.files else Path("範例圖片.jpg")
            n = max(2, len(self.files))
            ts = make_targets(src, 0, n, opt)
            name = "→ " + ts[0][0].name
            if len(ts) > 1:
                name += f" 等 {len(ts)} 個尺寸"
            elif opt["naming"] not in ("keep", "slider"):
                t2 = make_targets(self.files[1] if len(self.files) > 1 else src, 1, n, opt)[0][0].name
                name += f"、{t2}…"
        self.lbl_sum_name.configure(text=name)
        self.lbl_rs_value.configure(text=self._size_text(opt, short=True))
        self.lbl_out_value.configure(text={"subfolder": "原資料夾／converted", "same": "原資料夾",
                                           "custom": (Path(opt["out_dir"]).name or "（未選資料夾）")
                                           if opt["out_dir"] else "（未選資料夾）"}[opt["out_mode"]])

    @staticmethod
    def _show_row(row, items, before):
        """只顯示需要的欄位；全部不需要就把整列藏起來"""
        for w_, _ in items:
            w_.pack_forget()
        shown = [w_ for w_, on in items if on]
        for i, w_ in enumerate(shown):
            w_.pack(side="left", padx=(0 if i == 0 else (12 if i % 2 == 0 else 6), 0))
        if shown:
            row.pack(fill="x", pady=(0, 8), **({"before": before} if before else {}))
        else:
            row.pack_forget()

    @staticmethod
    def _en(w, on):
        if isinstance(w, ttk.Combobox):
            w.state(["!disabled", "readonly"] if on else ["disabled"])
        else:
            w.state(["!disabled"] if on else ["disabled"])

    # ---------- 檔案清單 ----------
    def _on_drop(self, paths):
        out = []
        for p in map(Path, paths):
            if p.is_dir():
                it = p.rglob("*") if self.v_rec.get() else p.glob("*")
                out += sorted((x for x in it if x.is_file()), key=lambda x: str(x).lower())
            else:
                out.append(p)
        self._add(out)

    def _add(self, paths):
        known = set(self.files)
        new = []
        for p in map(Path, paths):
            if p.suffix.lower() in SUPPORTED and p not in known and p.is_file():
                self.files.append(p)
                known.add(p)
                new.append(p)
                self.info[p] = probe(p)
                self.status[p] = ("待轉換", "")
        if new:
            threading.Thread(target=self._thumb_worker, args=(new,), daemon=True).start()
        self._refresh_list(select=[0] if self.files and not self.tree.selection() else None)

    def _thumb_worker(self, paths):
        """背景產生清單縮圖（圓角、置中裁成正方形）"""
        s = int(40 * self.k)
        mask = round_img(s, s, max(4, s // 6), (0, 0, 0, 255)).getchannel("A")
        for p in paths:
            try:
                with Image.open(p) as im:
                    im.draft("RGB", (s * 4, s * 4))
                    im = ImageOps.exif_transpose(im).convert("RGBA")
                    t = ImageOps.fit(im, (s, s), Image.LANCZOS)
                gap = int(8 * self.k)  # 左右留白：Mac 的清單圖片靠左對齊，不留白會貼著檔名
                out = Image.new("RGBA", (s + 2 * gap, s), (0, 0, 0, 0))
                out.paste(t, (gap, 0), mask)
                self.q.put(("thumb", p, out))
            except Exception:
                pass

    def _refresh_list(self, select=None):
        keep = select if select is not None else [self.tree.index(i) for i in self.tree.selection()]
        self.tree.delete(*self.tree.get_children())
        for i, p in enumerate(self.files):
            try:
                sz = human(p.stat().st_size)
            except OSError:
                sz = "—"
            st, tag = self.status.get(p, ("待轉換", ""))
            self.tree.insert("", "end", iid=str(i), image=self.thumbs.get(p, ""),
                             values=(p.name, self.info.get(p, ""), sz, "", st), tags=(tag,) if tag else ())
        for i in keep:
            if 0 <= i < len(self.files):
                self.tree.selection_add(str(i))
        if keep and 0 <= keep[0] < len(self.files):
            self.tree.see(str(keep[0]))
        # 沒有圖片：顯示大拖放區；有圖片：顯示清單與預覽
        if self.files:
            self.view_empty.pack_forget()
            self.view_list.pack(fill="both", expand=True)
        else:
            self.view_list.pack_forget()
            self.view_empty.pack(fill="both", expand=True)
            self._pv_ratio = None
        total = sum(p.stat().st_size for p in self.files if p.exists())
        self.lbl_count.configure(text=f"{len(self.files)} 張 · 原始 {human(total)}")
        self._update_summary()
        self._refresh_outnames()
        self._update_footer()
        self._schedule_preview()

    def _update_footer(self):
        if self.busy or not hasattr(self, "lbl_status"):
            return
        if not self.files:
            self.lbl_status.configure(text="還沒有圖片 · 先加入要轉換的圖片", fg=MUTED)
            return
        opt = self._collect(save=False)
        total = sum(p.stat().st_size for p in self.files if p.exists())
        txt = f"共 {len(self.files)} 張 · 原始 {human(total)}"
        if self._pv_ratio and not opt.get("multi"):
            est = total * self._pv_ratio
            txt += f" · 預估輸出約 {human(est)}（{diff_text(total, int(est))}）"
        txt += " · 存到「" + self.lbl_out_value.cget("text") + "」"
        self.lbl_status.configure(text=txt, fg=MUTED)

    def _refresh_outnames(self):
        if not hasattr(self, "tree") or self._loading:
            return
        opt = self._collect(save=False)
        n = len(self.files)
        need_base = opt["naming"] not in ("keep", "serial", "line", "generic") and not opt["base"]
        for i, p in enumerate(self.files):
            if need_base:
                txt = "（請先填 SKU）"
            else:
                names = [t[0].name for t in make_targets(p, i, n, opt)]
                txt = names[0] if len(names) == 1 else f"{names[0]}  ＋{len(names) - 1} 個尺寸"
                if opt["naming"] == "slider" and i > 0:
                    txt = "（Slider 一次只轉一張）"
            self.tree.set(str(i), "out", txt)

    def _set_status(self, p, text, tag=""):
        self.status[p] = (text, tag)
        if p in self.files:
            iid = str(self.files.index(p))
            if self.tree.exists(iid):
                self.tree.set(iid, "status", text)
                self.tree.item(iid, tags=(tag,) if tag else ())
                self.tree.see(iid)

    def _selected_idx(self):
        return [int(i) for i in self.tree.selection()]

    def add_files(self):
        exts = " ".join(f"*{e}" for e in sorted(SUPPORTED))
        self._add(filedialog.askopenfilenames(title="選擇圖片", filetypes=[("圖片", exts), ("所有檔案", "*.*")]))

    def add_folder(self):
        d = filedialog.askdirectory(title="選擇資料夾")
        if d:
            self._on_drop([d])

    def remove_selected(self):
        if self.busy:
            return
        for i in sorted(self._selected_idx(), reverse=True):
            del self.files[i]
        self._refresh_list(select=[0] if self.files else [])

    def clear_files(self):
        if self.busy:
            return
        self.files.clear()
        self._refresh_list(select=[])

    def move(self, step):
        sel = sorted(self._selected_idx())
        if not sel or self.busy:
            return
        for i in (sel if step < 0 else list(reversed(sel))):
            j = i + step
            if 0 <= j < len(self.files) and j not in sel:
                self.files[i], self.files[j] = self.files[j], self.files[i]
                sel[sel.index(i)] = j
        self._refresh_list(select=sel)

    def sort_files(self):
        if self.busy:
            return
        self.files.sort(key=lambda p: p.name.lower())
        self._refresh_list(select=[0])

    def pick_out(self):
        d = filedialog.askdirectory(title="選擇輸出資料夾")
        if d:
            self.v_out_dir.set(d)
            self.v_out_mode.set("custom")
            self._on_change()

    # ---------- 預覽 ----------
    def _schedule_preview(self):
        if self._loading or not hasattr(self, "cv"):
            return
        if self._pv_job:
            self.after_cancel(self._pv_job)
        self._pv_job = self.after(400, self._start_preview)

    def _start_preview(self):
        self._pv_job = None
        sel = self._selected_idx()
        if not sel or not self.files:
            self._pv_last = None
            self._redraw_preview()
            self.lbl_size.configure(text="")
            self.pill_save.set("")
            self.lbl_info_r.configure(text="點選清單中的圖片即可預覽")
            self.lbl_notes.configure(text="")
            return
        idx = sel[0]
        src = self.files[idx]
        opt = self._collect(save=False)
        self._pv_token += 1
        tok = self._pv_token
        self.lbl_info_r.configure(text="產生預覽中…")
        threading.Thread(target=self._preview_worker, args=(tok, src, idx, len(self.files), opt), daemon=True).start()

    def _preview_worker(self, tok, src, idx, n, opt):
        try:
            frames, durations, loop, extras = load_source(src, opt["keep_exif"])
            targets = make_targets(src, idx, n, opt)
            dst, rs, _ = targets[0]
            data, used_q, out0, up = render(frames, durations, loop, extras, rs, opt)
            with Image.open(io.BytesIO(data)) as im:
                im.seek(0)
                out = im.convert("RGBA")
            orig = frames[0].copy()
            old, new = src.stat().st_size, len(data)
            w2, h2 = out.size
            orig.thumbnail((1400, 1400))
            out.thumbnail((1400, 1400))
            q = "" if opt["fmt"] == "png" else (" 無損" if opt["mode"] == "lossless" and opt["fmt"] == "webp"
                                                 else f" 品質 {used_q if used_q is not None else opt['quality']}")
            meta = f"{w2}×{h2} · {opt['fmt'].upper()}{q} · {dst.name}"
            notes = []
            if up:
                notes.append("原圖比目標尺寸小，已放大（可能變糊）")
            if used_q is not None and used_q != int(opt["quality"]):
                notes.append(f"為符合 {opt['limit_kb']} KB，品質降到 {used_q}")
            if out0.info.get("shrink", 1.0) < 0.999:
                notes.append(f"為符合 {opt['limit_kb']} KB，尺寸已縮小")
            if opt["limit_kb"] and new > opt["limit_kb"] * 1024:
                notes.append(f"仍超過 {opt['limit_kb']} KB")
            if new > old:
                notes.append("轉完比原檔大（可以降低品質，或在進階設定勾「轉完比原檔大就不保留」）")
            if len(targets) > 1:
                notes.append("另外還會輸出 " + "、".join(t[2] for t in targets[1:]))
            warn = up or (opt["limit_kb"] and new > opt["limit_kb"] * 1024) or new > old
            self.q.put(("preview", tok, orig, out, old, new, meta, "；".join(notes), warn, len(targets) == 1))
        except Exception as e:
            self.q.put(("preview", tok, None, None, 0, 0, f"無法預覽：{e}", "", True, False))

    def _show_preview_info(self, old, new, meta, notes, warn):
        if not old:
            self.lbl_size.configure(text="")
            self.pill_save.set("")
            self.lbl_info_r.configure(text=meta)
            self.lbl_notes.configure(text=notes, style="CDanger.TLabel")
            return
        self.lbl_size.configure(text=f"{human(old)} → {human(new)}")
        pct = abs(1 - new / old) * 100
        if new <= old:
            self.pill_save.set(f"−{pct:.0f}%", OK_BG, OK)
        else:
            self.pill_save.set(f"+{pct:.0f}%", "#FDE8E8", DANGER)
        self.lbl_info_r.configure(text=meta)
        self.lbl_notes.configure(text=notes, style="CDanger.TLabel" if warn else "CHint.TLabel")

    def _pane_label(self, c, x, y, text):
        """預覽圖左上角的深色小標籤"""
        f = tkfont.Font(font=(UI_FONT, fs(8)))
        w, h = f.measure(text) + 14, f.metrics("linespace") + 4
        ph = ImageTk.PhotoImage(round_img(w, h, h // 2, (17, 17, 19, 210)))
        c._labels = getattr(c, "_labels", []) + [ph]
        c.create_image(x, y, anchor="nw", image=ph)
        c.create_text(x + w / 2, y + h / 2, text=text, fill="#FFFFFF", font=f)

    def _redraw_preview(self):
        if not hasattr(self, "cv"):
            return
        imgs = self._pv_last or (None, None)
        for i, c in enumerate(self.cv):
            c.delete("all")
            c._labels = []
            cw, ch = max(10, c.winfo_width()), max(10, c.winfo_height())
            im = imgs[i]
            lab = ("原圖 · 點圖放大", "輸出結果 · 點圖放大")[i]
            if im is None:
                c.create_text(cw // 2, ch // 2, text="—", fill="#A3A3AB", font=(UI_FONT, fs(14)))
                self._pane_label(c, 8, 8, lab.split(" · ")[0])
                continue
            r = min((cw - 24) / im.width, (ch - 24) / im.height, 1.0 if max(im.size) < 200 else 99)
            tw, th = max(1, int(im.width * r)), max(1, int(im.height * r))
            thumb = im.resize((tw, th), Image.LANCZOS)
            # 透明處用棋盤格
            if thumb.mode == "RGBA":
                bg = Image.new("RGBA", thumb.size, (255, 255, 255, 255))
                s = 8
                for y in range(0, th, s):
                    for x in range((y // s % 2) * s, tw, 2 * s):
                        bg.paste((225, 228, 233, 255), (x, y, min(x + s, tw), min(y + s, th)))
                bg.alpha_composite(thumb)
                thumb = bg
            ph = ImageTk.PhotoImage(thumb)
            self._pv_imgs[i] = ph
            x0, y0 = (cw - tw) // 2, (ch - th) // 2
            c.create_image(x0, y0, anchor="nw", image=ph)
            if i == 1 and self.v_safe.get():
                l_, t_, r_, b_, label = self._safe_box()
                bx, by = x0 + tw * l_, y0 + th * t_
                c.create_rectangle(bx, by, x0 + tw * (1 - r_), y0 + th * (1 - b_), outline=BRAND, dash=(5, 3), width=2)
                f = tkfont.Font(font=(UI_FONT, fs(8), "bold"))
                lw, lh = f.measure(label) + 10, f.metrics("linespace") + 2
                c.create_rectangle(bx + 1, by + 1, bx + 1 + lw, by + 1 + lh, fill=BRAND, outline="")
                c.create_text(bx + 1 + lw / 2, by + 1 + lh / 2, text=label, fill="#FFFFFF", font=f)
            self._pane_label(c, 8, 8, lab)

    def _safe_box(self):
        """安全區（左上右下，比例）：用途有平台規格就用規格，否則用中央 80%"""
        p = self._preset()
        safe = p.get("safe")
        if not safe:
            return 0.1, 0.1, 0.1, 0.1, "建議安全區 80%"
        if all(v <= 1 for v in safe):
            return (*safe, "安全區")
        if p.get("resize"):
            W, H = p["resize"][1], p["resize"][2]
        elif p.get("multi"):
            W, H = p["multi"][0][1], p["multi"][0][2]
        else:
            return 0.1, 0.1, 0.1, 0.1, "建議安全區 80%"
        l_, t_, r_, b_ = safe
        return l_ / W, t_ / H, r_ / W, b_ / H, "平台安全區"

    # ---------- 轉換 ----------
    def _ask(self, kind, text):
        (messagebox.showinfo if kind == "info" else messagebox.showwarning)(APP_TITLE, text, parent=self)

    def start(self):
        if self.busy:
            return
        if not self.files:
            self._ask("info", "請先加入要轉換的圖片（可以直接拖進視窗）。")
            return
        opt = self._collect()
        if opt["out_mode"] == "custom" and not opt["out_dir"]:
            if not self.body_out._open:
                self.body_out.toggle()
            self._ask("warn", "輸出位置選了「自訂」，請按「瀏覽…」選一個資料夾。")
            return
        if opt["naming"] not in ("keep", "serial", "line", "generic") and not opt["base"]:
            self.w_base.focus_set()
            self._ask("warn", "請先填寫 SKU（活動 Slider 填「年份＋活動代稱」）。")
            return
        if opt["naming"] == "slider" and len(self.files) > 1:
            self._ask("warn", "Slider 一次轉一張（同一個 SKU 只有一組 slider 檔名）。\n請只留一張圖，或分批轉換。")
            return
        self.busy = True
        self.stop_flag.clear()
        for p in self.files:
            self._set_status(p, "等待中", "")
        self._set_running(True, 0, len(self.files))
        p = self._preset()
        desc = f"{opt['fmt'].upper()}" + ("" if opt["fmt"] == "png" else f" 品質 {opt['quality']}")
        if opt["limit_kb"]:
            desc += f"，上限 {opt['limit_kb']} KB"
        self._log(f"── 開始：{p['label']}｜{desc}｜共 {len(self.files)} 張 ──", "head")
        self._run_t0 = time.monotonic()
        threading.Thread(target=self._run, args=(list(self.files), opt), daemon=True).start()

    def _set_running(self, on, done=0, total=0):
        """切換底部列：轉換中顯示進度條＋停止；閒置顯示摘要"""
        k = self.k
        if on:
            self.btn_open.pack_forget()
            self.lbl_status.pack_forget()
            self.btn_go.configure(state="disabled", text="轉換中…")
            self.btn_stop.pack(side="right", padx=(0, int(10 * k)))
            self.btn_stop.configure(state="normal")
            self.prog.pack(side="left", fill="x", expand=True)
            self.pb.configure(maximum=max(1, total), value=done)
            self.lbl_prog.configure(text=f"{done} / {total} 張")
        else:
            self.prog.pack_forget()
            self.btn_stop.pack_forget()
            self.btn_go.configure(state="normal", text="開始轉換")
            self.lbl_status.pack(side="left", fill="x", expand=True)

    def _run(self, files, opt):
        ok = fail = skip = 0
        tot_old = tot_new = 0
        produced: set = set()
        out_dirs = set()
        for i, src in enumerate(files):
            if self.stop_flag.is_set():
                self.q.put(("log", "已停止。", "warn"))
                break
            self.q.put(("status", src, "轉換中…", "run"))
            try:
                targets = make_targets(src, i, len(files), opt)
                f_old = f_new = f_ok = f_skip = 0
                warn = False
                for dst, status, old, new, note in process(src, targets, opt, produced):
                    if status == "完成":
                        ok += 1
                        f_ok += 1
                        tot_new += new
                        f_new += new
                        out_dirs.add(dst.parent)
                        bad = (new > old and len(targets) == 1) or "超過" in note
                        warn = warn or bad
                        self.q.put(("log", f"✓ {dst.name}  {human(old)} → {human(new)}（{diff_text(old, new)}）"
                                           f"  {note}  ← {src.name}", "warn" if bad else "ok"))
                    else:
                        skip += 1
                        f_skip += 1
                        self.q.put(("log", f"－ 略過 {dst.name}：{note}", "warn"))
                    f_old = old
                tot_old += src.stat().st_size
                if f_ok:
                    pct = (1 - (f_new / f_ok) / f_old) * 100 if f_old else 0
                    txt = (f"✓ −{pct:.0f}%" if pct >= 0 else f"✓ +{-pct:.0f}%") if f_ok == 1 else f"✓ {f_ok} 個檔"
                    if warn:
                        txt = "⚠ " + txt[2:] + " 注意"
                    self.q.put(("status", src, txt, "warn" if warn else "ok"))
                else:
                    self.q.put(("status", src, "－ 略過", "warn"))
            except Exception as e:
                fail += 1
                self.q.put(("log", f"✗ 失敗 {src.name}：{e}", "err"))
                self.q.put(("status", src, "✕ 失敗", "err"))
            self.q.put(("progress", i + 1, len(files)))
        if self.stop_flag.is_set():
            for src in files:
                self.q.put(("status_if", src, "等待中", "已停止", ""))
        self.q.put(("done", ok, skip, fail, tot_old, tot_new, sorted(out_dirs)))

    def _poll(self):
        try:
            while True:
                msg = self.q.get_nowait()
                kind = msg[0]
                if kind == "log":
                    self._log(msg[1], msg[2])
                elif kind == "thumb":
                    _, p, im = msg
                    ph = ImageTk.PhotoImage(im)
                    self.thumbs[p] = ph
                    if p in self.files:
                        iid = str(self.files.index(p))
                        if self.tree.exists(iid):
                            self.tree.item(iid, image=ph)
                elif kind == "status":
                    self._set_status(msg[1], msg[2], msg[3])
                elif kind == "status_if":
                    if self.status.get(msg[1], ("",))[0] == msg[2]:
                        self._set_status(msg[1], msg[3], msg[4])
                elif kind == "progress":
                    done, total = msg[1], msg[2]
                    self.pb.configure(value=done)
                    txt = f"{done} / {total} 張"
                    if 0 < done < total:
                        left = (time.monotonic() - self._run_t0) / done * (total - done)
                        txt += f" · 剩約 {max(1, round(left))} 秒" if left < 90 else f" · 剩約 {round(left / 60)} 分鐘"
                    self.lbl_prog.configure(text=txt)
                elif kind == "done":
                    _, ok, skip, fail, to, tn, dirs = msg
                    self._log(f"── 完成：輸出 {ok} 個、略過 {skip}、失敗 {fail}｜來源 {human(to)}，輸出 {human(tn)} ──", "head")
                    for d in dirs:
                        self._log(f"   輸出資料夾：{d}", "head")
                    self.busy = False
                    self._set_running(False)
                    self._out_dirs = dirs
                    txt = f"完成：輸出 {ok} 個檔案"
                    if to and tn:
                        txt += f"，{human(to)} → {human(tn)}（{diff_text(to, tn)}）"
                    if skip:
                        txt += f"，略過 {skip}"
                    if fail:
                        txt += f"，失敗 {fail}（看「轉換紀錄」）"
                    self.lbl_status.configure(text=txt, fg=DANGER if fail else OK)
                    if fail or skip:
                        self.v_tab.set("log")
                        self._switch_tab()
                    if ok and dirs:
                        self.btn_open.pack(side="right", padx=(0, int(10 * self.k)), after=self.btn_go)
                elif kind == "preview":
                    _, tok, orig, out, old, new, meta, notes, warn, single = msg
                    if tok != self._pv_token:
                        continue
                    self._pv_last = (orig, out) if orig is not None else None
                    self._pv_ratio = (new / old) if (old and single) else None
                    self._show_preview_info(old, new, meta, notes, warn)
                    self._redraw_preview()
                    self._update_footer()
        except queue.Empty:
            pass
        self.after(80, self._poll)

    def _log(self, text, tag=None):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n", tag)
        self.log.see("end")
        self.log.configure(state="disabled")

    # ---------- 拖放 ----------
    def _drop_enter(self, e):
        if self.files:
            self.drop_overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
            self.drop_overlay.lift()
        else:
            self._empty_hot = True
            self.lbl_drop_title.configure(text="放開滑鼠，加入圖片", fg=ACCENT)
            self._draw_empty(force=True)
        return e.action

    def _drop_leave(self, e=None):
        self.drop_overlay.place_forget()
        if self._empty_hot:
            self._empty_hot = False
            self.lbl_drop_title.configure(text="把圖片或資料夾拖到這裡", fg=INK)
            self._draw_empty(force=True)
        return e.action if e is not None else None

    def _drop(self, e):
        self._drop_leave()
        self._on_drop(list(self.tk.splitlist(e.data)))
        return e.action

    def open_output(self):
        for d in self._out_dirs[:3]:
            open_folder(d)

    def _zoom(self, i):
        """點預覽放大檢視"""
        if not self._pv_last or self._pv_last[i] is None:
            return
        im = self._pv_last[i]
        w = tk.Toplevel(self)
        w.title(("原圖" if i == 0 else "輸出結果") + " 放大檢視")
        w.configure(bg="#2A2A2E")
        sw, sh = int(self.winfo_screenwidth() * 0.85), int(self.winfo_screenheight() * 0.8)
        r = min(sw / im.width, sh / im.height, 1.0)
        shown = im.resize((max(1, int(im.width * r)), max(1, int(im.height * r))), Image.LANCZOS)
        if shown.mode == "RGBA":
            bg = Image.new("RGBA", shown.size, (255, 255, 255, 255))
            bg.alpha_composite(shown)
            shown = bg
        w._ph = ImageTk.PhotoImage(shown)
        c = tk.Canvas(w, width=shown.width, height=shown.height, bg="#2A2A2E", highlightthickness=0)
        c.pack(padx=12, pady=12)
        c.create_image(0, 0, anchor="nw", image=w._ph)
        if i == 1 and self.v_safe.get():
            l_, t_, r_, b_, label = self._safe_box()
            W, H = shown.width, shown.height
            c.create_rectangle(W * l_, H * t_, W * (1 - r_), H * (1 - b_), outline=BRAND, dash=(6, 4), width=2)
            c.create_text(W * l_ + 6, H * t_ + 6, anchor="nw", text=label, fill=BRAND, font=(UI_FONT, fs(11), "bold"))
        tk.Label(w, text="按 Esc 或點圖片關閉", bg="#2A2A2E", fg=DARK_MUTED, font=(UI_FONT, fs(9))).pack(pady=(0, 8))
        w.bind("<Escape>", lambda e: w.destroy())
        c.bind("<Button-1>", lambda e: w.destroy())
        w.transient(self)
        w.focus_set()

    def show_about(self):
        k = self.k
        w = tk.Toplevel(self)
        w.title(f"關於 {APP_NAME}")
        w.configure(bg=DARK)
        w.resizable(False, False)
        w.transient(self)
        box = tk.Frame(w, bg=DARK, padx=int(28 * k), pady=int(22 * k))
        box.pack()
        try:
            lg = Image.open(ASSETS / "logo-512.png").resize((int(72 * k), int(72 * k)), Image.LANCZOS)
            w._logo = ImageTk.PhotoImage(lg)
            tk.Label(box, image=w._logo, bg=DARK).pack()
        except Exception:
            pass
        tk.Label(box, text="Moksa Web", font=(self.brand_font, fs(20), "bold"), fg=DARK_INK, bg=DARK).pack(pady=(8, 0))
        tk.Label(box, text="S T U D I O  ·  台 中", font=(self.mono_font, fs(8)), fg=DARK_MUTED, bg=DARK).pack()
        tk.Frame(box, bg=BRAND, height=max(2, int(3 * k)), width=int(48 * k)).pack(pady=int(12 * k))
        tk.Label(box, text=f"WebP 圖片轉換工具  v{APP_VERSION}", font=(UI_FONT, fs(11), "bold"),
                 fg=DARK_INK, bg=DARK).pack()
        tk.Label(box, text=APP_ABOUT, font=(UI_FONT, fs(9)), fg=DARK_MUTED, bg=DARK, wraplength=int(360 * k),
                 justify="center").pack(pady=(8, 0))
        info = f"內建 {len(PRESETS)} 種用途"
        if PRESETS_VERSION:
            info += f"（尺寸規格查核日 {PRESETS_VERSION}）"
        if PRESETS_FILE and PRESETS_FILE in CUSTOM_PRESETS:
            info += "\n目前使用自訂的 presets.json"
        tk.Label(box, text=info, font=(UI_FONT, fs(8)), fg=DARK_MUTED, bg=DARK, justify="center").pack(pady=(10, 0))
        tk.Label(box, text="字型 Space Grotesk、JetBrains Mono 以 SIL Open Font License 授權",
                 font=(UI_FONT, fs(8)), fg="#6E6E76", bg=DARK).pack(pady=(4, 0))
        link = tk.Label(box, text="moksaweb.com", font=(self.mono_font, fs(10), "underline"), fg=BRAND, bg=DARK,
                        cursor="hand2")
        link.pack(pady=(12, 0))
        link.bind("<Button-1>", lambda e: webbrowser.open(APP_URL))
        ttk.Button(box, text="關閉", command=w.destroy).pack(pady=(14, 0))
        w.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() - w.winfo_width()) // 2
        y = self.winfo_rooty() + (self.winfo_height() - w.winfo_height()) // 3
        w.geometry(f"+{x}+{y}")
        w.grab_set()

    def _on_close(self):
        self._collect()
        self.stop_flag.set()
        self.destroy()


def selftest(out_dir: str) -> int:
    """不開視窗的自我測試（CI 用）：試轉幾種用途，結果寫到 out_dir/selftest.txt"""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    src = out / "selftest-src.png"
    img = Image.new("RGBA", (1800, 1200), (255, 90, 54, 255))
    for x in range(0, 1800, 60):
        img.paste((17, 17, 19, 128), (x, 0, x + 30, 1200))
    img.save(src)
    lines, ok = [f"{APP_TITLE} v{APP_VERSION} on {sys.platform}", f"presets={len(PRESETS)} file={PRESETS_FILE}"], True
    for key in ("web_product", "web_slider", "line_menu_l", "wp_featured", "wp_favicon"):
        p = PRESET_BY_KEY.get(key)
        if not p:
            lines.append(f"FAIL {key}: 找不到用途")
            ok = False
            continue
        o = dict(DEFAULTS)
        o.update(fmt=p.get("fmt", "webp"), quality=p.get("quality", 82), method=p.get("method", 6),
                 limit_kb=p.get("limit_kb", 0), naming=p["naming"], multi=p.get("multi"),
                 slug=bool(p.get("slug")), base="TEST-001", out_mode="custom", out_dir=str(out), overwrite=True)
        if p.get("resize"):
            o.update(resize_mode=p["resize"][0], rw=p["resize"][1] or 2000, rh=p["resize"][2] or 2000)
        try:
            for dst, st, old, new, note in process(src, make_targets(src, 0, 1, o), o, set()):
                with Image.open(dst) as chk:
                    lines.append(f"{st} {key} -> {dst.name} {chk.format} {chk.size} {new}B")
        except Exception as e:
            lines.append(f"FAIL {key}: {e!r}")
            ok = False
    lines.append("RESULT " + ("PASS" if ok else "FAIL"))
    (out / "selftest.txt").write_text("\n".join(lines), encoding="utf-8")
    return 0 if ok else 1


def uitest(out_dir: str, screen: str = "") -> int:
    """開視窗的介面測試（CI 用）：檢查拖放元件、字型、主題與各狀態的版面，截圖後自動關閉。
    用暫存的設定檔，不會改到使用者自己的設定。"""
    from PIL import ImageGrab
    global SIM_SCREEN, SETTINGS_FILE
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    tag = ""
    if screen:
        SIM_SCREEN = tuple(int(x) for x in screen.lower().split("x"))
        tag = f"-{screen}"
    SETTINGS_FILE = out / f"uitest-settings{tag}.json"
    SETTINGS_FILE.unlink(missing_ok=True)
    src_dir = out / f"uitest-src{tag}"
    conv_dir = out / f"uitest-converted{tag}"
    for d in (src_dir, conv_dir):
        if d.exists():
            for f in d.iterdir():
                f.unlink()
        d.mkdir(exist_ok=True)
    # 模擬商品照：四張不同比例、顏色
    for i, (bg, w, h) in enumerate((((214, 170, 140), 1800, 1200), ((120, 150, 170), 1200, 1600),
                                    ((200, 200, 190), 2000, 2000), ((60, 60, 66), 1600, 900)), 1):
        img = Image.new("RGB", (w, h), bg)
        d = ImageDraw.Draw(img)
        d.ellipse((w * 0.3, h * 0.25, w * 0.7, h * 0.75), fill=tuple(min(255, c + 45) for c in bg))
        d.rectangle((w * 0.42, h * 0.1, w * 0.58, h * 0.3), fill=(255, 90, 54))
        img.save(src_dir / f"範例商品{i}.jpg", quality=92)
    lines, ok = [f"{APP_TITLE} v{APP_VERSION} on {sys.platform}" + (f"，模擬螢幕 {screen}" if screen else "")], True
    app = App()

    def check(name, cond, detail=""):
        nonlocal ok
        ok = ok and bool(cond)
        lines.append(f"{'PASS' if cond else 'FAIL'} {name}" + (f"：{detail}" if detail else ""))

    def shot(name):
        app.update()
        try:
            if IS_MAC:
                subprocess.run(["screencapture", "-x", str(out / name)], check=True, timeout=20)
            else:
                x, y = app.winfo_rootx(), app.winfo_rooty()
                ImageGrab.grab(bbox=(x - 8, y - 32, x + app.winfo_width() + 8, y + app.winfo_height() + 8),
                               all_screens=True).save(out / name)
            lines.append(f"截圖 {name}")
        except Exception as e:
            lines.append(f"截圖失敗 {name}：{e!r}")

    def visible(w):
        """元件有顯示、而且整個在視窗裡"""
        if not w.winfo_ismapped():
            return False
        x, y = w.winfo_rootx(), w.winfo_rooty()
        return (app.winfo_rootx() <= x and x + w.winfo_width() <= app.winfo_rootx() + app.winfo_width() + 1
                and app.winfo_rooty() <= y and y + w.winfo_height() <= app.winfo_rooty() + app.winfo_height() + 1)

    def step1():  # 空白狀態
        fams = set(tkfont.families(app))
        check("Tk 版本", True, app.tk.call("info", "patchlevel"))
        check("拖放元件 tkdnd", app.dnd_ok, f"版本 {app.TkdndVersion}" if app.dnd_ok else app.dnd_error)
        check("品牌主題 sun-valley-light", app.themed)
        check("英文字型 Space Grotesk", app.brand_font == BRAND_FONT, app.brand_font)
        check("數字字型 JetBrains Mono", app.mono_font.startswith(MONO_FONT), app.mono_font)
        check(f"中文字型 {UI_FONT}", UI_FONT in fams)
        check("視窗大小", app.winfo_width() > 800, f"{app.winfo_width()}×{app.winfo_height()}")
        check("空白狀態：顯示拖放區、不顯示清單", app.view_empty.winfo_ismapped() and not app.view_list.winfo_ismapped())
        check("空白狀態：「加入檔案」大按鈕看得到", visible(app.btn_empty_add))
        check("「開始轉換」看得到", visible(app.btn_go))
        # 選電商 SKU 規範 → 商品圖，填 SKU
        app.v_cat.set("電商 SKU 規範")
        app._on_cat()
        app.v_base.set("TEST-001")
        app.update()
        shot(f"1-空白狀態{tag}.png")
        app._drop_enter(type("E", (), {"action": "copy"})())
        app.after(300, step1b)

    def step1b():
        shot(f"2-空白狀態-拖曳中{tag}.png")
        app._drop_leave()
        app._on_drop([str(src_dir)])  # 等同把資料夾拖進視窗
        app.after(3500, step2)

    def step2():  # 加了圖
        check("加入資料夾", len(app.files) == 4, f"{len(app.files)} 張")
        check("加圖後：顯示清單與預覽", app.view_list.winfo_ismapped() and not app.view_empty.winfo_ismapped())
        check("清單縮圖", len(app.thumbs) == 4, f"{len(app.thumbs)} 張")
        th = next(iter(app.thumbs.values()))
        check("縮圖與檔名有間距", app.tree.column("#0", "width") >= th.width() and th.width() > th.height(),
              f"縮圖欄 {app.tree.column('#0', 'width')}，縮圖 {th.width()}×{th.height()}")
        f_ = tkfont.Font(root=app, font=app.cb_preset.cget("font") or ttk.Style(app).lookup("TCombobox", "font")
                         or "TkTextFont")
        need, have = f_.measure(app.v_preset.get()) + int(36 * app.k), app.cb_preset.winfo_width()
        if app._W >= int(1200 * app.k) or need <= have:
            check("「用途」名稱完整顯示", need <= have, f"文字需要 {need}，欄位 {have}")
        else:  # 1024 寬這種極窄視窗，右側欄較窄，長名稱可能被切（下方說明文字仍完整）
            lines.append(f"注意 「用途」名稱在極窄視窗可能被切：文字需要 {need}，欄位 {have}")
        cut = [str(b.cget("text") or b.cget("image")) for b in app.bar_items if not visible(b)]
        check("工具列按鈕都看得到", not cut, "被擠掉：" + "、".join(cut) if cut else f"{len(app.bar_items)} 個")
        chips = [c.text for c in app.chips if c.winfo_ismapped()]
        check("輸出摘要", chips[:1] == ["WEBP"] and "TEST-001pic.webp" in app.lbl_sum_name.cget("text"),
              " · ".join(chips) + " " + app.lbl_sum_name.cget("text"))
        check("預覽大小徽章", "→" in app.lbl_size.cget("text") and app.pill_save.text,
              f"{app.lbl_size.cget('text')} {app.pill_save.text}")
        check("底部列預估", "預估輸出" in app.lbl_status.cget("text"), app.lbl_status.cget("text"))
        shot(f"3-加了圖之後{tag}.png")
        # 實際轉換到暫存資料夾
        app.v_out_mode.set("custom")
        app.v_out_dir.set(str(conv_dir))
        app._on_change()
        app.start()
        app.after(50, wait_run)

    seen = {"mid": False}

    def wait_run():
        if app.busy:
            if not seen["mid"] and app.pb["value"] >= 1:
                seen["mid"] = True
                check("轉換中：進度條與停止按鈕", app.prog.winfo_ismapped() and app.btn_stop.winfo_ismapped(),
                      app.lbl_prog.cget("text"))
                shot(f"4-轉換中{tag}.png")
            app.after(30, wait_run)
            return
        app.update()
        outs = sorted(f.name for f in conv_dir.iterdir())
        check("轉換結果", outs == ["TEST-001pic.webp", "TEST-001pic1.webp", "TEST-001pic2.webp", "TEST-001pic3.webp"],
              "、".join(outs))
        sts = [app.status[p][0] for p in app.files]
        check("清單狀態", all(t.startswith("✓") for t in sts), "、".join(sts))
        check("完成：「開啟輸出資料夾」", app.btn_open.winfo_ismapped(), app.lbl_status.cget("text"))
        if not seen["mid"]:
            lines.append("（轉換太快，沒截到轉換中的畫面）")
        shot(f"5-完成{tag}.png")
        # 展開 ③ ④ 與進階設定
        for body in (app.body_rs, app.body_out):
            if not body._open:
                body.toggle()
        app._toggle_adv()
        app.after(300, step3)

    def step3():
        cv, b = app.set_cv, app.btn_out_browse
        app.update()
        cv.yview_moveto(0.0)
        app.update()
        # 捲到「④ 輸出位置」的「瀏覽…」
        y_in = b.winfo_rooty() - cv.winfo_rooty()
        total = float(str(cv.cget("scrollregion")).split()[3] or 1)
        cv.yview_moveto(max(0.0, (y_in - cv.winfo_height() / 2) / total))
        app.update()
        y = b.winfo_rooty()
        check("「④ 輸出位置」看得到（必要時捲動）",
              cv.winfo_rooty() <= y and y + b.winfo_height() <= cv.winfo_rooty() + cv.winfo_height(),
              "設定欄有捲軸" if app.set_sb.winfo_ismapped() else "不需捲動")
        shot(f"6-設定展開{tag}.png")
        app.show_about()
        app.after(800, step4)

    def step4():
        shot(f"7-關於{tag}.png")
        app.after(100, app.destroy)

    app.attributes("-topmost", True)  # 截圖時不被其他視窗擋住
    app.lift()
    app.focus_force()
    app.after(1500, step1)
    app.mainloop()
    lines.append("RESULT " + ("PASS" if ok else "FAIL"))
    (out / f"uitest{tag}.txt").write_text("\n".join(lines), encoding="utf-8")
    return 0 if ok else 1

if __name__ == "__main__":
    if "--selftest" in sys.argv:
        i = sys.argv.index("--selftest")
        sys.exit(selftest(sys.argv[i + 1] if len(sys.argv) > i + 1 else "selftest-out"))
    if IS_WIN:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    register_fonts()
    if "--uitest" in sys.argv:
        i = sys.argv.index("--uitest")
        scr = sys.argv[sys.argv.index("--screen") + 1] if "--screen" in sys.argv else ""
        sys.exit(uitest(sys.argv[i + 1] if len(sys.argv) > i + 1 else "uitest-out", scr))
    App().mainloop()
