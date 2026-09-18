# IINA AI Subtitles — 產品與工程規格

**版本：** 1.0  
**規格日期：** 2026-09-19  
**狀態：** 可交付開發；硬體效能與原生整合須先通過 Phase 0 驗證  
**讀者：** Codex／實作者、產品負責人 Calvin  
**暫定專案名稱：** `iina-ai-subtitles`（不是既有產品或 repository）

> 在現有 IINA 中，安裝並設定一次，即可在觀看影片時，自動辨識音軌語言，逐段產生時間對齊的原文或翻譯字幕。只需準備播放位置附近的一小段，不必先處理完整影片。

本文件可獨立閱讀，不需要取得原始對話。`MUST` 是功能或正確性要求；`SHOULD` 是預設設計；`TARGET` 是待實測的效能／品質目標，不是已測得數據。除「外部能力與來源」之外，本文的數值、API、目錄與狀態名稱均是**本專案的設計契約**，不是宣稱 IINA 或第三方已經提供相同功能。

---

## 0. 給實作者的摘要

### 0.1 已決定的方向

| 項目 | 決定 |
|---|---|
| 交付形式 | 獨立 IINA JavaScript 外掛＋由外掛管理的本機 helper；不 fork IINA、不要求合併上游 |
| 主要裝置 | 使用者的 MacBook Pro 14 吋、M3 Max；RAM、GPU 核心數、macOS 與 IINA 版本在本機偵測，不從型號推定 |
| 初始平台 | Apple Silicon macOS；最低 macOS 版本由實際 runtime／wheel 相容性決定並記錄 |
| 播放來源 | MVP：本機可 seek、非 DRM 的影片檔，優先 MP4／MKV／MOV |
| 功能 | 原語言 transcription、translation、自動語言辨識、字幕時間對齊、漸進生成、快取、seek 後優先處理 |
| 主模型 | 優先評估公開的 **Gemma 4 E2B instruction-tuned**；不預設改成 12B |
| 推論方式 | 本機；無雲端 API、無帳號、無字幕／音訊上傳 |
| 時間軸 | 原文 forced alignment，再由翻譯繼承 cue 時間；不請文字模型猜 timestamps |
| 使用體驗 | 暖模型狀態下，首次字幕準備以 5–10 秒為目標；播放中保持領先緩衝 |
| 啟動 | 初次安裝設定後，不需要另外開 terminal、Python、模型 server 或 Eloquent |
| 第一個開發任務 | 驗證真實音訊推論、對齊、端到端速度，以及 IINA 增量字幕更新；不是先做漂亮設定頁 |

### 0.2 不可違反的限制

- 不得要求「完整影片全部算完」才開播。
- 不得把 chunk 起訖平均分配給文字，冒充精準對齊。
- 不得把晚到數秒的字幕當作正常即時模式。
- 不得在每個 chunk 重新載入模型，或讓每個 IINA 視窗各載入一套 GPU 模型。
- 不得把 mpv audio track ID 當成 FFmpeg stream index。
- 不得以最後一條字幕的結束時間，推斷中間所有區間都已處理。
- 不得因語言 metadata 缺失、無聲片頭或模型失敗，就假定是英文。
- 不得在使用者手動暫停、停用字幕或切換字幕後，偷偷恢復播放或搶回字幕選擇。
- 不得把 mocked tests、其他 Mac 的 tokens/s，當成 M3 Max 實測成功。
- 不得為了「完成」而偷偷切雲端、加入 12B、修改 IINA 原始碼或要求 Eloquent 常駐。

---

## 1. 需求、範圍與成功定義

### 1.1 背景

使用者實際使用 Eloquent 時，認為介面標示的「Gemma 4 2B Model」語音效果已經足夠好，希望把類似能力放入 IINA。不希望投入播放器核心開發，也不希望觀看前人工啟動多套工具。

**不要把這個觀察解讀為已證實 Eloquent 的精確 checkpoint、量化格式、prompt、前處理或 runtime。** 本專案使用可合法取得並固定版本的公開模型，不重用 Eloquent 的私有資源。Eloquent 的 App 是否開源、是否公開內部 API，不是本專案的依賴。

### 1.2 MVP 必備需求

| ID | 需求 | 可觀察結果 |
|---|---|---|
| FR-01 | 生成原文字幕 | 可輸出與載入原語言 SRT |
| FR-02 | 生成翻譯字幕 | 預設輸出繁體中文／台灣用語；可選英文 |
| FR-03 | 自動識別語言 | 顯示偵測結果、資訊來源與不確定狀態；可手動覆寫 |
| FR-04 | 準確時間對齊 | cue 使用音訊對齊結果，不由翻譯模型生成時間 |
| FR-05 | 漸進生成 | 第一個可播放區間完成後即可觀看，後續持續提前處理 |
| FR-06 | seek | 已有快取直接用；沒有快取則優先生成新位置附近 |
| FR-07 | 音軌切換 | 依實際選定音軌生成，不混用配音語言、快取或舊任務 |
| FR-08 | 快取與重開 | 重用已完成區間；影片無須完整處理也能保存進度 |
| FR-09 | 自動生命週期 | helper 按需啟動、模型重用、退出後釋放資源 |
| FR-10 | 錯誤恢復 | 可重試、停止、繼續無字幕播放；不無限暫停 |
| FR-11 | 本機隱私 | 模型備妥後，斷網仍可完成整個字幕流程 |
| FR-12 | 可安裝交付 | 提供可安裝外掛、helper 安裝流程與版本／環境診斷 |
| FR-13 | 現有字幕共存 | 不覆蓋現有檔案；不搶使用者選定字幕；排除只有 forced/signs 的不完整字幕 |
| FR-14 | 部分匯出 | 可匯出已生成區間，明確標示 partial，不假裝是完整影片字幕 |

### 1.3 支援語言

MVP 的**端到端驗收來源語言**為 `en`、`ja`、`zh`、`ko`。這是本專案的測試承諾範圍，不代表底層模型只有四種語言。

輸出：`original`、`zh-TW`、`en`。預設 `zh-TW`。其他語言可在能力檢查後提供實驗模式，但不得標成已驗收；對齊器不支援的語言不得沿用錯誤語言硬跑。

`zh` 是來源語言分類，不等同 `zh-TW` 地區或文字風格。不得只憑中文轉錄文本區分華語、粵語或台語；不支援的語種應顯示限制，而非歸入「中文已支援」。

### 1.4 延後功能

雙語同時顯示、完整既有字幕翻譯捷徑、glossary 編輯 UI、背景處理整片、更多來源／目標語言可列入 v1.1。資料模型應留擴充位置，但 MVP 不必全部實作。

**不在本規格範圍：** AI 補幀、超解析度、TTS／配音、speaker diarization、逐字 karaoke、畫面 OCR、字幕編輯器、影片摘要／聊天、直播、DRM、瀏覽器串流抓取、外接獨立音訊、多音軌混音、雲端服務、跨裝置同步、Windows／Linux。

NAS 經作業系統掛載後可以當一般檔案試用，但網路磁碟延遲不在 MVP 效能保證範圍。URL、HLS、YouTube 等不得假裝是本機檔案直接交 FFmpeg。

### 1.5 完成的意思

「有 UI」、「能輸出一份 SRT」、「mock 測試綠燈」都不等於完成。至少要能在真實 IINA 中，用真實模型播放一段對話影片，逐批更新字幕，完成 seek、音軌切換、重開快取與安全退出測試。

---

## 2. 外部能力與需要先核實的事項

### 2.1 已查到的公開能力

以下資訊核對於規格日期；實作時仍須固定套件／模型版本。

| 能力 | 核實結果 | 來源 |
|---|---|---|
| IINA 外掛 | 有 main/global entry、JavaScript API、打包與安裝機制 | [S01][S02][S03] |
| 外部程式 | `iina.utils.exec(file, args, ...)` 可執行程式；回傳結束結果的 Promise，不是 Node ChildProcess handle | [S04] |
| 播放整合 | 可讀 mpv properties、執行 commands、訂閱事件 | [S05][S06] |
| 漸進字幕 | mpv 有 `sub-add`／`sub-reload`；reload 會卸載再重新加入軌道，仍需實測 UI 行為 | [S07] |
| Gemma 音訊 | 官方範例使用 `google/gemma-4-E2B-it`；音訊上限 30 秒；有不指定來源語言的原語言 transcription 範例 | [S09][S10] |
| 本機 runtime | LiteRT-LM Python 文件涵蓋 macOS、GPU backend 與音訊輸入；不是只能使用文字 HTTP server | [S11] |
| 另一條 runtime | MLX-VLM 的 Gemma 4 文件列出 E2B／E4B 音訊理解 | [S12] |
| 對齊器 | Qwen3-ForcedAligner-0.6B 接收音訊與原文；MLX-Audio 提供對應載入／alignment 範例 | [S13][S14] |
| VAD / 文字 LID | Silero VAD 有 ONNX 路線；Lingua 是可離線使用的文字語言辨識器 | [S15][S16] |

### 2.2 特別注意：IINA 文件存在欄位差異

IINA Development Guide 的欄位為 `globalEntry`，目前公開原始碼也讀取 `globalEntry`；但 Global Entry 教學頁的短範例寫成 `global`。**本專案採用 `globalEntry`，並以實際安裝的 IINA release 原始碼／smoke test 為準。** 不可直接複製教學片段而不驗證。[S02][S03][S17]

### 2.3 不得視為已驗證的假設

1. 公開 Gemma E2B 與 Eloquent 介面「2B」是完全相同的包裝與效果。
2. M3 Max 可以在任何影片上於 5–10 秒內開始觀看。
3. Transformers 的 CUDA 範例可直接改成 `mps` 就達到相同性能。
4. LiteRT-LM 的 OpenAI-compatible HTTP server 一定支援所需的 audio modality。
5. 外掛安裝完成就自動擁有 Python、FFmpeg、模型權重與 helper。
6. `sub-reload` 永遠不閃爍、track ID 永遠不變，或 command 回傳代表畫面已更新。
7. 原文辨識、forced alignment 或翻譯任一項成功，就代表整條流程成功。

Phase 0 的任務就是將這些不確定性轉成可重現證據。

---

## 3. 架構

### 3.1 元件分工

```text
IINA（既有播放器，不修改原始碼）
  ├─ main entry：每個播放視窗一份
  │    讀取目前影片、音軌、時間、播放意圖
  │    生成／停止操作、OSD、狀態側欄、字幕載入與重載
  │
  └─ global entry：全域協調
       helper discovery / ensure / heartbeat
       接收各視窗訊息、去重啟動、轉送狀態
                │
                │ 本機 HTTP + bearer token
                ▼
Helper supervisor（單一使用者一份，按需啟動）
  ├─ API、session、排程、快取、字幕 snapshot、下載／診斷
  ├─ FFprobe / FFmpeg：讀取選定音軌與有時間映射的短 PCM
  ├─ VAD / 語言狀態 / cue 組裝
  └─ 長駐 inference worker（同一時間最多一項 GPU 任務）
       ├─ Gemma E2B：ASR 與文字翻譯
       └─ forced aligner：原文與音訊對齊
```

Global 與 main 的訊息依 IINA 文件使用 `iina.global` 傳送，帶上 player/session 身分，不透過全域 JS 變數共享 player 狀態。一般 IINA plugin instance 按 player core 隔離；global entry 不屬於任何特定播放器，不在 global entry 直接存取 `iina.core` 或 `iina.mpv`。[S03]

### 3.2 技術選擇

| 層 | 預設 |
|---|---|
| 外掛 | TypeScript＋`iina-plugin-definition`；bundle 成 JavaScriptCore 可用 JavaScript |
| 外掛 UI | 原生選單＋簡單 HTML/CSS 設定／側欄；不引入大型前端框架作為必要條件 |
| helper | Python 3.12 為初始候選，依鎖定 runtime 支援調整；獨立安裝環境 |
| control API | FastAPI＋Pydantic 或等價簡單 HTTP server；不對外開放 |
| IPC | v1 使用 IINA HTTP API 進行 polling [S18]；不需要 WebSocket、SSE、Redis、queue server |
| Gemma runtime | **先驗證 LiteRT-LM Python**；不適合時評估 MLX-VLM，不要求同時維護兩條正式路線 |
| aligner | 優先 Qwen3-ForcedAligner-0.6B 的 MLX-Audio 路線 |
| 語言辨識 | 原語言 ASR＋Lingua 文字 LID，metadata 為線索；必要時實測 Gemma 自報語言但不作唯一證據 |
| VAD | Silero VAD ONNX；CPU 執行，版本與資產 checksum 固定 |
| 媒體 | FFprobe＋FFmpeg，獨立 process，不使用麥克風／系統 loopback |
| 儲存 | SQLite（schema migration）＋原子更新的字幕檔 |
| 測試 | Python unit/integration；TypeScript unit；真實 macOS／IINA 手動與可自動化測試 |

這些是可實作預設，不是要求為可替換性建立通用插件框架。只有模型、媒體抽取、字幕載入、時鐘等邊界需要小型 adapter。

### 3.3 模型 adapter 契約

```python
# 本專案設計介面；不是第三方套件的既有 API。
class SpeechTextBackend(Protocol):
    def load(self, manifest: ModelManifest) -> BackendCapabilities: ...
    def transcribe(self, audio: AudioSpan, source_hint: str | None,
                   cancel: CancellationToken) -> TranscriptResult: ...
    def translate(self, cues: list[SourceCue], target_locale: str,
                  context: TranslationContext,
                  cancel: CancellationToken) -> TranslationResult: ...
    def unload(self) -> None: ...

class AlignmentBackend(Protocol):
    def align(self, audio: AudioSpan, source_text: str, language: str,
              cancel: CancellationToken) -> AlignmentResult: ...
```

`load()` 與 session／chunk 生命周期分開。每個請求使用獨立或有上限的 conversation，不把整部電影累積成無界聊天歷史。ASR 與 translation 可重用同一套 Gemma weights；不需要為兩個用途複製模型。

Capabilities 至少包含：真實 model ID／revision、runtime／quantization、audio 支援、單次最大音訊長度、實際 backend、支援 cancellation 的粒度、aligner 語言集合。GPU 不可用而轉 CPU 時，必須明確顯示，不能悄悄降級後仍稱即時。

### 3.4 多視窗與 process 邊界

MVP 允許多個 session，但只承諾一個主動 AI 觀看 session 的即時效能。優先最近**明確啟用 AI／要求繼續 AI 觀看**的視窗，不依賴未驗證的 focus API。其他視窗顯示「另一個影片正在使用字幕引擎」，可手動切換優先權；已有字幕快取仍可使用。

HTTP event loop MUST 不被推論阻塞。優先使用 supervisor＋單一 inference subprocess；模型載入該 subprocess 並保持長駐。FFmpeg 抽取和 CPU VAD 可以有限度重疊，GPU 工作預設序列化。

---

## 4. 使用流程

### 4.1 第一次設定

1. 安裝 `.iinaplgz` 外掛並啟用。
2. 外掛檢查 helper、FFmpeg、模型與空間，顯示缺少項目、總下載量與來源。
3. 使用者同意安裝／下載；必要的模型授權或憑證步驟明確呈現。
4. 安裝程序完成後做短音訊 smoke test，不以 import 成功代替模型可用。
5. 選預設模式、目標語言及自動啟用規則。
6. 之後正常開影片，不需另外執行任何命令。

開發期可以有一次性的 `setup-dev` 指令；但「一般使用者不需要 terminal 的安裝」是 v1 交付項目，不能用開發流程冒充完成。

### 4.2 一般開啟影片

- 先讀取實際起始播放位置；影片可能從上次看到的 36 分鐘繼續，而不是第 0 秒。
- 取得所選音軌與既有字幕，決定是否啟動 AI。
- 查詢快取；若目前位置已有足夠、已安裝的字幕 coverage，立即使用。
- 缺少時準備附近一個短窗口，同時顯示具體階段：載入模型／辨識語言／產生字幕。
- 需要 hold 時，保留 IINA 原本的起播／續播位置，不讓影片先無字幕前進幾秒再開始準備。Phase 0 驗證最早可安全設立 hold 的事件；不要在 mpv load hook 內長時間等待模型，造成播放器初始化死鎖。
- 已確認的無聲開頭可先形成可播放 coverage，不需要等待偵測出語言或產生第一句文字才開播。
- 當目前播放點之後的連續可用 coverage 達啟播門檻，而且字幕已載入 IINA，才自動解除外掛持有的暫停。
- 背景按需求向前處理，不自動跑完整部影片。

### 4.3 有現成字幕

預設 `autoPolicy = when_missing_target_subtitles`：已存在可用的目標語言完整字幕時，不啟動 ASR。識別不能只看有沒有 subtitle track：forced-only、signs/songs、損壞或空白軌道不當成完整字幕。

未知語言字幕或人工選定軌道，不得直接覆蓋。顯示「已有字幕，是否改用 AI？」或讓使用者手動啟動。

完整「既有原文字幕→翻譯」捷徑屬 v1.1；MVP 手動選擇 AI translation 時仍可走音訊 pipeline。不要為了捷徑加入 bitmap subtitle OCR。

### 4.4 seek、切換音軌與重開

- Seek 至已完成區間：先載入快取，不重跑模型。
- Seek 至未完成區間：丟棄未開始的舊位置工作，優先新位置；必要時短暫準備。
- 快速拖曳：300 ms debounce；以最終 seek 位置為主，不對每次滑動跑模型。
- 音軌切換：關閉舊 session，使用新的 stream identity 建立 session；不可保留錯誤配音字幕。
- 重開影片：以原始檔案／音軌／profile 身分取得已生成區間，不因上次未處理完整片而丟失。

### 4.5 明確降級選項

生成追不上時，預設暫停準備，但始終提供「先繼續播放」「停止 AI 字幕」「重試」。原文已完成而翻譯未完成，可提供「暫用原文」選項，**必須經使用者選擇**，不能默默將翻譯字幕換成原文。

---

## 5. 時間、音軌與音訊抽取

### 5.1 唯一時間基準

Canonical time 是 **IINA/mpv 播放媒體時間軸上的整數毫秒**。牆鐘用於效能／timeout；monotonic clock 用於排程／lease；兩者不能寫入 cue timestamps。

每份 `AudioSpan` MUST 記錄：

```text
media_id, stream_key
core_start_ms, core_end_ms        # 本片段負責的半開區間
sample_zero_media_ms             # 實際抽出 PCM sample 0 的媒體時間
sample_rate_hz, sample_count
left_context_ms, right_context_ms
source_pts_origin / time_mapping_version
```

對齊器的相對時間透過 `sample_zero_media_ms + relative_time_ms` 轉換。不能直接假設抽取命令要求的 `-ss` 就一定是 PCM 真正的起點。[S08]

### 5.2 音軌 mapping

從 `track-list` 選出目前的 audio track，保留 `id`、`ff-index`（可用時）、`src-id`、language、title、codec、channels 等資料。用 FFprobe 交叉確認；`ff-index` 是線索而不是絕對保證，官方亦提醒不同 demuxer 可能有差異。[S07]

`mpvTrackId != ffmpegStreamIndex`。確認後才用 `-map 0:<ffmpeg_stream_index>`。有歧義就回報／請使用者選擇，不得靜默取第一條。來源檔的識別與 mapping 結果進快取。

### 5.3 音訊抽取

內部統一為 mono、16 kHz、float32 PCM。這與 Gemma 官方音訊前處理說明一致；各 runtime 是否再次 resample，必須確認，避免重複處理。[S09]

抽取為短窗口，精確 seek／trim；從原始音軌讀取，不從 IINA 已經播放出來的音訊錄音，不需要麥克風或 Screen Recording 權限。多聲道採有文件的 downmix，不能只取左聲道造成中央對白遺失。

初始可靠實作可接受稍慢的準確解碼；最佳化為前置 seek＋尾端 trim 時，必須仍通過 PTS 測試。使用參數陣列，不使用 shell 字串拼接。不要預先解碼整部影片到 WAV。

### 5.4 時間正確性的特殊情況

測試 non-zero start PTS、音訊比影片晚開始、variable frame rate、音訊 codec priming、seek 落在非 keyframe、檔尾不足一個 chunk。影片幀率不能用來代替音訊時間軸。

使用者 `audio-delay`／`sub-delay` 是播放顯示設定，不得寫死到 canonical 快取。`sub-delay` 保持使用者原值；`audio-delay` 變更時，要依實際 mpv 語意讓字幕跟隨聽到的音訊，且不得雙重補償。Phase 0 用已知 offset fixture 驗證；無法驗證則明確把非零 audio-delay 標為未支援，不可宣稱所有情況都同步。

外接音檔、複雜 edit lists／ordered chapters／無法建立映射的媒體可以拒絕 AI 模式，但不影響 IINA 正常播放。

---

## 6. 分段、語言偵測與模型流程

### 6.1 分段預設

這些數值都是可調設計起點，必須在 benchmark 中調整：

| 參數 | 初值 |
|---|---:|
| 啟動 core window | 10 秒 |
| 順播 target core window | 16 秒 |
| 短 core 最小值 | 6 秒（EOF／短句可更短） |
| 單次 core 上限 | 24 秒 |
| 左／右音訊 context | 各 1 秒 |
| boundary 尚未確認保留區 | 約 1 秒，依 planner 調整 |

送入 Gemma 的**總音訊**（含重疊 context）不得超過 runtime 上限，且不得超過官方目前 30 秒限制。不能只檢查 core 長度。[S09]

優先在自然停頓／VAD 邊界切分；連續說話到上限仍需切割。VAD 只判斷是否有語音，不是 forced aligner。保留原時間上的停頓；不要將不連續語音拼接後，忘記保存時間映射。

### 6.2 語言偵測流程

優先順序：

1. **使用者對此檔案／音軌的手動覆寫**。
2. 可信音軌 metadata 作為 provisional hint。
3. 不指定來源語言的原語言 ASR，再從有效原文做文字 language identification。
4. 訊息仍不足時維持 `und`／`tentative`，採後續語音累積證據；必要時顯示手動選擇。

原語言 prompt 基線：`Transcribe the following speech segment in its original language.`；實際用法須遵守所選 runtime 的 audio/chat template。[S09]

字幕軌語言、檔名、影片製作國家都不是音軌語言的可靠替代品。原文 ASR 使用者提示不得要求翻譯，否則後續 LID 只會辨識到輸出語言。

文字 LID 首選 Lingua；保留適當語言集合，不可把 unsupported audio 強迫四選一。分類 confidence 是判斷線索，不是校準好的機率；Gemma 在文字裡自報的百分比不得當作可信分數。[S16]

### 6.3 語言狀態與轉移

```text
unknown → tentative → confirmed
    └──────────────→ manual
confirmed → conflict → tentative / manual
```

- `unknown`：無足夠可辨識語音，例如無聲、只有音樂、片頭 logo。
- `tentative`：單次結果或僅 metadata；可暫用於目前片段，不永久鎖定全片。
- `confirmed`：至少兩段有資訊量的不同語音窗口一致，或其他經 benchmark 證明可靠的條件。
- `manual`：使用者指定，優先權最高。
- `conflict`：metadata 與獨立內容證據矛盾，或後續持續出現不同語言。

確認語言不必阻塞第一批字幕：首次窗口 LID 已足以對齊時可先處理，後續再確認全軌。文字太短、只有數字／專名／單個「OK」不得用來永久確認。

若需要以 metadata 作語言 hint，初期仍至少保留一次**無 hint**的獨立辨識檢查，避免錯標語言形成自我驗證循環。分類可靠但 ASR 自己聽錯時，文字 LID 也不能證明音訊語言正確；對齊異常必須觸發重新檢查。

### 6.4 code-switching

MVP 有 track-level primary language，但它只是 bias，不是禁止其他語言的指令。短暫英文插句保留原文，不使整軌語言來回切換。

對齊器支援的語言片段可獨立對齊；確實無法可靠處理的混語片段顯示局部錯誤／略過選項，**不能用 primary language 硬對齊後標成成功**。長時間雙語訪談的完整自動切語種不列入第一版品質承諾。

### 6.5 ASR

- 產出原文與必要標點，不潤稿成不同意思，不生成 timestamp。
- 使用已驗證 non-thinking 設定和適當 token 上限；不得讓推理文本混入字幕。
- 當輸出截斷、重複、prompt 回音或不合理長度時，不提交完成狀態。
- 在 deadline 內重試一次；可以縮小窗口或解除錯誤 language hint。
- ASR 不确定／失敗不是「沒有說話」。
- 不在 ASR prompt 塞入整部影片歷史；必要前文限制在局部、且不複製舊音訊。

### 6.6 對齊與 chunk 邊界

將原文和同一份音訊交 forced aligner，取得 word／character units。檢查 finite、非負、單調、落在窗口範圍、足夠文字覆蓋和合理 duration。模型不提供真正 confidence 時，回 `null`，另存檢查結果；不得自行製造 confidence。[S13][S14]

對齊器不能替 ASR 判斷原文是否正確。大量 token 擠在同一時間、跨越明顯長無聲、對齊大量遺漏等需 retry／報錯，不能只要回傳 timestamps 就接受。

重疊片段的字詞，以實際時間及正規化文字共同去重。建議以 core 半開區間內的 word midpoint 決定 ownership；不能因文字相同就刪除不同時間真的重複說出的句子。

core 尾端尚未完成的句子保留為 draft；等待右側上下文後再完成。覆蓋範圍不能跨過這個未解決區間。已開始顯示的 committed cue 不在一般更新時改寫；需要修正時在未顯示範圍或明確重跑操作中處理。

### 6.7 cue 組裝

以對齊單位、標點和語音停頓分句；不把模型一整個 chunk 輸出當成一條字幕。句子可跨音訊 chunk，由 assembler 將尚未 committed 的邊界單位合併。

初始排版目標：單語最多兩行；CJK 每行約 16–22 個字，拉丁文字約 37–42 字元；一般 cue 顯示約 1–6 秒。這是本專案可調目標，不是對外字幕標準。短驚呼可更短，不得為了補滿最低顯示時間而把字拉到下一句對白。

若 cue 過長，依對齊單位切開；若 translation 太長，優先重寫為更精簡但語意完整版本。不能把翻譯字數平均分攤到時間軸冒充 word alignment。所有 cue 必須 `start_ms < end_ms`，排序穩定；MVP 預設同一字幕軌不重疊。

### 6.8 翻譯

對已組好的 source cue，以 stable ID 批次翻譯。模型只回 `{id, text}`，不回時間、不重新分配 ID。預設目標為繁體中文、自然台灣用語，保留人名、數字、術語和原意；不把字幕變成摘要。

提供前 2–4 個已完成 source cue 作 context，限制總 context budget，例如 512 tokens。已知 glossary 可經設定檔讀取；glossary UI 不必在 MVP 做。

驗證輸出 ID 全部且唯一、無額外 ID、無空白／解說／思考內容、目標文字合理。schema 失敗重試一次，不無限糾錯。先用一般 JSON parsing＋schema；只有 runtime 證明支援時才依賴 constrained decoding。

翻譯沿用 source cue 的起訖。若需重組多句，必須保留有明確 source span 的映射，MVP 可以禁止跨 cue 重組以降低錯位風險。首次版本不做 audio→translated text 的唯一通道，因為原文還要用來時間對齊與錯誤診斷。

來源與目標同語言時，能直接用原文則跳過翻譯；繁簡字形或台灣詞彙轉換是獨立的文字正規化設定，不要誤標為語種變換，且不能破壞 source alignment。

---

## 7. 緩衝、排程與播放控制

### 7.1 coverage 是區間集合，不是進度百分比

每個媒體／音軌／輸出 profile 的處理狀態保存為半開區間 `[start_ms, end_ms)`：

- `complete`：已生成且驗證所需字幕。
- `verified_no_speech`：可信的非語音區間，可不產生 cue。
- `pending`／`processing`：尚未完成。
- `failed`：處理失敗，不能偽裝成無聲。
- `unresolved_boundary`：chunk 交界尚未確認。

翻譯模式的 `complete` 必須包括 translation 完成；ASR 完成不夠。來源原文可有獨立 coverage，以供重用。只完成文字 ASR、尚未完成 alignment 的區間，不能當成原文字幕 complete。

**prepared coverage** 與 **installed coverage** 分開：前者在 helper 完成，後者對應已經被播放器接受的 subtitle snapshot。只有 installed coverage 能用來解除字幕緩衝暫停。確定沒有任何 cue 的無聲 snapshot 可以只確認 coverage，不必強迫 mpv 載入空 SRT。

### 7.2 緩衝定義

令 `p` 為目前 media time，`e` 為從 `p` 開始、無洞且符合目前輸出 profile 的連續 installed coverage 終點：

```text
buffer_media_ms = max(0, e - p)
buffer_wall_ms = buffer_media_ms / playback_rate
```

例如已完成 `[0, 60)` 與 `[600, 630)`，播放在 30 秒時只有 30 秒連續緩衝，不是 600 秒。已確認的無聲區間可連接 coverage；失敗區間不可。

### 7.3 初始排程參數

| 參數 | 初值 | 單位／用途 |
|---|---:|---|
| 啟播／rebuffer resume | 8 | media seconds |
| 低水位 | 15 | media seconds，優先補充 |
| 目標水位 | 45 | media seconds |
| 高水位 | 60 | media seconds，暫停額外推論 |
| 缺字幕安全 guard | 1 | wall second，依播放速度換算 |
| 播放狀態上報 | 500 | ms，active session |
| seek debounce | 300 | ms |
| 字幕更新最短間隔 | 1000 | ms；緊急首次／seek 更新例外 |

播放倍速上升時，SHOULD 按 wall-time 將水位放大，但仍受最大前瞻／記憶體預算限制。片尾不足 8 秒，只需涵蓋至 EOF，不可永遠等待不存在的區間。

### 7.4 工作優先序

1. 目前播放點的洞、啟播或 rebuffer 所需區間。
2. 該觀看 session 尚未完成的 translation／alignment，使已花費的 ASR 工作盡快可用。
3. 當前 session 低水位到目標水位。
4. 到高水位的額外前瞻。
5. 其他已明確啟用的 session，不承諾同時即時。

暫停播放時可補到高水位，之後停算，不趁暫停把全片做完。使用者選停止 AI，立即取消其未開始工作。CPU 解碼最多先準備少數窗口，禁止無界 queue。

### 7.5 取消與過期結果

每個工作攜帶：`session_id`、`seek_epoch`、`profile_revision`、`source_signature`、`job_id`。實際播放位置變化但不是 seek 不增加 epoch。

Seek 或 profile 變更後，舊 epoch 的未開始工作取消；running job 優先使用 runtime cooperative cancel。runtime 無法立即中斷時，記錄 cancel granularity，容許該小窗口結束，**不得讓過期結果改變當前播放或自動 resume**。

相同 source/profile 的有效舊結果可寫入通用 cache，但不能直接發布到新 session epoch。超時卡死才由 supervisor 結束自己擁有的 worker process，重建模型並顯示載入狀態；不要每次 seek 都殺模型。

### 7.6 pause ownership

播放器主動狀態與模型處理狀態分離：

```text
desired_playback = playing | paused
plugin_hold = none | startup | rebuffer | seek
session_state = disabled | preparing | running | idle | error
```

只有外掛自己因目前 session／epoch 設立的 hold，且使用者仍希望播放，完成後才能解除。模型完成並不等於呼叫 `play()`。

區分自己寫入的 `pause` property 事件和使用者的變更。使用者按播放以跳過準備，視為明確選擇繼續無字幕，外掛不能馬上再次暫停。使用者手動 pause、停用 AI、換字幕、關窗或新影片載入，清除舊 resume 權限。

若某種 IINA 操作無法可靠判定 pause intent，採保守策略：保持暫停並顯示「字幕已就緒，按播放繼續」，而不是猜測後自動開播。

### 7.7 效能持續不足

以 rolling complete-pipeline RTF／buffer drain 判斷，不只看單個快 chunk。建議連續數批低於 1× 且 buffer 持續下降時顯示「目前速度無法持續跟上」。

可以調窗口、token budget、排程、已驗證量化或較簡單輸出模式；不能隱藏降低對齊品質。加長初始等待只能推遲 buffer 耗盡，不能把慢於實時的管線說成已解決。

---

## 8. IINA 整合契約

### 8.1 執行環境

IINA 外掛執行於 JavaScriptCore，不是 Node，也不是一般瀏覽器。plugin main/global 不使用 Node `fs`／`child_process`、瀏覽器 `fetch`／`localStorage` 作假設；使用 IINA API。TypeScript 編譯後不得殘留未支援的 module import。[S02]

`iina.utils.exec` 不回傳可 `.kill()` 的 process handle；helper 的生命週期必須走本文件 supervisor／lease 設計。[S04]

### 8.2 manifest

最小能力：main entry、`globalEntry`、preferences page、sidebar、`file-system`、`network-request`、`show-osd`，需要原生對話框時加 `show-alert`。不用 overlay 顯示字幕，所以不因字幕本身要求 video-overlay。

`allowedDomains` 優先僅容許 loopback；實作前驗證實際 IINA 對 host／port 的比對方式，不直接設 `*`。模型下載由受控 installer／helper 執行，仍必須遵守下載來源限制。[S02]

### 8.3 播放 adapter

集中封裝 API，不讓 helper 知道 IINA 事件名字：

```typescript
interface PlayerAdapter {
  readSnapshot(): PlayerSnapshot;
  setPluginHold(reason: HoldReason, epoch: number): void;
  releaseOwnedHold(epoch: number): void;
  installSubtitle(snapshot: SubtitleSnapshot): Promise<RenderAck>;
  showStatus(status: PublicStatus): void;
  dispose(): void;
}
```

應驗證使用：`iina.file-loaded`、`iina.file-started`、`mpv.end-file`、`mpv.seek`、`mpv.playback-restart`，以及 `pause`、`aid`、`sid`、`track-list`、`speed`、`audio-delay` 的 property-change 事件。文件的事件規則是 `mpv.<property>.changed`；各事件是否可於所支援版本使用由 smoke test 確认。[S05]

`time-pos` 若事件量過大，改為 500 ms polling。事件訂閱、timer、pending callback 都必須在 session disposal／plugin reload 清除，不能每開一片多註冊一次。

### 8.4 原生字幕更新

MVP 使用 UTF-8 SRT，由 IINA/mpv 原生字幕引擎顯示，不在 WebView 模擬字幕。

流程：helper 產生完整有效 snapshot→同目錄暫存檔→atomic rename→通知 plugin→首次 `sub-add`，後續 `sub-reload`。SRT 是 committed cues 的 view；SQLite 才是 canonical 資料來源。[S07]

下列是官方已記錄的 IINA command 形式；不是完整的同步確認程式：[S06]

```javascript
const tracks = iina.mpv.getNative("track-list");
iina.mpv.command("sub-add", [absoluteSrtPath, "select", "AI · 繁體中文", "zh-TW"]);
// 對後續更新，先找出本外掛對應路徑的現有 track ID。
iina.mpv.command("sub-reload", [String(ownedSubtitleTrackId)]);
```

MUST 以已核准絕對檔案路徑辨認本外掛 track；reload 後重查 ID，不假設舊 ID 有效。不在每批重新 sub-add 造成軌道數一直增長。不要 reload／remove 其他外掛或使用者的字幕。

字幕可能已被使用者切換或停用，更新時保留其選擇。只在首次明確選用 AI 或仍選中本外掛 track 時維持 AI selection。不要重設字型、大小、位置、delay 等全域設定。

### 8.5 RenderAck

`mpv.command()` 返回不代表 snapshot 在畫面已可用。adapter 必須確認對應外部軌道存在、播放器未回報載入失敗、session／epoch／profile 仍相同，才回 render ack。Phase 0 實測 reload 的事件／完成時序並採用可驗證的策略。

初次載入／更新超過 3 秒仍不能確認就回 `SUBTITLE_INSTALL_FAILED`，不得假裝 installed。SRT hash／revision 可用來去重，避免不必要 reload。

一般更新 SHOULD 避開正在顯示的 cue 切換點，合併密集更新，但最多短暫延後，不能因此耗盡 buffer。Phase 0 必須確認全螢幕與連續更新有無可見閃爍；無法接受時先記錄 renderer ADR，不要把問題藏起來。

---
## 9. Helper 啟動、生命週期與資源

### 9.1 啟動方式

開發與發行的 helper bootstrap 都必須可由絕對路徑啟動，不依賴 GUI App 的 PATH 或使用者 shell 啟動檔。Global entry 只在需要 AI 時執行已安裝的 bootstrap executable，例如本專案 CLI `iina-ai-subtitles-helper ensure`。這是**待實作命令**，不是既有套件。

Bootstrap 做以下事情後迅速結束，不等待模型完整載入：

1. 在私人 runtime 目錄取得單例 lock。
2. 讀現有 connection manifest，核實 instance／protocol／health；有效則重用。
3. 無有效 instance 時啟動 helper supervisor，綁定 OS 分配的 loopback port。
4. 產生隨機 bearer token，原子寫入權限 `0600` 的 connection manifest。
5. supervisor 已可接受控制請求後，stdout 回一份 JSON，包含 connection file 路徑或連線資訊。
6. 釋放 bootstrap lock，結束。模型載入進度由 helper API 回報。

Bootstrap 可由 `iina.utils.exec` 執行；所有路徑用 argv，不啟 shell，不把 token 放在 command-line argument。失敗用明確 exit status 與結構化錯誤。[S04]

### 9.2 Connection manifest

```json
{
  "protocol_version": 1,
  "helper_version": "0.1.0",
  "instance_id": "opaque-random-instance-id",
  "host": "127.0.0.1",
  "port": 49152,
  "token": "runtime-generated-secret-not-committed",
  "pid": 12345,
  "started_at": "2026-09-19T00:00:00Z"
}
```

這些值僅示意，不能寫死 port／token／PID。安全目錄 `0700`；驗證擁有者、防止 symlink／path traversal。不得因一份 PID 檔就殺掉任意現存 PID，PID 可能已被重用。

### 9.3 Lease 與退出

- 全域 plugin client heartbeat：每 5 秒。
- 每個 active session 的 player snapshot 也更新 session lease。
- client lease 過期初值 45 秒；無有效 client 後寬限 15 秒，取消工作、釋放模型並退出。
- 關閉單一視窗只終止對應 session，其他視窗不受影響。
- IINA 仍開著但長時間未用 AI：保留小型 supervisor，閒置 10 分鐘卸載模型。下一部影片可能重新暖機。
- 正常退出／停用外掛若可取得事件，主動 deregister／shutdown；**不能只依賴退出 callback**，lease 必須兜底。
- 睡眠／喚醒：處理過期連線、重建 session、重新對齊目前時間，不補算睡眠期間「想像中前進」的影片。

不使用常駐開機 launch agent 作為預設；不需要 administrator 權限。退出 IINA 後，正常路徑目標快速清除，無通知崩潰路徑最遲約 60 秒清理（作業系統休眠期間除外）。

### 9.4 資源預算

同一時間一個 GPU inference job；模型按需載入並重用。一般閒置不持續占用 GPU。CPU thread 數受控，避免播放器和 helper 爭搶所有核心。

在實際可用記憶體確認後，初始以 helper 整體工作集約 12 GiB 內為優化目標，**不是已知模型需求**；低 RAM 裝置應有不同預算。量測需包含 native／Metal 配置，不只 Python objects。記憶體壓力過大時減少 queue／釋放暫存，必要時報錯，不讓系統無限 swap。

主模型量化、audio encoder backend、batch size、token budget 都記入 benchmark；不根據「2B」字樣推算記憶體。下載版型由 model manifest 固定，不從名字猜測資源大小。

### 9.5 Crash recovery

控制面保持可回應；worker crash 不損壞已 committed 字幕。最多自動重啟一次，保留已完成 cache，重新排目前位置；再次失敗顯示需要人工重試，避免反覆載入大型模型。

Supervisor 結束 FFmpeg／worker 時，只結束自己建立、仍能驗證身分的 child process group；先 graceful，再有限時間 kill。不使用 `killall python`、`pkill ffmpeg`。

---

## 10. 本機 API 與資料契約

所有 API 是本專案自己的控制協定，不要求 OpenAI-compatible。v1 使用 JSON，控制請求都是短請求；耗時工作排入 worker，回 `202`＋狀態，不讓 HTTP 等完整推論。

### 10.1 共通規則

- Base：`http://127.0.0.1:<dynamic-port>/v1`。
- 所有 endpoint，包括 health，需 `Authorization: Bearer <token>`。
- 由 plugin global client 轉送；WebView 不直接持有 token。
- `protocol_version` 不相容：回版本錯誤，引導更新，不勉強解析。
- 毫秒整數表示媒體時間；`playback_rate` 是正有限數。
- 所有 state update 帶遞增 `client_seq`；拒絕比已接受 sequence 舊的更新。
- 所有 response 包含 `instance_id`；helper 重啟後舊 response 作廢。
- 重試 create session 使用 `request_id` 去重，不產生重複推論。
- 對 request body、字串、array、range 長度設上限；session 必須屬於該 client。

### 10.2 Endpoint 清單

| Method / path | 功能 |
|---|---|
| `GET /health` | helper／protocol／instance 狀態；不載模型 |
| `GET /capabilities` | 確認 backend、模型、audio／alignment 語言、環境、限制 |
| `GET /setup` | 安裝、模型下載、磁碟空間與授權狀態 |
| `POST /setup/actions` | 使用者同意後的白名單安裝／下載／驗證動作；非任意命令執行 |
| `POST /clients` | 註冊全域 plugin client；回 client ID 和 lease |
| `POST /clients/{id}/heartbeat` | 延長 lease |
| `DELETE /clients/{id}` | 結束該 client 的 leases／sessions |
| `POST /sessions` | 建立媒體 session，驗證 path 與音軌 mapping，安排當前位置 |
| `PUT /sessions/{id}/playback` | 更新位置、rate、pause intent、seek epoch、當前 subtitle selection |
| `POST /sessions/{id}/settings` | 改來源／目標／模式；回新 profile revision |
| `GET /sessions/{id}/snapshot` | 取得狀態、coverage、最新字幕 artifact；支援 `after_revision` 減少 payload |
| `POST /sessions/{id}/render-ack` | 播放器確認 snapshot 已安裝或載入失敗 |
| `POST /sessions/{id}/actions` | retry、stop、prioritize、continue_without_subtitles 等白名單動作 |
| `POST /sessions/{id}/export` | 匯出已生成內容到使用者明確選定位置；預設不覆寫 |
| `DELETE /sessions/{id}` | 停止 session，保留可重用 committed cache |
| `GET /cache/status` | cache 大小、完成範圍摘要 |
| `POST /cache/actions` | 使用者確認後清除指定影片或 LRU；不能刪模型／任意路徑 |
| `POST /shutdown` | 僅結束本 instance；仍有其他有效 clients 時須拒絕或明確 force 語意 |

這是完整 v1 契約；實作可先交付 Phase 0/1 使用的子集合，但 `openapi.json` 與實際實作必須一致。setup/export/clear 等功能不得以固定成功回應充數。

### 10.3 Session create 範例

```json
{
  "request_id": "opaque-create-request",
  "client_id": "opaque-client",
  "player_id": "iina-player-id",
  "media": {
    "path": "/Users/example/Movies/example.mkv",
    "mpv_audio_track_id": 2,
    "ff_index_hint": 1,
    "metadata_language": "jpn",
    "metadata_title": "Japanese Stereo"
  },
  "playback": {
    "position_ms": 360000,
    "rate": 1.0,
    "desired_playback": "playing",
    "seek_epoch": 0,
    "client_seq": 1,
    "audio_delay_ms": 0
  },
  "settings": {
    "mode": "translate",
    "source_language": "auto",
    "target_locale": "zh-TW",
    "buffer_policy": "pause_until_ready"
  }
}
```

路徑只在受控本機 API 傳送，不進一般 log。helper 自行 probe duration／stream 身分，不把 client hint 當可信 stream mapping。

### 10.4 Snapshot 範例

```json
{
  "instance_id": "opaque-helper-instance",
  "session_id": "opaque-session",
  "seek_epoch": 0,
  "profile_revision": 1,
  "snapshot_revision": 7,
  "state": "running",
  "stage": "translating",
  "language": {
    "code": "ja",
    "status": "confirmed",
    "method": "original_asr_text_lid",
    "score": 0.96,
    "score_kind": "classifier_relative_score",
    "manual_override": false
  },
  "prepared_ranges": [[360000, 395000]],
  "installed_ranges": [[360000, 382000]],
  "buffer_media_ms": 22000,
  "buffer_wall_ms": 22000,
  "artifact": {
    "path": "/Users/example/Library/Caches/IINA AI Subtitles/sessions/opaque-session/snapshot.srt",
    "sha256": "illustrative-not-a-real-digest",
    "revision": 7,
    "cue_count": 12,
    "complete_movie": false
  },
  "metrics": {
    "rolling_rtf": 0.45,
    "model_warm": true
  },
  "error": null
}
```

範例數字不是效能結果；score 不存在則為 `null`，不能湊一個。`installed_ranges` 只納入成功 ack 的 revision，且不可將較舊 ack 覆蓋較新的 installed 狀態。

### 10.5 Canonical source 與 cue

```text
SourceUnit
  id, source_run_id, chunk_id
  start_ms, end_ms, text, language
  alignment_method, quality_flags[]

SourceCue
  id, source_unit_ids[]
  start_ms, end_ms, text
  source_revision, commit_state

TranslatedCue
  id, source_cue_id, text, target_locale
  translation_profile_hash, context_fingerprint
  validation_status

RenderedCue
  source_cue_id, start_ms, end_ms, display_text
  profile_revision
```

對齊器 units 可為詞或字；不要強迫英文 tokenization 到中日文。`id` 不是 SRT 顯示序號；每次輸出 SRT 可重新編連續序號，而資料庫 stable ID 不變。

### 10.6 錯誤格式

```json
{
  "error": {
    "code": "ALIGNMENT_FAILED",
    "message_key": "alignment_failed",
    "retryable": true,
    "session_id": "opaque-session",
    "range_ms": [372000, 388000],
    "recovery_actions": ["retry", "continue_without_subtitles", "stop"],
    "diagnostic_id": "local-diagnostic-id"
  }
}
```

至少涵蓋：`SETUP_REQUIRED`、`MODEL_DOWNLOAD_FAILED`、`MODEL_LOAD_FAILED`、`BACKEND_UNSUPPORTED`、`MEDIA_UNSUPPORTED`、`NO_AUDIO_TRACK`、`AUDIO_TRACK_MAPPING_AMBIGUOUS`、`LANGUAGE_UNCERTAIN`、`ALIGNMENT_LANGUAGE_UNSUPPORTED`、`ASR_FAILED`、`ALIGNMENT_FAILED`、`TRANSLATION_FAILED`、`SUBTITLE_INSTALL_FAILED`、`RESOURCE_PRESSURE`、`HELPER_DISCONNECTED`、`PROTOCOL_MISMATCH`、`SOURCE_CHANGED`、`DISK_FULL`。

`LANGUAGE_UNCERTAIN` 可以是可繼續累積資料的狀態，不必立刻硬錯誤；但無法可靠對齊的區間不能推進 complete coverage。

---

## 11. 快取、持久化與字幕輸出

### 11.1 身分與分層

開播前不可為了完整 SHA-256 而順讀整支影片。初始 `media_signature` 使用檔案大小、mtime、高辨識度的頭／中／尾採樣 hash、stream／duration 摘要；記錄策略版本。檔名或 path 本身不足以當身分。

這是工程上避免大成本的 fingerprint，不是檔案密碼學身分的證明。讀到來源變更、mapping 矛盾或 signature 不一致就停止 session；不得將另一份影片快取套用過來。跨路徑移動後能否重用屬改善項目，不要求在 MVP 完美 dedup。

分層 key：

```text
media_key = file fingerprint + fingerprint version
stream_key = media_key + verified stream identity + time mapping version
source_profile = ASR model/revision/quantization/runtime + source override
                 + ASR prompt + VAD/planner + aligner + segmentation versions
translation_profile = source profile + target locale + translation model
                      + prompt/style/glossary versions
```

變更目標語言只重做 translation，不重跑原文／對齊；改 source override 則需要新的來源 profile。每批翻譯另記錄 context fingerprint，避免不同上下文被錯當完全相同推論。已播放 committed cue 不因新的前文補齊而自動改寫。

### 11.2 儲存位置

```text
~/Library/Application Support/IINA AI Subtitles/
  config.json
  runtime/<version>/
  models/<pinned-artifact>/
  run/connection.json
  run/bootstrap.lock

~/Library/Caches/IINA AI Subtitles/
  cache.sqlite3
  sessions/<session-id>/snapshot.srt
  audio-temp/<job-id>.wav
  exports-manifest/

~/Library/Logs/IINA AI Subtitles/
  helper.log
```

這些是本專案擬定目錄。model weights 不是一般 LRU cache，清除字幕不能順便刪模型。安裝根目錄與 IINA plugin 檔案位置分開，不把大型權重塞進 `.iinaplgz`。

SQLite 表至少涵蓋 media、streams、profiles、source units/cues、translations、coverage、language evidence、migration version。Job queue 可主要在記憶體，但已完成資料要交易式保存；crash 後 processing 狀態改回可重試，不假裝完成。

### 11.3 寫入與清理

先 transaction 提交 canonical cues／coverage，再產生完整有效 snapshot；寫暫存檔後 atomic rename。驗證字幕格式和 hash 後才通知 plugin。多視窗可共用 canonical cache，但各自 render artifact，避免互相重載另一語言。

音訊暫存預設在工作完成／取消後移除；crash 啟動時清理 stale temp。字幕／metadata cache 初始上限 2 GiB，採 LRU，保護目前 active session；上限可設定。Logs 例如 5 份各 5 MiB rotation，不包含正文／音訊。

### 11.4 匯出

原文 SRT、翻譯 SRT 分別匯出；UTF-8、合法時碼、連續序號。目的檔存在預設加序號或請求確認，不覆寫原始影片或現有字幕。

不完整輸出檔名包含 `.partial.srt`，並提供 sidecar JSON 記錄已完成 coverage、缺口、source/target、模型版本。只有已確認覆蓋完整 `[0, duration)` 的所有區間，才能標 `complete_movie = true`；跳到檔尾不代表處理完整。

內部播放 snapshot 可包含不連續已完成區間；coverage 決定可播放的洞，而不是靠 SRT 是否有下一條字幕猜測。

---

## 12. 設定與 UI

### 12.1 預設設定

```json
{
  "enabled": true,
  "autoPolicy": "when_missing_target_subtitles",
  "mode": "translate",
  "sourceLanguage": "auto",
  "targetLocale": "zh-TW",
  "bufferPolicy": "pause_until_ready",
  "startupBufferMs": 8000,
  "lowWaterMs": 15000,
  "targetBufferMs": 45000,
  "highWaterMs": 60000,
  "pollIntervalMs": 500,
  "seekDebounceMs": 300,
  "idleUnloadMs": 600000,
  "cacheMaxBytes": 2147483648,
  "cloudEnabled": false,
  "telemetryEnabled": false
}
```

runtime／model 路徑由驗證後的 manifest 管理，不放一個會悄悄追最新版本的 `model = latest`。設定需 schema 驗證，例如 `startup <= low <= target <= high`、所有時間為正、source language 合法。進階設定可先放 config，主要選項提供 UI。

### 12.2 選單

```text
AI 字幕
  為目前影片啟用／停止
  模式：原文／翻譯
  來源語言：自動／英文／日文／中文／韓文
  目標語言：繁體中文／英文
  優先處理這個視窗
  重新生成目前位置
  匯出已生成字幕…
  設定與診斷…
```

不加入沒有實作的 disabled marketing buttons。主要 UI 以繁體中文，程式與 log identifier 使用英文。每個選項對應真實狀態，setup 未完成時明確引導而不是點了沒反應。

### 12.3 狀態呈現

常見字樣：

- 「正在載入本機模型…」
- 「正在辨識語言…」
- 「日文 → 繁體中文 · 正在準備字幕」
- 「字幕已準備至 12:40 · 領先約 38 秒」
- 「已跳到 36:10，正在準備此處字幕」
- 「目前生成速度較慢，可等待或先繼續播放」
- 「尚無足夠語音，語言待確認」

「領先秒數」預設以 wall seconds 顯示，倍速時不得錯用 media seconds。未測得足夠樣本前不顯示虛構倒數。OSD 僅在重要狀態轉換出現，平常不每 500 ms 彈通知。詳情放側欄。

UI 進度聚焦「目前播放位置是否 ready、領先多少」，不要用整片完成百分比讓使用者以為必須等待 100%。

### 12.4 可及性與尊重既有操作

選單可鍵盤操作，字級可讀，錯誤有可行動按鈕；不要只靠顏色表示狀態。字幕本身沿用 IINA 原生排版偏好。模型準備時不竊取鍵盤焦點，不反覆跳出 blocking alert。

---

## 13. 安全、隱私與下載

### 13.1 本機服務

僅綁 `127.0.0.1`，不得 `0.0.0.0`。使用 256-bit 以上安全隨機 token；每次 helper instance 更換，token 不寫一般 log、不放 URL query、不進命令列或 WebView。

無 CORS wildcard；拒絕非預期 Host／Origin、沒有 token 的請求和跨 client session 存取。不是因為「只在 localhost」就可以省略驗證。防止任意網站經 loopback 觸發檔案讀取／程序執行。

同一 OS 使用者的惡意程序能接觸該使用者資源，不宣稱此設計可隔離已遭控制的同帳號環境；核心防護是非授權瀏覽器、其他帳號、意外對外暴露與任意命令注入。

### 13.2 輸入與檔案

- 路徑正規化、明確允許的檔案／目錄、拒絕 path traversal 和惡意 symlink。
- 媒體 filename、metadata、字幕、模型回應全是 untrusted data。
- subprocess 使用 argv，`shell=False`；絕不把字幕文本或模型輸出當命令。
- 翻譯模型不接工具，不讓影片中的指令觸發外部動作。
- HTML 顯示使用 textContent／escaping；SRT control characters、非必要 markup 經 sanitizer。
- JSON schema 驗證所有模型輸出；失敗不 fallback 成 eval。

### 13.3 隱私

模型與依賴備妥後，generation 路徑不得需要網路。無遙測、無雲端 fallback、無隱藏 API key。一般 log 僅含 opaque IDs、時長、狀態、錯誤碼與效能，不含完整 path、transcript、translation 或 PCM。

使用者可主動匯出診斷；預覽敏感內容、預設刪除媒體路徑／正文／token。Debug transcript 保存必須 opt-in 且說明刪除方式。

### 13.4 下載與供應鏈

初次安裝先顯示實際下載大小、磁碟需求和來源，經同意才下載。固定 runtime 版本、model repository/revision、artifact filename、sha256、轉換／量化資訊與授權來源。不可把範例假 hash 放進正式 manifest。

下載至暫存，驗證後移入正式目錄；支援失敗重試／resume，防 ZIP Slip。不得在每次開片時自動 `pip install -U`、執行任意遠端 Python、`curl | sh`，或修改使用者全域 Python／shell profile。

模型 repository 需要登入或條款同意時，提供正常操作步驟；不借用 Eloquent credentials。Runtime 不預設 `trust_remote_code=True`；確有需要時先審核、固定 revision 並取得明確許可。

### 13.5 交付與授權紀錄

提供 third-party notices 與各 binary／weights 來源；分開核對原始模型、量化轉換、runtime、FFmpeg build 的實際條件，不用主專案授權替全部相依套件背書。

可簽署／notarize 的發行流程留在 scripts 與 release docs；沒有 Developer ID／憑證時標記尚未執行，不能聲稱已簽署。不要要求關閉 Gatekeeper、SIP 或下載安全檢查。

---

## 14. 效能與品質驗證

### 14.1 要量什麼

```text
pipeline_rtf = active_pipeline_elapsed_wall_time / unique_media_seconds_prepared
speed_factor = 1 / pipeline_rtf
```

分母不重複計 overlap。分子取持續處理測試的實際 elapsed wall time，包含解碼與 I/O 等待，但排除刻意的 high-water 閒置；流水線重疊的 stage 不重複加總。另保留真實觀看全程的 buffer／stall 紀錄。完整時間包含抽取、VAD、語言偵測所需工作、ASR、alignment、cue 組裝、translation、persist/render 準備；另外報 IINA 安裝 ack 延遲。不要只報 decoder tokens/s。

每批另記各 stage 耗時、音訊／語音秒數、輸入輸出 token 數、cache hit、重試、取消、peak memory、compute backend。MLX 等非同步 GPU runtime 必須做適當同步後才結束計時，不能只量 enqueue。

### 14.2 啟動時間的三種情況

| 名稱 | 定義 | 驗收方式 |
|---|---|---|
| First-run setup | 尚未下載／安裝模型 | 只報實際時間與進度，不納入 5–10 秒目標 |
| Cold-model start | 資產已在本機、模型不在記憶體 | 獨立測試，不冒充 warm |
| Warm-model start | helper、ASR／translation 和必要 aligner 已載入且可用 | 5–10 秒啟播目標所對應的情況 |

時間起點為 IINA 已載入當前影片並決定啟用 AI，終點為足夠 installed coverage 且允許播放。不能只量第一個 token 或第一句尚未對齊文字。

### 14.3 初始 performance targets

以下是本專案目標；只有實測通過才可標記達標：

| 指標 | 初始 TARGET |
|---|---|
| Warm startup | p95 ≤10 秒，日常期望約 5–10 秒 |
| Cold startup | 報 p50/p95，不預先承諾 10 秒；UI 有分階段進度 |
| 完整管線 RTF | 對話密集素材 median ≤0.5，保留約 2× 餘裕 |
| 最低順播能力 | 支援語言各自的密集長片測試 RTF <1，不能只靠無聲片段拉低平均 |
| 連續觀看 | 1080p、1×、20 分鐘測試中，初次準備後無非預期字幕 underrun |
| 已快取 seek | 不跑模型；新增字幕準備延遲目標 ≤1 秒，不含 IINA 自身 seek 延遲 |
| 未快取 seek | Warm 下目標接近首次準備；分開報不可中斷 running job 的影響 |
| API 可回應性 | 推論中 control API p95 ≤250 ms，不含 job 本身 |
| 累積漂移 | 長片後段不得比前段出現持續增加的對齊偏移 |
| 播放影響 | 與同影片、無 AI 的 baseline 比較 dropped frames、音訊中斷與能耗；無可見卡頓 |

M3 Max 的測試要同時在 IINA 播片，而不是空機只跑 inference。記錄供電／低耗電模式／散熱、RAM、GPU 核心數、其他主要負載、顯示解析度、IINA 與嵌入 mpv 版本。4K、HDR、1.5×／2× 做額外壓力測試，不自動納入 MVP 承諾。

### 14.4 品質 targets

至少建立 4 種來源語言的 held-out 測試；調 prompt 的 development set 與驗收 set 分開。

- 語言：每種至少 20 段有足夠語音、單一主語言的片段。初始整體正確率目標 ≥95%；每語言及 `und`／abstention 比例分別報，不靠大量拒答美化準確率。
- ASR：英文報 WER；中／日文報 CER；韓文報 CER 並說明 normalization。保存原始和正規化結果。初始清晰語音目標英文 WER ≤15%、中／日 CER ≤15%、韓文 CER ≤20%；達不到先報證據，不私自調鬆門檻。
- 時間：至少每語言 50 個人工核對 source cue。開始／結束邊界絕對誤差目標 median ≤200 ms、p95 ≤500 ms；另列 >1 秒的 outliers 和原因。
- 翻譯：每語言至少 50 句，人工檢查意義、人名、數字、否定、遺漏／捏造與可讀性。不得用「JSON 正確」代替翻譯品質。提供問題清單，不虛構人工評分。
- 無聲／非語音：至少 30 個負例，包括數位靜音、環境音、純配樂；不能產生無中生有的對話。
- 小聲／背景音：另測低音量對白、音樂底下說話，避免 VAD 過濾掉正常台詞。

這些是產品驗收的初始門檻，不是引用第三方 benchmark 標準。正式調整必須寫明資料與取捨，經產品負責人確認；不能改數字讓測試變綠。

ASR accuracy 是對齊品質的前提。既有網路 SRT 可能是翻譯／不同剪輯，不能未核對就當 gold timing。素材使用權利清楚、可重現的小樣本或使用者本機合法素材；不把整部商業影片提交 repository。

### 14.5 Phase 0 可行性結論

至少提供以下真實證據：

1. 本機所選 Gemma E2B artifact 收到音訊並輸出正確類型原文，沒有靠外部雲端。
2. 同一模型可對 source cues 做目標語言翻譯，並保留 ID。
3. 指定 aligner 真正回傳可用時間單位，四語言各有案例。
4. 3–5 分鐘對話片段完整 pipeline 的 stage timing、RTF、記憶體和 sample SRT。
5. IINA 逐次重載字幕可用，以及字幕／音軌 ID、PTS mapping 的 smoke test。

沒有 Apple Silicon／IINA 或模型資產時，可繼續寫純邏輯與 mock tests，但 phase status 必須是 `blocked_on_hardware_validation`，並交可直接執行的測試命令。不得捏造「已在 M3 Max 通過」。

---

## 15. 測試計畫

### 15.1 Unit tests

| 測試群 | 必測案例 |
|---|---|
| Coverage | disjoint ranges、silence bridge、failed gap、EOF、倍速換算、prepared≠installed |
| Scheduler | 緊急洞優先、high-water 停算、pause 後停在上限、多 session 優先序 |
| Cancellation | 舊 epoch 結果、target 改變、音軌切換、快速 seeks、重啟 instance |
| Timeline | 相對→絕對時間、non-zero origin、resample 後 sample mapping、delay 不寫快取 |
| Chunk merge | overlap 去重、不同時間重複台詞不可誤刪、未完成句不推進 coverage |
| LID | metadata 缺失／錯誤、短句、只含數字、漢字歧義、manual override、混語 |
| Alignment | 負值、NaN、倒序、超界、zero-duration、對齊不全、unsupported language |
| Translation | missing／duplicate ID、截斷 JSON、額外解說、空字串、錯語言、prompt injection |
| SRT | 時碼、UTF-8、合法序號、長片小時數、partial、markup/control character 清理 |
| Cache | target 變更重用原文、檔案修改失效、音軌隔離、profile/version 失效、migration |
| Security | 無 token、錯 Host/Origin、跨 session、path traversal、shell 字元、symlink |
| Playback intent | user pause 不 auto resume、continue 無字幕不反覆 pause、舊 hold 不影響新檔 |

採可注入 clock、fake player、fake backend、fake decoder；測試不得依賴實際 wall-time sleep 才成立。

### 15.2 Integration tests

- 啟動多個 bootstrap 同時 `ensure`：只得到一個正常 helper。
- helper busy 時仍可 heartbeat、cancel、查 status。
- worker 中途 crash，已完成 cache 可讀、未完成區間不變 complete。
- DB transaction 或 atomic rename 中斷，不載入半個 SRT。
- FFmpeg 處理帶空格、中文、引號、shell metacharacters 的合法檔名。
- 兩條音軌的 MP4／MKV，確認 mapping 不是盲信數字相同。
- 實際非零 PTS fixture，輸出字幕時間不累積偏移。
- 來源刪除／修改、磁碟滿、模型下載中斷、有舊 helper 協定版本。
- 連線 manifest 被替換、stale PID、client lease 消失、安全退出。
- 資產已備妥後封鎖網路，仍可跑完整 pipeline。

### 15.3 IINA 真機 acceptance

- 安裝／啟用一次，之後單純開影片就能依設定生成。
- 使用者先 pause，再等字幕 ready，不會被自動播放。
- 開頭 60 秒純音樂或無聲，不會卡在「偵測語言」禁止看影片。
- 片尾不到啟播 buffer，仍正常完成。
- 從上次位置恢復，不先算開頭。
- 跳到第 40 分鐘，只先處理附近，不先做前 40 分鐘。
- 2 秒內連續 seek 10 次，最後只由最後位置決定 UI／hold。
- 切換配音音軌，立刻停止顯示舊音軌的 AI 字幕。
- 切換原文／翻譯、改 target，舊 response 不覆蓋新設定。
- 人工選另一字幕／關閉字幕，下一次 reload 不搶回。
- 更新至少 100 批，不增加 100 條字幕軌道，不累積 timer／memory leak。
- 全螢幕下字幕連續更新；可用時測 PiP，否則列明限制。
- 關單一視窗不殺另一個正在用的 session；退出 IINA 後 helper 最終清除。
- 睡眠／喚醒和外掛 reload 後恢復，不啟動重複 helper。
- 首次設定完成後，完全不用另外開 terminal 或 Eloquent。

### 15.4 必須記錄的 acceptance 表

每項記錄 `pass | fail | not_run | blocked`，附 environment、commit、命令／操作步驟、result 路徑、限制。`not_run` 不能記為 pass。QA 可以使用 mock 驗證控制邏輯，但真實模型品質／真實播放器行為要有不同欄位。

---

## 16. 開發階段與交付順序

### Phase 0 — 可行性與高風險 smoke tests

**先做，不先寫整套 UI。**

交付：

- 環境診斷 CLI：硬體、OS、IINA、mpv、FFmpeg、Python、runtime、GPU。
- 真實 Gemma E2B audio→原文→對齊→翻譯→SRT 的最小可重現腳本。
- 短片 benchmark 與 cold/warm 分開的結果。
- 最小 IINA plugin：事件讀取、目前音軌、dummy SRT 的增量更新、載入時序。
- `docs/feasibility.md`、`docs/runtime-decision.md`、初版 `models/manifest.json` 與 dependency lock。

先試 LiteRT-LM Python；遇到確認的 macOS audio／效能／打包阻礙，再試 MLX-VLM。可以在相同 E2B 模型下更換 runtime 並記 ADR。**不能不告知就換大型模型或雲端。** 若兩條路都無法達到目標，先交實際瓶頸與替代方案，再決定改 ASR 模型。

Phase 0 通過後，固定一條主要 runtime，不為「以後也許需要」同時建立多後端產品。

### Phase 1 — 無 UI 裝飾的端到端 vertical slice

- 建立 supervisor、single worker、基本 HTTP 契約與 session。
- 本機媒體→10 秒附近窗口→原文／翻譯→source timing→cache→SRT。
- IINA 選單手動「啟用 AI 字幕」，helper 由外掛啟動，不手動先開 server。
- 確認第一段 ready 即可播放；此階段即可展示真實字幕。

Gate：至少一種來源語言真機可播放，所有 timings 由對齊產生，不是 stub。

### Phase 2 — 漸進觀看核心

- coverage interval store、scheduler、水位控制、installed ack。
- seek／取消／epoch fencing、音軌切換、pause ownership。
- cache 重開、分層 profile、partial export、錯誤恢復。
- 四語言 LID／alignment／translation smoke；持續觀看 benchmark。

Gate：不需要完整影片預處理，正常順播及 seek 行為符合本規格。

### Phase 3 — 使用體驗與安裝

- 初次 setup、下載進度與 checksum、後續自動啟用。
- 主要設定、狀態側欄、manual language override、原文／翻譯選擇。
- single-instance、leases、退出、idle unload、診斷與安全。
- helper 可安裝包與 `.iinaplgz`；一般使用者不必 terminal。

Gate：乾淨 macOS user environment 裝好後，正常開影片即可使用；沒有假設已安裝 Homebrew／Python／模型 server。

### Phase 4 — 驗收、性能與發行準備

- 完成 acceptance matrix、20 分鐘觀看測試、timestamp 和 translation quality 檢查。
- 記錄未達目標、特定媒體限制及最低環境；不隱藏失敗。
- 測試 update／rollback／uninstall，不移除別的工具環境或使用者影片。
- third-party notices、版本相容矩陣、release checklist、可重現 build。

對外發行、推送 remote repository、購買服務、上傳私人素材、執行需要憑證的簽署步驟都不是本規格自動授權的動作。

---

## 17. 建議 repository 結構與開發契約

```text
iina-ai-subtitles/
  README.md
  AGENTS.md
  package.json
  <js-package-manager-lockfile>
  plugin/
    Info.json
    src/main.ts
    src/global.ts
    src/player-adapter.ts
    src/helper-client.ts
    src/session-controller.ts
    src/preferences/
    src/sidebar/
    tests/
    dist/
  helper/
    pyproject.toml
    uv.lock
    src/iina_ai_subtitles/
      cli.py
      bootstrap.py
      supervisor.py
      api/
      sessions/
      scheduler/
      media/
      language/
      backends/
      alignment/
      subtitles/
      cache/
      diagnostics/
    tests/unit/
    tests/integration/
  contracts/
    openapi.json
    schemas/
  models/
    manifest.json
  scripts/
    setup-dev
    doctor
    benchmark
    build-plugin
    build-helper
    package-release
  benchmarks/
    fixtures/manifest.json
    results/.gitkeep
  docs/
    IINA_AI_SUBTITLES_SPEC.md
    feasibility.md
    runtime-decision.md
    acceptance.md
    architecture-decisions/
    install.md
    troubleshooting.md
    release-checklist.md
  THIRD_PARTY_NOTICES.md
```

這是責任切分，不要求每個小 module 都拆成目錄。可按實際大小簡化，但不要把 player 控制、推論、SQLite 和 shell 操作塞進同一個巨大檔案。

要求：type hints／strict TypeScript、schema 驗證、合理 logging、可重現 lockfile、unit/integration tests、一條命令執行各測試。Python 安裝和 Node build 只污染專案／專屬環境，不修改使用者全域環境。

`AGENTS.md` 應摘要本規格不變條件與實際已驗證命令；不得只是複製所有內容。把 pipeline constants 集中成可測試設定，不在多個檔案散落 magic numbers。

### 17.1 CLI 交付要求

請實作並文件化等價能力：

```text
helper ensure
helper doctor
helper benchmark --media <path> --from-ms <n> --duration-ms <n> --mode <...>
helper export --media <path> --target <locale> --output <path>
helper cache status
helper cache clear --media <path>
helper shutdown
```

命令名稱可依 package entry point 調整，但 `README`、spec 附註與實際 `--help` 必須一致。benchmark 無影片路徑時列出如何提供測試素材，不任意掃描使用者 Videos 目錄。

### 17.2 每階段回報格式

```text
本階段完成：哪些實際功能
實際執行：命令／環境
驗證結果：真模型、mock、真 IINA 分開
測量：startup、RTF、alignment、memory（未測填未測）
已知限制／阻塞
下一個最小可執行步驟
```

不要只交設計文件而不開始實作，也不要一次建立大量空殼後宣稱所有階段完成。可在本規格預設範圍內自行決定實作細節；只有需要改動產品限制、付費、發布、權限或無法取得資源時才要求使用者決策。

---

## 18. v1 最終 Definition of Done

| ID | 必須成立 |
|---|---|
| AC-01 | 正常 IINA＋獨立外掛，不修改 IINA binary／source |
| AC-02 | setup 一次後，AI 功能不需手動啟動 helper／Python／Eloquent |
| AC-03 | 在公開可取得且固定 revision 的小型 Gemma 路線上，原文／翻譯實際生成 |
| AC-04 | 自動語言識別可不確定、可覆寫，不假定英文、不盲信 metadata |
| AC-05 | source→audio 對齊＋translation 映射，沒有模型臆造 timestamps |
| AC-06 | 首批完成即可開播，持續生成，不依賴整片預先處理 |
| AC-07 | seek 到未處理位置先做該處，舊結果不影響當前播放 |
| AC-08 | audio track、source profile、target profile、session／epoch 不混淆 |
| AC-09 | cached subtitles 可重開使用，部分完成不等於完整，無聲 coverage 不需要假字幕 |
| AC-10 | 原生 subtitle reload 不累積軌道，不搶使用者字幕／播放狀態 |
| AC-11 | helper 安全管理、單一模型 worker、停止／退出會釋放資源 |
| AC-12 | offline 可用，無未同意上傳／遙測，loopback 有 auth，安全下載 |
| AC-13 | 有真實 M3 Max benchmark，cold/warm、RTF、品質與播放影響分開呈現 |
| AC-14 | 未達 5–10 秒或持續即時目標時明確標示，不用別的數據冒充 |
| AC-15 | tests、可安裝 artifact、診斷、installation、known limitations、第三方來源齊全 |

功能正確性與效能達標分別記錄。若核心正確但尚未達即時效能，可交技術預覽版；不得將它標為已達成本產品的完整觀看體驗。

---

## 19. 外部來源與核實紀錄

以下均為官方文件、模型發布方或實際套件維護者的主要來源。網址供實作者重新核實，不代表網頁所指的最新版本已在本專案實測。**Implementation 時將實際採用的 release/tag/commit、artifact checksum 補到 lockfile 和 manifest。**

- **[S01] IINA Creating Plugins**：CLI、打包、安裝與 development linking。  
  `https://docs.iina.io/pages/creating-plugins.html`
- **[S02] IINA Development Guide**：Info.json、permissions、JavaScriptCore 執行環境。  
  `https://docs.iina.io/pages/dev-guide.html`
- **[S03] IINA Global Entry Point**：player instance 隔離、global/main 溝通。欄位範例須與 S02/S17 核對。  
  `https://docs.iina.io/pages/global-entry.html`
- **[S04] IINA Utils API**：exec、檔案路徑、對話框等能力。  
  `https://docs.iina.io/interfaces/IINA.API.Utils`
- **[S05] IINA Event API**：IINA/mpv 事件與 property changes。  
  `https://docs.iina.io/interfaces/IINA.API.Event`
- **[S06] IINA MPV API**：getNative、set、command、hooks。  
  `https://docs.iina.io/interfaces/IINA.API.MPV`
- **[S07] mpv Stable Manual**：track-list、ff-index、current-tracks、sub-add/sub-reload、時間與播放屬性。注意 IINA 嵌入版本可能不同。  
  `https://mpv.io/manual/stable/`
- **[S08] FFmpeg CLI Documentation**：seek、stream mapping、時間處理。  
  `https://ffmpeg.org/ffmpeg.html`
- **[S09] Google Gemma Audio Understanding**：E2B model ID、30 秒限制、16 kHz mono float32、原語言轉錄範例。  
  `https://ai.google.dev/gemma/docs/capabilities/audio`
- **[S10] Google Gemma 4 Model Card**：模型系列與 modalities。  
  `https://ai.google.dev/gemma/docs/core/model_card_4`
- **[S11] LiteRT-LM Python API**：macOS、GPU／audio backend、AudioFile 輸入、模型生命週期。  
  `https://developers.google.com/edge/litert-lm/python`
- **[S12] MLX-VLM Gemma 4 文件**：E2B／E4B 音訊、chat template 與 non-thinking。  
  `https://github.com/Blaizzy/mlx-vlm/blob/main/mlx_vlm/models/gemma4/README.md`
- **[S13] Qwen3-ASR／ForcedAligner 官方 repository**：獨立 forced alignment API 與支援語言。  
  `https://github.com/QwenLM/Qwen3-ASR`
- **[S14] MLX-Audio repository**：Qwen3-ForcedAligner 的 MLX 載入範例。  
  `https://github.com/Blaizzy/mlx-audio`
- **[S15] Silero VAD repository**：VAD、ONNX 推論與 sample-rate 支援。  
  `https://github.com/snakers4/silero-vad`
- **[S16] Lingua Python repository**：離線文字語言識別、語言集合與 confidence 用法。  
  `https://github.com/pemistahl/lingua-py`
- **[S17] IINA JavascriptPlugin.swift**：本次檢查 develop 的 manifest parser 讀取 `globalEntry`；實作時仍應對照已安裝 release。  
  `https://github.com/iina/iina/blob/develop/iina/JavascriptPlugin.swift`
- **[S18] IINA HTTP API**：plugin 與 helper 本機 HTTP 通訊的基礎。  
  `https://docs.iina.io/interfaces/IINA.API.HTTP`
- **[S19] LiteRT-LM 官方 Python 文件連結的 E2B artifact repository**：可作候選來源；必須確認具體檔案、audio 內容、revision 與 checksum。  
  `https://huggingface.co/litert-community/gemma-4-E2B-it-litert-lm`

**未做的驗證：** 此文件準備階段沒有執行 Gemma／aligner 模型、沒有安裝 IINA plugin、沒有在使用者 M3 Max 上量測速度。本文的效能、品質門檻與程式介面皆是開發規格，不能當成已完成的產品測試報告。
