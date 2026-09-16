import pandas as pd
import numpy as np
from tabulate import tabulate

from src.constants import (
    REGION_TO_DISTRICT,
    USER_COL,
    TOP_N,
    MAIN_DOMAIN,
    NOT_SPECIFIED,
    NOT_IN_DICT,
    DOMAINS,
    ACTION_VISIT,
    ACTION_DOWNLOAD,
    DEFAULT_MONTHS_RANGE,
    TOP_PERIOD_DAYS
)
from src.loader import load_clean_data
from src.utilits import (
    filter_by_domain,
    add_identity_column,
    add_session_id,
    add_site_column,
    clean_empty,
    filter_by_action,
    add_month_column,
    get_month_range,
    filter_by_date_range,
    get_last_n_days_range,
    filter_by_month_list,
    get_calculator_names,
    _add_readable_site_to_calculator,
    get_month_columns,

)
from src.report import export_to_excel


def top_downloaders(
    df: pd.DataFrame,
    top_n: int = TOP_N,
    site: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> pd.DataFrame:
    """
    Топ-N пользователей по количеству скачанных отчётов.
    Без date_from/date_to — за весь переданный df (топ за всё время).
    С ними — только за произвольный период (не обязательно календарный
    месяц, например 15.08-15.09).
    """
    df = filter_by_date_range(df, date_from, date_to)

    main_df = filter_by_domain(df, MAIN_DOMAIN)
    downloads = filter_by_action(main_df, ACTION_DOWNLOAD)
    valid_user = clean_empty(downloads[USER_COL]).notna()
    downloads = downloads[valid_user]

    top_users = downloads.groupby(USER_COL).size().sort_values(
        ascending=False
    ).head(top_n).reset_index(name='Количество скачиваний')

    period_label = f' за {date_from}—{date_to}' if date_from or date_to else ''
    if top_users.empty:
        print(
            'Данная выборка не нашла пользователей для '
            f'формирования TOP листа{period_label}'
        )

    return add_site_column(top_users, site)


def uniq_users_by_region(
    df: pd.DataFrame,
    site: str | None = None,
) -> pd.DataFrame:
    """
    Уникальные пользователи по регионам и федеральным округам,
    по калькуляторам.
    """
    df = add_identity_column(df)
    downloads = df[df['Действие'] == ACTION_DOWNLOAD].copy()
    downloads['Регион'] = clean_empty(
        downloads['Регион']
    ).fillna(NOT_SPECIFIED)
    downloads['Округ'] = downloads['Регион'].map(REGION_TO_DISTRICT)
    downloads.loc[
        downloads['Регион'] == NOT_SPECIFIED, 'Округ'
    ] = NOT_SPECIFIED

    missing = downloads[downloads['Округ'].isna()]['Регион'].unique()
    if len(missing) > 0:
        print(f'Нет в справочнике округов: {list(missing)}')

    downloads['Округ'] = downloads['Округ'].fillna(NOT_IN_DICT)

    result = (
        downloads
        .groupby(['Округ'])['identity']
        .nunique()
        .reset_index(name='Уникальных активностей по региону')
        .sort_values('Уникальных активностей по региону', ascending=False)
    )

    return add_site_column(result, site)


def conversion_rate(df: pd.DataFrame, site: str | None = None) -> pd.DataFrame:
    """
    Конверсия по сессиям: один визит (Uuid + временное окно 30 мин)
    считается один раз, вне зависимости от числа скачиваний внутри.

    Знаменатель — сессии с зафиксированным заходом. 'Скачивание без
    захода' — отдельная колонка: сессии, где есть скачивание, но нет
    события захода (обычно повторный визит на уже открытую страницу),
    не участвуют в проценте конверсии, чтобы его не завышать.
    """
    df = add_session_id(df)

    result = []
    for calc in df['Калькулятор'].unique():
        calc_df = df[df['Калькулятор'] == calc]
        visits = set(
            calc_df[calc_df['Действие'] == ACTION_VISIT]['session_id']
        )
        downloads = set(
            calc_df[calc_df['Действие'] == ACTION_DOWNLOAD]['session_id']
        )

        converted = visits & downloads
        orphan = downloads - visits

        result.append({
            'Калькулятор': calc,
            ACTION_VISIT: len(visits),
            ACTION_DOWNLOAD: len(converted),
            'Конверсия, %': round(
                len(converted) / len(visits) * 100, 1
            ) if visits else np.nan,
            'Скачивание без захода': len(orphan),
            'Всего сессий': len(visits | downloads),
        })

    return add_site_column(pd.DataFrame(result), site)


def calculator_downloads(
    df: pd.DataFrame,
    site: str | None = None
) -> pd.DataFrame:
    """
    Количество скачиваний отчёта по калькулятору — сырые события
    ACTION_DOWNLOAD (.size()), без привязки к сессиям. Другая единица,
    чем у конверсии (там считаются сессии): пользователь, скачавший
    5 раз за визит, даёт здесь 5, а не 1.

    Считается только ради сборки на листе 'Сравнение'
    (см. downloads_by_calculator) — на per-site листах пока не
    выводится (помесячная версия этой же метрики — отдельный пункт
    ToDo, п.2, ещё не сделан).
    """
    downloads = filter_by_action(df, ACTION_DOWNLOAD)
    result = (
        downloads.groupby('Калькулятор')
        .size()
        .reset_index(name='Количество скачиваний')
    )
    return add_site_column(result, site)


def downloads_by_calculator(results: dict) -> pd.DataFrame:
    """
    Количество скачиваний по калькулятору, в разбивке по сайтам.
    В отличие от conversion_by_calculator — не сборка уже
    существовавшей таблицы (calculator_downloads считается впервые
    именно под этот отчёт), но механика сборки (concat + сортировка +
    человекочитаемые имена) та же самая.
    """
    tables = [
        site_tables['calculator_downloads']
        for site_tables in results.values()
        if site_tables.get('calculator_downloads') is not None
        and not site_tables['calculator_downloads'].empty
    ]
    if not tables:
        return pd.DataFrame()

    combined = (
        pd.concat(tables, ignore_index=True)
        .sort_values(['Калькулятор', 'Сайт'])
        .reset_index(drop=True)
    )
    return _add_readable_site_to_calculator(combined)


def conversion_by_calculator(results: dict) -> pd.DataFrame:
    """
    Конверсия по калькулятору, в разбивке по сайтам. Сборка, не новый
    подсчёт: конверсия методологически одна и та же для всех сайтов
    (сессии) — просто склеиваем уже посчитанные per-site таблицы
    conversion_rate и сортируем по калькулятору, чтобы сайты одного
    калькулятора шли рядом.
    """
    tables = [
        site_tables['conversion']
        for site_tables in results.values()
        if site_tables.get('conversion') is not None
        and not site_tables['conversion'].empty
    ]
    if not tables:
        return pd.DataFrame()

    combined = (
        pd.concat(tables, ignore_index=True)
        .sort_values(['Калькулятор', 'Сайт'])
        .reset_index(drop=True)
    )
    return _add_readable_site_to_calculator(combined)


def sessions_by_calculator_by_month(results: dict) -> pd.DataFrame:
    """
    Сессии по месяцам, в разбивке по калькулятору и сайту. Сборка:
    склеивает уже посчитанные per-site таблицы sessions_by_month (не
    conversion_rate — там нет месяцев, только итог за весь период).

    Осторожно: у разных сайтов может быть разный диапазон месяцев
    (get_month_range считается отдельно для каждого домена). После
    concat месяц вне диапазона сайта — NaN ('период не считался'),
    а не 0 ('сессий не было') — это разные вещи, не путать при чтении.
    """
    tables = [
        site_tables['sessions_by_month']
        for site_tables in results.values()
        if site_tables.get('sessions_by_month') is not None
        and not site_tables['sessions_by_month'].empty
    ]
    if not tables:
        return pd.DataFrame()

    combined = pd.concat(tables, ignore_index=True, sort=False)
    month_cols = sorted(get_month_columns(combined))
    other_cols = [c for c in combined.columns if c not in month_cols]

    combined = (
        combined[other_cols + month_cols]
        .sort_values(['Калькулятор', 'Сайт'])
        .reset_index(drop=True)
    )
    return _add_readable_site_to_calculator(combined)


def print_results(results: dict, comparison: dict | None = None) -> None:
    """
    Печатает results (словарь {сайт: {'top'/'regions'/'conversion': df}})
    в консоль через tabulate — по сайту заголовок, по каждой таблице
    отдельный блок. None означает "метрика не считается для этого сайта",
    пустой df — "посчиталась, но строк не нашлось".
    """
    for site, tables in results.items():
        print(f'\n{"=" * 60}')
        print(f'САЙТ: {site}')
        print('=' * 60)

        for name, df in tables.items():
            if name == 'calculator_name':
                continue
            print(f'\n--- {name} ---')
            if df is None:
                print('(не считается для этого сайта)')
            elif df.empty:
                print('(пусто)')
            else:
                print(tabulate(
                    df,
                    headers='keys',
                    tablefmt='rounded_outline',
                    showindex=False,
                    floatfmt='.1f',
                ))

    if not comparison:
        return

    print(f'\n{"=" * 60}')
    print('СРАВНЕНИЕ (по сайтам)')
    print('=' * 60)

    for name, df in comparison.items():
        if name == 'calculator_name':
            continue
        print(f'\n--- {name} ---')
        if df is None or df.empty:
            print('(пусто)')
        else:
            print(tabulate(
                df,
                headers='keys',
                tablefmt='rounded_outline',
                showindex=False,
                floatfmt='.1f',
            ))


def build_sessions(
    df: pd.DataFrame
) -> pd.DataFrame:
    """
    Схлопывает df до одной строки на сессию (session_id): первое по
    времени действие сессии определяет калькулятор, округ и месяц.
    Основа для любой месячной/региональной статистики по числу сессий —
    без риска задвоить одну сессию между несколькими группами.
    """
    df = add_session_id(df)
    df = add_month_column(df)
    df = df.copy()

    df['Регион'] = clean_empty(df['Регион']).fillna(NOT_SPECIFIED)
    df['Округ'] = df['Регион'].map(REGION_TO_DISTRICT)
    df.loc[df['Регион'] == NOT_SPECIFIED, 'Округ'] = NOT_SPECIFIED

    missing = df[df['Округ'].isna()]['Регион'].unique()
    if len(missing) > 0:
        print(f'Нет в справочнике округов: {list(missing)}')
    df['Округ'] = df['Округ'].fillna(NOT_IN_DICT)

    return (
        df.sort_values('Время отчета')
        .groupby('session_id')
        .first()[['Калькулятор', 'Округ', 'Месяц']]
        .reset_index()
    )


def sessions_by_month(
    df: pd.DataFrame,
    site: str | None = None,
    start_month: str | None = None,
    end_month: str | None = None,
    months_back: int = DEFAULT_MONTHS_RANGE,
) -> pd.DataFrame:
    """
    Количество сессий по месяцам, в разрезе калькулятора.
    По умолчанию — последние 6 месяцев от самого позднего месяца в
    данных. Месяцы без единой сессии показываются нулём, а не
    пропадают из таблицы.
    """
    months = get_month_range(df, start_month, end_month, months_back)
    df = filter_by_month_list(df, months)
    sessions = build_sessions(df)

    result = (
        sessions.groupby(['Калькулятор', 'Месяц'])
        .size()
        .unstack('Месяц', fill_value=0)
        .reindex(columns=months, fill_value=0)
        .reset_index()
    )
    return add_site_column(result, site)


def sessions_by_month_and_district(
    df: pd.DataFrame,
    site: str | None = None,
    start_month: str | None = None,
    end_month: str | None = None,
    months_back: int = DEFAULT_MONTHS_RANGE,
) -> pd.DataFrame:
    """Аналогично sessions_by_month, но с разбивкой по федеральному округу."""
    months = get_month_range(df, start_month, end_month, months_back)
    df = filter_by_month_list(df, months)
    sessions = build_sessions(df)

    result = (
        sessions.groupby(['Калькулятор', 'Округ', 'Месяц'])
        .size()
        .unstack('Месяц', fill_value=0)
        .reindex(columns=months, fill_value=0)
        .reset_index()
    )
    return add_site_column(result, site)


if __name__ == '__main__':
    df = load_clean_data()

    PERIOD_KWARGS = {'months_back': DEFAULT_MONTHS_RANGE}
    date_from, date_to = get_last_n_days_range(TOP_PERIOD_DAYS)

    results = {}
    for label, domain in DOMAINS.items():
        df_domain = filter_by_domain(df, domain=domain)
        results[label] = {
            'calculator_name': get_calculator_names(df_domain),
            'top': top_downloaders(
                df_domain, site=label
            ) if domain == MAIN_DOMAIN else None,
            'top_30d': top_downloaders(
                df_domain, site=label,
                date_from=date_from, date_to=date_to,
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
                **PERIOD_KWARGS
            ),
            'sessions_by_month_district': sessions_by_month_and_district(
                df_domain,
                site=label,
                **PERIOD_KWARGS
            ),
        }
    comparison = {
        'calculator_name': results.get(
            'calc',
            {}
        ).get(
            'calculator_name',
            ''
        ),
        'conversion_by_calc': conversion_by_calculator(results),
        'sessions_by_calc_month': sessions_by_calculator_by_month(results),
        'downloads_by_calc': downloads_by_calculator(results),
    }

    print_results(results, comparison)
    export_to_excel(results, df, comparison=comparison)
