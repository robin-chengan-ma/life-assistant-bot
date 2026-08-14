-- Mobile App 飲食／運動雙輸入模式與 AI／人工來源追蹤（FR-64）。

ALTER TABLE diet_logs
    ADD COLUMN nutrition_source TEXT NOT NULL DEFAULT 'ai',
    ADD CONSTRAINT diet_logs_nutrition_source_check CHECK (nutrition_source IN ('ai', 'manual')),
    ADD CONSTRAINT diet_logs_calories_range_check
        CHECK (estimated_calories IS NULL OR (estimated_calories > 0 AND estimated_calories <= 10000)) NOT VALID,
    ADD CONSTRAINT diet_logs_macros_range_check CHECK (
        (protein_g IS NULL OR (protein_g >= 0 AND protein_g <= 1000))
        AND (carbs_g IS NULL OR (carbs_g >= 0 AND carbs_g <= 1000))
        AND (fat_g IS NULL OR (fat_g >= 0 AND fat_g <= 1000))
    ) NOT VALID,
    ADD CONSTRAINT diet_logs_manual_nutrition_required_check CHECK (
        entry_type <> 'food' OR nutrition_source <> 'manual'
        OR (estimated_calories IS NOT NULL AND protein_g IS NOT NULL
            AND carbs_g IS NOT NULL AND fat_g IS NOT NULL)
    );

UPDATE diet_logs SET nutrition_source = 'manual' WHERE entry_type = 'water';

ALTER TABLE exercise_logs
    ALTER COLUMN duration_minutes DROP NOT NULL,
    ADD COLUMN input_mode TEXT NOT NULL DEFAULT 'time',
    ADD COLUMN calorie_source TEXT NOT NULL DEFAULT 'ai',
    ADD COLUMN training_details TEXT,
    ADD CONSTRAINT exercise_logs_input_mode_check CHECK (input_mode IN ('time', 'calories')),
    ADD CONSTRAINT exercise_logs_calorie_source_check CHECK (calorie_source IN ('ai', 'manual')),
    ADD CONSTRAINT exercise_logs_calories_range_check
        CHECK (estimated_calories IS NULL OR (estimated_calories > 0 AND estimated_calories <= 5000)) NOT VALID,
    ADD CONSTRAINT exercise_logs_mode_fields_check CHECK (
        (input_mode = 'time' AND duration_minutes IS NOT NULL AND duration_minutes > 0 AND calorie_source = 'ai')
        OR (input_mode = 'calories' AND duration_minutes IS NULL AND heart_rate IS NULL
            AND estimated_calories IS NOT NULL AND calorie_source = 'manual')
    );

COMMENT ON COLUMN diet_logs.nutrition_source IS '營養數值來源：ai=完全採用 AI 估算，manual=人工輸入或修改 AI 數值';
COMMENT ON COLUMN exercise_logs.input_mode IS 'Mobile 輸入模式：time=依時間由 AI 估算，calories=人工輸入熱量';
COMMENT ON COLUMN exercise_logs.calorie_source IS '熱量來源：ai 或 manual';
COMMENT ON COLUMN exercise_logs.training_details IS '重訓時間模式的強度與組數描述，供 AI 估算熱量參考';
