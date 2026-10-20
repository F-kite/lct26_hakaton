-- Открывай в Query Tool базы technology_signals.
-- Выделяй один SELECT до точки с запятой и нажимай F5.
-- Проверки ничего не изменяют. Ожидаемые результаты подписаны рядом.

-- 1. Количество строк: 100, 7299, 248, 19.
SELECT 'reference_signals' AS dataset, count(*) FROM signals.reference_signals
UNION ALL SELECT 'publications', count(*) FROM signals.publications
UNION ALL SELECT 'training_examples', count(*) FROM signals.training_examples
UNION ALL SELECT 'source_catalog', count(*) FROM signals.source_catalog;

-- 2. Пропуск — NULL или пустая строка. Это НЕ числовой ноль.
-- В ленте: описание 2935; автор 327; дата 5; категории 3893.
SELECT count(*) FILTER (WHERE NULLIF(btrim(summary), '') IS NULL) AS missing_summary,
       count(*) FILTER (WHERE NULLIF(btrim(author), '') IS NULL) AS missing_author,
       count(*) FILTER (WHERE NULLIF(btrim(published_at), '') IS NULL) AS missing_date,
       count(*) FILTER (WHERE NULLIF(btrim(raw_categories), '') IS NULL) AS missing_categories
FROM signals.publications;

-- 3. Пропуски основных полей, нулевые ID: везде 0.
SELECT count(*) FILTER (WHERE NULLIF(btrim(id), '') IS NULL) AS missing_id,
       count(*) FILTER (WHERE NULLIF(btrim(url), '') IS NULL) AS missing_url,
       count(*) FILTER (WHERE NULLIF(btrim(title), '') IS NULL) AS missing_title,
       count(*) FILTER (WHERE btrim(id) = '0') AS zero_id
FROM signals.publications;

-- 4. Дубли ID и URL: обе выдачи пустые.
SELECT id, count(*) FROM signals.publications GROUP BY id HAVING count(*) > 1;
SELECT url, count(*) FROM signals.publications GROUP BY url HAVING count(*) > 1;

-- 5. Одинаковые заголовки после приведения регистра и пробелов: 35 пар.
-- Это кандидаты на объединение, а не разрешение автоматически удалить статью.
SELECT lower(regexp_replace(btrim(title), '\s+', ' ', 'g')) AS title_key, count(*)
FROM signals.publications GROUP BY 1 HAVING count(*) > 1 ORDER BY 2 DESC;

-- 6. Описание дословно повторяет заголовок: 2537 строк.
SELECT count(*) AS summary_equals_title FROM signals.publications
WHERE lower(btrim(summary)) = lower(btrim(title));

-- 7. Разные годы в ссылке и заполненной дате: 76 строк.
-- Проверить страницу. Год в URL не является доказательством ошибки даты.
SELECT id, title, url, published_at FROM signals.publications
WHERE published_at IS NOT NULL
  AND substring(url from '/(20[0-9]{2})/') IS NOT NULL
  AND substring(url from '/(20[0-9]{2})/') <> left(published_at, 4);

-- 8. Состав ленты. Уровень доверия к сайту НЕ является классом технологии.
SELECT source_name, count(*) FROM signals.publications GROUP BY 1 ORDER BY 2 DESC;
SELECT language, count(*) FROM signals.publications GROUP BY 1;
SELECT trust_level, count(*) FROM signals.publications GROUP BY 1;
SELECT sponsored, is_translated, count(*) FROM signals.publications GROUP BY 1, 2;

-- 9. Пропуски, нули и дубли исходного Excel: все счётчики 0; выдача дублей пустая.
SELECT count(*) FILTER (WHERE source_no IS NULL) AS missing_id,
       count(*) FILTER (WHERE technology IS NULL) AS missing_technology,
       count(*) FILTER (WHERE direction IS NULL) AS missing_direction,
       count(*) FILTER (WHERE score IS NULL) AS missing_score,
       count(*) FILTER (WHERE score = '0') AS zero_score,
       count(*) FILTER (WHERE source_links IS NULL) AS missing_sources
FROM signals.reference_signals;
SELECT source_no, count(*) FROM signals.reference_signals GROUP BY 1 HAVING count(*) > 1;
SELECT lower(btrim(technology)), count(*) FROM signals.reference_signals GROUP BY 1 HAVING count(*) > 1;
SELECT direction, count(*) FROM signals.reference_signals GROUP BY 1 ORDER BY 1;

-- 10. Проверяем числовой формат перед приведением типов: выдача пустая.
SELECT source_no, score, stage_points, trend_points FROM signals.reference_signals
WHERE score !~ '^[0-9]+$' OR stage_points !~ '^[0-9]+$' OR trend_points !~ '^[0-9]+$';

-- 11. Распределение баллов: 3→7, 4→22, 5→28, 6→28, 7→15.
SELECT score::integer AS score, count(*) FROM signals.reference_signals GROUP BY 1 ORDER BY 1;

-- 12. Гипотеза: балл = стадия + темп роста. Совпадает 97 раз из 100.
-- Стадия: исследование 1; прототип/PoC 2; пилот 3; раннее внедрение 4.
-- Тренд: стабилен 1; растёт 2; растёт быстро 3.
-- Кодирование основано на словесных описаниях; при нескольких стадиях взята наиболее поздняя.
SELECT count(*) FILTER (WHERE score::integer = stage_points::integer + trend_points::integer) AS matches,
       count(*) AS total FROM signals.reference_signals;

-- 13. Расхождения: №66 (5 вместо 7), №69 (5 вместо 7), №93 (4 вместо 6).
-- Не исправляем: формула не подтверждена авторами исходного файла.
SELECT source_no, technology, stage, trend, score::integer AS original_score,
       stage_points::integer + trend_points::integer AS calculated_score
FROM signals.reference_signals
WHERE score::integer <> stage_points::integer + trend_points::integer
ORDER BY source_no::integer;

-- 14. Состав размеченных данных: обучение 172, проверка 76.
SELECT dataset_part, label, count(*) FROM signals.training_examples GROUP BY 1, 2 ORDER BY 1, 2;

-- 15. Технология не должна встретиться и в обучении, и в проверке: выдача пустая.
SELECT technology_group, count(DISTINCT dataset_part)
FROM signals.training_examples GROUP BY 1 HAVING count(DISTINCT dataset_part) > 1;
SELECT url, count(DISTINCT dataset_part)
FROM signals.training_examples GROUP BY 1 HAVING count(DISTINCT dataset_part) > 1;

-- 16. Нет пустых слов/классов/групп и повторных ID: счётчик 0; выдача пустая.
SELECT count(*) AS incomplete_examples FROM signals.training_examples
WHERE words IS NULL OR label IS NULL OR technology_group IS NULL OR dataset_part IS NULL;
SELECT id, count(*) FROM signals.training_examples GROUP BY 1 HAVING count(*) > 1;

-- 17. На чём основана разметка. Её происхождение сохранено отдельно от ответа модели.
SELECT label_origin, label, count(*) FROM signals.training_examples GROUP BY 1, 2;

-- 18. Таблица источников перенесена из вашего файла. Это справочник, не обучающие ответы.
SELECT source_name, trust_level, topics FROM signals.source_catalog ORDER BY source_name;
