"""TOEIC 雙軌題庫 Pipeline（對應 docs/specs/robinson/SPEC.md FR-24、FR-25a～FR-25f、Step 3.2）。

僅 Robin 可用（`certificate` 功能開關）。**這個模組只負責「把題庫建好、存進 DB」**，不處理
推播/作答/批改（FR-26～FR-30，留待 Step 3.3；2026-08-07 經 AskUserQuestion 與 Robin 確認的
範圍邊界）。固定每週日台灣時間 22:00 執行（借用 `/healthz` 既有 cron 頻率），見
`run_weekly_pipeline()`。

兩條軌道：
- **軌道一**（`sync_track1_from_drive()`）：掃描 Google Drive 資料夾內 Robin 手動上傳的題目
  照片/音檔，依檔名比對成一題一題，呼叫 Gemini Vision 解析文字與選項，寫入 `toeic_questions`。
  聽力題若只有整包 MP3、還沒切成單題小檔，先用 Groq Whisper 依語句停頓自動切割（見
  `_find_split_plan()`：**啟發式邏輯，是 Robin 2026-08-07 已知情並選擇這次一起做的風險項**。
  同日用 Robin 提供的真實錄音 `Test01_Part1.mp3` 實測，發現有些音檔開頭會有一段作答說明語音
  （例如 TOEIC Part 1 開考前的固定口頭指示），若直接照「取最大的幾個停頓」切割，說明語音會被
  併進第一題、導致第一段長度異常；改為「無說明語音／有說明語音」兩種假設各切一次、比較每段
  長度變異數，自動選出較合理的一組，說明語音若被判定存在會直接捨棄不計入任何題目。之後可能
  仍需依更多真實素材微調）。
- **軌道二**（`generate_track2_vocab_questions()`）：呼叫 Gemini 即時生成多益核心單字英翻中
  選擇題，依 `users.toeic_weekly_question_count`（Robin 自訂，預設 21）產生新題，跳過已存在
  的單字避免重複出題、浪費 Token（FR-25e）。

檔名規則（Robin 2026-08-07 確認）：
- `toeic_{test_id}_write_{題號}.{ext}`：填空/單字題，只有圖片
- `toeic_{test_id}_listen_{題號}.{ext}`：聽力題，Robin 已切好的單題圖片/音檔
- `toeic_{test_id}_listen.mp3`：聽力題整包音檔（無題號），尚未切割，交給系統自動切割

去重（**2026-08-07 修正 FR-25f**：原規劃用「檔名日期是否在過去一週內」判斷，但 Robin 確認的
實際檔名格式沒有日期，這條規則對不上；改用 `toeic_questions.source_image_filename` 是否已存在
資料庫判斷是否處理過，更直覺也不會漏掉任何檔案）。軌道一天然是冪等的（重複掃到已處理過的檔案
會直接跳過），軌道二額外靠 `users.toeic_pipeline_last_run_on` 擋下同一個週日 22:00 那個小時內
`/healthz` 多次觸發造成的重複生成（否則會超出預期的每週題數）。
"""
import io
import json
import logging
import random
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from pydub import AudioSegment

from src.bot import toggles
from submodules.cloudsql.client import CloudSQLClient

_logger = logging.getLogger(__name__)

_TAIWAN_TZ = ZoneInfo("Asia/Taipei")
_PIPELINE_WEEKDAY = 6  # Python datetime.weekday()：Monday=0 ... Sunday=6
_PIPELINE_HOUR = 22
_FEATURE_KEY = "certificate"

_AUDIO_EXTENSIONS = {"mp3", "m4a", "wav", "ogg"}

_FILENAME_PATTERN = re.compile(
    r"^toeic_(?P<test_id>[0-9A-Za-z]+)_(?P<type>write|listen)(?:_(?P<qnum>\d+))?\.(?P<ext>[A-Za-z0-9]+)$"
)

_VISION_PARSE_PROMPT = (
    "你是 Robinson，請解析這張多益（TOEIC）題目照片，用以下固定格式輸出，不要輸出其他任何文字：\n"
    "QUESTION: <題目文字>\n"
    "OPTIONS: <選項，用「|」分隔，例如 A. xxx|B. xxx|C. xxx|D. xxx>\n"
    "若圖片中同時有多題，只解析看起來最完整、最主要的一題；若圖片模糊到完全無法辨識文字，"
    "QUESTION 欄位請填「無法辨識」。"
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
    """解析 TOEIC 素材檔名，回傳 `test_id`／`type`／`question_number`／`extension`；
    不符合規則（非 TOEIC 素材）回傳 `None`。
    """
    match = _FILENAME_PATTERN.match(filename)
    if match is None:
        return None
    groups = match.groupdict()
    return {
        "test_id": groups["test_id"],
        "type": groups["type"],
        "question_number": int(groups["qnum"]) if groups["qnum"] else None,
        "extension": groups["ext"],
    }


def classify_drive_files(files: list[dict]) -> dict:
    """把 Drive 檔案清單依檔名規則分成四類，供後續比對/切割使用；不符合命名規則的檔案忽略。

    回傳結構：
    - `write_images`：`{(test_id, qnum): file}`，填空/單字題圖片
    - `listen_images`：`{(test_id, qnum): file}`，聽力題圖片
    - `listen_audio_segments`：`{(test_id, qnum): file}`，已切好的單題聽力音檔
    - `listen_whole_audio`：`{test_id: file}`，尚未切割的整包聽力音檔
    """
    write_images: dict = {}
    listen_images: dict = {}
    listen_audio_segments: dict = {}
    listen_whole_audio: dict = {}

    for file in files:
        parsed = parse_filename(file["name"])
        if parsed is None:
            continue

        is_audio = parsed["extension"].lower() in _AUDIO_EXTENSIONS
        test_id = parsed["test_id"]
        qnum = parsed["question_number"]

        if parsed["type"] == "write":
            if qnum is not None and not is_audio:
                write_images[(test_id, qnum)] = file
        else:  # listen
            if qnum is None and is_audio:
                listen_whole_audio[test_id] = file
            elif qnum is not None and is_audio:
                listen_audio_segments[(test_id, qnum)] = file
            elif qnum is not None and not is_audio:
                listen_images[(test_id, qnum)] = file

    return {
        "write_images": write_images,
        "listen_images": listen_images,
        "listen_audio_segments": listen_audio_segments,
        "listen_whole_audio": listen_whole_audio,
    }


# --- 軌道一：Drive 掃描 + Gemini Vision 解析 ---


def _is_already_processed(db: CloudSQLClient, source_image_filename: str) -> bool:
    return (
        db.select(
            "toeic_questions",
            where="source_image_filename = %s",
            params=(source_image_filename,),
            fetch_one=True,
        )
        is not None
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


def _parse_question_image(image_bytes: bytes, image_llm_clients: list) -> dict | None:
    """呼叫 Gemini Vision 解析題目文字與選項；解析失敗或格式不符回傳 `None`（呼叫端記 log 跳過，
    不寫入髒資料，見 SPEC.md 風險表「比對失敗時不寫入資料庫」）。
    """
    llm_client = random.choice(image_llm_clients)
    try:
        raw = llm_client.generate_with_image(_VISION_PARSE_PROMPT, image_bytes, mime_type="image/jpeg")
    except Exception:
        _logger.exception("Gemini Vision 解析 TOEIC 題目圖片失敗")
        return None

    parsed = _parse_vision_output(raw)
    if parsed is None:
        _logger.warning("Gemini Vision 回覆格式不符預期，略過這題：%r", raw)
    return parsed


def _insert_question(db: CloudSQLClient, test_id: str, question_type: str, qnum: int, parsed: dict, image_file: dict, audio_url: str | None) -> None:
    db.insert(
        "toeic_questions",
        {
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
    for (test_id, qnum), image_file in classified["write_images"].items():
        if _is_already_processed(db, image_file["name"]):
            continue
        image_bytes = gdrive_client.download_file(image_file["id"])
        parsed = _parse_question_image(image_bytes, image_llm_clients)
        if parsed is None:
            continue
        _insert_question(db, test_id, "write", qnum, parsed, image_file, audio_url=None)


def _process_listen_questions_with_existing_audio(
    db: CloudSQLClient, gdrive_client, image_llm_clients: list, classified: dict
) -> None:
    for key, image_file in classified["listen_images"].items():
        audio_file = classified["listen_audio_segments"].get(key)
        if audio_file is None:
            continue
        if _is_already_processed(db, image_file["name"]):
            continue
        test_id, qnum = key
        image_bytes = gdrive_client.download_file(image_file["id"])
        parsed = _parse_question_image(image_bytes, image_llm_clients)
        if parsed is None:
            continue
        _insert_question(db, test_id, "listen", qnum, parsed, image_file, audio_url=audio_file.get("webViewLink"))


# 2026-08-07（Robin 實測 Test01_Part1.mp3 後追加）：有些整包音檔開頭會有一段作答說明語音
# （例如 TOEIC Part 1 開考前的固定口頭指示），有些則沒有——無法事先知道是哪一種，見下方
# `_find_split_plan()` 用「有無說明語音、說明語音在哪裡結束」多種假設各切一次、比較結果哪個
# 更合理來自動判斷。
_INTRO_MAX_CANDIDATE_RATIO = 0.6  # 說明語音只會出現在開頭，只在音檔前 60% 範圍內找它的結尾候選點
_MIN_GAP_RATIO_OF_MAX = 0.5  # 候選切割點的停頓長度至少要達到全音檔最大停頓的一半，排除句子內部的小停頓雜訊


def _segment_length_variance(start_offset: float, split_points: list[float], total_duration: float) -> float:
    """評估一組切割方案「每段音檔長度是否夠平均」的變異數，數值越小代表切割結果越合理。

    TOEIC 每一題的音檔長度通常彼此相近；若某一段明顯比其他段長很多（例如混進了說明語音或其他
    非題目內容），變異數會被拉高，藉此讓 `_find_split_plan()` 判斷出「這組切法比較不合理」。
    """
    boundaries = [start_offset] + split_points + [total_duration]
    lengths = [boundaries[i + 1] - boundaries[i] for i in range(len(boundaries) - 1)]
    if not lengths or any(length <= 0 for length in lengths):
        return float("inf")
    mean_length = sum(lengths) / len(lengths)
    return sum((length - mean_length) ** 2 for length in lengths) / len(lengths)


def _split_points_for_target_length(
    candidates: list[float], num_splits: int, start_offset: float, target_length: float
) -> list[float]:
    """依「每題預期長度」（`target_length`）找出最接近理想切割位置的自然停頓點；找不到候選點
    （或已被前一個切割點用掉）時，直接退回理想位置本身，確保一定會回傳 `num_splits` 個切割點。
    """
    used: set[float] = set()
    points: list[float] = []
    for k in range(1, num_splits + 1):
        target = start_offset + k * target_length
        remaining = [c for c in candidates if c not in used]
        nearest = min(remaining, key=lambda c: abs(c - target)) if remaining else None
        if nearest is None:
            points.append(target)
        else:
            used.add(nearest)
            points.append(nearest)
    return sorted(points)


def _find_split_plan(segments: list[dict], num_questions: int, total_duration: float) -> tuple[float, list[float]]:
    """決定切割方案，回傳 `(題目起始秒數, 題目之間的切割點列表)`。

    做法：候選切割點先篩選成「停頓長度至少達到全音檔最大停頓一半」的那些（`_MIN_GAP_RATIO_OF_
    MAX`），排除句子/說明語音內部無意義的小停頓雜訊——題目與題目之間的停頓通常明顯比句子內部的
    停頓長很多、彼此長度也相近，用比例篩選比單純取「最大的 N 個」更能過濾掉雜訊。接著把「完全
    沒有說明語音」（題目起始秒數＝0）以及「篩選後音檔前 60% 範圍內的每一個候選停頓都當作一次
    可能的說明語音結尾」逐一當作假設，各自把剩餘時間平分成 `num_questions` 題並計算
    `_segment_length_variance()`，最後選變異數最小（也就是每題長度最平均）的那組。

    **2026-08-07 修正**：原本只挑「前 60% 範圍內最大的那個停頓」當說明語音結尾、候選點也只是
    單純取「最大的 N 個」，但實測 Robin 提供的真實錄音 `Test01_Part1.mp3` 發現兩個問題：
    ① 說明語音結尾之後的題目間停頓，也有好幾個一樣落在前 60% 範圍內、量級相近，只取「最大」
    那個容易誤判成別的題目邊界，改為每個候選點都各自試切一次、實際比較結果優劣
    ② 候選點若只取「最大的 N 個」，當 N 訂得夠大時會混入大量句子內部的小停頓，這些小停頓剛好
    離某個理想切割位置很近時會被誤選中，讓「沒有說明語音」的假設看起來變異數異常地低（因為到處
    都找得到差不多近的小停頓去湊數，不代表真的是題目邊界）；改為依「停頓長度佔全音檔最大停頓的
    比例」篩選，只留下真正夠長、夠可能是題目邊界的候選點。**啟發式邏輯**，見模組 docstring 已知
    風險，之後可能仍需依更多真實素材調整。
    """
    if num_questions <= 1 or len(segments) < 2:
        return 0.0, []

    gaps = []
    for i in range(len(segments) - 1):
        gap_duration = segments[i + 1]["start"] - segments[i]["end"]
        midpoint = (segments[i]["end"] + segments[i + 1]["start"]) / 2
        gaps.append((gap_duration, midpoint))
    gaps.sort(key=lambda g: g[0], reverse=True)

    max_gap_duration = gaps[0][0]
    candidates = [midpoint for duration, midpoint in gaps if duration >= max_gap_duration * _MIN_GAP_RATIO_OF_MAX]
    # 篩選後的候選點若不夠湊出所需的切割數，代表比例門檻篩太嚴，放寬回取最大的 (num_questions - 1) 個，
    # 確保至少有足夠候選點可以組出一組切法（見 `_split_points_for_target_length` 的 fallback 保底）。
    if len(candidates) < num_questions - 1:
        candidates = [midpoint for _, midpoint in gaps[: num_questions - 1]]

    intro_hypotheses = [0.0] + sorted(c for c in candidates if c <= total_duration * _INTRO_MAX_CANDIDATE_RATIO)

    best_start_offset = 0.0
    best_points: list[float] = []
    best_variance = float("inf")
    for start_offset in intro_hypotheses:
        remaining_candidates = [c for c in candidates if c > start_offset]
        target_length = (total_duration - start_offset) / num_questions
        points = _split_points_for_target_length(remaining_candidates, num_questions - 1, start_offset, target_length)
        variance = _segment_length_variance(start_offset, points, total_duration)
        if variance < best_variance:
            best_variance = variance
            best_start_offset = start_offset
            best_points = points

    return best_start_offset, best_points


def split_audio_by_question_count(
    audio_bytes: bytes, question_numbers: list[int], transcript_segments: list[dict]
) -> dict[int, bytes]:
    """把整包音檔依 `_find_split_plan()` 決定的方案切成 `len(question_numbers)` 段，依序對應到
    由小到大排序的 `question_numbers`；若判斷開頭有說明語音，該段會被捨棄、不計入任何題目。
    需要系統安裝 `ffmpeg`（`pydub` 依賴，見 Dockerfile）。
    """
    sorted_numbers = sorted(question_numbers)
    audio = AudioSegment.from_file(io.BytesIO(audio_bytes))
    total_duration = len(audio) / 1000

    start_offset, split_points_sec = _find_split_plan(transcript_segments, len(sorted_numbers), total_duration)

    total_ms = len(audio)
    boundaries_ms = (
        [int(start_offset * 1000)] + [int(point * 1000) for point in split_points_sec] + [total_ms]
    )

    result: dict[int, bytes] = {}
    for qnum, start_ms, end_ms in zip(sorted_numbers, boundaries_ms[:-1], boundaries_ms[1:]):
        segment = audio[start_ms:end_ms]
        buffer = io.BytesIO()
        segment.export(buffer, format="mp3")
        result[qnum] = buffer.getvalue()
    return result


def _split_whole_audio(gdrive_client, voice_client, whole_audio_file: dict, question_numbers: list[int]) -> dict[int, bytes]:
    audio_bytes = gdrive_client.download_file(whole_audio_file["id"])
    segments = voice_client.transcribe_with_segments(
        audio_bytes, filename=whole_audio_file["name"], mime_type="audio/mpeg"
    )
    return split_audio_by_question_count(audio_bytes, question_numbers, segments)


def _process_listen_questions_needing_split(
    db: CloudSQLClient, gdrive_client, image_llm_clients: list, voice_client, classified: dict
) -> None:
    # 依 test_id 分組：找出「有聽力圖片、還沒有對應單題音檔、且該場次有整包音檔」的題號。
    pending_by_test_id: dict[str, list[int]] = {}
    for (test_id, qnum), image_file in classified["listen_images"].items():
        if (test_id, qnum) in classified["listen_audio_segments"]:
            continue
        if _is_already_processed(db, image_file["name"]):
            continue
        if test_id not in classified["listen_whole_audio"]:
            continue
        pending_by_test_id.setdefault(test_id, []).append(qnum)

    for test_id, question_numbers in pending_by_test_id.items():
        whole_audio_file = classified["listen_whole_audio"][test_id]
        try:
            segments_by_qnum = _split_whole_audio(gdrive_client, voice_client, whole_audio_file, question_numbers)
        except Exception:
            _logger.exception("整包 MP3 切割失敗（test_id=%s），這批聽力題暫緩處理，下次排程重試", test_id)
            continue

        for qnum in question_numbers:
            segment_bytes = segments_by_qnum.get(qnum)
            if segment_bytes is None:
                continue
            image_file = classified["listen_images"][(test_id, qnum)]
            try:
                segment_filename = f"toeic_{test_id}_listen_{qnum}.mp3"
                audio_url = gdrive_client.upload_file(segment_filename, segment_bytes, mime_type="audio/mpeg")
            except Exception:
                _logger.exception("上傳切割後的聽力小檔失敗（test_id=%s, qnum=%s）", test_id, qnum)
                continue

            image_bytes = gdrive_client.download_file(image_file["id"])
            parsed = _parse_question_image(image_bytes, image_llm_clients)
            if parsed is None:
                continue
            _insert_question(db, test_id, "listen", qnum, parsed, image_file, audio_url=audio_url)


def sync_track1_from_drive(db: CloudSQLClient, gdrive_client, image_llm_clients: list, voice_client) -> None:
    """FR-25a～FR-25c：掃描 Drive 資料夾，比對新的 write/listen 題目並解析寫入 DB。

    掃到 0 個檔案（例如 Robin 還沒上傳任何素材）時三個 `_process_*` 函式都會直接跑完、不做
    任何事，不會報錯，符合「還沒有素材也能安全部署」的要求。
    """
    files = gdrive_client.list_files(name_contains="toeic")
    classified = classify_drive_files(files)

    _process_write_questions(db, gdrive_client, image_llm_clients, classified)
    _process_listen_questions_with_existing_audio(db, gdrive_client, image_llm_clients, classified)
    _process_listen_questions_needing_split(db, gdrive_client, image_llm_clients, voice_client, classified)


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


def generate_track2_vocab_questions(db: CloudSQLClient, llm_client, count: int) -> int:
    """FR-25d～FR-25e：呼叫 Gemini 生成 `count` 題新的單字題（跳過已存在單字），寫入 DB。

    回傳實際成功生成並寫入的題數；單題生成失敗（格式不符/單字重複）只記 log 跳過，不中斷整批
    生成，避免一次沒生成好就整批都拿不到；`max_attempts` 設上限避免 Gemini 一直重複給同一批
    單字時無限迴圈。
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
