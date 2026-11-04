# -*- coding: utf-8 -*-
"""產生轉換工具的用途預設 assets/presets.json

來源：
  1. 電商 SKU 命名規範（商品圖／銷售長圖／Slider）——手寫在 CUSTOM_TOP
  2. 網站（WordPress／WooCommerce）建議尺寸——Moksa Web 建議值，手寫在 WEB_SITE
  3. 社群／LINE／廣告／電商平台——讀 data/sizes.json（2026-10-02 查核）
用法：python scripts/gen_presets.py [sizes.json 路徑，預設 data/sizes.json]
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
SIZES = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE.parent / "data" / "sizes.json"

SLIDER = [["slider", 2560, 1440], ["sliderpc", 1920, 1080], ["slidertablet", 1200, 675], ["slidermobile", 800, 450]]
CENTER80 = [0.1, 0.1, 0.1, 0.1]  # 比例安全區（左上右下）

CUSTOM_TOP = [
    # 類別：電商 SKU 規範
    dict(key="web_product", cat="電商 SKU 規範", label="商品圖（首圖＋特色圖）2000×2000", naming="product",
         fmt="webp", quality=82, limit_kb=0, resize=["pad", 2000, 2000],
         hint="第 1 張命名為 SKUpic（首圖），其餘 SKUpic1、pic2…（特色圖）。補白邊成 2000×2000，商品不會被裁掉。"),
    dict(key="web_feature", cat="電商 SKU 規範", label="商品特色圖 2000×2000", naming="feature",
         fmt="webp", quality=82, limit_kb=0, resize=["pad", 2000, 2000],
         hint="命名為 SKUpic1、pic2…；要接續補圖時調整「起始號」。"),
    dict(key="web_sale", cat="電商 SKU 規範", label="銷售長圖（不限尺寸）", naming="sale",
         fmt="webp", quality=82, limit_kb=0, resize=["none", 0, 0],
         hint="命名為 SKUsale1、sale2…；不調整尺寸（WebP 單邊上限 16383 px，超過自動縮小）。"),
    dict(key="web_slider", cat="電商 SKU 規範", label="Slider 輪播（一次輸出 4 種尺寸）", naming="slider",
         fmt="webp", quality=82, limit_kb=500, multi=SLIDER, safe=CENTER80,
         hint="一張 16:9 原圖輸出 slider 2560×1440（網站上傳）、sliderpc、slidertablet、slidermobile。"
              "活動 Slider 的 SKU 欄填「年份＋活動代稱」。文字請放在虛線安全區內。"),
]

WEB_SITE = [
    # 類別：網站 WordPress（Moksa Web 建議值）
    dict(key="wp_featured", label="部落格特色圖 1200×675", fmt="webp", quality=80, limit_kb=200,
         resize=["cover", 1200, 675], hint="16:9，置中裁切。"),
    dict(key="wp_og", label="OG 分享圖 1200×630", fmt="jpg", quality=85, limit_kb=300,
         resize=["cover", 1200, 630], safe=[135, 55, 135, 55],
         hint="FB、LINE 分享預覽用 JPG 較保險；部分 App 會裁成 2:1 或 1:1，重點放中間。"),
    dict(key="wp_content", label="文章內文圖（寬 1200）", fmt="webp", quality=80, limit_kb=200,
         resize=["width", 1200, 0], hint="寬 1200、高度等比；超過上限會先降品質再縮尺寸。"),
    dict(key="wp_portfolio", label="作品集／案例截圖 1024×640", fmt="webp", quality=82, limit_kb=120,
         resize=["fit", 1024, 640], hint="16:10，等比縮放不裁切。"),
    dict(key="woo_main", label="WooCommerce 商品主圖 1200×1200", fmt="webp", quality=82, limit_kb=300,
         resize=["pad", 1200, 1200], hint="1:1，補白底，商品不會被裁掉。"),
    dict(key="woo_thumb", label="WooCommerce 縮圖／分類圖 600×600", fmt="webp", quality=82, limit_kb=80,
         resize=["pad", 600, 600], hint="1:1，補白底。"),
    dict(key="wp_banner", label="內頁頁首橫幅 1920×600", fmt="webp", quality=82, limit_kb=300,
         resize=["cover", 1920, 600], safe=[480, 0, 480, 0],
         hint="手機會裁掉左右兩側，文字請放在中間的虛線框內。"),
    dict(key="wp_logo", label="Logo（寬 600，透明 PNG）", fmt="png", quality=100, limit_kb=50,
         resize=["width", 600, 0], hint="保留透明背景，不裁切。"),
    dict(key="wp_favicon", label="Favicon 網站圖示 512×512", fmt="png", quality=100, limit_kb=50,
         resize=["pad", 512, 512], hint="補透明成正方形；WordPress 會自動產生小尺寸。"),
]
for p in WEB_SITE:
    p.update(cat="網站 WordPress", naming="generic", slug=True)

# 自訂（不自動套用設定）
CUSTOM_END = [
    dict(key="custom_keep", cat="自訂", label="保留原檔名", naming="keep", apply=False,
         hint="下方格式、品質、尺寸全部自己設定。"),
    dict(key="custom_serial", cat="自訂", label="名稱＋流水號", naming="serial", apply=False,
         hint="檔名＝名稱＋符號＋號碼，例如 banner-01、banner-02。"),
]

# 使用者提供的 LINE 規範（優先於 sizes.json 的同類項目）
LINE_SPEC = [
    dict(key="line_carousel", label="多頁訊息 1540×1000", fmt="jpg", quality=90, limit_kb=10240,
         resize=["cover", 1540, 1000], hint="比例 1.54:1，置中裁切；10 MB 以下。"),
    dict(key="line_rich", label="圖文訊息 1040×1040", fmt="jpg", quality=90, limit_kb=10240,
         resize=["cover", 1040, 1040], hint="比例 1:1；10 MB 以下。"),
    dict(key="line_rich2x", label="圖文訊息 高清 2080×2080", fmt="jpg", quality=90, limit_kb=10240,
         resize=["cover", 2080, 2080], hint="1040×1040 的兩倍，畫面較清晰；10 MB 以下。"),
    dict(key="line_menu_l", label="圖文選單 大（一次輸出 3 種尺寸）", fmt="jpg", quality=88, limit_kb=1024,
         multi=[["", 2500, 1686], ["", 1200, 810], ["", 800, 540]],
         hint="輸出 2500×1686、1200×810、800×540，檔名後加尺寸；每張 1 MB 以下（超過自動降品質）。"),
    dict(key="line_menu_s", label="圖文選單 小（一次輸出 3 種尺寸）", fmt="jpg", quality=88, limit_kb=1024,
         multi=[["", 2500, 843], ["", 1200, 405], ["", 800, 270]],
         hint="輸出 2500×843、1200×405、800×270，檔名後加尺寸；每張 1 MB 以下（超過自動降品質）。"),
    dict(key="line_image", label="一般圖片訊息（寬 1024）", fmt="jpg", quality=90, limit_kb=10240,
         resize=["width", 1024, 0], hint="寬度 1024、長度不限；10 MB 以下。"),
]
for p in LINE_SPEC:
    p.update(cat="LINE 官方帳號", naming="generic")
LINE_SKIP = {"line_rich_message", "line_rich_menu_large", "line_rich_menu_compact", "line_image_message"}

GROUP_CAT = {
    "Instagram": "Instagram", "Facebook": "Facebook", "LINE": "LINE 官方帳號",
    "X / Threads": "X／Threads", "Pinterest / YouTube / TikTok": "YouTube／Pinterest／TikTok",
    "Google Ads": "Google 廣告", "E-commerce (TW)": "台灣電商平台", "E-commerce (Global)": "國際電商平台",
    "Web / Open Graph": "網站 WordPress",
}
CAT_ORDER = ["電商 SKU 規範", "網站 WordPress", "LINE 官方帳號", "Instagram", "Facebook", "X／Threads",
             "YouTube／Pinterest／TikTok", "Google 廣告", "台灣電商平台", "國際電商平台", "自訂"]
CONF = {"official": "官方規格", "widely-cited": "業界常用", "project": "實測"}
# 不能出現在工具裡的字（例如客戶品牌）：一行一個正規表示式，寫在 scripts/brand_words.local.txt（不進 repo）。
# 原始資料 sizes.json 若含這些字，產生 presets.json 時會自動拿掉；最後再檢查一次有沒有殘留。
_BW_FILE = HERE / "brand_words.local.txt"
_BW = [ln.strip() for ln in (_BW_FILE.read_text(encoding="utf-8").splitlines() if _BW_FILE.exists() else [])
       if ln.strip() and not ln.startswith("#")]
BRAND_ANY = re.compile("|".join(_BW), re.I) if _BW else None
BRAND_WORDS = re.compile("|".join(rf"（?\(?\s*(?:{w})\s*[^）)]*[）)]?|(?:{w})" for w in _BW), re.I) if _BW else None


def debrand(s: str) -> str:
    s = s or ""
    if BRAND_WORDS:
        s = BRAND_WORDS.sub(lambda m: "（實測安全區）" if "安全" in m.group(0) else "", s)
    return re.sub(r"\s{2,}", " ", s).strip()


def from_sizes(x: dict) -> dict | None:
    if x["id"] in LINE_SKIP or x["id"] == "og_image":
        return None
    fm = [f.lower() for f in x.get("formats") or []]
    fmt = "jpg" if ("jpg" in fm or "jpeg" in fm) else ("png" if "png" in fm else ("webp" if "webp" in fm else None))
    if not fmt:
        return None
    name = debrand(x.get("name_zh") or x.get("name_en"))
    w, h = int(x["w"]), int(x["h"])
    is_product = x["group"].startswith("E-commerce") and any(k in name for k in ("商品圖", "主圖", "規格圖"))
    no_pad = x["id"].startswith("momo")  # momo 不可白邊／黑邊
    mode = "pad" if is_product and not no_pad else "cover"
    note = debrand(x.get("note_zh") or "")
    parts = [f"{w}×{h}（{x.get('ratio') or ''}）", "補白邊不裁切" if mode == "pad" else "置中裁切"]
    if x.get("max_kb"):
        parts.append(f"上限 {x['max_kb']:,} KB")
    parts.append(CONF.get(x.get("confidence"), ""))
    hint = "，".join(p for p in parts if p) + ("。" + note if note else "")
    safe = x.get("safe")
    key = BRAND_ANY.sub("measured", x["id"]) if BRAND_ANY else x["id"]
    source = "" if x.get("confidence") == "project" else x.get("source", "")
    return dict(key=key, cat=GROUP_CAT.get(x["group"], x["group"]),
                label=name if f"{w}×{h}" in name else f"{name} {w}×{h}", naming="generic", fmt=fmt,
                quality=90 if fmt == "jpg" else 100, limit_kb=int(x["max_kb"]) if x.get("max_kb") else 0,
                resize=[mode, w, h], safe=safe if safe and any(safe) else None, hint=hint,
                source=source, confidence=x.get("confidence", ""))


def main():
    data = json.loads(SIZES.read_text(encoding="utf-8"))
    presets = CUSTOM_TOP + WEB_SITE + LINE_SPEC
    for x in data["sizes"]:
        p = from_sizes(x)
        if p:
            if p["cat"] == "網站 WordPress":
                p["slug"] = True
            presets.append(p)
    presets += CUSTOM_END
    for p in presets:
        p.setdefault("method", 6)
    presets.sort(key=lambda p: CAT_ORDER.index(p["cat"]) if p["cat"] in CAT_ORDER else 99)
    out = {"version": data.get("checked", ""), "categories": CAT_ORDER, "presets": presets}
    dst = HERE.parent / "src" / "assets" / "presets.json"
    dst.parent.mkdir(exist_ok=True)
    dst.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    from collections import Counter
    c = Counter(p["cat"] for p in presets)
    print(f"共 {len(presets)} 個用途 → {dst}")
    for cat in CAT_ORDER:
        print(f"  {cat}: {c.get(cat, 0)}")
    bad = [p["label"] for p in presets if BRAND_ANY and BRAND_ANY.search(json.dumps(p, ensure_ascii=False))]
    print("品牌字樣殘留：", bad or "無")


if __name__ == "__main__":
    main()
