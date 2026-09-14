import pandas as pd
from urllib.parse import urlparse

from src.constants import (
    EXCLUDED_USERS_FILE,
    EXCLUDED_DOMAINS_FILE,
    RAW_FILE,
    NAME_COL,
    PAGE_COL,
    USER_COL,
)

from src.utilits import exclude_by_column


def load_excluded_users(path: str) -> list[str]:
    """Читает список пользователей, которых нужно выкинуть из аналитики."""
    excluded_df = pd.read_csv(path, encoding='utf-8-sig')
    return excluded_df['users'].str.strip().tolist()


def load_excluded_domains(path: str) -> list[str]:
    """Читает список доменов, которые нужно выкинуть из аналитики."""
    excluded_df = pd.read_csv(path, encoding='utf-8-sig')
    return excluded_df['domain'].str.strip().tolist()


def load_clean_data(raw_file_path: str = RAW_FILE) -> pd.DataFrame:
    """
    Точка входа в пайплайн чтения: загружает сырой файл и убирает
    из него служебных пользователей и домены по exclude-листам
    (config/excluded_users.csv, config/excluded_domains.csv).
    Дальше по коду используется только этот df, не load_raw_data напрямую.
    """
    excluded_users = load_excluded_users(
        EXCLUDED_USERS_FILE
    )
    excluded_domains = load_excluded_domains(
        EXCLUDED_DOMAINS_FILE
    )

    df = load_raw_data(raw_file_path)
    df = exclude_by_column(
        df, USER_COL,
        excluded_users,
        'users',
        f'проверь колонку "{USER_COL}" в csv.'
    )
    df = exclude_by_column(
        df,
        'domain',
        excluded_domains,
        'domains',
        'проверь формат домена в csv (без http://, без слэша в конце).'
    )

    return df


def get_domain(url: str) -> str:
    """Достаёт голый домен из URL, игнорируя протокол/путь/query-параметры."""
    return urlparse(url).netloc


def load_raw_data(path: str) -> pd.DataFrame:
    """
    Читает сырой xlsx-лог с листа 'Статистика', парсит колонку
    времени в datetime, приводит текстовые поля к строкам без
    хвостовых пробелов и добавляет колонку 'domain', извлечённую
    из URL в PAGE_COL.
    """
    df = pd.read_excel(path, sheet_name='Статистика', engine='openpyxl')
    df['Время отчета'] = pd.to_datetime(
        df['Время отчета'],
        format='%d-%m-%Y %H:%M:%S'
    )

    for col in NAME_COL:
        df[col] = df[col].astype(str).str.strip()

    df['domain'] = df[PAGE_COL].apply(get_domain)

    return df
