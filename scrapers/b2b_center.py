# scrapers/b2b_center.py
import re, time, random
from datetime import datetime
from html import unescape
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter


def _make_session() -> requests.Session:
    """Создаёт сессию с заголовками и политикой повторных попыток."""
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 TenderScraper/0.3",
        "Accept-Language": "ru"
    })
    retry = Retry(
        total=5, connect=3, read=3,
        backoff_factor=1.2,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS"],
        respect_retry_after_header=True,
    )
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.mount("http://", HTTPAdapter(max_retries=retry))
    return s


SESSION = _make_session()


def _get(url: str, *, timeout=(10, 30)) -> str | None:
    """Возвращает HTML страницы или None при ошибке запроса."""
    try:
        r = SESSION.get(url, timeout=timeout)
        r.raise_for_status()
        return r.text
    except requests.RequestException:
        return None


def _sleep():
    """Пауза между запросами, чтобы не блокировали."""
    time.sleep(2 + random.random())


def _clean(text: str | None) -> str | None:
    """Удаляет лишние пробелы и HTML-сущности."""
    if not text:
        return None
    text = unescape(text).replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip() or None


def _parse_price(text: str | None) -> float | None:
    """Извлекает цену из текста."""
    if not text:
        return None
    m = re.search(r"([\d\s.,]+)\s*(₽|руб)", text.replace("\xa0", " "), re.I)
    if not m:
        return None
    raw = m.group(1).replace(" ", "").replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def _extract_links_from_list(html: str) -> list[str]:
    """Извлекает ссылки на карточки тендеров из HTML-страницы списка."""
    soup = BeautifulSoup(html, "lxml")
    seen, out = set(), []
    for a in soup.select('a[href*="tender-"]'):
        href = a.get("href") or ""
        if "/market/" in href and re.search(r"tender-\d+", href) and href not in seen:
            seen.add(href)
            out.append(href)
    return out


def _extract_detail(url: str):
    """Собирает подробности тендера с карточки: заголовок, дата, цена, организатор и т.д."""
    html = _get(url)
    if not html:
        return [None] * 7

    soup = BeautifulSoup(html, "lxml")

    # Заголовок
    h1 = soup.select_one('h1[itemprop="headline"], h1, .title-h2')
    if h1:
        for tag in h1.select('.favorite-container, .favorite-click, .on_boarding-step-1'):
            tag.decompose()
        title = _clean(h1.find(string=True, recursive=False) or h1.get_text(" ", strip=True))
    else:
        t = soup.find("title")
        title = _clean(t.get_text()) if t else None

    # Дата окончания
    deadline = None
    tag = soup.find(id="trade_info_date_end")
    if tag:
        raw = _clean(tag.get_text())
        m = re.search(r"\d{2}\.\d{2}\.\d{4}(?: \d{2}:\d{2})?", raw)
        deadline = m.group(0) if m else None

    # Организатор
    organizer = None
    org_row = soup.find(id="trade-info-organizer-name")
    if org_row:
        tds = org_row.find_all("td")
        if len(tds) > 1:
            organizer = _clean(tds[1].get_text(" ", strip=True))

    # Дата публикации
    published = None
    tag = soup.find("span", itemprop="datePublished")
    if tag:
        raw = _clean(tag.get_text())
        for fmt in ("%d.%m.%Y %H:%M", "%d.%m.%Y"):
            try:
                published = datetime.strptime(raw, fmt)
                break
            except:
                continue
        published = published or raw

    # Цена
    price = None
    price_el = soup.find(id="trade-info-lot-price-main") or soup.select_one('[id*="price"]')
    if price_el:
        price = _parse_price(price_el.get_text())
    if price is None:
        any_rub = soup.find(string=re.compile(r"(₽|руб(?![а-я]))", re.I))
        price = _parse_price(any_rub) if isinstance(any_rub, str) else None

    # Место поставки
    location = "Место поставки не указано"
    row = soup.find("tr", id="trade_info_address")
    if row:
        tds = row.find_all("td")
        if len(tds) >= 2:
            location = _clean(tds[1].get_text(" ", strip=True)) or location

    # Отрасли/Заказчик
    inds = []
    for a in soup.select('nav.breadcrumbs a, ul.breadcrumbs a, [itemtype*="BreadcrumbList"] a'):
        t = a.get_text(strip=True)
        if t.lower() not in {"главная", "тендеры", "закупки", "b2b-center"}:
            inds.append(t)
    customer = ", ".join(dict.fromkeys(inds)) or None

    return title, deadline, price, published, location, customer, organizer


def fetch_b2b(max_items: int = 20) -> list[dict]:
    """
    Загружает до `max_items` тендеров с B2B Center и возвращает их в виде списка словарей.
    """
    base = "https://www.b2b-center.ru/market/"
    items, seen = [], set()

    html = _get(base)
    if not html:
        return []

    for rel in _extract_links_from_list(html):
        if len(items) >= max_items:
            break
        if rel in seen:
            continue
        seen.add(rel)

        url = urljoin(base, rel)
        m = re.search(r"tender-(\d+)", rel)
        tid = m.group(1) if m else None
        if not tid:
            continue

        title, deadline, price, published, location, customer, organizer = _extract_detail(url)

        items.append({
            "id": tid,
            "Наименование": title or f"Тендер {tid}",
            "Дата Публикации": published.isoformat() if isinstance(published, datetime) else published,
            "Дата Окончания": deadline,
            "Начальная цена": price if price is not None else "цена не указана",
            "Ссылка": url,
            "Место Поставки": location,
            "Организатор": organizer,
            "Заказчик/Отрасли": customer,
            "Источник": "b2b",
        })

        _sleep()

    return items
