import pandas as pd
import numpy as np
from tabulate import tabulate

from constants import (
    REGION_TO_DISTRICT,
    USER_COL,
    TOP_N,
    MAIN_DOMAIN,
    NOT_SPECIFIED,
    ACTIONS,
    NOT_IN_DICT,
    DOMAINS,
    ACTION_VISIT,
    ACTION_DOWNLOAD,
)
from loader import load_clean_data
from utilits import (
    filter_by_domain,
    add_identity_column,
    add_session_id,
    add_site_column,
    clean_empty,
    filter_by_action,
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


def conversion_rate(
    df: pd.DataFrame,
    site: str | None = None,
) -> pd.DataFrame:
    """
    Конверсия по сессиям: один визит (Uuid + временное окно 30 мин)
    считается один раз, вне зависимости от числа скачиваний внутри.
    """
    df = add_session_id(df)
    pivot = (
        df.groupby(['Калькулятор', 'Действие'])['session_id']
        .nunique()
        .unstack(fill_value=0)
        .reindex(columns=ACTIONS, fill_value=0)
    )
    pivot['Конверсия, %'] = np.where(
        pivot[ACTION_VISIT] > 0,
        (
            pivot[ACTION_DOWNLOAD]
            / pivot[ACTION_VISIT]
            * 100
        ).round(1),
        np.nan
    )
    result = pivot.reset_index()

    return add_site_column(result, site)


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


if __name__ == '__main__':
    df = load_clean_data()

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
        }

    print_results(results)
