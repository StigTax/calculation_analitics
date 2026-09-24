import pandas as pd

from src.constants import MONTH_COL_RE


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


def get_month_columns(df: pd.DataFrame) -> list[str]:
    """Колонки вида 'YYYY-MM' в df, в порядке следования."""
    return [c for c in df.columns if MONTH_COL_RE.match(str(c))]
