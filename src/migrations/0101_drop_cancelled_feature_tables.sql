-- 2026-11 功能大幅精簡（Robin 明確決策，見 docs/ADR/discuss/ 對應條目）：Telegram 選單砍到只剩
-- 運動/飲食/體態、記帳、待辦事項（簡化為純一次性提醒）、生日設定（簡化為純週期性生日）、權限管理。
-- 本檔移除已無任何程式碼引用的功能模組資料表：心情小記、收藏與旅遊、成果展示、跨模組目標追蹤、
-- 功能開關、YouTube 技術情報、求職模組、TOEIC／證照題庫、個人技能成長電子報、系統錯誤管理與告警。
-- 這些表皆無真實保留價值的資料（詳見各功能盤點），刻意不使用 CASCADE：若發現未盤點到的依賴，
-- migration 必須失敗並停止，不可連帶刪除非預期的資料表。
--
-- 先移除會卡住後面 DROP TABLE 的跨模組外鍵／欄位，再依「先刪有外鍵指向其他待刪表的表」順序刪除。

BEGIN;

-- 記帳 (transactions) 保留，但指向即將刪除之 trips 的欄位必須先移除。
ALTER TABLE transactions DROP COLUMN IF EXISTS trip_id;

-- 個人技能成長：TOEIC／證照題庫（answer_logs／certificate_daily_assignments 先刪，
-- 兩者皆有外鍵指向 certificate_questions／toeic_vocab_questions）。
DROP TABLE IF EXISTS answer_logs;
DROP TABLE IF EXISTS certificate_daily_assignments;
DROP TABLE IF EXISTS certificate_questions;
DROP TABLE IF EXISTS toeic_vocab_questions;
DROP TABLE IF EXISTS certificate_listen_split_failures;
DROP TABLE IF EXISTS certificate_daily_settings;
DROP TABLE IF EXISTS certificate_daily_schedule_overrides;
DROP TABLE IF EXISTS certificate_goals;
DROP TABLE IF EXISTS exam_official_scores;
DROP TABLE IF EXISTS certificate_profiles;

-- 個人技能成長：每日技術分享電子報。
DROP TABLE IF EXISTS skill_growth_digests;

-- YouTube 技術情報模組。
DROP TABLE IF EXISTS youtube_topics;
DROP TABLE IF EXISTS youtube_pushed_videos;

-- 求職模組（job_applications／job_postings 先刪，皆有外鍵指向 job_postings／job_companies）。
DROP TABLE IF EXISTS job_applications;
DROP TABLE IF EXISTS job_postings;
DROP TABLE IF EXISTS job_companies;
DROP TABLE IF EXISTS job_search_criteria;

-- 心情小記。
DROP TABLE IF EXISTS mood_journals;

-- 收藏與旅遊、成果展示（Mobile App Phase 5）：先刪有外鍵指向 trips／collection_items／
-- exploration_events／achievements 的表，再刪這些被指向的表本身。
DROP TABLE IF EXISTS trip_itinerary_items;
DROP TABLE IF EXISTS trip_collection_items;
DROP TABLE IF EXISTS exploration_photos;
DROP TABLE IF EXISTS exploration_events;
DROP TABLE IF EXISTS collection_items;
DROP TABLE IF EXISTS trips;
DROP TABLE IF EXISTS user_achievements;
DROP TABLE IF EXISTS achievements;
DROP TABLE IF EXISTS achievement_candidates;

-- 跨模組目標追蹤（不是 body_goals，body_goals 保留）。
DROP TABLE IF EXISTS module_goals;
DROP TABLE IF EXISTS goal_summaries;

-- 功能開關與排程設定。
DROP TABLE IF EXISTS feature_toggles;

-- 系統錯誤管理與告警（子表先刪，皆有外鍵指向 system_error_reports）。
DROP TABLE IF EXISTS system_error_notification_recipients;
DROP TABLE IF EXISTS system_error_affected_users;
DROP TABLE IF EXISTS system_error_reports;

-- users 表上隨對應模組一併刪除的欄位。
ALTER TABLE users DROP COLUMN IF EXISTS toeic_weekly_question_count;
ALTER TABLE users DROP COLUMN IF EXISTS toeic_pipeline_last_run_on;
ALTER TABLE users DROP COLUMN IF EXISTS certificate_answer_reminder_sent_on;
ALTER TABLE users DROP COLUMN IF EXISTS youtube_last_run_on;
ALTER TABLE users DROP COLUMN IF EXISTS job_resume;
ALTER TABLE users DROP COLUMN IF EXISTS job_expectation;
ALTER TABLE users DROP COLUMN IF EXISTS years_of_experience;
ALTER TABLE users DROP COLUMN IF EXISTS expected_salary_min;
ALTER TABLE users DROP COLUMN IF EXISTS expected_salary_max;
ALTER TABLE users DROP COLUMN IF EXISTS job_search_last_run_on;

COMMIT;
