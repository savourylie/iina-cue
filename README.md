# Cue for IINA

Your videos. Your language. In sync.

People installing Cue, rather than building it, should follow [Install Cue](docs/install-cue.md). That guide uses either a double-click of the `.iinaplgz` or IINA's Install from GitHub. It has no Terminal commands. IINA may warn that a plugin "can execute other programs or applications that can harm your computer". The guide explains that warning. This runtime needs macOS 14.0 or later and about 16 GB of memory.

目前已包含 **0.1.0 開發技術預覽版**：IINA 外掛、本機 Python helper、短窗口排程、字幕快取、seek 隔離與測試。模型已安裝，真實辨識、對齊、翻譯與原生字幕顯示已跑通；**目前是可測試的開發版，尚未完成規格的 v1 驗收。**

## 檔案

| 檔案 | 用途 |
|---|---|
| `IINA_AI_SUBTITLES_SPEC.md` | 完整產品與工程規格、資料／API 契約、測試、開發階段、主要來源 |
| `CODEX_KICKOFF.md` | 可直接貼給 Codex 的第一輪開發指令，要求先做可行性驗證 |

## 使用

將兩份文件放入 Codex 可以讀取的專案目錄，或直接附加兩份文件。以 `CODEX_KICKOFF.md` 的指令開始。已有 repository 時，先保存文件並檢查現有內容，不要覆寫既有專案。

規格先聚焦本機影片的原文／翻譯字幕、語言偵測與準確對齊，透過前瞻緩衝邊看邊算。AI 補幀不在此版本範圍。

**實測效能（M3 Max、180.128 秒合成語音）：** 繁中完整流程冷啟動 55.8 秒、暖機 51.3 秒（RTF 0.285，約 17.1 秒／分鐘）；原文暖機約 30.7 秒（RTF 0.171）。四語言測試都完成真實管線，但自然對話品質仍待驗收，韓文樣本有辨識錯字。素材不同，不能直接宣稱比 dora 快。詳見 [可行性報告](docs/feasibility.md) 和 [驗收表](docs/acceptance.md)。

## 開發版使用

```sh
scripts/setup-dev                  # 專案 .venv + npm，無模型下載
scripts/doctor
scripts/setup-models               # 只列來源、大小、條款
# 確認同意後才執行：
scripts/setup-models --accept-download
scripts/test
npm run build
```

安裝包：`dist/Cue.iinaplugin-0.1.0.iinaplgz`。此機已用 IINA 官方 CLI 建立開發連結，IINA 設定 → Plugins 已辨識 Cue，已啟用供本機驗證。模型設定已完成；字幕預設保留影片原語言，側欄 **Subtitle language** 會依辨識結果顯示如 **English (original)**，也可改選 Traditional Chinese、Simplified Chinese、English、Japanese 或 Korean。側欄 **Subtitle size** 滑桿會即時調整 Cue 字幕大小，停止 Cue 時還原播放器原本的字級。影片預設在字幕準備期間繼續播放，字幕就緒後自動接上；可勾選 **Pause until captions are ready** 與切換 **White text on a translucent black background**（預設開啟）。整個外掛介面使用英文；IINA 外掛選單另提供手動啟用、停止、來源語言、重試與部分匯出。

安裝包不內含 Python、FFmpeg 或模型；本版 helper 預設指向建置此包的專案路徑，搬移專案後須重建或更新外掛設定。這是開發版流程，免 Terminal 安裝器尚未實作。[安裝與復原](docs/install.md)

```sh
scripts/benchmark --media /absolute/path/movie.mp4 --duration-ms 180000 --mode zh-TW --source en
scripts/cue-helper cache status
scripts/cue-helper export --media /absolute/path/movie.mp4 --target zh-TW --output /absolute/path/subtitles.srt
scripts/cue-helper shutdown
```

不提供素材路徑就不搜尋私人影片。完整 benchmark 預設同一常駐模型跑 cold／warm 兩輪。尚未完整覆蓋的匯出會使用 `.partial.srt` 與 coverage JSON。

## 換一台 Mac 繼續開發

從 GitHub clone 後，依照 [新機設定步驟](docs/install.md#another-mac) 安裝 IINA、`uv`、Node/npm 與 FFmpeg，於新 checkout 執行 `scripts/setup-dev`，檢視模型來源與條款後再執行 `scripts/setup-models --accept-download`，最後用 IINA 官方 CLI link 新 checkout 的 `plugin/`。`.venv`、模型、快取、生成測試媒體、診斷結果及打包檔都是本機產物，沒有上傳到 Git；新機會重建它們。打包時會寫入目前 checkout 的 helper 絕對路徑，所以移動專案後須重新 build。

## 已實作的效能設計

- 一個共享、長駐的 inference 子程序，控制 API 可持續回應。
- 先處理播放位置附近 10 秒，後續窗口 16 秒；達到約 60 秒前瞻後停算，最多超出一個 16 秒窗口。
- 原文和翻譯分層快取；改目標語言時重用已完成的原文／對齊。
- 每批最多 8 個 source cue 翻譯，保留原來 ID 與時間；不重新編造 timestamps。
- seek 以 epoch 隔離，過期結果可進快取，但不能回報為新位置已載入。

效能數據包含真實模型與 SRT 寫入；不包含播放器安裝確認時間。dora 的腳本與環境未修改。

## 目前限制

- 模型資產共約 3.56 GB；另有編譯快取。使用同一 E2B 的完整多模態版本，GPU-only 檔缺少音訊編碼器。
- 自動啟用預設關閉；等待字幕的暫停模式可手動勾選，字幕就緒後仍由使用者按播放，不會自動解除使用者的暫停。
- 目前只把「全為零的數位靜音」直接列為無語音；Silero VAD／音樂負例驗收尚未完成。
- 日／韓 tokenizer 已安裝並固定版本；四語言合成語音通過流程測試，真人語音品質皆未驗收。
- 非零 audio-delay、外接音訊與串流來源不支援。
- 100 次真 IINA 重載已通過，不累積軌道；全螢幕閃爍與 20 分鐘順播尚待驗收。
- 一支使用者指定的 14:03 本機影片暴露純數字 cue 的翻譯誤判，以及接合先前快取時的對齊文字衝突。兩處已修正；本機 helper 從 20 秒逐段處理到片尾，IINA 已載入該區間的原文字幕，並在尾段看見字幕。尚未宣稱整片連續播放驗收。
- 完整安裝器、LRU 上限、睡眠喚醒復原、模型自動下載 UI、簽署／公證仍未交付。
