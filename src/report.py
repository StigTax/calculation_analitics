import xlsxwriter
import pandas as pd

import os

from constants import (
    ACTION_VISIT,
    ACTION_DOWNLOAD,
    USER_COL,
    MONTH_COL_RE,
    CHART_HEIGHT_ROWS,
    GAP_ROWS,
)
from utilits import build_output_filename


def get_month_columns(df: pd.DataFrame) -> list[str]:
    """Колонки вида 'YYYY-MM' в df, в порядке следования."""
    return [c for c in df.columns if MONTH_COL_RE.match(str(c))]


def write_df(worksheet, workbook, df: pd.DataFrame, start_row: int) -> tuple[int, int]:
    """
    Пишет df на worksheet начиная со start_row (строка заголовков).
    Возвращает (data_start_row, data_end_row) для построения графика.
    """
    header_fmt = workbook.add_format(
        {
            'bold': True,
            'bg_color': '#D9E1F2',
            'border': 1
        }
    )
    cell_fmt = workbook.add_format({'border': 1})

    for col_idx, col_name in enumerate(df.columns):
        worksheet.write(start_row, col_idx, str(col_name), header_fmt)
        worksheet.set_column(col_idx, col_idx, max(len(str(col_name)) + 2, 12))

    for row_offset, row in enumerate(df.itertuples(index=False)):
        for col_idx, value in enumerate(row):
            if pd.isna(value):
                worksheet.write_blank(
                    start_row + 1 + row_offset,
                    col_idx,
                    None,
                    cell_fmt
                )
            else:
                worksheet.write(
                    start_row + 1 + row_offset,
                    col_idx,
                    value,
                    cell_fmt
                )

    data_start = start_row + 1
    data_end = data_start + len(df) - 1
    return data_start, data_end


def write_table_block(workbook, worksheet, df, title, start_row, chart_builder=None) -> int:
    """
    Заголовок + таблица (+ график под ней, если передан chart_builder
    и он вернул объект графика; если chart_builder вернул None — вместо
    графика применяется heatmap на месячные колонки, если они есть).
    Возвращает строку, с которой можно писать следующий блок.
    """
    title_fmt = workbook.add_format({'bold': True, 'font_size': 12})
    worksheet.write(start_row, 0, title, title_fmt)
    header_row = start_row + 1

    if df is None or df.empty:
        worksheet.write(header_row, 0, '(нет данных за период)')
        return header_row + GAP_ROWS + 1

    data_start, data_end = write_df(worksheet, workbook, df, header_row)
    next_row = data_end + 1 + GAP_ROWS

    if chart_builder is not None:
        chart = chart_builder(workbook, worksheet.get_name(),
                              df, header_row, data_start, data_end)
        if chart is not None:
            chart_row = data_end + 2
            worksheet.insert_chart(chart_row, 0, chart)
            next_row = max(next_row, chart_row + CHART_HEIGHT_ROWS + GAP_ROWS)
        else:
            month_cols = get_month_columns(df)
            if month_cols:
                first_col = df.columns.get_loc(month_cols[0])
                last_col = df.columns.get_loc(month_cols[-1])
                apply_heatmap(worksheet, data_start,
                              data_end, first_col, last_col)
            # next_row не увеличиваем — heatmap не занимает доп. строк

    return next_row


# --- построители графиков под конкретные таблицы ---

def top_chart(workbook, sheet_name, df, header_row, data_start, data_end):
    # горизонтальные — читаемее для длинных логинов
    chart = workbook.add_chart({'type': 'bar'})
    name_col = df.columns.get_loc(USER_COL)
    value_col = df.columns.get_loc('Количество скачиваний')
    chart.add_series({
        'categories': [sheet_name, data_start, name_col, data_end, name_col],
        'values': [sheet_name, data_start, value_col, data_end, value_col],
    })
    chart.set_title({'name': 'Топ пользователей по скачиваниям'})
    chart.set_legend({'none': True})
    return chart


def regions_chart(workbook, sheet_name, df, header_row, data_start, data_end):
    chart = workbook.add_chart({'type': 'bar'})
    name_col = df.columns.get_loc('Округ')
    value_col = df.columns.get_loc('Уникальных активностей по региону')
    chart.add_series({
        'categories': [sheet_name, data_start, name_col, data_end, name_col],
        'values': [sheet_name, data_start, value_col, data_end, value_col],
    })
    chart.set_title({'name': 'Активности по федеральным округам'})
    chart.set_legend({'none': True})
    return chart


def conversion_chart(
    workbook,
    sheet_name,
    df,
    header_row,
    data_start,
    data_end
):
    chart = workbook.add_chart({'type': 'column'})
    calc_col = df.columns.get_loc('Калькулятор')
    for metric in [ACTION_VISIT, ACTION_DOWNLOAD]:
        col = df.columns.get_loc(metric)
        chart.add_series({
            'name': metric,
            'categories': [
                sheet_name,
                data_start,
                calc_col,
                data_end,
                calc_col
            ],
            'values': [sheet_name, data_start, col, data_end, col],
        })
    chart.set_title({'name': 'Заходы vs скачивания'})
    return chart


def sessions_by_month_chart(
    workbook,
    sheet_name,
    df,
    header_row,
    data_start,
    data_end
):
    chart = workbook.add_chart({'type': 'line'})
    month_cols = get_month_columns(df)
    calc_col = df.columns.get_loc('Калькулятор')
    first_col = df.columns.get_loc(month_cols[0])
    last_col = df.columns.get_loc(month_cols[-1])

    for row in range(data_start, data_end + 1):
        chart.add_series({
            'name': [sheet_name, row, calc_col],
            'categories': [
                sheet_name,
                header_row,
                first_col,
                header_row,
                last_col
            ],
            'values': [sheet_name, row, first_col, row, last_col],
        })
    chart.set_title({'name': 'Сессии по месяцам'})
    chart.set_x_axis({'name': 'Месяц'})
    return chart


def sessions_district_chart(workbook, sheet_name, df, header_row, data_start, data_end):
    """
    Bar-график для 1-3 периодов — наглядное сравнение по округам.
    Для 4+ месяцев возвращает None: report будет строить по этой
    таблице heatmap вместо графика (см. write_table_block).
    """
    month_cols = get_month_columns(df)
    if len(month_cols) > 3:
        return None

    chart = workbook.add_chart({'type': 'bar'})
    district_col = df.columns.get_loc('Округ')

    for month in month_cols:
        col = df.columns.get_loc(month)
        chart.add_series({
            'name': month,
            'categories': [sheet_name, data_start, district_col, data_end, district_col],
            'values': [sheet_name, data_start, col, data_end, col],
        })

    chart.set_title({'name': 'Сессии по округам'})
    chart.set_x_axis({'name': 'Количество сессий'})
    return chart


def apply_heatmap(worksheet, data_start, data_end, first_col, last_col):
    """Цветовая шкала на диапазон месячных колонок — альтернатива графику при 4+ периодах."""
    worksheet.conditional_format(
        data_start, first_col, data_end, last_col,
        {'type': '3_color_scale'}
    )


def export_site(workbook, site_label: str, tables: dict) -> None:
    worksheet = workbook.add_worksheet(site_label)
    row = 0

    if tables.get('top') is not None:
        row = write_table_block(
            workbook, worksheet, tables['top'], 'Топ пользователей', row, top_chart)

    row = write_table_block(
        workbook, worksheet, tables['regions'], 'Активности по региону', row, regions_chart)
    row = write_table_block(
        workbook, worksheet, tables['conversion'], 'Конверсия', row, conversion_chart)
    row = write_table_block(
        workbook, worksheet, tables['sessions_by_month'], 'Сессии по месяцам', row, sessions_by_month_chart)
    write_table_block(
        workbook, worksheet, tables['sessions_by_month_district'],
        'Сессии по месяцам и округам', row,
        chart_builder=sessions_district_chart  # было: chart_builder=None
    )


def export_to_excel(
    results: dict,
    df: pd.DataFrame,
    output_path: str | None = None
) -> None:
    if output_path is None:
        output_path = os.path.join('output', build_output_filename(df))
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    workbook = xlsxwriter.Workbook(output_path)
    for site_label, tables in results.items():
        export_site(workbook, site_label, tables)
    workbook.close()
    print(f'Отчёт сохранён: {output_path}')
