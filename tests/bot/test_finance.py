"""src/bot/finance.py 的單元測試（對應 robinson SPEC.md FR-41～FR-44，Step 2.1）。"""
from datetime import date

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
