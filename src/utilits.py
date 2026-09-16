import pandas as pd
import numpy as np
import re

from datetime import datetime

from src.constants import (
    MAIN_DOMAIN,
    USER_COL,
    SESSION_GAP_MINUTES,
    DEFAULT_MONTHS_RANGE,
    TOP_PERIOD_DAYS,
    SITE_LABELS,
    CALCULATOR_DISPLAY_OVERRIDES,
    MONTH_COL_RE,
)


def _unique_calculators(df: pd.DataFrame, context: str) -> list[str]:
    """
    Уникальные калькуляторы в df, с предупреждением, если их больше одного.
    """
    calculators = list(df['Калькулятор'].unique())
    if len(calculators) > 1:
        print(
            f'В файле несколько калькуляторов: {calculators} '
            f'— {context} будет собирательным'
        )
    return calculators


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
    Название калькулятора для имени файла (без запрещённых Windows-символов).
    """
    calculators = _unique_calculators(df, 'имя файла')
    label = '_'.join(calculators)
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


def filter_by_date_range(
    df: pd.DataFrame,
    date_from: str | pd.Timestamp | None = None,
    date_to: str | pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Срез по 'Время отчета' в границах [date_from, date_to] включительно."""
    if date_from is not None:
        df = df[df['Время отчета'] >= pd.Timestamp(date_from)]
    if date_to is not None:
        df = df[df['Время отчета'] <= pd.Timestamp(date_to)]
    return df


def get_last_n_days_range(
    n: int = TOP_PERIOD_DAYS
) -> tuple[pd.Timestamp, pd.Timestamp]:
    """
    Границы 'последние n дней' от момента запуска отчёта (datetime.now()),
    а не от последней даты в логе — иначе это не 'последние 30 дней',
    а 'последний месяц из выгрузки', что не то же самое.
    """
    now = pd.Timestamp.now()
    return now - pd.Timedelta(days=n), now


def get_calculator_names(df: pd.DataFrame) -> str:
    """
    Человекочитаемое название калькулятора(ов) —
    для заголовков таблиц и графиков.
    """
    calculators = _unique_calculators(df, 'заголовок')
    display = [get_calculator_display_name(c) for c in calculators]
    return ', '.join(display)


def _merge_calculator_and_site(df: pd.DataFrame) -> pd.DataFrame:
    """
    Заменяет служебный ключ сайта в 'Сайт' человекочитаемым (SITE_LABELS)
    и приклеивает к названию калькулятора одной строкой. Отдельная
    колонка 'Сайт' с сырым ключом в кросс-сайтовых таблицах избыточна
    и нечитаема для итогового отчёта — здесь она схлопывается.
    """
    df = df.copy()
    site_label = df['Сайт'].map(SITE_LABELS)

    missing = df.loc[site_label.isna(), 'Сайт'].unique()
    if len(missing) > 0:
        print(f'Нет человекочитаемого названия в SITE_LABELS: {list(missing)}')

    df['Калькулятор'] = df['Калькулятор'] + ' — ' + site_label.fillna(
        df['Сайт']
    )
    return df.drop(columns='Сайт')


def _add_readable_site_to_calculator(df: pd.DataFrame) -> pd.DataFrame:
    """
    Приклеивает к названию калькулятора человекочитаемый сайт (SITE_LABELS)
    и применяет override неоднозначных названий калькулятора
    (CALCULATOR_DISPLAY_OVERRIDES) — например, 'СФТК' без уточнения
    превращается в 'СФТК (Розничный)', чтобы не путать с 'СФТК
    (Проектный)'. Колонка 'Сайт' со служебным ключом остаётся нетронутой.
    """
    df = df.copy()
    site_label = df['Сайт'].map(SITE_LABELS)

    missing = df.loc[site_label.isna(), 'Сайт'].unique()
    if len(missing) > 0:
        print(f'Нет человекочитаемого названия в SITE_LABELS: {list(missing)}')

    calc_display = df['Калькулятор'].map(get_calculator_display_name)
    df['Калькулятор'] = calc_display + ' — ' + site_label.fillna(df['Сайт'])
    return df


def get_calculator_display_name(raw_name: str) -> str:
    """
    Человекочитаемое название калькулятора для заголовков и графиков.
    Сейчас единственное исключение — 'Калькулятор СФТК' само по себе
    неоднозначно: в выгрузках существует отдельный 'Калькулятор СФТК
    (Проектный)', так что базовое имя дополняется словом '(Розничный)',
    чтобы не путать эти два калькулятора при просмотре отчёта отдельно
    от файла-источника.
    """
    return CALCULATOR_DISPLAY_OVERRIDES.get(raw_name, raw_name)


def get_report_date(df: pd.DataFrame) -> str:
    """
    Дата самой свежей записи в логе, в формате дд.мм.гггг — для
    заголовков таблиц/графиков ('от ...'). Отдельная сущность от
    generated_at в имени файла (build_output_filename) — то момент
    запуска скрипта, это момент последних данных, они могут не совпадать.
    """
    return df['Время отчета'].max().strftime('%d.%m.%Y')


def _with_calc(
    title: str,
    calc_name: str = '',
    site_label: str = '',
    report_date: str = '',
) -> str:
    """
    Достраивает заголовок: '{title} - {calc_name} - {site_label} -
    от {report_date}'. Каждый хвост добавляется только если аргумент
    не пустой — так сравнительные таблицы (без привязки к одному сайту)
    получают заголовок без site_label, но с датой.
    """
    parts = [p for p in (calc_name, site_label) if p]
    result = title
    if parts:
        result += ' - ' + ' - '.join(parts)
    if report_date:
        result += f' - от {report_date}'
    return result


def get_month_columns(df: pd.DataFrame) -> list[str]:
    """Колонки вида 'YYYY-MM' в df, в порядке следования."""
    return [c for c in df.columns if MONTH_COL_RE.match(str(c))]
