import pandas as pd
import numpy as np
from tabulate import tabulate

from constants import (
    REGION_TO_DISTRICT,
    USER_COL,
    TOP_N,
    MAIN_DOMAIN,
    NOT_SPECIFIED,
    NOT_IN_DICT,
    DOMAINS,
    ACTION_VISIT,
    ACTION_DOWNLOAD,
    DEFAULT_MONTHS_RANGE
)
from loader import load_clean_data
from utilits import (
    filter_by_domain,
    add_identity_column,
    add_session_id,
    add_site_column,
    clean_empty,
    filter_by_action,
    add_month_column,
    get_month_range,
    filter_by_month_list,

)


def top_downloaders(
    df: pd.DataFrame,
    top_n: int = TOP_N,
    site: str | None = None,
) -> pd.DataFrame:
    """Топ-N пользователей по количеству скачанных отчётов."""
    main_df = filter_by_domain(df, MAIN_DOMAIN)
    downloads = filter_by_action(main_df, ACTION_DOWNLOAD)
    valid_user = clean_empty(downloads[USER_COL]).notna()
    downloads = downloads[valid_user]

    top_users = downloads.groupby(USER_COL).size().sort_values(
        ascending=False
    ).head(
        top_n
    ).reset_index(name='Количество скачиваний')
    if top_users.empty:
        print(
            'Данная выборка не нашла пользователей для формирования TOP листа'
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


def print_results(results: dict) -> None:
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

    results = {}
    for label, domain in DOMAINS.items():
        df_domain = filter_by_domain(df, domain=domain)
        results[label] = {
            'Топ-5 пользователей': top_downloaders(
                df_domain,
                site=label
            ) if domain == MAIN_DOMAIN else None,
            'Количество скачиваний по округам': uniq_users_by_region(
                df_domain,
                site=label
            ),
            'Конверсия': conversion_rate(df_domain, site=label),
            'Сессии по месяцам': sessions_by_month(
                df_domain,
                site=label
            ),
            'Сессии по месяца за последние 3 месяца': sessions_by_month(
                df_domain, site=label, months_back=3
            ),
            'Сессии по месяцам за период август-сентябрь': sessions_by_month(
                df_domain,
                site=label,
                start_month='2026-08',
                end_month='2026-09'
            ),
            'Сессий по округам по месяцым': sessions_by_month_and_district(
                df_domain,
                site=label
            ),
            'Сессии по округам по месяцым за последние 3 месяца': sessions_by_month_and_district(
                df_domain, site=label, months_back=3
            ),
            'Сессии по округам по месяцым за период август-сентябрь': sessions_by_month_and_district(
                df_domain,
                site=label,
                start_month='2026-08',
                end_month='2026-09'
            ),
        }

    print_results(results)

    df_calc = filter_by_domain(df, MAIN_DOMAIN)
    sessions = add_session_id(df_calc)

    with_visit = set(
        sessions[sessions['Действие'] == ACTION_VISIT]['session_id']
    )
    all_sessions = set(sessions['session_id'])
    no_visit = all_sessions - with_visit

    if no_visit:
        orphan_uuid = sessions[
            sessions['session_id'].isin(no_visit)
        ]['Uuid'].iloc[0]
        print(
            sessions[
                sessions['Uuid'] == orphan_uuid
            ][
                [
                    'Действие',
                    'Время отчета',
                    'session_id'
                ]
            ].sort_values('Время отчета')
        )
    else:
        print('Сессий без захода не найдено')

    print(f'Сессий без захода: {len(no_visit)} из {len(all_sessions)}')
    print(f'Сессий с расчётом конверсии (заход+результат): {46}')
    print(
        f'Сессий "только скачивание" (без залогированного захода): {
            len(no_visit)
        }'
    )
    print(f'Итого сессий за период: {len(all_sessions)}')
