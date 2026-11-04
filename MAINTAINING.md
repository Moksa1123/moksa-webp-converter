# 維護說明

## 資料來源
| 內容 | 位置 |
|---|---|
| 各平台尺寸（IG、FB、LINE、X、YouTube、Google 廣告、蝦皮、momo、國際電商） | `data/sizes.json`（2026-10-02 查核；`confidence` 欄：official 官方、widely-cited 業界常用、project 實測） |
| 網站 WordPress 建議尺寸 | `scripts/gen_presets.py` 的 `WEB_SITE` |
| 電商 SKU 命名（pic／picN／saleN／slider…）與 LINE 官方帳號規格 | `scripts/gen_presets.py` 的 `CUSTOM_TOP`、`LINE_SPEC` |

`src/assets/presets.json` 由 `python scripts/gen_presets.py` 產生，不要手改。
如果原始資料含有不該出現在工具裡的字（例如客戶品牌），把它們寫在 `scripts/brand_words.local.txt`（一行一個正規表示式，不進 repo），產生時會自動拿掉，最後一行會印出「品牌字樣殘留：無」。

## 常見維運
- **平台規格變了**：改 `data/sizes.json` → `python scripts/gen_presets.py` → 發版（見 README）。
- **某個客戶要專屬尺寸或命名**：給他一份 `presets.json`，Windows 放在 exe 旁邊，Mac 放在 `~/Library/Application Support/Moksa Web/`，不必重新打包。
- **改品牌色或主題**：改 `scripts/prepare_assets.py` 的色碼 → 執行它（需 `pip install sv-ttk fonttools`）→ 發版。
- **轉完變大**：原圖已經壓過時會發生，品質設 75～85，或勾「轉完比原檔大就不保留」。
- **Mac 打不開**：沒有 Apple 簽章，照 `docs/使用說明_Mac.txt` 放行。要免除這一步需申請 Apple Developer（每年 99 美元），在 workflow 加簽章與公證。
- **zip 解出來中文檔名亂碼**：zip 的檔名是 UTF-8 並設了 bit 11（標準做法）。檔案總管、7-Zip、tar、Expand-Archive 都正確；Git Bash 附的舊版 `unzip` 會亂碼。

## 可以再做的
- Mac 版簽章與公證、Windows 安裝程式
- 手機直式 1080×1350 專用用途、Slider 多張批次、自訂後綴命名
