# 01 官方韌體 4.01 解析

日期：2026-10-25。範圍只有下載、驗證、解包和靜態字串分析，沒有修改韌體。

## 來源與驗證

| 項目 | 值 |
|---|---|
| 下載 | Sony 官網的 `Update_ILCE7RM2V401.exe` |
| 大小 | 274,158,784 bytes，與官網標示一致 |
| SHA-256 | `257690fc2a8e3cc81cc0bfb257de89de3c4cd30c846526fba20c8ebfe2210cb8` |
| 數位簽章 | Windows 驗證有效，簽署者 Sony Corporation，時間戳記 DigiCert 2022 |

## 解包

1. **fwtool 不能直接讀這個 `.exe`。** 這版更新程式在 2022 年重新簽章，`.exe` 後面接的是沒有壓縮的自訂檔案容器，不是 fwtool 認得的 LZH。
2. **先用 `tools/extract_sony_exe.py` 解開容器。** 它取出 28 個檔案，最大的是 `FirmwareData_ILCE7RM2V401.dat`。所有檔案的大小加總剛好接到簽章表之前，所以解析結果可信。`tools/scan_exe.py` 是當初用來看清楚容器結構的掃描工具。
3. **再交給 [fwtool.py](https://github.com/ma1co/fwtool.py) 處理 `.dat`。** 用 CXD90014 方式解密，再展開 tar 和各分割區的檔案系統。

## 分割區內容

| 分割區 | 內容 |
|---|---|
| nflasha3 | Linux 核心、`av-cam.bin`（影像處理核心）、initrd、鏡頭像差資料 |
| nflasha5 | WBI 快速開機記憶體快照。對照機身讀出的內容，它是隨韌體出廠的，不是在機身上產生的 |
| nflasha15 | 相機的 Linux 使用者空間：`libObj.so`（主程式庫）、`libScalarDaemon.so`（PMCA App 和相機之間的橋樑） |
| nflasha16 | PMCA App 執行用的 Android 系統 |
| 0110_backup | 各地區的預設設定，BK4 格式，每份 19,466 項屬性 |

## 和色彩有關的發現

- **App 的 API 會轉成內部參數。** `libScalarDaemon.so` 把 App 的呼叫轉成內部參數：
  - RGB 矩陣是 `PARAMID_SYS_DATA_RGB_MATRIX_{RR..BB}_SET/ACT`。
  - 色彩深度是 `PARAMID_SYS_DATA_COLOR_DEPTH_*`。
  - 擴充 gamma 走 `MSGID_CAMERA_SET_EXTENDED_GAMMATABLE` 訊息。
- **擴充 gamma 只存在執行期。** `libObj.so` 裡只有 `PARAMID_EX_GAMMA_TABLE_POINTER` 和開關 `..._SW`，也就是一個記憶體指標加一個開關，無法用寫設定的方式保存。
- **RGB 矩陣屬於 SYS_DATA，當時懷疑可能會被保存。** [02](02-app-matrix-is-runtime-only.md) 的實驗否定了這個猜想。
- **Picture Profile 參數很齊全。** 包括原生選單沒有開放的 `PP_COLOR_CORRECT`。
- **沒有獨立的色調曲線檔。** 曲線應該編譯在 `libObj.so` 或 `av-cam.bin` 裡。

## 當時的判斷

| 做法 | 評估 |
|---|---|
| 任意 3D LUT | 沒有找到 3D LUT 處理單元，要改影像管線程式，工程最大 |
| 自訂曲線常駐 | 要改 `libObj.so` 或 `av-cam.bin`，nflasha5 開機快照也要處理，風險高 |
| 矩陣常駐 | 先驗證 App 矩陣會不會被保存，結果否定。後來改找原生風格自己的矩陣，見 [03](03-native-matrix-table.md) |
| Picture Profile | 原生功能，零風險 |

在任何寫入之前，先用 updater shell 唯讀備份了整台機身：開機程式、全部分割區和設定檔。機身內容和官方 4.01 映像逐位元組相同。那份備份含有機身序號和校正資料，所以不在這個專案裡。
