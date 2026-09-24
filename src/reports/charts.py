# src/report/charts.py
from src.constants import ACTION_VISIT, ACTION_DOWNLOAD, USER_COL
from src.common.utils import get_month_columns
from src.reports.utils import _with_calc


def month_line_chart(
    workbook, sheet_name, df, header_row, data_start, data_end,
    title, y_axis_name=None,
):
    """
    Общий line-график 'калькулятор -> значения по месяцам'. Каждая
    строка df становится отдельной серией, месячные колонки — осью X.
    Используется тремя обёртками ниже (sessions/conversion/downloads
    by month) — они отличаются только заголовком и подписью оси Y,
    сама механика построения серий одна и та же.
    """
    chart = workbook.add_chart({'type': 'line'})
    month_cols = get_month_columns(df)
    calc_col = df.columns.get_loc('Калькулятор')
    first_col = df.columns.get_loc(month_cols[0])
    last_col = df.columns.get_loc(month_cols[-1])

    for row in range(data_start, data_end + 1):
        chart.add_series({
            'name': [sheet_name, row, calc_col],
            'categories': [
                sheet_name, header_row, first_col, header_row, last_col
            ],
            'values': [sheet_name, row, first_col, row, last_col],
        })
    chart.set_title({'name': title})
    chart.set_x_axis({'name': 'Месяц'})
    if y_axis_name:
        chart.set_y_axis({'name': y_axis_name})
    return chart


def top_chart(
    workbook,
    sheet_name,
    df,
    header_row,
    data_start,
    data_end,
    calc_name='',
    site_label='',
    report_date='',
):
    # горизонтальные — читаемее для длинных логинов
    chart = workbook.add_chart({'type': 'bar'})
    name_col = df.columns.get_loc(USER_COL)
    value_col = df.columns.get_loc('Количество скачиваний')
    chart.add_series({
        'categories': [sheet_name, data_start, name_col, data_end, name_col],
        'values': [sheet_name, data_start, value_col, data_end, value_col],
    })
    chart.set_title({
        'name': _with_calc(
            'Топ пользователей по скачиваниям',
            calc_name,
            site_label,
            report_date,
        )
    })
    chart.set_legend({'none': True})
    # данные уже отсортированы по убыванию (сверху вниз в таблице),
    # но Excel рисует bar-график категориями снизу вверх по умолчанию —
    # разворачиваем ось, чтобы наибольшее значение было сверху
    chart.set_y_axis({'reverse': True})
    return chart


def regions_chart(
    workbook,
    sheet_name,
    df,
    header_row,
    data_start,
    data_end,
    calc_name='',
    site_label='',
    report_date='',
):
    chart = workbook.add_chart({'type': 'bar'})
    name_col = df.columns.get_loc('Округ')
    value_col = df.columns.get_loc('Уникальных активностей по региону')
    chart.add_series({
        'categories': [sheet_name, data_start, name_col, data_end, name_col],
        'values': [sheet_name, data_start, value_col, data_end, value_col],
    })
    chart.set_title({
        'name': _with_calc(
            'Активности по федеральным округам',
            calc_name,
            site_label,
            report_date,
        )
    })
    chart.set_legend({'none': True})
    chart.set_y_axis({'reverse': True})
    return chart


def conversion_chart(
    workbook,
    sheet_name,
    df,
    header_row,
    data_start,
    data_end,
    calc_name='',
    site_label='',
    report_date='',
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
    chart.set_title({
        'name': _with_calc(
            'Заходы vs скачивания',
            calc_name,
            site_label,
            report_date,
        )
    })
    return chart


def conversion_by_month_chart(
    workbook, sheet_name, df, header_row, data_start, data_end,
    calc_name='', site_label='', report_date='',
):
    return month_line_chart(
        workbook, sheet_name, df, header_row, data_start, data_end,
        _with_calc(
            'Конверсия по месяцам, %', calc_name, site_label, report_date,
        ),
        y_axis_name='%',
    )


def downloads_by_month_chart(
    workbook, sheet_name, df, header_row, data_start, data_end,
    calc_name='', site_label='', report_date='',
):
    return month_line_chart(
        workbook, sheet_name, df, header_row, data_start, data_end,
        _with_calc(
            'Скачивания по месяцам', calc_name, site_label, report_date,
        ),
    )


def sessions_by_month_chart(
    workbook, sheet_name, df, header_row, data_start, data_end,
    calc_name='', site_label='', report_date='',
):
    return month_line_chart(
        workbook, sheet_name, df, header_row, data_start, data_end,
        _with_calc('Сессии по месяцам', calc_name, site_label, report_date),
    )


def sessions_district_chart(
    workbook,
    sheet_name,
    df,
    header_row,
    data_start,
    data_end,
    calc_name='',
    site_label='',
    report_date='',
):
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
            'categories': [
                sheet_name,
                data_start,
                district_col,
                data_end,
                district_col
            ],
            'values': [sheet_name, data_start, col, data_end, col],
        })

    chart.set_title(
        {
            'name': _with_calc(
                'Сессии по округам',
                calc_name,
                site_label,
                report_date
            )
        }
    )
    chart.set_x_axis({'name': 'Количество сессий'})
    return chart


def conversion_by_calculator_chart(
    workbook,
    sheet_name,
    df,
    header_row,
    data_start,
    data_end,
    calc_name='',
    site_label='',
    report_date='',
):
    """
    Группированная колонка для сравнительной таблицы конверсии:
    категории — уже склеенная 'Калькулятор — Сайт' (готовит
    aggregate._add_readable_site_to_calculator), два ряда — заходы и
    скачивания. calc_name не используется: сравнение не привязано
    к одному калькулятору по определению этой таблицы.
    """
    chart = workbook.add_chart({'type': 'column'})
    calc_col = df.columns.get_loc('Калькулятор')
    for metric in [ACTION_VISIT, ACTION_DOWNLOAD]:
        col = df.columns.get_loc(metric)
        chart.add_series({
            'name': metric,
            'categories': [
                sheet_name, data_start, calc_col, data_end, calc_col
            ],
            'values': [sheet_name, data_start, col, data_end, col],
        })
    chart.set_title({
        'name': _with_calc(
            'Сравнение конверсии между сайтами',
            calc_name, site_label, report_date
        )
    })
    return chart


def sessions_by_calculator_chart(
    workbook,
    sheet_name,
    df,
    header_row,
    data_start,
    data_end,
    calc_name='',
    site_label='',
    report_date='',
):
    """
    Группированная колонка для сравнительной таблицы сессий по месяцам:
    категории — месяцы, один ряд — одна строка таблицы ('Калькулятор —
    Сайт'). В отличие от sessions_by_month_chart/month_line_chart (line,
    один сайт за раз) здесь осознанно column: сравниваем сайты между
    собой внутри каждого месяца, пересекающиеся линии тут читались бы
    хуже группировки. Поэтому не переиспользует month_line_chart —
    другой тип графика, а не то же самое с другим заголовком.
    """
    chart = workbook.add_chart({'type': 'column'})
    month_cols = get_month_columns(df)
    calc_col = df.columns.get_loc('Калькулятор')
    first_col = df.columns.get_loc(month_cols[0])
    last_col = df.columns.get_loc(month_cols[-1])

    for row in range(data_start, data_end + 1):
        chart.add_series({
            'name': [sheet_name, row, calc_col],
            'categories': [
                sheet_name, header_row, first_col, header_row, last_col
            ],
            'values': [sheet_name, row, first_col, row, last_col],
        })
    chart.set_title({
        'name': _with_calc(
            'Динамика количества сессий по сайтам',
            calc_name, site_label, report_date
        )
    })
    return chart


def downloads_by_calculator_chart(
    workbook,
    sheet_name,
    df,
    header_row,
    data_start,
    data_end,
    calc_name='',
    site_label='',
    report_date='',
):
    """
    Одна колонка на категорию (без группировки, в отличие от
    conversion_by_calculator_chart) — тут всего одна метрика,
    а не пара визит/скачивание.
    """
    chart = workbook.add_chart({'type': 'column'})
    calc_col = df.columns.get_loc('Калькулятор')
    value_col = df.columns.get_loc('Количество скачиваний')
    chart.add_series({
        'categories': [sheet_name, data_start, calc_col, data_end, calc_col],
        'values': [sheet_name, data_start, value_col, data_end, value_col],
    })
    chart.set_title({
        'name': _with_calc(
            'Сравнение количества скачиваний отчетов',
            calc_name, site_label, report_date,
        )
    })
    chart.set_legend({'none': True})
    return chart


def apply_heatmap(worksheet, data_start, data_end, first_col, last_col):
    """
    Цветовая шкала на диапазон месячных колонок — альтернатива
    графику при 4+ периодах.
    """
    worksheet.conditional_format(
        data_start, first_col, data_end, last_col,
        {'type': '3_color_scale'}
    )
