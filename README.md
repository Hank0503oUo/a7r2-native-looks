# A7R II Native Looks

把富士、徠卡等色彩風格，直接寫進 Sony A7R II **原生**創意風格和 Picture Profile 的色彩矩陣。

寫入之後不需要開任何 App：機身拍的 JPEG 會直接是新的顏色。錄影、PC 遙控和 Monitor+ 走的也是同一條原生處理流程，理論上同樣生效，但還沒有分別實測。

這個專案記錄整個摸索過程，也收錄每一步實際用過的工具。核心是機身設定裡一張 1536 bytes 的色彩矩陣表：屬性 `0x00030001`，裡面有 17 組 3x3 矩陣。

> **風險自負。** 寫入需要讓相機進入韌體更新模式（updater mode），這不是 Sony 支援的操作。
> 目前只在一台 ILCE-7RM2、韌體 4.01 上驗證過。其他機型或韌體的表格位置可能不同，工具遇到格式不符會拒絕寫入。
> 本專案與 Sony、FUJIFILM、Leica 無關。

## 結果

v2（2026-11-01 寫入）的對照如下。誤差是在校正色卡上，和官方 LUT 目標相比的色度誤差，乘以 1000，越小越接近。

| 相機選單 | 換成 | 依據 | v2 | v1 | 原廠風格 |
|---|---|---|---|---|---|
| 創意風格「中性」 | 富士 PROVIA | 富士官方 LUT | 52 | 105 | 77 |
| 創意風格「鮮艷」 | 富士 Velvia | 富士官方 LUT | 54 | 119 | 87 |
| 創意風格「人像」 | 富士 ASTIA | 富士官方 LUT | 52 | 102 | 89 |
| 創意風格「清晰」 | 富士 REALA ACE | 富士官方 LUT | 62 | 115 | 104 |
| 創意風格「深色」 | 富士 Classic Chrome | 富士官方 LUT | 39 | 78 | 70 |
| 創意風格「日落」 | 富士 Classic Neg | 富士官方 LUT | 56 | 103 | 129 |
| PP4 | 富士 ETERNA | 富士官方 LUT | 24 | 70 | 76 |
| 創意風格「風景」 | 徠卡 Classic | 徠卡官方 L-Log LUT | 62 | 100 | 90 |
| PP5、PP6 | 徠卡 Natural | 徠卡官方 L-Log LUT | 36 | 103 | 73 |
| 創意風格「淡色」 | Sony FL（近似） | Recipe Lab 社群配方 | | | |
| PP1、PP3 | Sony IN（近似） | Recipe Lab 社群配方 | | | |
| 創意風格「秋葉」 | 哈蘇 HNCS（近似） | Recipe Lab 社群配方 | | | |

- **沒有改動的：** 「標準」「夜景」「棕褐色」和 PP2（四者共用同一組），以及 PP7 S-Log2。
- **誤差是模型預測值。** 寫入後的實拍驗證還在進行中。
- **矩陣本身在 [`looks/v2.json`](looks/v2.json)。**

## 思路

1. **問題。** 膠片工坊這類機內 App 用 `setRGBMatrix` 和擴充 gamma 套濾鏡，只在 App 裡有效。一接手機 Monitor+ 或 PC 遙控，相機就會離開 App，濾鏡也跟著消失。
2. **想法。** 如果顏色能存在機身設定裡，原生模式就會直接生效，也就不需要 App。
3. **韌體分析。** 解開官方 4.01 更新檔後發現，App 的 RGB 矩陣對應到 `PARAMID_SYS_DATA_RGB_MATRIX_*`，擴充 gamma 只是執行期的記憶體指標。詳見 [docs/01](docs/01-firmware-analysis.md)。
4. **實驗一（否定）。** App 設定的矩陣在離開 App 後就被平台重設，設定檔裡也找不到它，所以 App 這條路無法常駐。詳見 [docs/02](docs/02-app-matrix-is-runtime-only.md)。
5. **轉向。** 原生風格本身一定也有色彩矩陣。在機身設定的 19,466 項屬性裡搜尋 3x3 矩陣，找到 `0x00030001`。它由 768 個 int16 組成，含 17 組矩陣，1.0 = 1024，每一列加總為 1024。
6. **實驗二（寫入與對應）。** 把每一組換成不同色相的測試矩陣，在每個風格和 PP 下各拍一張白色畫面，從偏色判斷它用哪一組，色相打亂後再拍一輪確認。結果證實原生處理流程確實讀這張表，寫入、讀回、存檔和還原也都可行。詳見 [docs/03](docs/03-native-matrix-table.md)。
7. **v1（失敗）。** 直接沿用膠片工坊的富士矩陣，結果過飽和，白牆偏黃綠。原因是那些矩陣是對 WDR-709 畫面擬合的，不是對這顆感光元件。詳見 [docs/04](docs/04-v1-and-why-it-failed.md)。
8. **v2。** 拍 RAW+JPEG 色卡，把相機建模成 `JPEG = T_s(M_s · P · raw)`。目標由同一張 RAW 算出：先轉成 F-Log2 或 L-Log，再套官方 LUT。解矩陣時限制每列加總為 1，讓灰色維持中性，同時保留相機原本的亮度，最後再用 Levenberg–Marquardt 微調。詳見 [docs/05](docs/05-v2-calibration.md)。
9. **寫入與還原。** 先讀出並保存自己相機的原始表，所有寫入都從它組出來。詳見 [docs/06](docs/06-write-and-restore.md)。

## 做不到的事

- **只有矩陣，沒有曲線。** 亮度和對比仍是各風格原本的色調曲線，LUT 的曲線部分做不出來。可以在該風格裡調對比 ±3 自行補償。
- **只能做線性變換。** 3x3 矩陣無法重現 LUT 裡只針對特定色相的扭曲，例如單獨偏移膚色或天空。剩下的誤差主要來自這部分。
- **S-Log3 做不到。** S-Log3 的差別在曲線，不在矩陣。
- **不影響 RAW 和黑白。** RAW 檔不受影響。「黑白」輸出本來就是單色，也不受影響。

## 快速開始

需要的東西：
- Windows 電腦。
- [Sony-PMCA-RE](https://github.com/ma1co/Sony-PMCA-RE) v0.18 的 Windows 版 `pmca-console.exe`。
- Python 3。`table.py` 只用標準函式庫。

相機 USB 設為 MTP，電池充滿。

```powershell
# 1. 讀出並保存「你自己」的原始表（只讀）
python nativelooks\table.py read-cmds -o cmds_read.txt
powershell -ExecutionPolicy Bypass -File windows\run-updatershell.ps1 -Commands cmds_read.txt -Log pmca_read.log
python nativelooks\table.py extract pmca_read.log -o my_original.bin
python nativelooks\table.py show my_original.bin          # 另外備份 my_original.bin

# 2. 組出新表；只會改 looks 檔列出的槽，預設拒絕動「標準」和 S-Log2
python nativelooks\table.py build --base my_original.bin --looks looks\v2.json -o looks_v2.bin

# 3. 寫入：讀、寫、讀回、存檔；接著核對
python nativelooks\table.py write-cmds looks_v2.bin -o cmds_write.txt
powershell -ExecutionPolicy Bypass -File windows\run-updatershell.ps1 -Commands cmds_write.txt -Log pmca_write.log
python nativelooks\table.py verify pmca_write.log --before my_original.bin --after looks_v2.bin

# 還原：把 my_original.bin 寫回去
python nativelooks\table.py write-cmds my_original.bin -o cmds_restore.txt
powershell -ExecutionPolicy Bypass -File windows\run-updatershell.ps1 -Commands cmds_restore.txt -Log pmca_restore.log
```

Windows 跳出系統管理員權限視窗時請按「是」。相機會進入更新模式，大約 20 秒到 1 分半後自動重開。

如果要用自己的相機重新擬合，流程見 [docs/05](docs/05-v2-calibration.md)。擬合需要 `pip install -r requirements.txt`，官方 LUT 請自行從富士、徠卡官網下載。

## 目錄

| 路徑 | 內容 |
|---|---|
| `nativelooks/table.py` | 讀取、顯示、組合、產生指令、核對 `0x00030001` 表；也能產生對應實驗用的測試表 |
| `nativelooks/slotmap.py` | 從兩輪測試照片判斷每個風格用哪一組矩陣 |
| `calibration/` | 色卡產生器、相機建模（`build_model.py`）、矩陣擬合（`fit_looks.py`）、v1 配方（`recipes_v1.py`） |
| `looks/` | v1 和 v2 的矩陣 |
| `windows/run-updatershell.ps1` | 以系統管理員身分執行 PMCA updater shell，並保存記錄 |
| `tools/` | Sony 更新檔解包（`extract_sony_exe.py`、`scan_exe.py`）、在 Backup.bin 中找矩陣表（`find_matrix_tables.py`） |
| `experiments/slot-mapping/` | 對應實驗的測試計畫、拍攝清單和結果 |
| `docs/` | 每一步的紀錄 |

## 刻意不收錄的東西

- **Sony 的資料。** 包括韌體、機身備份和原廠矩陣表。所有寫入都從你自己讀出的表組合出來。
- **官方 LUT 檔。** 富士和徠卡的 LUT 請到官網下載。
- **照片。** 不收錄任何拍攝的照片。

## 致謝

- [ma1co/Sony-PMCA-RE](https://github.com/ma1co/Sony-PMCA-RE)：updater shell、備份解析。
- [ma1co/fwtool.py](https://github.com/ma1co/fwtool.py)：韌體解包。
- [膠片工坊 sony-a5100-film-studio](https://github.com/ukiki0718-netizen/sony-a5100-film-studio)：v1 的富士矩陣。
- Recipe Lab：Sony FL/IN、徠卡、哈蘇的社群配方。
- FUJIFILM 的 GFX ETERNA 55 3D LUT、Leica 的 L-Log LUT 和 L-Log Reference Manual。

程式碼以 MIT 授權釋出，見 [LICENSE](LICENSE)。Sony、FUJIFILM、Leica、Hasselblad 等名稱是各自公司的商標。
