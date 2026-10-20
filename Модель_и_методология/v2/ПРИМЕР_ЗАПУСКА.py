from signals import SignalAnalyzer

articles = [
    {
        "id": "article-1",
        "title": "Название публикации",
        "text": "Полный очищенный текст статьи из открытого источника.",
        "url": "https://example.org/article",
        # Необязательно: одинаковый ключ объединяет страницы об одной технологии.
        "technology_key": "technology-1",
    }
]

model = SignalAnalyzer()
print(model.classify(articles))
print(model.analyze("фотонные процессоры для ИИ", articles))
print(model.rank("фотонные процессоры для ИИ", articles, limit=15))
