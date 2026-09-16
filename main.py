# main.py
import argparse
import os

from src.constants import (
    DOMAINS,
    MAIN_DOMAIN,
    DEFAULT_MONTHS_RANGE,
    TOP_PERIOD_DAYS
)
from src.loader import load_clean_data
from src.utilits import (
    filter_by_domain,
    filter_by_month_list,
    get_month_range,
    get_last_n_days_range,
    get_calculator_names
)
from src.aggregate import (
    top_downloaders,
    uniq_users_by_region,
    conversion_rate,
    sessions_by_month,
    sessions_by_month_and_district,
    conversion_by_calculator,
    sessions_by_calculator_by_month,
    calculator_downloads,
    downloads_by_calculator,
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

    # df_full — без обрезки по месяцам. Нужен отдельно, потому что
    # "топ за всё время" и "топ за последние 30 дней" не должны зависеть
    # от --months-back/--period, которые управляют только sessions-таблицами.
    df_full = load_clean_data(args.input_file)

    if df_full.empty:
        print('Файл загружен, но после exclude-фильтров не осталось строк.')
        return

    if args.period:
        start_month, end_month = args.period
        months = get_month_range(
            df_full,
            start_month=start_month,
            end_month=end_month
        )
    else:
        months = get_month_range(
            df_full,
            months_back=args.months_back or DEFAULT_MONTHS_RANGE
        )

    df = filter_by_month_list(df_full, months)
    if df.empty:
        print(
            f'После фильтра по периоду {months} не осталось '
            'ни одной строки — проверь границы периода.'
        )
        return

    # 30-дневное окно считается от момента запуска отчёта, а не от
    # последней даты в логе — так что оно не зависит от --months-back/--period.
    date_from, date_to = get_last_n_days_range(TOP_PERIOD_DAYS)

    results = {}
    for label, domain in DOMAINS.items():
        df_domain_full = filter_by_domain(df_full, domain=domain)
        df_domain = filter_by_domain(df, domain=domain)

        results[label] = {
            'calculator_name': get_calculator_names(df_domain_full),
            'top': top_downloaders(
                df_domain_full,
                site=label
            ) if domain == MAIN_DOMAIN else None,
            'top_30d': top_downloaders(
                df_domain_full,
                site=label,
                date_from=date_from,
                date_to=date_to,
            ) if domain == MAIN_DOMAIN else None,
            'regions': uniq_users_by_region(df_domain, site=label),
            'conversion': conversion_rate(df_domain, site=label),
            'calculator_downloads': calculator_downloads(
                df_domain,
                site=label
            ),
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
    comparison = {
        'calculator_name': results.get('calc', {}).get('calculator_name', ''),
        'conversion_by_calc': conversion_by_calculator(results),
        'sessions_by_calc_month': sessions_by_calculator_by_month(results),
        'downloads_by_calc': downloads_by_calculator(results),
    }

    export_to_excel(
        results,
        df,
        comparison=comparison,
        output_path=args.output
    )


if __name__ == '__main__':
    main()
