import re, time, random, requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from datetime import datetime

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/115.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "ru,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://rostender.info/extsearch",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
}

def _sleep():
    """Пауза между запросами 2–3 сек."""
    time.sleep(2 + random.random())


def _soup(url):
    """Возвращает soup-объект с HTML по ссылке."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.status_code == 200:
            return BeautifulSoup(r.text, "lxml")
    except:
        pass


def txt(node):
    """Чистит текст из тега."""
    return re.sub(r'\s+', ' ', (node.get_text(" ", strip=True) if node else '')).replace('\xa0', ' ').strip() or None


def parse_date(text):
    """Парсит дату из строки."""
    m = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{2,4})", text or "")
    if not m:
        return None
    d, mo, y = map(int, m.groups())
    y += 2000 if y < 100 else 0
    return datetime(y, mo, d)


def parse_price(text):
    """Извлекает число из строки с рублями."""
    m = re.search(r"([\d\s.,]+)\s*(?:руб|₽)", (text or "").lower())
    if not m:
        return None
    try:
        return float(m.group(1).replace(" ", "").replace(",", "."))
    except:
        return None


def _extract_organizer(_):
    """Организатор скрыт за авторизацией."""
    return "Данные об организаторе скрыты, необходима авторизация"


def _extract_customer(soup):
    """Возвращает список заказчиков/отраслей."""
    def norm(s):
        return re.sub(r'\s+', ' ', s or '').strip()
    found = []

    for a in soup.select('div.tender-customer-branch .list-branches a.list-branches__link'):
        t = a.get('title') or a.get_text(' ', strip=True)
        if (t := norm(t)): found.append(t)

    if not found:
        for a in soup.select('a[href*="/tendery-"], a[href*="/category/"], a[href*="/industry/"]'):
            if (t := norm(a.get('title') or a.get_text())): found.append(t)

    for a in soup.select('nav.breadcrumbs a, ul.breadcrumbs a'):
        t = norm(a.get_text()).lower()
        if t not in {'главная', 'тендеры', 'закупки'}:
            found.append(a.get_text())

    uniq = []
    seen = set()
    for t in found:
        k = t.lower()
        if k not in seen:
            seen.add(k)
            uniq.append(t)

    return ', '.join(uniq) if uniq else None


def _extract_detail(url):
    """Извлекает данные из карточки тендера."""
    soup = _soup(url)
    if not soup:
        return (None,) * 7

    title = txt(soup.select_one('h1.tender__title')) or txt(soup.select_one('h1'))

    # Дата публикации
    published = None
    pub_el = soup.select_one('.tender-info-header-start_date, .tender__date-start, [class*="date-start"]')
    if pub_el:
        t = txt(pub_el)
        if (m := re.search(r'(\d{1,2}\.\d{1,2}\.\d{2,4})(?:\s*(?:в|,)?\s*(\d{1,2}:\d{2}))?', t)):
            d = parse_date(m.group(1))
            if d and m.group(2):
                h, mi = map(int, m.group(2).split(':'))
                d = d.replace(hour=h, minute=mi)
            published = d

    # Дата окончания
    deadline = None
    t = txt(soup.select_one('.tender__date-end, .tender__countdown-text, [class*="date-end"]')) or ''
    if not t and (lab := soup.find(string=re.compile(r'Окончание', re.I))):
        t = txt(lab.parent)

    if (m := re.search(r'(\d{1,2}\.\d{1,2}\.\d{2,4})\s+(\d{1,2}:\d{2})', t)):
        d = parse_date(m.group(1))
        if d:
            h, mi = map(int, m.group(2).split(':'))
            deadline = d.replace(hour=h, minute=mi)
    elif (m := re.search(r'(\d{1,2}\.\d{1,2}\.\d{2,4})', t)):
        deadline = parse_date(m.group(1))

    # Цена
    price = parse_price(txt(soup.select_one('.tender__price, .tender-short__price'))) or None
    if price is None:
        if (any_rub := soup.find(string=re.compile(r'(₽|руб(?![а-я]))', re.I))):
            price = parse_price(any_rub)

    # Место поставки
    location = None
    if (lab := soup.find(string=re.compile(r'Место поставки', re.I))):
        container = lab.find_parent(['div', 'section', 'li', 'tr', 'td']) or lab.parent
        if container:
            raw = re.sub(r'.*?Место поставки', '', container.get_text(' ', strip=True), flags=re.I)
            raw = re.split(r'\s+(Организатор|Заказчик|Окончание|Документация)\b', raw)[0]
            location = re.sub(r'\s+', ' ', raw.replace('\xa0', ' ')).strip()

    customer = _extract_customer(soup)
    organizer = _extract_organizer(soup)

    return title, deadline, price, published, location, organizer, customer


def fetch_rostender(max_items=100):
    """Парсит тендеры по страницам с https://rostender.info/extsearch"""
    items, seen = [], set()
    per_page = 20
    total_pages = (max_items + per_page - 1) // per_page

    for page in range(1, total_pages + 1):
        soup = _soup(f"https://rostender.info/extsearch?page={page}")
        if not soup:
            break

        for a in soup.select("a[href]"):
            if not (m := re.search(r"/(\d{6,})-tender-", a.get("href", ""))):
                continue
            tid = m.group(1)
            if tid in seen:
                continue
            seen.add(tid)
            url = urljoin("https://rostender.info", a["href"])
            title = a.get_text(strip=True)

            title2, deadline, price, published, location, organizer, customer = _extract_detail(url)

            items.append({
                "id": tid,
                "Наименование": title2 or title,
                "Дата Публикации": published.strftime("%Y-%m-%d") if isinstance(published, datetime) else published,
                "Дата Окончания": deadline.strftime("%Y-%m-%d %H:%M") if isinstance(deadline, datetime) else deadline,
                "Начальная цена": price if price else "цена не указана",
                "Ссылка": url,
                "Место Поставки": location,
                "Организатор": organizer,
                "Заказчик/Отрасли": customer,
                "Источник": "rostender",
            })

            if len(items) >= max_items:
                return items

        _sleep()

    return items
