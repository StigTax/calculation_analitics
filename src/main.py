# main.py
import argparse
import os

from src.constants import DOMAINS, MAIN_DOMAIN, DEFAULT_MONTHS_RANGE
from src.loader import load_clean_data
from src.utilits import filter_by_domain, filter_by_month_list, get_month_range
from src.aggregate import (
    top_downloaders,
    uniq_users_by_region,
    conversion_rate,
    sessions_by_month,
    sessions_by_month_and_district,
)
from src.report import export_to_excel


def parse_args() -> argparse.Namespace:
    """
    CLI-аргументы: путь к логу, путь вывода, период
    (взаимоисключающие способы задать).
    """
    parser = argparse.ArgumentParser(
        description='Ежемесячная аналитика по калькуляторам'
    )
    parser.add_argument(
        'input_file',
        type=str,
        help=(
            'Путь к excel-файлу с логом (например: '
            '"C:/Downloads/statistics.xlsx")'
        )
    )
    parser.add_argument(
        '--output',
        type=str,
        default=None,
        help=(
            'Путь к итоговому xlsx. По умолчанию — автогенерация в output/ '
            'по калькулятору и периоду.'
        )
    )

    period_group = parser.add_mutually_exclusive_group()
    period_group.add_argument(
        '--months-back',
        type=int,
        default=None,
        help=(
            'Последние N месяцев от самого позднего месяца в данных '
            f'(по умолчанию {DEFAULT_MONTHS_RANGE})'
        )
    )
    period_group.add_argument(
        '--period',
        nargs=2,
        metavar=('START_MONTH', 'END_MONTH'),
        default=None,
        help='Явный диапазон, например: --period 2026-07 2026-09'
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if not os.path.exists(args.input_file):
        print(f'Файл не найден: {args.input_file}')
        return

    df = load_clean_data(args.input_file)

    if args.period:
        start_month, end_month = args.period
        months = get_month_range(
            df,
            start_month=start_month,
            end_month=end_month
        )
    else:
        months = get_month_range(
            df,
            months_back=args.months_back or DEFAULT_MONTHS_RANGE
        )

    df = filter_by_month_list(df, months)
    if df.empty:
        print(
            f'После фильтра по периоду {months} не осталось '
            'ни одной строки — проверь границы периода.'
        )
        return

    results = {}
    for label, domain in DOMAINS.items():
        df_domain = filter_by_domain(df, domain=domain)
        results[label] = {
            'top': top_downloaders(
                df_domain,
                site=label
            ) if domain == MAIN_DOMAIN else None,
            'regions': uniq_users_by_region(df_domain, site=label),
            'conversion': conversion_rate(df_domain, site=label),
            'sessions_by_month': sessions_by_month(
                df_domain,
                site=label,
                start_month=months[0],
                end_month=months[-1]
            ),
            'sessions_by_month_district': sessions_by_month_and_district(
                df_domain,
                site=label,
                start_month=months[0],
                end_month=months[-1]
            ),
        }

    export_to_excel(results, df, output_path=args.output)


if __name__ == '__main__':
    main()
