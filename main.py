import argparse
from scrapers.b2b_center import fetch_b2b
from scrapers.rostender import fetch_rostender
from storage import save


def main():
    """Парсит аргументы командной строки и запускает загрузку тендеров."""
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', choices=['b2b', 'rostender'], required=True, help="Источник тендеров")
    parser.add_argument('--max', type=int, default=100, help="Максимум тендеров")
    parser.add_argument('--output', required=True, help="Файл для сохранения (CSV)")
    args = parser.parse_args()

    items = fetch_b2b(args.max) if args.source == 'b2b' else fetch_rostender(args.max)
    save(args.output, items)

    print(f"Сохранено {len(items)} записей (источник: {args.source}) в {args.output}")
    print(f"Получено {len(items)} тендеров:")
    for item in items:
        print(item)


if __name__ == '__main__':
    main()
