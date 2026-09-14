"""證照題庫 Pipeline（對應 docs/specs/robinson/SPEC.md FR-24、FR-25a～FR-25f、Step 3.2）。

僅 Robin 可用（`certificate` 功能開關）。**這個模組只負責「把題庫建好、存進 DB」**，不處理
推播/作答/批改（FR-26～FR-30，留待 Step 3.3；2026-08-07 經 AskUserQuestion 與 Robin 確認的
範圍邊界）。固定每週日台灣時間 22:00 執行（借用 `/healthz` 既有 cron 頻率），見
`run_weekly_pipeline()`。

兩條軌道：
- **軌道一**（`sync_track1_from_drive()`）：掃描 Google Drive 資料夾內 Robin 手動上傳的題目
  照片/音檔，依檔名比對成一題一題，呼叫 Gemini Vision 解析文字與選項，寫入 `certificate_
  questions`。聽力題若只有整包 MP3、還沒切成單題小檔，先用 Groq Whisper 轉錄，掃描逐句轉錄
  文字裡實際念出的「Number N」題號標記來切割（見 `_find_number_marker_starts()`）。**2026-09-13
  修改（Robin 明確要求，見 `docs/ADR/discuss/robinson.md` 對應日期條目）**：早期版本用「語句
  停頓長度」啟發式猜測切割位置，實測發現整批猜錯的狀況，Robin 要求「沒把握的題目就跳過，不要
  用猜的，儲存到資料庫的只能是 100% 確定的題目」，因此改為只在能同時確定一題的起始與結束邊界
  （都靠實際念出的題號標記，不是猜的）時才切出並存入該題，其餘題目直接跳過、留給下次排程依
  既有檔名去重機制自動重試，完全不使用任何猜測性的退路邏輯。**2026-08-07 追加（Robin 提出未來要擴充 GCP／AWS 等其他
  證照）**：軌道一泛用化為支援任意證照類型（`exam_type` 是開放字串、不寫死清單，來源就是檔名
  第一段），新增證照類型完全不需要改程式碼，只要換檔名前綴即可；聽力/切割相關能力仍保留給任何
  可能有聽力的證照使用，但軌道二單字題生成刻意仍只服務 TOEIC（見下方）。
- **軌道二**（`generate_track2_vocab_questions()`）：呼叫 Gemini 即時生成多益核心單字英翻中
  選擇題，依 `users.toeic_weekly_question_count`（Robin 自訂，預設 21）產生新題，跳過已存在
  的單字避免重複出題、浪費 Token（FR-25e）。**這條軌道刻意維持 TOEIC 專屬**：「單字刷題」是
  語言檢定特有的概念，GCP／AWS 這類證照沒有對應需求，不需要、也不該泛用化。

檔名規則（Robin 2026-08-07 確認，同日追加 `exam_type` 前綴支援任意證照類型；**2026-08-24 大幅
擴充，見 `docs/ADR/discuss/skill-growth.md` 對應日期條目**，一題一張，不可整批/整頁拍）：
- `{exam_type}_{test_id}_write_{題號}.{ext}`：閱讀/填空題目照片（圖片，一題一張）
- `{exam_type}_{test_id}_write_{題號}_ans.{ext}`：閱讀/填空解答／詳解照片（圖片，一題一張）
- `{exam_type}_{test_id}_listen_{題號}_ans.{ext}`：聽力解答照片（圖片，一題一張）——**2026-08-24
  起，聽力題（不分 Part）的題目文字／選項／正解／詳解全部改成從這張解析**，不再需要題目照片
  才能建立一題（見下方「聽力題內容來源」）
- `{exam_type}_{test_id}_listen_{題號}.{ext}`（音檔）：這一題已經剪好的單題聽力音檔，有的話
  直接使用，不會進整包切割
- `{exam_type}_{test_id}_listen_{題號}.{ext}`（圖片，非音檔）：題目照片，**選填**，只有像 Part 1
  這種作答時真的需要看圖的題型才需要；不影響這一題能不能建立
- `{exam_type}_{test_id}_listen.mp3`：整包聽力音檔（無題號），依這個場次目前待處理的聽力解答
  照片數量自動均分切割
- `{exam_type}_{test_id}_listen_cutoff{秒數}.mp3`：**2026-08-24 新增**，整包聽力音檔＋只處理到
  指定秒數為止（例如只要前 19 分鐘就是 `..._listen_cutoff1150.mp3`），超過秒數的內容完全不看、
  不計入任何題目——用於「丟一整份涵蓋多個 Part 的錄音，但只要自動切某個 Part」的情境（例如整份
  聽力 45 分鐘，只要自動切 Part 1+2，Part 3+4 不處理）；沒帶這個後綴的整包音檔維持原行為（整支
  都視為要切割的範圍）
- `exam_type` 開放任意小寫英數字/連字號組合（例如 `toeic`／`gcp`／`aws-saa`），不寫死清單；
  Drive 掃描不再用檔名關鍵字過濾（原本是 `name_contains="toeic"`），改成整個資料夾列出所有
  檔案，交給 `parse_filename()` 判斷哪些符合命名規則，不符合的直接忽略（Robin 2026-08-07
  確認：這個資料夾裡其他用途的檔案量不大，直接全列出換取實作簡單、不需要另外約定共用前綴）

**聽力題內容來源（2026-08-24 決策，見 `docs/ADR/discuss/skill-growth.md` 對應日期條目）**：
正式聽力考試現場沒有印刷版題目/選項可拍（Part 2 甚至完全沒有任何畫面），只有 Robin 的測驗書
「詳解頁」印有題目/選項逐字稿與正解——因此聽力題（不分 Part）的存在判斷、去重與內容全部改用
聽力解答照片（`answer_keys` 裡 type=listen 的項目）為準，`_process_answer_keys()`（原本負責事後
補正解/詳解的兩階段流程）改成只處理 write／閱讀題型，聽力題一律一階段直接從解答照片建好完整
內容。對應地，**作答時聽力題不顯示 `question_text`／`options` 文字**（見 `certificate_answer.py`
`_build_certificate_question_view()`）——Part 1 只顯示題目照片（有的話）＋音檔，Part 2 什麼畫面
都不顯示、只有音檔，文字題目只存在資料庫給事後對答案／看詳解使用，這樣才符合「聽力題只能用聽的
作答」；write／閱讀題型不受影響，維持照樣顯示文字題目＋選項。

去重（**2026-08-07 修正 FR-25f**：原規劃用「檔名日期是否在過去一週內」判斷，但 Robin 確認的
實際檔名格式沒有日期，這條規則對不上；改用 `certificate_questions.source_image_filename` 是否
已存在資料庫判斷是否處理過，更直覺也不會漏掉任何檔案）。軌道一天然是冪等的（重複掃到已處理過
的檔案會直接跳過），軌道二額外靠 `users.toeic_pipeline_last_run_on` 擋下同一個週日 22:00 那個
小時內 `/healthz` 多次觸發造成的重複生成（否則會超出預期的每週題數）。

**2026-08-07（Step 3.3，見 SPEC.md FR-27、ADR-19 決策 2）追加**：Robin 改為把購買的測驗書正確
解答／詳解也一併拍照上傳，檔名多一個 `_ans` 後綴：`{exam_type}_{test_id}_write/listen_{題號}
_ans.{ext}`。`sync_track1_from_drive()` 因此分兩階段處理——先跑原本的三個 `_process_*` 建立
題目，最後才呼叫 `_process_answer_keys()` 比對 `(exam_type, test_id, question_type,
question_number)` 找到既有題目後 `UPDATE` 補上 `correct_answer`／`explanation`，不新建題目列；
這個順序讓同一批次內「題目照片與答案照片一起上傳」也能正確處理。找不到對應題目的答案照片（例如
題目照片還沒上傳）會被略過並記警告 log，不會報錯；去重同樣採用「檔名是否已存在資料庫」
（`certificate_questions.answer_source_filename`）。因為正解來自真實資料而非 AI 推論，批改時
不需要額外的不確定性提醒；沒有 `correct_answer` 的題目不會出現在每日推播候選池（見 FR-26）。
"""
import io
import json
import logging
import random
import re
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from pydub import AudioSegment

from src.bot import toggles
from submodules.cloudsql.client import CloudSQLClient
from submodules.llm.client import LLMQuotaGuardError

_logger = logging.getLogger(__name__)

_TAIWAN_TZ = ZoneInfo("Asia/Taipei")
_PIPELINE_WEEKDAY = 6  # Python datetime.weekday()：Monday=0 ... Sunday=6
_PIPELINE_HOUR = 22
_FEATURE_KEY = "certificate"

_AUDIO_EXTENSIONS = {"mp3", "m4a", "wav", "ogg"}

# exam_type 開放任意小寫英數字/連字號組合（例如 toeic、gcp、aws-saa），不寫死清單；
# test_id 沿用原本的英數字場次代號規則。2026-08-07（Step 3.3）新增選填的 `_ans` 後綴群組，
# 辨識「答案照片」（跟一般題目照片共用同一套 exam_type/test_id/type/qnum 規則，差在多一段後綴）。
# 2026-08-24 新增選填的 `_cutoff{秒數}` 群組，只用於整包聽力音檔（沒有 qnum、有 `_ans`）；
# 見模組 docstring「檔名規則」。
_FILENAME_PATTERN = re.compile(
    r"^(?P<exam_type>[0-9a-z][0-9a-z-]*)_(?P<test_id>[0-9A-Za-z]+)_(?P<type>write|listen)"
    r"(?:_(?P<qnum>\d+))?(?:_cutoff(?P<cutoff>\d+))?(?P<ans>_ans)?\.(?P<ext>[A-Za-z0-9]+)$"
)

_VISION_PARSE_PROMPT = (
    "你是 Robinson，請解析這張「{exam_type}」證照考試的題目照片，用以下固定格式輸出，"
    "不要輸出其他任何文字：\n"
    "QUESTION: <題目文字>\n"
    "OPTIONS: <選項，用「|」分隔，例如 A. xxx|B. xxx|C. xxx|D. xxx>\n"
    "若圖片中同時有多題，只解析看起來最完整、最主要的一題；若圖片模糊到完全無法辨識文字，"
    "QUESTION 欄位請填「無法辨識」。"
)

# 2026-08-07（Step 3.3，見 SPEC.md FR-27、ADR-19 決策 2）：解析 Robin 拍攝的測驗書正確解答／
# 詳解照片，正解來自真實資料而非 AI 推論。**只用於 write／閱讀題型**，聽力題改用下方
# `_LISTEN_ANSWER_VISION_PARSE_PROMPT`（2026-08-24，見模組 docstring「聽力題內容來源」）。
_ANSWER_VISION_PARSE_PROMPT = (
    "你是 Robinson，請解析這張「{exam_type}」證照考試的正確解答／詳解照片，用以下固定格式輸出，"
    "不要輸出其他任何文字：\n"
    "CORRECT_ANSWER: <正確答案，例如選項代號或完整正確選項內容>\n"
    "EXPLANATION: <詳解文字，說明為什麼這是正確答案>\n"
    "若圖片模糊到完全無法辨識文字，CORRECT_ANSWER 欄位請填「無法辨識」。"
)

# 2026-08-24（見模組 docstring「聽力題內容來源」）：聽力解答照片是聽力題唯一的內容來源，一次
# 解析出題目逐字稿／選項／正解／詳解四項，取代原本「題目照片建題＋答案照片補正解」的兩階段流程。
_LISTEN_ANSWER_VISION_PARSE_PROMPT = (
    "你是 Robinson，請解析這張「{exam_type}」聽力測驗解答／詳解照片，這張照片上印有原始聽力題目、"
    "選項的逐字稿，以及正確答案／詳解，用以下固定格式輸出，不要輸出其他任何文字：\n"
    "QUESTION: <題目文字逐字稿>\n"
    "OPTIONS: <選項，用「|」分隔，例如 A. xxx|B. xxx|C. xxx|D. xxx>\n"
    "CORRECT_ANSWER: <正確答案，例如選項代號或完整正確選項內容>\n"
    "EXPLANATION: <詳解文字，說明為什麼這是正確答案>\n"
    "若圖片模糊到完全無法辨識文字，QUESTION 與 CORRECT_ANSWER 欄位請填「無法辨識」。"
)

_VOCAB_GENERATE_PROMPT = (
    "你是 Robinson，請生成一題多益（TOEIC）核心單字英翻中選擇題，單字不可以是以下已經出過的："
    "{existing_words}\n"
    "用以下固定格式輸出，不要輸出其他任何文字：\n"
    "WORD: <英文單字>\n"
    'QUESTION: <英翻中選答題目文字，例如："abundant" 這個字最接近下列何者意思？>\n'
    "OPTION_A: <繁體中文選項>\n"
    "OPTION_B: <繁體中文選項>\n"
    "OPTION_C: <繁體中文選項>\n"
    "OPTION_D: <繁體中文選項>\n"
    "CORRECT: <正確答案的選項代號，只能是 A 或 B 或 C 或 D>\n"
    "EXAMPLE: <包含該單字的英文實用例句>\n"
    "EXAMPLE_ZH: <例句的繁體中文翻譯>"
)


# --- 檔名解析與 Drive 檔案分類 ---


def parse_filename(filename: str) -> dict | None:
    """解析證照素材檔名，回傳 `exam_type`／`test_id`／`type`／`question_number`／`extension`／
    `is_answer_key`／`cutoff_seconds`；不符合規則（非本 Pipeline 使用的素材）回傳 `None`。

    `is_answer_key`（2026-08-07 追加，見 FR-27）：檔名是否帶 `_ans` 後綴，代表這是 Robin 拍攝
    的正確解答／詳解照片，而非題目本身。

    `cutoff_seconds`（2026-08-24 追加）：整包聽力音檔檔名是否帶 `_cutoff{秒數}` 後綴，代表只
    處理音檔前 N 秒、之後的內容完全忽略；沒有這個後綴回傳 `None`（維持整支都處理的原行為）。
    """
    match = _FILENAME_PATTERN.match(filename)
    if match is None:
        return None
    groups = match.groupdict()
    return {
        "exam_type": groups["exam_type"],
        "test_id": groups["test_id"],
        "type": groups["type"],
        "question_number": int(groups["qnum"]) if groups["qnum"] else None,
        "extension": groups["ext"],
        "is_answer_key": groups["ans"] is not None,
        "cutoff_seconds": int(groups["cutoff"]) if groups["cutoff"] else None,
    }


def classify_drive_files(files: list[dict]) -> dict:
    """把 Drive 檔案清單依檔名規則分成五類，供後續比對/切割使用；不符合命名規則的檔案忽略。

    key 一律包含 `exam_type`，避免不同證照類型剛好用了相同 `test_id` 造成互相覆蓋。回傳結構：
    - `write_images`：`{(exam_type, test_id, qnum): file}`，填空/單字題（或任何無聽力考題）圖片
    - `listen_images`：`{(exam_type, test_id, qnum): file}`，聽力題目照片（**選填**，2026-08-24
      起不再是聽力題是否成立的判斷依據，只用於作答時額外顯示圖片，見模組 docstring）
    - `listen_audio_segments`：`{(exam_type, test_id, qnum): file}`，已切好的單題聽力音檔
    - `listen_whole_audio`：`{(exam_type, test_id): {"file": file, "cutoff_seconds": int | None}}`，
      尚未切割的整包聽力音檔，`cutoff_seconds` 為 `None` 代表整支都要處理（2026-08-24 追加
      cutoff 支援，見模組 docstring「檔名規則」）
    - `answer_keys`：`{(exam_type, test_id, type, qnum): file}`，Robin 拍攝的正確解答／詳解照片
      （**2026-08-07 追加，見 FR-27**；**2026-08-24 起，聽力題型的這張照片同時也是題目文字／
      選項的唯一來源**）；key 多帶 `type`（write/listen）避免同一題號在兩種題型各自出現時
      互相覆蓋
    """
    write_images: dict = {}
    listen_images: dict = {}
    listen_audio_segments: dict = {}
    listen_whole_audio: dict = {}
    answer_keys: dict = {}

    for file in files:
        parsed = parse_filename(file["name"])
        if parsed is None:
            continue

        is_audio = parsed["extension"].lower() in _AUDIO_EXTENSIONS
        exam_type = parsed["exam_type"]
        test_id = parsed["test_id"]
        qtype = parsed["type"]
        qnum = parsed["question_number"]

        if parsed["is_answer_key"]:
            if qnum is not None:
                answer_keys[(exam_type, test_id, qtype, qnum)] = file
            continue

        if qtype == "write":
            if qnum is not None and not is_audio:
                write_images[(exam_type, test_id, qnum)] = file
        else:  # listen
            if qnum is None and is_audio:
                listen_whole_audio[(exam_type, test_id)] = {
                    "file": file,
                    "cutoff_seconds": parsed["cutoff_seconds"],
                }
            elif qnum is not None and is_audio:
                listen_audio_segments[(exam_type, test_id, qnum)] = file
            elif qnum is not None and not is_audio:
                listen_images[(exam_type, test_id, qnum)] = file

    return {
        "write_images": write_images,
        "listen_images": listen_images,
        "listen_audio_segments": listen_audio_segments,
        "listen_whole_audio": listen_whole_audio,
        "answer_keys": answer_keys,
    }


# --- 軌道一：Drive 掃描 + Gemini Vision 解析 ---


def _download_file_or_none(gdrive_client, file_id: str, context: str) -> bytes | None:
    """2026-09-14 新增（見 `docs/ADR/debug/robinson.md` 對應日期條目）：`gdrive_client.download_
    file()` 原本在各處都是直接呼叫、沒有包 try/except，一旦下載途中網路抖動（例如 `IncompleteRead`，
    Robin 本機重跑測試時實際遇到過），例外會直接往外傳、把整個 `sync_track1_from_drive()` 中斷掉，
    連帶讓「本來已經確定要處理的其他題目」連進資料庫或記錄失敗的機會都沒有，憑空消失、兩張表都
    查不到（Robin 回報 monster01 第 1~3 題就是這樣不見的）。改成下載失敗時記 log、回傳 `None`，
    呼叫端跳過這一題即可，不影響同一批次裡其他題目，也不影響其他 exam_type/test_id；因為沒有寫入
    `source_image_filename`／`answer_source_filename`，下次排程重新掃描時會自動重試（跟原本設計的
    重試機制一致，這裡不是「切不出邊界」的永久放棄，只是單純下載失敗，值得重試）。
    """
    try:
        return gdrive_client.download_file(file_id)
    except Exception:
        _logger.exception("下載 Google Drive 檔案失敗，這次先跳過（%s）", context)
        return None


def _is_already_processed(db: CloudSQLClient, source_image_filename: str) -> bool:
    return (
        db.select(
            "certificate_questions",
            where="source_image_filename = %s",
            params=(source_image_filename,),
            fetch_one=True,
        )
        is not None
    )


def _is_listen_split_already_failed(db: CloudSQLClient, exam_type: str, test_id: str, qnum: int) -> bool:
    """2026-09-13 新增（Robin 明確要求，見 `docs/ADR/discuss/robinson.md` 對應日期條目）：某一題
    聽力題如果先前已經確認「切不出 100% 確定的邊界、放棄這一題」（`certificate_listen_split_
    failures`，見 migration `0100`），就不要再嘗試下載/轉錄/切割——同一份錄音的轉錄結果基本上
    是固定的，週週重試注定週週失敗，純粹浪費時間與 Groq API 額度。這是永久跳過，不是「下次自動
    重試」；真的要重試（例如錄音已修正）需要手動刪除這張表對應的紀錄。
    """
    return (
        db.select(
            "certificate_listen_split_failures",
            where="exam_type = %s AND test_id = %s AND question_number = %s",
            params=(exam_type, test_id, qnum),
            fetch_one=True,
        )
        is not None
    )


def _record_listen_split_failure(
    db: CloudSQLClient, exam_type: str, test_id: str, qnum: int, source_image_filename: str
) -> None:
    """記錄某一題聽力題「確認切不出 100% 確定的邊界、放棄」，之後排程不會再重試（見
    `_is_listen_split_already_failed()`）。
    """
    db.insert(
        "certificate_listen_split_failures",
        {
            "exam_type": exam_type,
            "test_id": test_id,
            "question_number": qnum,
            "source_image_filename": source_image_filename,
        },
    )


def _parse_vision_output(raw: str) -> dict | None:
    question_match = re.search(r"QUESTION:\s*(.+)", raw)
    options_match = re.search(r"OPTIONS:\s*(.+)", raw)
    if not question_match or not options_match:
        return None
    question_text = question_match.group(1).strip()
    options = [opt.strip() for opt in options_match.group(1).split("|") if opt.strip()]
    if not question_text or not options:
        return None
    return {"question_text": question_text, "options": options}


def _parse_question_image(image_bytes: bytes, image_llm_clients: list, exam_type: str) -> dict | None:
    """呼叫 Gemini Vision 解析題目文字與選項；解析失敗或格式不符回傳 `None`（呼叫端記 log 跳過，
    不寫入髒資料，見 SPEC.md 風險表「比對失敗時不寫入資料庫」）。`exam_type` 帶入 prompt 讓
    Gemini 知道這是哪種證照的題目（例如 toeic／gcp／aws），不寫死特定證照的措辭。
    """
    llm_client = random.choice(image_llm_clients)
    prompt = _VISION_PARSE_PROMPT.format(exam_type=exam_type)
    try:
        raw = llm_client.generate_with_image(prompt, image_bytes, mime_type="image/jpeg")
    except Exception:
        _logger.exception("Gemini Vision 解析證照題目圖片失敗（exam_type=%s）", exam_type)
        return None

    parsed = _parse_vision_output(raw)
    if parsed is None:
        _logger.warning("Gemini Vision 回覆格式不符預期，略過這題：%r", raw)
    return parsed


def _insert_question(
    db: CloudSQLClient,
    exam_type: str,
    test_id: str,
    question_type: str,
    qnum: int,
    parsed: dict,
    image_file: dict,
    audio_url: str | None,
) -> None:
    db.insert(
        "certificate_questions",
        {
            "exam_type": exam_type,
            "test_id": test_id,
            "question_type": question_type,
            "question_number": qnum,
            "question_text": parsed["question_text"],
            "options": json.dumps(parsed["options"]),
            "image_gdrive_url": image_file.get("webViewLink"),
            "audio_gdrive_url": audio_url,
            "source_image_filename": image_file["name"],
        },
    )


def _process_write_questions(db: CloudSQLClient, gdrive_client, image_llm_clients: list, classified: dict) -> None:
    for (exam_type, test_id, qnum), image_file in classified["write_images"].items():
        if _is_already_processed(db, image_file["name"]):
            continue
        image_bytes = _download_file_or_none(
            gdrive_client, image_file["id"], f"write 題目照片 exam_type={exam_type} test_id={test_id} qnum={qnum}"
        )
        if image_bytes is None:
            continue
        parsed = _parse_question_image(image_bytes, image_llm_clients, exam_type)
        if parsed is None:
            continue
        _insert_question(db, exam_type, test_id, "write", qnum, parsed, image_file, audio_url=None)


_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20,
}
_NUMBER_MARKER_PATTERN = re.compile(r"(?i)^\s*number\s+(\d+|[a-z]+)[.,!?]?\s*$")


def _find_number_marker_starts(segments: list[dict], question_numbers: list[int]) -> dict[int, float]:
    """掃描 Whisper 逐句轉錄文字裡的「Number N」標記，找出每一題實際念出題號的起始時間。

    2026-09-07（Robin 提出，見 `docs/ADR/discuss/robinson.md` 對應日期條目）：TOEIC 聽力錄音
    本來就會口頭念出題號（「Number 1」「Number 2」...），這是比 `_find_split_plan()` 用停頓長度
    猜邊界可靠得多的真實依據。

    **2026-09-07（Robin 提出疑慮：內容裡剛好也提到某個數字怎麼辦）**：兩層防護，缺一不可——
    ①`_NUMBER_MARKER_PATTERN` 要求整句轉錄文字幾乎只有「Number N」本身（`^...$` 整句錨定，
    容許結尾一個標點），不是「文字裡任何地方出現這個詞」都算數，排除掉「gate number 5」「room
    number 12」這種內容裡順帶提到數字、但整句話不是題號播報的情況；②依題號順序、依序往後掃描
    （找到第 N 題的標記後，找第 N+1 題只會從第 N 題標記之後的內容繼續找，不回頭比對已用過的
    範圍），確保就算真的有兩句都符合「整句就是 Number N」（例如同一題重複播報兩次），也是採用
    照順序第一次遇到的那次，不會被之後不相關的重複或提前出現的數字打亂。

    數字辨識同時支援阿拉伯數字（Whisper 常見輸出，如「Number 1」）與英文拼字（如「Number One」），
    拼字對照表只到 20——TOEIC 單一 Part 的題號通常不會超過這個範圍，超過就直接視為找不到，不會
    嘗試更大的數字拼字表。

    2026-09-13 修改（Robin 提出，見 `docs/ADR/discuss/robinson.md` 對應日期條目）：原本是「找不到
    任一個題號的標記，整批直接放棄、回傳 `None` 給呼叫端去猜」的全有全無設計。Robin 明確要求「沒
    把握的題目就跳過，不要用猜的」，所以改成回傳「有找到標記的題號 -> 起始時間」的部分結果（可能
    比 `question_numbers` 少），找不到的題號單純不會出現在回傳的 dict 裡，由呼叫端（`split_audio_
    by_question_count()`）判斷每一題是否有足夠把握切出音檔，而不是在這裡就整批放棄或整批用猜的。
    """
    sorted_numbers = sorted(question_numbers)
    starts: dict[int, float] = {}
    cursor_index = 0
    for expected in sorted_numbers:
        found_index = None
        for i in range(cursor_index, len(segments)):
            match = _NUMBER_MARKER_PATTERN.match(segments[i]["text"])
            if match is None:
                continue
            token = match.group(1).lower()
            value = int(token) if token.isdigit() else _NUMBER_WORDS.get(token)
            if value == expected:
                found_index = i
                break
        if found_index is None:
            # 找不到就跳過這一題，不影響後面題號繼續掃描（cursor 不前進，下一題從同一個位置開始找）。
            continue
        starts[expected] = segments[found_index]["start"]
        cursor_index = found_index + 1

    return starts


def split_audio_by_question_count(
    audio_bytes: bytes, question_numbers: list[int], transcript_segments: list[dict]
) -> dict[int, bytes]:
    """把整包音檔切成音檔片段，依實際念出的「Number N」題號標記（`_find_number_marker_starts()`）
    決定每一題的邊界；回傳的 dict 只包含「100% 確定切對」的題號，可能比 `question_numbers` 少。

    2026-09-13 修改（Robin 明確要求，見 `docs/ADR/discuss/robinson.md` 對應日期條目）：「如果是
    沒有把握的題目，就跳過吧，也不要用猜的，沒意義啊，所以說儲存到資料庫的只能是 100% 確定的
    題目」。原本找不到完整標記時會退回 `_find_split_plan()` 的停頓長度啟發式猜測整批切法，一旦
    猜錯（實測發生過整批 6 題全部猜錯的狀況），寫進資料庫的題目就是錯的、而且很難事後發現。
    現在完全移除這個猜測退路，改成逐題判斷「有沒有 100% 把握」：

    - 一題的「起始邊界」100% 確定，若且唯若找得到它自己的「Number N」標記。
    - 一題的「結束邊界」100% 確定，若且唯若：
      (a) 找得到下一題（依題號排序）的「Number N」標記，結束邊界就是下一題的起始；或
      (b) 這一題是這一批要處理的題號中最後一題，結束邊界直接用音檔（或 cutoff）結尾——頂多尾巴
          多幾秒安靜，不影響內容正確性，可以接受。
    - 只要起始或結束任一邊界不確定，這一題就整個跳過、不寫進回傳的 dict，交由呼叫端不寫入資料庫。
      因為 `certificate_questions.source_image_filename`（存的是解答照片檔名）沒有這一題的
      紀錄，下次排程重新掃到同一批素材時會自動再嘗試切割一次，不需要額外的重試機制。

    需要系統安裝 `ffmpeg`（`pydub` 依賴，見 Dockerfile）。
    """
    sorted_numbers = sorted(question_numbers)
    audio = AudioSegment.from_file(io.BytesIO(audio_bytes))
    total_ms = len(audio)

    starts = _find_number_marker_starts(transcript_segments, sorted_numbers)

    result: dict[int, bytes] = {}
    for i, qnum in enumerate(sorted_numbers):
        start_sec = starts.get(qnum)
        if start_sec is None:
            continue

        is_last = i == len(sorted_numbers) - 1
        if is_last:
            end_ms = total_ms
        else:
            next_qnum = sorted_numbers[i + 1]
            next_start_sec = starts.get(next_qnum)
            if next_start_sec is None:
                continue
            end_ms = int(next_start_sec * 1000)

        start_ms = int(start_sec * 1000)
        segment = audio[start_ms:end_ms]
        buffer = io.BytesIO()
        segment.export(buffer, format="mp3")
        result[qnum] = buffer.getvalue()
    return result


def _split_whole_audio(
    gdrive_client, voice_client, whole_audio_file: dict, question_numbers: list[int], cutoff_seconds: int | None = None
) -> dict[int, bytes]:
    """`cutoff_seconds`（2026-08-24 新增）：只保留音檔前 N 秒再送進切割演算法，`None` 代表整支
    都要處理（維持原行為）。裁切同時套用在音檔本身跟逐句時間軸，避免 cutoff 之後的內容（例如同一
    支錄音裡的其他 Part）被誤算進切割範圍。

    2026-09-06 修正（見 `docs/ADR/debug/robinson.md` 對應日期條目）：原本先把「整份沒剪過」的
    音檔送去 Groq 轉錄、事後才裁切，完全沒發揮 `cutoff_seconds` 該有的效果——Robin 上傳的整份
    ~45 分鐘錄音直接被 Groq API 以 `413 Payload Too Large` 拒絕，裁切邏輯根本沒機會執行到。
    改成有 `cutoff_seconds` 時先用 `pydub` 剪好，只把剪過、小很多的那段送去轉錄；沒有
    `cutoff_seconds`（`None`）維持原行為，整支都送去轉錄。
    """
    audio_bytes = gdrive_client.download_file(whole_audio_file["id"])
    if cutoff_seconds is not None:
        audio = AudioSegment.from_file(io.BytesIO(audio_bytes))
        cutoff_ms = cutoff_seconds * 1000
        trimmed_buffer = io.BytesIO()
        audio[:cutoff_ms].export(trimmed_buffer, format="mp3")
        audio_bytes = trimmed_buffer.getvalue()
    segments = voice_client.transcribe_with_segments(
        audio_bytes, filename=whole_audio_file["name"], mime_type="audio/mpeg"
    )
    if cutoff_seconds is not None:
        segments = [seg for seg in segments if seg["start"] < cutoff_seconds]
    return split_audio_by_question_count(audio_bytes, question_numbers, segments)


def _parse_listen_answer_vision_output(raw: str) -> dict | None:
    question_match = re.search(r"QUESTION:\s*(.+)", raw)
    options_match = re.search(r"OPTIONS:\s*(.+)", raw)
    answer_match = re.search(r"CORRECT_ANSWER:\s*(.+)", raw)
    explanation_match = re.search(r"EXPLANATION:\s*(.+)", raw)
    if not question_match or not options_match or not answer_match or not explanation_match:
        return None
    question_text = question_match.group(1).strip()
    options = [opt.strip() for opt in options_match.group(1).split("|") if opt.strip()]
    correct_answer = answer_match.group(1).strip()
    explanation = explanation_match.group(1).strip()
    if not question_text or question_text == "無法辨識" or not options:
        return None
    if not correct_answer or correct_answer == "無法辨識":
        return None
    return {
        "question_text": question_text,
        "options": options,
        "correct_answer": correct_answer,
        "explanation": explanation,
    }


def _parse_listen_answer_image(image_bytes: bytes, image_llm_clients: list, exam_type: str) -> dict | None:
    """2026-08-24（見模組 docstring「聽力題內容來源」）：聽力解答照片是聽力題唯一的內容來源，
    一次解析出題目逐字稿／選項／正解／詳解，解析失敗或格式不符回傳 `None`（呼叫端記 log 跳過，
    不寫入髒資料）。"""
    llm_client = random.choice(image_llm_clients)
    prompt = _LISTEN_ANSWER_VISION_PARSE_PROMPT.format(exam_type=exam_type)
    try:
        raw = llm_client.generate_with_image(prompt, image_bytes, mime_type="image/jpeg")
    except Exception:
        _logger.exception("Gemini Vision 解析聽力解答照片失敗（exam_type=%s）", exam_type)
        return None

    parsed = _parse_listen_answer_vision_output(raw)
    if parsed is None:
        _logger.warning("Gemini Vision 聽力解答照片回覆格式不符預期，略過：%r", raw)
    return parsed


def _insert_listen_question_from_answer_key(
    db: CloudSQLClient,
    exam_type: str,
    test_id: str,
    qnum: int,
    parsed: dict,
    answer_file: dict,
    image_file: dict | None,
    audio_url: str | None,
) -> None:
    """2026-08-24：聽力題一階段直接從解答照片建好完整內容（題目文字/選項/正解/詳解），不再需要
    `_process_answer_keys()` 事後補正解——`image_gdrive_url` 只有真的有題目照片（例如 Part 1）
    才會填，Part 2 這種沒有題目照片的題型留空（見 migration 0099，`image_gdrive_url` 已改為
    允許 NULL）；作答時聽力題不顯示 `question_text`／`options` 文字，見
    `certificate_answer.py` `_build_certificate_question_view()`。
    """
    db.insert(
        "certificate_questions",
        {
            "exam_type": exam_type,
            "test_id": test_id,
            "question_type": "listen",
            "question_number": qnum,
            "question_text": parsed["question_text"],
            "options": json.dumps(parsed["options"]),
            "image_gdrive_url": image_file.get("webViewLink") if image_file else None,
            "audio_gdrive_url": audio_url,
            "source_image_filename": answer_file["name"],
            "correct_answer": parsed["correct_answer"],
            "explanation": parsed["explanation"],
            "answer_source_filename": answer_file["name"],
        },
    )


def _process_listen_questions(
    db: CloudSQLClient, gdrive_client, image_llm_clients: list, voice_client, classified: dict
) -> None:
    """2026-08-24（見模組 docstring「聽力題內容來源」，取代原本的 `_process_listen_questions_
    with_existing_audio()`／`_process_listen_questions_needing_split()` 兩個函式）：聽力題（不分
    Part）改成完全由聽力解答照片（`answer_keys` 裡 type=listen 的項目）驅動，依序判斷：
    ①有現成單題音檔（`listen_audio_segments`）→ 直接配對，不進切割 ②沒有單題音檔、但這個場次有
    整包音檔（`listen_whole_audio`）→ 排進這批要切割的清單，依整批共幾題均分切割（套用 cutoff，
    若有） ③兩者都沒有 → 先跳過，下次排程重新掃描時再試。
    """
    pending_by_test: dict[tuple[str, str], list[int]] = {}
    answer_key_by_qnum: dict[tuple[str, str, int], dict] = {}

    for (exam_type, test_id, qtype, qnum), answer_file in classified["answer_keys"].items():
        if qtype != "listen" or qnum is None:
            continue
        if _is_already_processed(db, answer_file["name"]):
            continue
        if _is_listen_split_already_failed(db, exam_type, test_id, qnum):
            continue
        answer_key_by_qnum[(exam_type, test_id, qnum)] = answer_file
        if (exam_type, test_id, qnum) in classified["listen_audio_segments"]:
            continue
        if (exam_type, test_id) in classified["listen_whole_audio"]:
            pending_by_test.setdefault((exam_type, test_id), []).append(qnum)

    # ① 有現成單題音檔的，直接處理，不進切割。
    for (exam_type, test_id, qnum), answer_file in answer_key_by_qnum.items():
        audio_file = classified["listen_audio_segments"].get((exam_type, test_id, qnum))
        if audio_file is None:
            continue
        answer_bytes = _download_file_or_none(
            gdrive_client, answer_file["id"], f"聽力解答照片 exam_type={exam_type} test_id={test_id} qnum={qnum}"
        )
        if answer_bytes is None:
            continue
        parsed = _parse_listen_answer_image(answer_bytes, image_llm_clients, exam_type)
        if parsed is None:
            continue
        image_file = classified["listen_images"].get((exam_type, test_id, qnum))
        _insert_listen_question_from_answer_key(
            db, exam_type, test_id, qnum, parsed, answer_file, image_file, audio_url=audio_file.get("webViewLink")
        )

    # ② 需要整包切割的，依場次分組、依整批共幾題均分切割。
    for (exam_type, test_id), question_numbers in pending_by_test.items():
        whole_audio_entry = classified["listen_whole_audio"][(exam_type, test_id)]
        try:
            segments_by_qnum = _split_whole_audio(
                gdrive_client,
                voice_client,
                whole_audio_entry["file"],
                question_numbers,
                cutoff_seconds=whole_audio_entry.get("cutoff_seconds"),
            )
        except Exception:
            _logger.exception(
                "整包 MP3 切割失敗（exam_type=%s, test_id=%s），這批聽力題暫緩處理，下次排程重試",
                exam_type, test_id,
            )
            continue

        for qnum in question_numbers:
            answer_file = answer_key_by_qnum[(exam_type, test_id, qnum)]
            segment_bytes = segments_by_qnum.get(qnum)
            if segment_bytes is None:
                # 2026-09-13（Robin 明確要求）：這一題這次沒辦法 100% 確定切割邊界，記錄放棄，
                # 之後排程不會再重試（見 `_is_listen_split_already_failed()`）。
                _record_listen_split_failure(db, exam_type, test_id, qnum, answer_file["name"])
                continue
            try:
                segment_filename = f"{exam_type}_{test_id}_listen_{qnum}.mp3"
                audio_url = gdrive_client.upload_file(segment_filename, segment_bytes, mime_type="audio/mpeg")
            except Exception:
                _logger.exception(
                    "上傳切割後的聽力小檔失敗（exam_type=%s, test_id=%s, qnum=%s）", exam_type, test_id, qnum
                )
                continue

            answer_bytes = _download_file_or_none(
                gdrive_client, answer_file["id"], f"聽力解答照片 exam_type={exam_type} test_id={test_id} qnum={qnum}"
            )
            if answer_bytes is None:
                continue
            parsed = _parse_listen_answer_image(answer_bytes, image_llm_clients, exam_type)
            if parsed is None:
                continue
            image_file = classified["listen_images"].get((exam_type, test_id, qnum))
            _insert_listen_question_from_answer_key(
                db, exam_type, test_id, qnum, parsed, answer_file, image_file, audio_url=audio_url
            )


def _parse_answer_vision_output(raw: str) -> dict | None:
    answer_match = re.search(r"CORRECT_ANSWER:\s*(.+)", raw)
    explanation_match = re.search(r"EXPLANATION:\s*(.+)", raw)
    if not answer_match or not explanation_match:
        return None
    correct_answer = answer_match.group(1).strip()
    explanation = explanation_match.group(1).strip()
    if not correct_answer or correct_answer == "無法辨識":
        return None
    return {"correct_answer": correct_answer, "explanation": explanation}


def _parse_answer_image(image_bytes: bytes, image_llm_clients: list, exam_type: str) -> dict | None:
    """呼叫 Gemini Vision 解析答案照片中的正解與詳解；解析失敗或格式不符回傳 `None`（呼叫端記
    log 跳過，不覆蓋既有資料）。跟 `_parse_question_image` 是分開的 Prompt，因為讀取的版面內容
    不同（答案頁 vs. 題目頁）。**2026-08-24 起只服務 write／閱讀題型**，聽力題改走
    `_parse_listen_answer_image()`（見 `_process_answer_keys()`）。
    """
    llm_client = random.choice(image_llm_clients)
    prompt = _ANSWER_VISION_PARSE_PROMPT.format(exam_type=exam_type)
    try:
        raw = llm_client.generate_with_image(prompt, image_bytes, mime_type="image/jpeg")
    except Exception:
        _logger.exception("Gemini Vision 解析證照答案照片失敗（exam_type=%s）", exam_type)
        return None

    parsed = _parse_answer_vision_output(raw)
    if parsed is None:
        _logger.warning("Gemini Vision 答案照片回覆格式不符預期，略過：%r", raw)
    return parsed


def _is_answer_already_processed(db: CloudSQLClient, answer_source_filename: str) -> bool:
    return (
        db.select(
            "certificate_questions",
            where="answer_source_filename = %s",
            params=(answer_source_filename,),
            fetch_one=True,
        )
        is not None
    )


def _find_matching_question(
    db: CloudSQLClient, exam_type: str, test_id: str, question_type: str, qnum: int
) -> dict | None:
    return db.select(
        "certificate_questions",
        where="exam_type = %s AND test_id = %s AND question_type = %s AND question_number = %s",
        params=(exam_type, test_id, question_type, qnum),
        fetch_one=True,
    )


def _process_answer_keys(db: CloudSQLClient, gdrive_client, image_llm_clients: list, classified: dict) -> None:
    """FR-27（見 ADR-19 決策 2）：比對 `_ans` 答案照片到既有題目，`UPDATE` 補上正解與詳解。
    **2026-08-24 起只處理 write／閱讀題型**——聽力題已改成在 `_process_listen_questions()` 一階段
    直接從解答照片建好完整內容（含正解／詳解），這裡不需要也不應該重複處理，避免 `answer_source_
    filename`（UNIQUE 欄位）衝突。

    必須在其他 `_process_*`（建立題目）之後呼叫，確保同一批次內「題目照片與答案照片一起
    上傳」也能正確比對到；找不到對應題目（例如題目照片還沒上傳、或還沒被本次批次處理到）的答案
    照片會被略過並記警告 log，不會報錯，下次排程重新掃描時會再次嘗試比對。
    """
    for (exam_type, test_id, qtype, qnum), answer_file in classified["answer_keys"].items():
        if qtype != "write":
            continue
        if _is_answer_already_processed(db, answer_file["name"]):
            continue

        question = _find_matching_question(db, exam_type, test_id, qtype, qnum)
        if question is None:
            _logger.warning(
                "找不到對應題目，略過這張答案照片（exam_type=%s, test_id=%s, type=%s, qnum=%s）",
                exam_type, test_id, qtype, qnum,
            )
            continue

        image_bytes = _download_file_or_none(
            gdrive_client, answer_file["id"], f"write 答案照片 exam_type={exam_type} test_id={test_id} qnum={qnum}"
        )
        if image_bytes is None:
            continue
        parsed = _parse_answer_image(image_bytes, image_llm_clients, exam_type)
        if parsed is None:
            continue

        db.update(
            "certificate_questions",
            {
                "correct_answer": parsed["correct_answer"],
                "explanation": parsed["explanation"],
                "answer_source_filename": answer_file["name"],
            },
            where="id = %s",
            params=(question["id"],),
        )


def sync_track1_from_drive(db: CloudSQLClient, gdrive_client, image_llm_clients: list, voice_client) -> None:
    """FR-25a～FR-25c、FR-27：掃描 Drive 資料夾，比對新的 write/listen 題目並解析寫入 DB，
    再比對答案照片補上正解／詳解。

    支援任意證照類型（`exam_type` 從檔名第一段解析而來，不寫死清單）。**2026-08-07 追加**：
    不再用檔名關鍵字（原本是 `name_contains="toeic"`）過濾 Drive 檔案列表，改成列出整個資料夾
    所有檔案，交給 `parse_filename()` 判斷哪些符合命名規則——因為 `exam_type` 開放任意字串後，
    沒有單一關鍵字可以用來過濾，Robin 確認這個資料夾其他用途的檔案量不大，直接全列出換取實作
    簡單（見 Robin AskUserQuestion 選定）。

    掃到 0 個檔案（例如 Robin 還沒上傳任何素材）時所有 `_process_*` 函式都會直接跑完、不做
    任何事，不會報錯，符合「還沒有素材也能安全部署」的要求。

    **2026-08-07（Step 3.3）追加**：`_process_answer_keys()` 必須排在最後執行——先把這批次能
    建的題目都建完，答案照片才有機會比對到「剛好同一批次一起上傳」的題目（見 ADR-19 決策 2）。
    **2026-08-24 起 `_process_answer_keys()` 只處理 write／閱讀題型的答案照片；聽力題改由
    `_process_listen_questions()` 一階段直接從聽力解答照片建好完整內容**（見模組 docstring
    「聽力題內容來源」）。
    """
    files = gdrive_client.list_files()
    classified = classify_drive_files(files)

    _process_write_questions(db, gdrive_client, image_llm_clients, classified)
    _process_listen_questions(db, gdrive_client, image_llm_clients, voice_client, classified)
    _process_answer_keys(db, gdrive_client, image_llm_clients, classified)


# --- 軌道二：Gemini 即時生成單字題 ---


def _existing_target_words(db: CloudSQLClient) -> list[str]:
    rows = db.select("toeic_vocab_questions", columns=("target_word",))
    return [row["target_word"] for row in rows]


def _parse_vocab_output(raw: str) -> dict | None:
    fields: dict[str, str] = {}
    for key in ("WORD", "QUESTION", "OPTION_A", "OPTION_B", "OPTION_C", "OPTION_D", "CORRECT", "EXAMPLE", "EXAMPLE_ZH"):
        match = re.search(rf"{key}:\s*(.+)", raw)
        if not match:
            return None
        fields[key] = match.group(1).strip()
    if fields["CORRECT"].upper() not in ("A", "B", "C", "D"):
        return None
    if not fields["WORD"]:
        return None
    return fields


_QUOTA_GUARD_RETRY_DELAY_SECONDS = 8


def generate_track2_vocab_questions(
    db: CloudSQLClient, llm_client, count: int, sleep_func=time.sleep
) -> int:
    """FR-25d～FR-25e：呼叫 Gemini 生成 `count` 題新的單字題（跳過已存在單字），寫入 DB。

    回傳實際成功生成並寫入的題數；單題生成失敗（格式不符/單字重複）只記 log 跳過，不中斷整批
    生成，避免一次沒生成好就整批都拿不到；`max_attempts` 設上限避免 Gemini 一直重複給同一批
    單字時無限迴圈。

    2026-08-24（見 docs/ADR/debug/skill-growth.md「TOEIC 單字題生成撞本地端節流上限」條目）：
    `submodules/llm/client.py` 有本地端節流保護（同一把 API Key 60 秒內最多 8 次），原本這裡
    兩次呼叫之間完全沒有延遲，且被節流擋下（`LLMQuotaGuardError`）時只是當成一般失敗略過，
    立刻進下一輪——結果是前 8 次瞬間打完，後面所有嘗試機會在同一秒內全部被節流擋下、瞬間
    燒光，`max_attempts` 形同虛設。現在遇到節流擋下時改成：**不算浪費一次嘗試機會**（`attempts`
    退回），並等待 `_QUOTA_GUARD_RETRY_DELAY_SECONDS` 秒讓節流視窗消化一些額度再重試，讓整批
    生成有機會真的用完 `max_attempts` 次真正呼叫 Gemini 的機會，而不是在毫秒內就放棄。
    """
    if count <= 0:
        return 0

    generated = 0
    attempts = 0
    max_attempts = count * 3
    existing_words = {word.lower() for word in _existing_target_words(db)}

    while generated < count and attempts < max_attempts:
        attempts += 1
        prompt = _VOCAB_GENERATE_PROMPT.format(existing_words="、".join(sorted(existing_words)) or "（無）")
        try:
            raw = llm_client.generate_text(prompt)
        except LLMQuotaGuardError:
            attempts -= 1
            sleep_func(_QUOTA_GUARD_RETRY_DELAY_SECONDS)
            continue
        except Exception:
            _logger.exception("Gemini 生成 TOEIC 單字題失敗")
            continue

        parsed = _parse_vocab_output(raw)
        if parsed is None:
            _logger.warning("Gemini 單字題回覆格式不符預期，略過：%r", raw)
            continue

        word_lower = parsed["WORD"].lower()
        if word_lower in existing_words:
            continue

        try:
            db.insert(
                "toeic_vocab_questions",
                {
                    "target_word": parsed["WORD"],
                    "question_text": parsed["QUESTION"],
                    "option_a": parsed["OPTION_A"],
                    "option_b": parsed["OPTION_B"],
                    "option_c": parsed["OPTION_C"],
                    "option_d": parsed["OPTION_D"],
                    "correct_option": parsed["CORRECT"].upper(),
                    "example_sentence": parsed["EXAMPLE"],
                    "example_sentence_translation": parsed["EXAMPLE_ZH"],
                },
            )
        except Exception:
            _logger.exception("寫入 TOEIC 單字題失敗（可能撞到 UNIQUE 約束），略過這題")
            continue

        existing_words.add(word_lower)
        generated += 1

    return generated


# --- 排程進入點 ---


def _get_owner(db: CloudSQLClient) -> dict | None:
    return db.select(
        "users", where="is_owner = %s AND telegram_user_id IS NOT NULL", params=(True,), fetch_one=True
    )


def run_weekly_pipeline(
    db: CloudSQLClient,
    gdrive_client,
    image_llm_clients: list,
    voice_client,
    text_llm_client,
    now: datetime | None = None,
) -> None:
    """固定每週日台灣時間 22:00 執行軌道一＋軌道二（Step 3.2）。

    只在台灣時間週日 22 點這個小時內執行；`certificate` 功能開關（僅 Robin 可用）關閉時整批
    跳過，不消耗任何外部 API 額度。靠 `users.toeic_pipeline_last_run_on`（今天是否已執行過）
    避免 `/healthz` 同一小時內多次觸發重複掃描/重複生成（見模組 docstring「去重」）。
    """
    now = now or datetime.now(timezone.utc)
    now_local = now.astimezone(_TAIWAN_TZ)
    if now_local.weekday() != _PIPELINE_WEEKDAY or now_local.hour != _PIPELINE_HOUR:
        return

    owner = _get_owner(db)
    if owner is None:
        return

    if not toggles.is_feature_enabled(db, owner["id"], _FEATURE_KEY):
        return

    today = now_local.date()
    if owner.get("toeic_pipeline_last_run_on") == today:
        return

    try:
        sync_track1_from_drive(db, gdrive_client, image_llm_clients, voice_client)
    except Exception:
        _logger.exception("TOEIC 軌道一（Drive 掃描）執行失敗")

    try:
        weekly_count = owner.get("toeic_weekly_question_count") or 21
        generate_track2_vocab_questions(db, text_llm_client, weekly_count)
    except Exception:
        _logger.exception("TOEIC 軌道二（單字題生成）執行失敗")

    db.update("users", {"toeic_pipeline_last_run_on": today}, where="id = %s", params=(owner["id"],))
