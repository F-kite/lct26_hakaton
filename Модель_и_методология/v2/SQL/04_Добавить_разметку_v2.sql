-- Дополнительный слой разметки новой модели.
-- Запускать после 01, 02 и 03. Таблица не меняет исходные баллы.
BEGIN;
CREATE TABLE IF NOT EXISTS signals.model_v2_annotations (
    id text PRIMARY KEY,
    technology_group text,
    partition_name text,
    label text CHECK (label IN ('weak','mature','noise')),
    annotation_origin text,
    url text,
    title text,
    published_at text,
    reason text
);
CREATE INDEX IF NOT EXISTS idx_model_v2_annotations_label ON signals.model_v2_annotations(label);
CREATE INDEX IF NOT EXISTS idx_model_v2_annotations_partition ON signals.model_v2_annotations(partition_name);
COMMIT;
-- Данные для этой таблицы находятся в ../Данные/Разметка.csv.
-- Их загружает backend или psql-команда COPY после проверки пути к CSV:
-- \copy signals.model_v2_annotations FROM '.../Разметка.csv' WITH (FORMAT csv, HEADER true, NULL '');
