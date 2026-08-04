"""src/bot/finance.py 的單元測試（對應 robinson SPEC.md FR-41～FR-44，Step 2.1）。"""
from datetime import date, datetime, timezone

from src.bot import finance

# --- 交易類型/分類 ---


def test_format_type_prompt_lists_both_types():
    text = finance.format_type_prompt()
    assert "1. 支出" in text
    assert "2. 收入" in text


def test_resolve_type_accepts_index_and_label():
    assert finance.resolve_type("1") == "expense"
    assert finance.resolve_type("2") == "income"
    assert finance.resolve_type("支出") == "expense"
    assert finance.resolve_type("收入") == "income"


def test_resolve_type_rejects_unrecognized_text():
    assert finance.resolve_type("0") is None
    assert finance.resolve_type("3") is None
    assert finance.resolve_type("花錢") is None


def test_type_label_returns_chinese_label():
    assert finance.type_label("expense") == "支出"
    assert finance.type_label("income") == "收入"


def test_categories_for_type_differs_by_type():
    assert finance.categories_for_type("expense") == finance.EXPENSE_CATEGORIES
    assert finance.categories_for_type("income") == finance.INCOME_CATEGORIES


def test_format_category_prompt_lists_categories_for_expense():
    text = finance.format_category_prompt("expense")
    assert "1. 餐飲" in text
    assert "7. 其他" in text


def test_format_category_prompt_lists_categories_for_income():
    text = finance.format_category_prompt("income")
    assert "1. 薪資" in text
    assert "3. 其他" in text


def test_resolve_category_accepts_index_and_label():
    assert finance.resolve_category("expense", "1") == "餐飲"
    assert finance.resolve_category("expense", "購物") == "購物"
    assert finance.resolve_category("income", "1") == "薪資"


def test_resolve_category_rejects_out_of_range_or_wrong_type():
    assert finance.resolve_category("expense", "0") is None
    assert finance.resolve_category("expense", "8") is None
    assert finance.resolve_category("income", "薪資水") is None


# --- 交易 CRUD ---


def test_create_transaction_inserts_row(fake_db):
    transaction_id = finance.create_transaction(
        fake_db, user_id=1, transaction_type="expense", category="餐飲", amount=120, note="午餐",
        transaction_date=date(2026, 8, 4),
    )

    row = fake_db.select("transactions", where="id = %s", params=(transaction_id,), fetch_one=True)
    assert row["user_id"] == 1
    assert row["type"] == "expense"
    assert row["category"] == "餐飲"
    assert row["amount"] == 120
    assert row["note"] == "午餐"
    assert row["transaction_date"] == date(2026, 8, 4)


def test_update_transaction_changes_fields_but_not_date(fake_db):
    transaction_id = finance.create_transaction(
        fake_db, 1, "expense", "餐飲", 100, "早餐", date(2026, 8, 1)
    )

    finance.update_transaction(fake_db, transaction_id, "expense", "交通", 50, "改過的備註")

    row = fake_db.select("transactions", where="id = %s", params=(transaction_id,), fetch_one=True)
    assert row["category"] == "交通"
    assert row["amount"] == 50
    assert row["note"] == "改過的備註"
    assert row["transaction_date"] == date(2026, 8, 1)


def test_delete_transaction_removes_row(fake_db):
    transaction_id = finance.create_transaction(fake_db, 1, "expense", "餐飲", 100, None, date(2026, 8, 1))

    finance.delete_transaction(fake_db, transaction_id)

    assert fake_db.select("transactions", where="id = %s", params=(transaction_id,), fetch_one=True) is None


def test_list_transactions_sorts_by_date_descending(fake_db):
    old_id = finance.create_transaction(fake_db, 1, "expense", "餐飲", 100, None, date(2026, 8, 1))
    new_id = finance.create_transaction(fake_db, 1, "expense", "交通", 50, None, date(2026, 8, 4))

    transactions = finance.list_transactions(fake_db, 1)

    assert [row["id"] for row in transactions] == [new_id, old_id]


def test_list_transactions_limits_result_count(fake_db):
    for day in range(1, 6):
        finance.create_transaction(fake_db, 1, "expense", "餐飲", 100, None, date(2026, 8, day))

    transactions = finance.list_transactions(fake_db, 1, limit=2)

    assert len(transactions) == 2
    assert transactions[0]["transaction_date"] == date(2026, 8, 5)


def test_format_transaction_list_empty():
    assert finance.format_transaction_list([]) == "目前還沒有記帳紀錄喔！"


def test_format_transaction_list_shows_expense_and_income_with_sign(fake_db):
    finance.create_transaction(fake_db, 1, "expense", "餐飲", 120, "午餐", date(2026, 8, 4))
    finance.create_transaction(fake_db, 1, "income", "薪資", 50000, None, date(2026, 8, 5))
    transactions = finance.list_transactions(fake_db, 1)

    text = finance.format_transaction_list(transactions)

    assert "薪資 +50000 元" in text
    assert "餐飲 -120 元　午餐" in text


# --- 預算設定 ---


def test_set_and_get_monthly_budget(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": 1, "role": "Robin", "is_owner": True})

    finance.set_monthly_budget(fake_db, user_id, 15000)

    assert finance.get_monthly_budget(fake_db, user_id) == 15000.0


def test_get_monthly_budget_returns_none_when_unset(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": 1, "role": "Robin", "is_owner": True})

    assert finance.get_monthly_budget(fake_db, user_id) is None


def test_get_monthly_budget_returns_none_when_user_not_found(fake_db):
    assert finance.get_monthly_budget(fake_db, 999) is None


# --- 月加總 ---


def test_monthly_expense_total_only_counts_expense_within_month(fake_db):
    finance.create_transaction(fake_db, 1, "expense", "餐飲", 100, None, date(2026, 8, 1))
    finance.create_transaction(fake_db, 1, "expense", "交通", 50, None, date(2026, 8, 31))
    finance.create_transaction(fake_db, 1, "income", "薪資", 50000, None, date(2026, 8, 5))  # 不算支出
    finance.create_transaction(fake_db, 1, "expense", "餐飲", 999, None, date(2026, 7, 31))  # 不同月不算
    finance.create_transaction(fake_db, 1, "expense", "餐飲", 999, None, date(2026, 9, 1))  # 不同月不算

    assert finance.monthly_expense_total(fake_db, 1, 2026, 8) == 150.0


def test_monthly_expense_total_handles_december_month_boundary(fake_db):
    finance.create_transaction(fake_db, 1, "expense", "餐飲", 100, None, date(2026, 12, 31))
    finance.create_transaction(fake_db, 1, "expense", "餐飲", 999, None, date(2027, 1, 1))  # 不算

    assert finance.monthly_expense_total(fake_db, 1, 2026, 12) == 100.0


def test_monthly_income_total_only_counts_income(fake_db):
    finance.create_transaction(fake_db, 1, "income", "薪資", 50000, None, date(2026, 8, 5))
    finance.create_transaction(fake_db, 1, "expense", "餐飲", 100, None, date(2026, 8, 1))

    assert finance.monthly_income_total(fake_db, 1, 2026, 8) == 50000.0


def test_monthly_expense_breakdown_sorted_by_amount_desc(fake_db):
    finance.create_transaction(fake_db, 1, "expense", "餐飲", 100, None, date(2026, 8, 1))
    finance.create_transaction(fake_db, 1, "expense", "交通", 500, None, date(2026, 8, 2))
    finance.create_transaction(fake_db, 1, "expense", "餐飲", 50, None, date(2026, 8, 3))

    breakdown = finance.monthly_expense_breakdown(fake_db, 1, 2026, 8)

    assert breakdown == [("交通", 500.0), ("餐飲", 150.0)]


# --- FR-44 文字摘要 ---


def test_format_monthly_summary_without_budget(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": 1, "role": "Robin", "is_owner": True})
    finance.create_transaction(fake_db, user_id, "expense", "餐飲", 100, None, date(2026, 8, 1))
    finance.create_transaction(fake_db, user_id, "income", "薪資", 50000, None, date(2026, 8, 1))

    text = finance.format_monthly_summary(fake_db, user_id, date(2026, 8, 4))

    assert "支出總計：100 元" in text
    assert "收入總計：50000 元" in text
    assert "尚未設定每月支出預算上限" in text
    assert "餐飲：100 元（100%）" in text


def test_format_monthly_summary_with_budget_shows_usage_percent(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": 1, "role": "Robin", "is_owner": True})
    finance.set_monthly_budget(fake_db, user_id, 1000)
    finance.create_transaction(fake_db, user_id, "expense", "餐飲", 500, None, date(2026, 8, 1))

    text = finance.format_monthly_summary(fake_db, user_id, date(2026, 8, 4))

    assert "預算上限：1000 元（已使用 50%）" in text


def test_format_monthly_summary_compares_with_previous_month(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": 1, "role": "Robin", "is_owner": True})
    finance.create_transaction(fake_db, user_id, "expense", "餐飲", 100, None, date(2026, 7, 15))
    finance.create_transaction(fake_db, user_id, "expense", "餐飲", 150, None, date(2026, 8, 1))

    text = finance.format_monthly_summary(fake_db, user_id, date(2026, 8, 4))

    assert "跟上個月（100 元）相比，增加了 50%" in text


def test_format_monthly_summary_handles_january_previous_month_boundary(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": 1, "role": "Robin", "is_owner": True})
    finance.create_transaction(fake_db, user_id, "expense", "餐飲", 100, None, date(2025, 12, 20))
    finance.create_transaction(fake_db, user_id, "expense", "餐飲", 80, None, date(2026, 1, 5))

    text = finance.format_monthly_summary(fake_db, user_id, date(2026, 1, 10))

    assert "跟上個月（100 元）相比，減少了 20%" in text


def test_format_monthly_summary_skips_comparison_when_no_previous_month_data(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": 1, "role": "Robin", "is_owner": True})
    finance.create_transaction(fake_db, user_id, "expense", "餐飲", 100, None, date(2026, 8, 1))

    text = finance.format_monthly_summary(fake_db, user_id, date(2026, 8, 4))

    assert "跟上個月" not in text


def test_format_monthly_summary_skips_breakdown_when_no_expenses(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": 1, "role": "Robin", "is_owner": True})

    text = finance.format_monthly_summary(fake_db, user_id, date(2026, 8, 4))

    assert "支出分類佔比" not in text


# --- FR-43 門檻預警推播 ---


class _FakeTelegramClient:
    def __init__(self):
        self.sent = []

    def send_text(self, chat_id, text):
        self.sent.append((chat_id, text))


def test_check_and_push_budget_alerts_sends_mid_month_alert_before_day_15(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": 1, "role": "Robin", "is_owner": True})
    finance.set_monthly_budget(fake_db, user_id, 1000)
    finance.create_transaction(fake_db, user_id, "expense", "餐飲", 500, None, date(2026, 8, 10))
    telegram_client = _FakeTelegramClient()

    finance.check_and_push_budget_alerts(
        fake_db, telegram_client, now=datetime(2026, 8, 10, 3, 0, tzinfo=timezone.utc)  # 台灣時間 11:00
    )

    assert len(telegram_client.sent) == 1
    assert "50%" in telegram_client.sent[0][1]
    row = fake_db.select("users", where="id = %s", params=(user_id,), fetch_one=True)
    assert row["budget_alert_50_sent_month"] == date(2026, 8, 1)


def test_check_and_push_budget_alerts_skips_mid_month_alert_after_day_15(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": 1, "role": "Robin", "is_owner": True})
    finance.set_monthly_budget(fake_db, user_id, 1000)
    finance.create_transaction(fake_db, user_id, "expense", "餐飲", 500, None, date(2026, 8, 20))
    telegram_client = _FakeTelegramClient()

    finance.check_and_push_budget_alerts(
        fake_db, telegram_client, now=datetime(2026, 8, 20, 3, 0, tzinfo=timezone.utc)
    )

    assert telegram_client.sent == []


def test_check_and_push_budget_alerts_sends_severe_alert_any_day(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": 1, "role": "Robin", "is_owner": True})
    finance.set_monthly_budget(fake_db, user_id, 1000)
    finance.create_transaction(fake_db, user_id, "expense", "餐飲", 850, None, date(2026, 8, 25))
    telegram_client = _FakeTelegramClient()

    finance.check_and_push_budget_alerts(
        fake_db, telegram_client, now=datetime(2026, 8, 25, 3, 0, tzinfo=timezone.utc)
    )

    assert len(telegram_client.sent) == 1
    assert "80%" in telegram_client.sent[0][1] or "85%" in telegram_client.sent[0][1]
    row = fake_db.select("users", where="id = %s", params=(user_id,), fetch_one=True)
    assert row["budget_alert_80_sent_month"] == date(2026, 8, 1)


def test_check_and_push_budget_alerts_does_not_resend_within_same_month(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": 1, "role": "Robin", "is_owner": True})
    finance.set_monthly_budget(fake_db, user_id, 1000)
    finance.create_transaction(fake_db, user_id, "expense", "餐飲", 900, None, date(2026, 8, 10))
    telegram_client = _FakeTelegramClient()
    now = datetime(2026, 8, 10, 3, 0, tzinfo=timezone.utc)

    finance.check_and_push_budget_alerts(fake_db, telegram_client, now=now)
    first_count = len(telegram_client.sent)
    finance.check_and_push_budget_alerts(fake_db, telegram_client, now=now)

    assert first_count == 2  # 50% 與 80% 門檻都達標，各推播一次
    assert len(telegram_client.sent) == 2  # 第二次呼叫沒有重複推播


def test_check_and_push_budget_alerts_skips_user_without_budget(fake_db):
    fake_db.insert("users", {"telegram_user_id": 1, "role": "Robin", "is_owner": True})
    telegram_client = _FakeTelegramClient()

    finance.check_and_push_budget_alerts(fake_db, telegram_client, now=datetime(2026, 8, 10, 3, 0, tzinfo=timezone.utc))

    assert telegram_client.sent == []


def test_check_and_push_budget_alerts_skips_user_without_telegram_id(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": None, "role": "媽媽", "is_owner": False})
    finance.set_monthly_budget(fake_db, user_id, 1000)
    finance.create_transaction(fake_db, user_id, "expense", "餐飲", 900, None, date(2026, 8, 10))
    telegram_client = _FakeTelegramClient()

    finance.check_and_push_budget_alerts(fake_db, telegram_client, now=datetime(2026, 8, 10, 3, 0, tzinfo=timezone.utc))

    assert telegram_client.sent == []


def test_check_and_push_budget_alerts_skips_zero_budget(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": 1, "role": "Robin", "is_owner": True})
    finance.set_monthly_budget(fake_db, user_id, 0)
    finance.create_transaction(fake_db, user_id, "expense", "餐飲", 100, None, date(2026, 8, 10))
    telegram_client = _FakeTelegramClient()

    finance.check_and_push_budget_alerts(fake_db, telegram_client, now=datetime(2026, 8, 10, 3, 0, tzinfo=timezone.utc))

    assert telegram_client.sent == []


def test_check_and_push_budget_alerts_default_now_uses_utc_now(fake_db, monkeypatch):
    """防禦性測試：不傳 now 時應該使用目前的真實時間，而不是拋出例外。"""
    fake_db.insert("users", {"telegram_user_id": 1, "role": "Robin", "is_owner": True})

    finance.check_and_push_budget_alerts(fake_db, _FakeTelegramClient())


# --- FR-41a 預算套用範圍/月份解析 ---


def test_format_budget_scope_prompt_lists_both_options():
    text = finance.format_budget_scope_prompt()
    assert "1. 全部月份" in text
    assert "2. 只套用某幾個月" in text


def test_resolve_budget_scope_accepts_index_and_keyword():
    assert finance.resolve_budget_scope("1") == "global"
    assert finance.resolve_budget_scope("2") == "months"
    assert finance.resolve_budget_scope("全部月份") == "global"
    assert finance.resolve_budget_scope("只套用某幾個月") == "months"
    assert finance.resolve_budget_scope("全部") == "global"
    assert finance.resolve_budget_scope("某幾個月") == "months"


def test_resolve_budget_scope_rejects_unrecognized_text():
    assert finance.resolve_budget_scope("0") is None
    assert finance.resolve_budget_scope("3") is None
    assert finance.resolve_budget_scope("隨便") is None


def test_parse_months_accepts_comma_and_dun_separator():
    assert finance.parse_months("8,9") == [8, 9]
    assert finance.parse_months("8、9") == [8, 9]
    assert finance.parse_months("8月, 9月") == [8, 9]
    assert finance.parse_months("8") == [8]


def test_parse_months_dedupes_and_preserves_order():
    assert finance.parse_months("9,8,9") == [9, 8]


def test_parse_months_rejects_out_of_range_or_non_numeric():
    assert finance.parse_months("13") is None
    assert finance.parse_months("0") is None
    assert finance.parse_months("八月") is None
    assert finance.parse_months("") is None


def test_format_months_label_joins_with_dun():
    assert finance.format_months_label([8, 9]) == "8月、9月"


def test_format_budget_global_confirm_prompt_shows_current_amount():
    text = finance.format_budget_global_confirm_prompt(43000)
    assert "43000 元" in text
    assert "確認要改成新的金額嗎" in text


def test_format_budget_override_confirm_prompt_lists_conflicts():
    text = finance.format_budget_override_confirm_prompt([(8, 43000.0), (9, 50000.0)])
    assert "8月：43000 元" in text
    assert "9月：50000 元" in text


# --- FR-41a 預算覆蓋 CRUD / 生效預算查詢 ---


def test_get_budget_override_returns_none_when_unset(fake_db):
    assert finance.get_budget_override(fake_db, 1, 2026, 8) is None


def test_set_budget_override_inserts_new_row(fake_db):
    finance.set_budget_override(fake_db, 1, 2026, 8, 43000)

    assert finance.get_budget_override(fake_db, 1, 2026, 8) == 43000.0


def test_set_budget_override_updates_existing_row(fake_db):
    finance.set_budget_override(fake_db, 1, 2026, 8, 43000)
    finance.set_budget_override(fake_db, 1, 2026, 8, 50000)

    assert finance.get_budget_override(fake_db, 1, 2026, 8) == 50000.0
    assert len(fake_db.select("budget_overrides", where="user_id = %s", params=(1,))) == 1


def test_get_effective_monthly_budget_prefers_override_over_default(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": 1, "role": "Robin", "is_owner": True})
    finance.set_monthly_budget(fake_db, user_id, 15000)
    finance.set_budget_override(fake_db, user_id, 2026, 8, 43000)

    assert finance.get_effective_monthly_budget(fake_db, user_id, 2026, 8) == 43000.0
    assert finance.get_effective_monthly_budget(fake_db, user_id, 2026, 9) == 15000.0


def test_get_effective_monthly_budget_none_when_neither_set(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": 1, "role": "Robin", "is_owner": True})

    assert finance.get_effective_monthly_budget(fake_db, user_id, 2026, 8) is None


def test_format_monthly_summary_uses_override_budget(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": 1, "role": "Robin", "is_owner": True})
    finance.set_monthly_budget(fake_db, user_id, 1000)
    finance.set_budget_override(fake_db, user_id, 2026, 8, 2000)
    finance.create_transaction(fake_db, user_id, "expense", "餐飲", 1000, None, date(2026, 8, 1))

    text = finance.format_monthly_summary(fake_db, user_id, date(2026, 8, 4))

    assert "預算上限：2000 元（已使用 50%）" in text


def test_check_and_push_budget_alerts_uses_override_only_user_without_default(fake_db):
    """使用者從未設定全局預設，只針對這個月設了覆蓋值，門檻預警仍要抓得到（決策⑤）。"""
    user_id = fake_db.insert("users", {"telegram_user_id": 1, "role": "Robin", "is_owner": True})
    finance.set_budget_override(fake_db, user_id, 2026, 8, 1000)
    finance.create_transaction(fake_db, user_id, "expense", "餐飲", 900, None, date(2026, 8, 20))
    telegram_client = _FakeTelegramClient()

    finance.check_and_push_budget_alerts(
        fake_db, telegram_client, now=datetime(2026, 8, 20, 3, 0, tzinfo=timezone.utc)
    )

    assert len(telegram_client.sent) == 1
    assert "80%" in telegram_client.sent[0][1] or "90%" in telegram_client.sent[0][1]


# --- FR-42a 每日記帳提醒 ---


def test_check_and_push_finance_reminders_sends_when_no_expense_today(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": 1, "role": "Robin", "is_owner": True})
    finance.set_monthly_budget(fake_db, user_id, 15000)
    telegram_client = _FakeTelegramClient()

    finance.check_and_push_finance_reminders(
        fake_db, telegram_client, now=datetime(2026, 8, 4, 15, 0, tzinfo=timezone.utc)  # 台灣時間 23:00
    )

    assert len(telegram_client.sent) == 1
    assert telegram_client.sent[0][0] == 1
    row = fake_db.select("users", where="id = %s", params=(user_id,), fetch_one=True)
    assert row["finance_reminder_sent_date"] == date(2026, 8, 4)


def test_check_and_push_finance_reminders_skips_when_already_recorded_today(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": 1, "role": "Robin", "is_owner": True})
    finance.set_monthly_budget(fake_db, user_id, 15000)
    finance.create_transaction(fake_db, user_id, "expense", "餐飲", 100, None, date(2026, 8, 4))
    telegram_client = _FakeTelegramClient()

    finance.check_and_push_finance_reminders(
        fake_db, telegram_client, now=datetime(2026, 8, 4, 15, 0, tzinfo=timezone.utc)
    )

    assert telegram_client.sent == []


def test_check_and_push_finance_reminders_skips_outside_reminder_hour(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": 1, "role": "Robin", "is_owner": True})
    finance.set_monthly_budget(fake_db, user_id, 15000)
    telegram_client = _FakeTelegramClient()

    finance.check_and_push_finance_reminders(
        fake_db, telegram_client, now=datetime(2026, 8, 4, 3, 0, tzinfo=timezone.utc)  # 台灣時間 11:00
    )

    assert telegram_client.sent == []


def test_check_and_push_finance_reminders_skips_user_without_budget(fake_db):
    fake_db.insert("users", {"telegram_user_id": 1, "role": "Robin", "is_owner": True})
    telegram_client = _FakeTelegramClient()

    finance.check_and_push_finance_reminders(
        fake_db, telegram_client, now=datetime(2026, 8, 4, 15, 0, tzinfo=timezone.utc)
    )

    assert telegram_client.sent == []


def test_check_and_push_finance_reminders_skips_user_without_telegram_id(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": None, "role": "媽媽", "is_owner": False})
    finance.set_monthly_budget(fake_db, user_id, 15000)
    telegram_client = _FakeTelegramClient()

    finance.check_and_push_finance_reminders(
        fake_db, telegram_client, now=datetime(2026, 8, 4, 15, 0, tzinfo=timezone.utc)
    )

    assert telegram_client.sent == []


def test_check_and_push_finance_reminders_does_not_resend_same_day(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": 1, "role": "Robin", "is_owner": True})
    finance.set_monthly_budget(fake_db, user_id, 15000)
    telegram_client = _FakeTelegramClient()
    now = datetime(2026, 8, 4, 15, 0, tzinfo=timezone.utc)

    finance.check_and_push_finance_reminders(fake_db, telegram_client, now=now)
    finance.check_and_push_finance_reminders(fake_db, telegram_client, now=now)

    assert len(telegram_client.sent) == 1


def test_check_and_push_finance_reminders_uses_override_only_user_without_default(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": 1, "role": "Robin", "is_owner": True})
    finance.set_budget_override(fake_db, user_id, 2026, 8, 20000)
    telegram_client = _FakeTelegramClient()

    finance.check_and_push_finance_reminders(
        fake_db, telegram_client, now=datetime(2026, 8, 4, 15, 0, tzinfo=timezone.utc)
    )

    assert len(telegram_client.sent) == 1


def test_check_and_push_finance_reminders_default_now_uses_utc_now(fake_db):
    """防禦性測試：不傳 now 時應該使用目前的真實時間，而不是拋出例外。"""
    fake_db.insert("users", {"telegram_user_id": 1, "role": "Robin", "is_owner": True})

    finance.check_and_push_finance_reminders(fake_db, _FakeTelegramClient())
