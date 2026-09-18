# Codex 啟動指令

將 `IINA_AI_SUBTITLES_SPEC.md` 與本檔案一起交給 Codex。以下內容可直接作為第一個開發訊息。

---

請閱讀同目錄的 `IINA_AI_SUBTITLES_SPEC.md`，按照規格實作 `iina-ai-subtitles`。這是一個**獨立 IINA 外掛＋自動管理的本機 AI helper**，不是 fork IINA，也不是新的播放器。

請先檢查目前 repository／工作目錄與可用環境，保留既有檔案和使用者變更。沒有 repository 時，可在指定工作目錄建立專案；不要自行建立遠端 repo、發布、上傳素材或執行付費服務。

## 這一輪從 Phase 0 開始

先驗證最可能讓產品失敗的地方，不要第一輪就把所有 UI、endpoint 和空殼類別建滿。

1. 偵測目前 macOS／Apple Silicon／RAM／IINA／嵌入 mpv／FFmpeg／Python 和模型資產，交付可重現的 `doctor`。
2. 先驗證 LiteRT-LM Python＋Gemma 4 E2B 的真實 audio input、原語言 transcription 和文字 translation；如有確認的阻礙，再評估 MLX-VLM。固定實際 model artifact、revision、量化與依賴版本。
3. 驗證 Qwen3-ForcedAligner-0.6B 的可行 Apple Silicon 路線，產出原文對齊時間，再讓翻譯繼承 source cue 的時間。
4. 用可用且有權使用的 3–5 分鐘素材跑完整管線，分別記錄 cold/warm、各 stage、完整 RTF、記憶體與 sample SRT。沒有素材時不要掃描私有目錄；先建立測試入口，再明確說明需要的輸入。
5. 做最小 IINA smoke plugin，驗證選定音軌 mapping、字幕增量 `sub-add`／`sub-reload`、reload 後 track ID，以及播放／暫停事件。特別核實 `Info.json` 的 `globalEntry` 欄位，不照抄教學頁的 `global` 範例。
6. 寫入 `docs/feasibility.md`、`docs/runtime-decision.md` 和測量結果。環境允許就實際執行，不只回覆實作計畫。

## 必須守住

- 主模型以 E2B 為優先；不要偷偷升級 12B、改雲端、依賴 Eloquent 安裝或擷取其私有模型。
- 本機可 seek 影片為 MVP；不加入直播、補幀、TTS、OCR、影片聊天或跨平台工程。
- 只需要準備目前播放點附近的字幕，不能先處理整片才開播。
- 模型保持載入，一個共享 inference worker；不每段重載、不每視窗一套模型。
- timestamps 必須由音訊與原文對齊，不能由模型猜或平均分配字數。
- metadata 是線索，`unknown` 必須是合法結果；不能預設英文。
- `mpv track ID` 不等於 FFmpeg stream index；prepared coverage 不等於 installed coverage。
- 不將 mock、Linux／其他 Mac 測量、單純 tokens/s 當成使用者 M3 Max 的真機證據。
- 5–10 秒是 warm startup 目標，不是可宣稱已達到的性能。
- 安裝外掛／helper、下載大型權重前，先列出必要權限、空間與來源；不得修改全域 Python 或安全設定。

## 環境不足時

可以實作純邏輯、adapter、fake backend、測試 fixtures 與可在目標 Mac 執行的命令；真機驗證欄位標 `blocked`／`not_run`。不要生成假測量結果，也不要讓 production pipeline 靜默用 fake backend。

## 回報格式

請在第一輪回報實際完成項目、修改檔案、實際執行的命令、真實結果、尚未驗證的部分，以及下一個最小可交付步驟。只在需要改變產品範圍、額外權限／付費、無法取得必要資源時詢問；其他細節採 spec 的預設。

Phase 0 通過後，繼續 Phase 1 的最小真實垂直流程，再逐步加入緩衝、seek、快取、生命週期與安裝 UX。每階段都要有可運行證據，不把「建立檔案」當成「功能已完成」。
