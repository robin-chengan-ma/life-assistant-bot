-- 重要通知模組：已知 5 位家人生日資料（Robin 提供，2026-08-04 核准），對應 FR-53。
-- 弟媳／大妹婿／小妹婿／阿姨的生日尚未提供，留待 Robin 之後用「設定家人生日」指令自行補上。
UPDATE users SET birthday = '1999-04-22' WHERE role = '弟弟';
UPDATE users SET birthday = '2000-05-27' WHERE role = '大妹';
UPDATE users SET birthday = '2000-05-27' WHERE role = '小妹';
UPDATE users SET birthday = '1970-08-01' WHERE role = '爸爸';
UPDATE users SET birthday = '1978-06-23' WHERE role = '媽媽';
