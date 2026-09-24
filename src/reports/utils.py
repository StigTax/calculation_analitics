import pandas as pd
import re

from datetime import datetime

from src.common.utils import _unique_calculators


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
