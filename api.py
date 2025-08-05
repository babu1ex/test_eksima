from datetime import datetime
from typing import List, Optional
from fastapi import FastAPI, Query, HTTPException
from pydantic import BaseModel

from scrapers.rostender import fetch_rostender
from scrapers.b2b_center import fetch_b2b
from storage import save

app = FastAPI(title="Tender API")


class Tender(BaseModel):
    """
    Модель тендера, возвращаемого через API.
    """
    id: str
    title: Optional[str] = None
    published: Optional[str] = None
    deadline: Optional[str] = None
    price: Optional[float | str] = None
    description: Optional[str] = None
    url: str
    source: str
    location: Optional[str] = None
    customer: Optional[str] = None
    organizer: Optional[str] = None


RU2EN = {
    "Наименование": "title",
    "Дата Публикации": "published",
    "Дата Окончания": "deadline",
    "Начальная цена": "price",
    "Ссылка": "url",
    "Источник": "source",
    "Место Поставки": "location",
    "Заказчик/Отрасли": "customer",
    "Организатор": "organizer",
}


def normalize_item(d: dict) -> dict:
    """
    Преобразует поля с русскими названиями в формат API.
    Преобразует даты в строки.
    """
    out = dict(d) if ("url" in d and "source" in d) else {RU2EN.get(k, k): v for k, v in d.items()}
    for k in ("published", "deadline"):
        if isinstance(out.get(k), datetime):
            out[k] = out[k].strftime("%Y-%m-%d %H:%M")
    if not out.get("url") or not out.get("source"):
        raise HTTPException(500, detail="У записи нет url/source после маппинга")

    out.setdefault("description", None)
    out.setdefault("location", None)
    out.setdefault("industries_text", None)
    out.setdefault("organizer", None)
    return out


@app.get("/tenders", response_model=List[Tender])
def get_tenders(
    source: str = Query("rostender", pattern="^(rostender|b2b)$"),
    max_tenders: int = Query(20, ge=1, le=200),
    save_to: Optional[str] = None
):
    """
    Возвращает список тендеров из источника 'rostender' или 'b2b'.
    Можно указать максимальное количество и путь для сохранения CSV.
    """
    raw: List[dict] = []

    if source in ("rostender"):
        raw.extend(fetch_rostender(max_tenders))
    if source in ("b2b"):
        raw.extend(fetch_b2b(max_tenders))

    items = [normalize_item(dict(x)) for x in raw]

    if save_to:
        save(save_to, raw)

    return items
