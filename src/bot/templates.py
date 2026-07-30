"""靜態文字範本，皆不經過 LLM 生成（節省 Token，且措辭已經 Robin 逐字核准）。"""

# 對應 robinson SPEC.md 附錄 A，FR-6d（綁定成功歡迎訊息）與 FR-55（/rule）共用同一份文案。
# 2026-07-30 Robin 核准；若要調整措辭，須先更新 robinson SPEC.md 附錄 A 並記錄變更，不可直接改這裡。
APPENDIX_A_TEXT = (
    "📋 以下是羅賓森的使用須知：\n"
    "\n"
    "✨ 服務使用須知：\n"
    "1. 本服務皆使用免費資源建置。\n"
    "2. 每個功能皆設有開關：若開啟後發現暫時不需要使用，請直接關閉，避免消耗 AI 使用額度。\n"
    "3. 支援「打字」或「語音」兩種訊息傳送方式。\n"
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

# 對應 FR-56：/function 路由需涵蓋 spec 所有已定義的功能模組；正式文案模板待產品原型後由 Robin 補上
# （見 robinson SPEC.md 附錄 B），MVP 先用最簡單的條列格式呈現。
FEATURE_LIST = [
    {"key": "todo", "name": "待辦事項", "owner_only": False, "desc": "用自然語言記錄「什麼時候要做什麼事」"},
    {"key": "job_search", "name": "求職", "owner_only": False, "desc": "104 職缺追蹤與履歷契合度評分"},
    {"key": "budget", "name": "記帳", "owner_only": False, "desc": "每日記帳與花費預警"},
    {"key": "body", "name": "體態管理", "owner_only": False, "desc": "身高體重、運動、飲食紀錄"},
    {"key": "skill_growth", "name": "技能成長（TOEIC／技術情報）", "owner_only": True, "desc": "每日技術摘要、TOEIC 題庫、YouTube 技術影片推薦"},
    {"key": "mood_journal", "name": "心情小記", "owner_only": False, "desc": "記錄每日心情與隨筆"},
    {"key": "friend_mode", "name": "好友模式", "owner_only": False, "desc": "以聊天方式呈現心情趨勢並陪伴"},
    {"key": "important_notify", "name": "重要通知", "owner_only": False, "desc": "節日／生日提醒"},
    {"key": "complaint", "name": "客訴回饋", "owner_only": False, "desc": "輸入「我要客訴你」告訴我們哪裡需要改進"},
]


def build_function_list_text() -> str:
    """組出 /function 路由的簡易條列文字（MVP 版本，未來由 Robin 補正式文案）。"""
    lines = ["🤖 羅賓森目前的功能清單：", ""]
    for feature in FEATURE_LIST:
        tag = "👑 僅 Robin 可用" if feature["owner_only"] else "👨‍👩‍👧‍👦 全體使用者可用"
        lines.append(f"• {feature['name']}（{tag}）：{feature['desc']}")
    return "\n".join(lines)
