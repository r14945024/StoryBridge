# StoryBridge 1.0 — 視障友善雙模式影音理解系統（可執行 MVP）

> **這是一套可以執行的技術原型，不是已通過使用者測試、可保證辨識正確的商品。** 範例故事的角色與口述由人工標註，並非 AI 自行辨識。連接 Ollama 後，上傳自己的授權影片才會呼叫真正的視覺模型。

## 1. 最快開始：Windows 11

1. 解壓縮整個 `StoryBridge_MVP.zip`（**不要只開 zip 裡面的檔案**）。
2. 安裝 **Python 3.11～3.13**；安裝時勾選 **Add Python to PATH**。若已有 Python 3.12 可以直接使用。
3. 在資料夾內**雙擊 `start_windows.bat`**。第一次會自動建立 `.venv`，安裝所需套件，並開啟瀏覽器。需要網路下載套件。
4. 網址：**http://127.0.0.1:8765**。開啟左側「消失的鑰匙」範例，按播放。建議使用 Chrome 或 Edge。
5. 在 00:09 之後詢問「剛剛誰拿走鑰匙？」；在 00:25 之後詢問「穿藍色外套的是同一人嗎？」。**00:09 之前不會提前回答誰拿走鑰匙。**
6. 原聲與中文口述分開控制。瀏覽器或作業系統須有可用的中文語音合成聲音；否則會顯示口述字幕，但可能無法朗讀。

本機啟動的伺服器只聆聽 `127.0.0.1`，不是公開上線的網站。關閉執行的命令提示字元即可停止。

### Mac / Linux

在終端機執行：

```bash
bash start_mac_linux.sh
```

本程式以 Windows 11 + Chrome / Edge 為主要操作目標，未對所有作業系統保證相同的文字轉語音效果。

## 2. 真正啟用 AI 影片理解（可選，額外下載本機模型）

沒有 Ollama 時，**示範影片仍可直接觀看、同步播放人工口述、詢問範例問題。** 但是系統不會謊稱已啟用模型；Live 分析與自動預處理需要另外安裝 AI。

1. 安裝 [Ollama](https://ollama.com/download) 並確認背景服務已啟動。
2. 在 PowerShell 執行以下指令（首次會下載數 GB 模型，需要足夠 RAM/VRAM 與儲存空間）：

```powershell
ollama pull qwen3-vl:4b-instruct
ollama list
```

3. 重新開啟 StoryBridge，在左下角按 **↻**。顯示「本機 AI 已連線」後，即可上傳自己的 MP4，選擇「使用本機 AI 分析整部影片」，或切換 Live 模式邊播放邊分析。
4. 建議先試 30～60 秒的合法影片；模型速度受 GPU、RAM、CPU 影響，Live 可能**明顯延遲**，並非承諾每 8 秒一定完成辨識。

**本機模型實作範圍**：每隔數秒取一張畫面（包含上一張畫面作為上下文），以 Ollama 視覺模型產生繁體中文場景描述、可能的外觀線索與口述。問答時僅使用目前時間點之前已經產生的事件。**並未內建經過驗證的人臉嵌入、跨鏡頭 Re-ID、說話者聲紋、真正 ASR 對白辨識或聲音指紋同步**。角色換裝正確性目前只在人工標註示範成立；真實影片不能保證同一人辨識正確。

如果電腦比較弱，可改用 `qwen3-vl:2b-instruct`：

```powershell
ollama pull qwen3-vl:2b-instruct
$env:STORYBRIDGE_VISION_MODEL="qwen3-vl:2b-instruct"
$env:STORYBRIDGE_TEXT_MODEL="qwen3-vl:2b-instruct"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8765
```

以上環境變數只作用於當前 PowerShell 工作階段。可以自行編輯 `start_windows.bat` 在啟動前使用 `set STORYBRIDGE_VISION_MODEL=...` 改為預設值。

## 3. Prepared Mode / Live Mode

| | Prepared 模式 | Live 模式 |
|---|---|---|
| 不安裝 AI 的展示影片 | 可使用人工標註的完整時間軸 | 不會假裝自動辨識，需要 Ollama |
| 自己上傳的 MP4 | 可讓 Ollama 事先抽幀分析；或手動新增／匯入 JSON 事件 | 把播放中的代表性影格傳給本機 Ollama，即時建立事件 |
| 中文口述 | 使用瀏覽器 SpeechSynthesis 依時間排程 | 模型推論完成後口述，延遲過大則只顯示文字 |
| 劇情問答 | Demo 用人工撰寫問答規則；一般影片 Ollama 或退化成事件關鍵字檢索 | 用截至提問時刻的已觀看事件；不抓取未來影片內容 |
| 角色記憶 | 展示範例是人工真值、會正確維持 C001、C002 | 只提供 AI 初步人物外觀線索，身分**未驗證** |

**暫停、快轉、倒退**：播放器會根據目前時間更新已觀看事件，並重新計算口述時間。跳過的事件不會突然連續朗讀。

**口述避讓對白**：程式碼支援在事件時間與預先標記的字幕／對白區間重疊時跳過口述，但本版不會從任意影片自動抽取字幕或辨識對白（API `captions` 預留）。**若未提供字幕或 VAD，無法保證口述不覆蓋真人對白。**

## 4. YouTube 功能範圍（重要）

可以按「YouTube 播放同步」貼上網址，在 StoryBridge 的網頁內透過 **YouTube 官方嵌入播放器**播放、顯示播放時間、暫停／快轉，以及利用自行匯入的合法口述時間軸播放語音。

**不能做到：** 直接下載 YouTube 影片、從 YouTube iframe 取出畫面來分析、獲得任意 YouTube 影片的自動角色辨識，也未實現手機麥克風音訊指紋同步。這些屬於後續擴充，還需考慮平台條款、影音取得方式與使用者授權。

## 5. 匯入自己的口述 JSON

先上傳 MP4 或建立 YouTube 播放器，再按「匯入口述 JSON」。結構範例：

```json
{
  "characters": [
    {"id": "C001", "name": "小安", "description": "短髮青年", "first_seen": 0}
  ],
  "events": [
    {
      "id": "e1", "t": 3.2,
      "description": "小安走進咖啡廳。",
      "narration": "小安走進咖啡廳。",
      "character_ids": ["C001"],
      "importance": 2,
      "source": "human_annotation"
    }
  ]
}
```

`source` 欄位會被顯示以協助辨認是人工標註或 AI 生成。匯入的資料預設標示 `user_imported_annotations`，不是由 AI 自行分析。

## 6. 介面操作

- **空白鍵**：播放／暫停（游標不在輸入框時）。
- **Q**：移動游標至問題輸入框。
- **N**：開關中文口述。
- **⇄ 5s**：倒退或快轉五秒。
- **語速**：可調語音合成速度。
- **語音輸入**：視瀏覽器支援情況可使用 `SpeechRecognition`。**注意：部分瀏覽器語音辨識可能使用遠端雲端服務，因此麥克風內容未必留在本機。**

語音合成亦依使用者作業系統／瀏覽器聲音服務而定，不能保證所有語音功能完全離線。

## 7. 專案結構

```
StoryBridge_MVP/
├─ start_windows.bat        Windows 雙擊啟動
├─ start_mac_linux.sh
├─ README_請先看.md
├─ requirements.txt
├─ app/
│  ├─ main.py               FastAPI API / 影片管理 / 模式整合
│  ├─ services/ai_engine.py Ollama 視覺分析 + 問答
│  └─ static/               網頁播放器 + CSS + JavaScript
├─ media/demo_story.mp4     原創 64 秒短片
├─ data/demo_story.json     公開標示的人工劇情標註與問答
├─ assets/                 原創插畫畫格及封面
├─ scripts/make_demo.py    可重新生成示範影片
├─ tests/test_api.py       API 測試
└─ user_data/               上傳素材／分析結果（本機生成）
```

## 8. 技術邊界及下一步

已完成：可執行網頁＋影片播放、上傳管理、雙模式處理介面、示範同步口述、人工角色資料、劇情記憶、時間篩選問答、Ollama 視覺分析連接與工作狀態、YouTube 播放器時間同步、手動事件標註、JSON 匯入。

尚未完成：經過基準測試的角色跨換裝再辨識、說話者辨識、ASR/VAD 對白空檔、任意影片自動情節完整理解、真實視障使用者測試、真人手機 App、影院環境音訊指紋同步、YouTube 任意串流畫面理解、競賽指定 GPU 的部署效能驗證。這些不能被當作已完成的產品功能。

建議優先擴充：① face embedding + 手動確認角色庫；② ASR 字幕與對白空檔；③ 每部影片的完整評分集；④ 聲音指紋（僅對取得合法音訊的影片）與跨裝置同步。

## 9. 基本隱私與安全

- 本版沒有帳號系統，也沒有部署到網際網路，僅供自己電腦上的技術展示；請勿把埠轉發到公開網路。
- 上傳影片會存到 `user_data/media/`；預處理事件存到 `user_data/analyses/`。刪除 `user_data` 內檔案前，先關閉程式。
- Ollama 依預設連到 `http://127.0.0.1:11434`，不需要付費 API key。若自行把這個位址設為遠端，資料就會傳送到那個伺服器，請自行注意隱私與權限。
- 真實影片可能有著作權、表演者肖像、內容使用與平台條款限制，僅處理具有使用權限的影片。

## 10. 檢查與測試

```powershell
.\.venv\Scripts\python.exe -m pip install pytest httpx
.\.venv\Scripts\python.exe -m pytest -q
```

程式可直接啟動但**未包含 GPU 模型權重**（權重數 GB），需要自己透過 Ollama 下載。已包含的原創展示影片約 350 KB，可離線瀏覽和執行人工標註問答。
