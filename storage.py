import csv
from datetime import datetime


def _save_csv(path, rows):
    """
    Сохраняет список словарей в CSV-файл с нужными колонками.
    Преобразует дату окончания в строку ISO, если нужно.
    """
    cols = ["id", "Наименование", "Дата Публикации", "Дата Окончания", "Начальная цена",
            "Место Поставки", "Организатор", "Заказчик/Отрасли", "Ссылка", "Источник"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=cols)
        writer.writeheader()
        for row in rows:
            r = dict(row)
            if isinstance(r.get("Дата Окончания"), datetime):
                r["Дата Окончания"] = r["Дата Окончания"].isoformat()
            writer.writerow(r)


def save(path, rows):
    """Публичный интерфейс для сохранения CSV."""
    _save_csv(path, rows)
