import pandas as pd
import numpy as np
import re

from datetime import datetime

from src.constants import (
    MAIN_DOMAIN,
    USER_COL,
    SESSION_GAP_MINUTES,
    DEFAULT_MONTHS_RANGE
)


def filter_by_period(
    df: pd.DataFrame,
    year: int | None = None,
    month: int | None = None,
) -> pd.DataFrame:
    """
    Опциональный срез по году/месяцу.
    Без параметров — возвращает df как есть.
    """

    if year is not None:
        df = df[df['Время отчета'].dt.year == year]
    if month is not None:
        df = df[df['Время отчета'].dt.month == month]
    return df


def filter_by_domain(
    df: pd.DataFrame,
    domain: str | list[str] | None = None,
) -> pd.DataFrame:
    """
    Опциональный срез по домену(ам).
    Без параметра — возвращает df по домену "calc.saint-gobain.ru".
    """
    if domain is None:
        return df
    if isinstance(domain, str):
        domain = [domain]
    result = df[df['domain'].isin(domain)]
    if result.empty:
        print(
            f'После фильтра по домену {domain} не осталось ни одной строки'
        )
    return result


def add_identity_column(
    df: pd.DataFrame,
    main_domain: str = MAIN_DOMAIN
) -> pd.DataFrame:
    """
    identity — единый ключ для подсчёта уникальных:
    - на MAIN_DOMAIN, если логин указан -> логин (реальный человек)
    - иначе (другой домен, или логин пуст даже на главном) -> Uuid (сессия)
    identity_type — прозрачность: чем именно посчитано в этой строке
    """
    df = df.copy()
    user = clean_empty(df[USER_COL])
    is_main = df['domain'] == main_domain
    has_user = is_main & user.notna()

    df['identity'] = np.where(has_user, user, df['Uuid'])
    df['identity_type'] = np.where(has_user, 'логин', 'uuid-сессия')
    return df


def add_session_id(
    df: pd.DataFrame,
    gap_minutes: int = SESSION_GAP_MINUTES
) -> pd.DataFrame:
    """
    Группирует действия одного Uuid в сессии: разрыв больше gap_minutes
    между соседними действиями начинает новую сессию.
    Порог подобран по факту: 90-й перцентиль реальных пауз ~14 минут.

    Ограничение: если пользователь возвращается на уже открытую
    страницу спустя долгое время и сразу скачивает — новая сессия
    может не содержать событие "Открыта страница" (единичные случаи,
    не влияют на метрику существенно).
    """
    df = df.sort_values(['Uuid', 'Время отчета']).copy()
    time_diff = df.groupby('Uuid')['Время отчета'].diff()
    new_session = (
        time_diff.isna()
    ) | (time_diff > pd.Timedelta(minutes=gap_minutes))
    df['session_num'] = new_session.groupby(df['Uuid']).cumsum()
    df['session_id'] = df['Uuid'] + '_' + df['session_num'].astype(str)
    return df


def add_site_column(df: pd.DataFrame, site: str | None) -> pd.DataFrame:
    """Добавляет колонку 'Сайт' первой, если site передан явно."""
    if site is not None:
        df = df.copy()
        df.insert(0, 'Сайт', site)
    return df


def clean_empty(series: pd.Series) -> pd.Series:
    """Пустая строка -> NaN, для унификации проверок на отсутствие значения."""
    return series.replace('', pd.NA)


def exclude_by_column(
    df: pd.DataFrame,
    column: str,
    excluded: list[str],
    label: str,
    hint: str = '',
) -> pd.DataFrame:
    """
    Убирает строки, где значение column входит в excluded,
    с диагностикой в консоль.
    """
    before = len(df)
    matched = df[column].isin(excluded).sum()
    df_clean = df[~df[column].isin(excluded)].copy()

    print(f'[{label}] Всего строк: {before}')
    print(f'[{label}] Найдено совпадений с exclude-листом: {matched}')
    print(f'[{label}] Осталось после фильтрации: {len(df_clean)}')

    if matched == 0 and len(excluded) > 0:
        print(
            f'[{label}] Ни одного совпадения не найдено' + (
                f' — {hint}' if hint else ''
            )
        )

    return df_clean


def filter_by_action(df: pd.DataFrame, action: str) -> pd.DataFrame:
    """Строки с конкретным значением 'Действие'."""
    return df[df['Действие'] == action]


def add_month_column(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """Добавляет колонку 'Месяц' в формате 'YYYY-MM' из 'Время отчета'."""
    df = df.copy()
    df['Месяц'] = df['Время отчета'].dt.strftime('%Y-%m')
    return df


def get_month_range(
    df: pd.DataFrame,
    start_month: str | None = None,
    end_month: str | None = None,
    months_back: int = DEFAULT_MONTHS_RANGE,
) -> list[str]:
    """
    Список месяцев ('YYYY-MM') для отчёта.
    Без start_month/end_month — последние months_back месяцев, считая
    от самого позднего месяца в данных. С явными границами — диапазон
    между ними включительно (месяц можно не указывать с обеих сторон).
    """
    if df.empty:
        return []

    max_period = df['Время отчета'].max().to_period('M')
    end_period = pd.Period(end_month, freq='M') if end_month else max_period
    start_period = (
        pd.Period(start_month, freq='M') if start_month
        else end_period - (months_back - 1)
    )
    return [
        str(p) for p in pd.period_range(
            start_period,
            end_period,
            freq='M'
        )
    ]


def filter_by_month_list(df: pd.DataFrame, months: list[str]) -> pd.DataFrame:
    """Оставляет строки, чей месяц ('Время отчета') входит в months."""
    if not months:
        return df.iloc[0:0]
    return df[df['Время отчета'].dt.strftime('%Y-%m').isin(months)]


def get_calculator_label(df: pd.DataFrame) -> str:
    """
    Название калькулятора для имени файла, из сырого df (до разбивки
    по доменам). Если калькуляторов в файле несколько — предупреждает
    в консоль и склеивает имена через '_' (по текущей структуре
    выгрузок такого быть не должно, но на всякий случай не молчим).
    """
    calculators = df['Калькулятор'].unique()
    if len(calculators) > 1:
        print(
            f'В файле несколько калькуляторов: {list(calculators)} '
            '— имя файла будет собирательным'
        )

    label = '_'.join(calculators)
    # запрещённые в именах файлов Windows символы
    label = re.sub(r'[\\/:*?"<>|]', '', label)
    label = label.replace(' ', '_').replace('(', '').replace(')', '')
    return label


def build_output_filename(df: pd.DataFrame, prefix: str = 'report') -> str:
    """
    Имя файла: <prefix>_<калькулятор>_<период_данных>_<когда_сформирован>.xlsx
    """
    period_start = df['Время отчета'].min().strftime('%Y-%m')
    period_end = df['Время отчета'].max().strftime('%Y-%m')
    period = (
        period_start
        if period_start == period_end
        else f'{period_start}_{period_end}'
    )

    calculator = get_calculator_label(df)
    generated_at = datetime.now().strftime('%Y%m%d_%H%M%S')

    return f'{prefix}_{calculator}_{period}_{generated_at}.xlsx'
