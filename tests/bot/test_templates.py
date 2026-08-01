from src.bot import templates


def test_appendix_a_text_matches_approved_wording_exactly():
    # 逐字比對 Robin 於 2026-07-30 核准的規範文本（robinson SPEC.md 附錄 A），
    # 避免日後有人不小心改動措辭卻沒有經過審核流程。
    expected = (
        "📋 以下是羅賓森的使用須知：\n"
        "\n"
        "✨ 服務使用須知：\n"
        "1. 本服務皆使用免費資源建置。\n"
        "2. 每個功能皆設有開關：若開啟後發現暫時不需要使用，請直接關閉，避免消耗 AI 使用額度。\n"
        "3. 支援「打字」或「語音」兩種訊息傳送方式。\n"
        "4. 想清除您與羅賓森的對話紀錄（不含知識庫內容）時，可以輸入「我想要刪除所有對話紀錄」。\n"
        "\n"
        "⚠️ 使用限制與規範：\n"
        "1. 嚴禁記錄個人敏感隱私資訊（如身分證字號、電話號碼、信用卡號等）。\n"
        "2. 圖片與語音檔案都可以上傳給羅賓森辨識，但僅支援這兩種格式喔！PDF、Excel、PPT 等其他檔案格式他沒辦法處理。\n"
        "3. 上傳影像前請務必確認內容不包含個人資料（如證件、帳單等），若上傳含有個資的影像，後果需由您自行承擔。\n"
        "4. 請勿拿來錄製長篇會議紀錄或演講（避免消耗大量 AI 使用額度）。\n"
        "5. 羅賓森目前僅會根據「已知知識」做出回答。若需要即時上網查詢的資訊"
        "（例如：「國道有沒有塞車」、「下午天氣如何」等），請先自行搜尋。若是固定知識"
        "（例如：「威靈頓牛排食譜」或「澎湖行程規劃」），您可以把答案提供給羅賓森，"
        "他會幫忙記錄下來、學習更多新知識喔！\n"
        "\n"
        "🔒 隱私承諾： 羅賓森非常注重「您的個人隱私」，絕對不會將您的個人資料與聊天記錄提供給其他人，"
        "包含「馬承安 (Robin)」本人也完全無法存取或查看喔！\n"
        "\n"
        "-----------------------------------\n"
        "💡 貼心小撇步：您可以長按這條訊息點選「釘選或置頂 (Pin)」，以後隨時查看規範更方便，"
        "又或是隨時在聊天室輸入「我要看使用規則」也能重新呼叫這份說明喔！"
        "如果您對羅賓森的服務有任何不滿意或想建議改進的地方，也歡迎隨時輸入「我要客訴你」告訴我們！"
    )
    assert templates.APPENDIX_A_TEXT == expected


def test_build_function_overview_raw_text_lists_every_feature():
    text = templates.build_function_overview_raw_text()
    for feature in templates.FEATURE_LIST:
        assert feature["name"] in text


def test_build_function_overview_raw_text_tags_owner_only_features():
    text = templates.build_function_overview_raw_text()
    lines = text.splitlines()
    for feature in templates.FEATURE_LIST:
        line = next(line for line in lines if feature["name"] in line)
        if feature["owner_only"]:
            assert "僅 Robin" in line
        else:
            assert "全體使用者" in line


def test_build_function_overview_raw_text_omits_examples():
    # 總覽階段的原始素材不該包含情境範例文字，避免總覽 LLM 呼叫的 prompt 過長（FR-56）
    text = templates.build_function_overview_raw_text()
    assert "情境" not in text


def test_build_function_manual_text_includes_examples_for_features_with_examples():
    text = templates.build_function_manual_text()
    assert "早餐花80元" in text  # 記帳 FR-56d
    assert "我下午要去買菜" in text  # 待辦事項 FR-56e
    assert "我最近想要找工作了" in text  # 求職 FR-56f
    assert "體態管理" in text  # 體態管理 FR-56g（功能名稱本身）
    assert "我想做心情筆記" in text  # 心情小記 FR-56h


def test_build_function_manual_text_marks_features_without_examples():
    text = templates.build_function_manual_text()
    assert "（此功能尚未實作，暫無範例）" in text


def test_build_function_manual_text_includes_every_feature_name():
    text = templates.build_function_manual_text()
    for feature in templates.FEATURE_LIST:
        assert feature["name"] in text
