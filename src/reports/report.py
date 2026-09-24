# src/report/report.py
import os

import pandas as pd
import xlsxwriter

from src.constants import CHART_HEIGHT_ROWS, GAP_ROWS, SITE_LABELS
from src.common.utils import get_month_columns
from src.reports.utils import (
    build_output_filename, get_report_date, _with_calc
)
from src.reports.charts import (
    apply_heatmap,
    top_chart,
    regions_chart,
    conversion_chart,
    conversion_by_month_chart,
    downloads_by_month_chart,
    sessions_by_month_chart,
    sessions_district_chart,
    conversion_by_calculator_chart,
    sessions_by_calculator_chart,
    downloads_by_calculator_chart,
)


def write_df(
    worksheet,
    workbook,
    df: pd.DataFrame,
    start_row: int
) -> tuple[int, int]:
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


def write_table_block(
    workbook,
    worksheet,
    df,
    title,
    start_row,
    chart_builder=None,
    calc_name='',
    site_label='',
    report_date='',
) -> int:
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
        chart = chart_builder(
            workbook, worksheet.get_name(),
            df, header_row, data_start, data_end,
            calc_name, site_label, report_date,
        )
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


def export_legend(workbook) -> None:
    """
    Лист-пояснение к метрикам отчёта. Ставится первым — порядок листов
    в xlsxwriter определяется порядком вызовов add_worksheet.

    Колонки: 0 — метка/название метрики (40), 1-3 — три равные (по 30,
    суммарно старая ширина колонки 'Пояснение'). Текстовые секции
    мержат 1-3 в одну ячейку; диаграмма ниже использует те же три
    колонки поодиночке — как слоты для параллельных блоков схемы.
    """
    worksheet = workbook.add_worksheet('Пояснительная записка')
    worksheet.set_column(0, 0, 40)
    worksheet.set_column(1, 3, 30)

    title_fmt = workbook.add_format({'bold': True, 'font_size': 14})
    section_fmt = workbook.add_format({
        'bold': True, 'font_size': 12, 'bg_color': '#D9E1F2', 'border': 1
    })
    header_fmt = workbook.add_format({
        'bold': True, 'bg_color': '#D9E1F2', 'border': 1
    })
    text_fmt = workbook.add_format({
        'border': 1, 'valign': 'top', 'text_wrap': True
    })

    def write_section(
        row: int,
        title: str,
        rows: list[tuple[str, str]]
    ) -> int:
        worksheet.merge_range(row, 0, row, 3, title, section_fmt)
        row += 1
        worksheet.write(row, 0, 'Метрика', header_fmt)
        worksheet.merge_range(row, 1, row, 3, 'Пояснение', header_fmt)
        row += 1
        for name, desc in rows:
            worksheet.write(row, 0, name, text_fmt)
            worksheet.merge_range(row, 1, row, 3, desc, text_fmt)
            worksheet.set_row(row, 45)
            row += 1
        return row + 1

    def write_diagram(start_row: int) -> None:
        """
        Схема пути от сырых событий до итоговых метрик — через
        merge_range + border/заливка, без плавающих shapes: живёт в
        обычной сетке строк, поэтому при правке текста выше она просто
        сдвигается вместе с листом, а не наезжает на контент.
        """
        box_fmt = workbook.add_format({
            'border': 2, 'align': 'center', 'valign': 'vcenter',
            'bg_color': '#DDEBF7', 'text_wrap': True, 'bold': True,
        })
        box_fmt_download = workbook.add_format({
            'border': 2, 'align': 'center', 'valign': 'vcenter',
            'bg_color': '#FCE4D6', 'text_wrap': True, 'bold': True,
        })
        arrow_fmt = workbook.add_format({
            'align': 'center', 'valign': 'vcenter',
            'font_size': 16, 'bold': True,
        })
        note_fmt = workbook.add_format({
            'align': 'center', 'valign': 'vcenter',
            'italic': True, 'font_size': 9, 'text_wrap': True,
        })

        row = start_row
        worksheet.merge_range(
            row, 0, row, 3, 'Схема: откуда берутся метрики', section_fmt
        )
        row += 2

        worksheet.merge_range(
            row, 0, row, 3,
            'Сырые события в логе\n'
            '(каждая строка — одно действие пользователя)',
            box_fmt,
        )
        worksheet.set_row(row, 30)
        row += 1

        worksheet.merge_range(row, 0, row, 3, '↓', arrow_fmt)
        row += 1

        worksheet.merge_range(
            row, 0, row, 1,
            'Действие:\n«Открыта страница калькулятора»',
            box_fmt,
        )
        worksheet.merge_range(
            row, 2, row, 3,
            'Действие:\n«Пользователь скачал отчёт»',
            box_fmt_download,
        )
        worksheet.set_row(row, 30)
        row += 1

        worksheet.merge_range(
            row, 0, row, 3,
            '↓ Оба типа событий группируются по Uuid: разрыв между '
            'действиями меньше 30 минут — одна сессия (session_id)',
            note_fmt,
        )
        worksheet.set_row(row, 24)
        row += 1

        worksheet.merge_range(
            row, 0, row, 1,
            'Сессии с заходом\n(уникальные session_id)',
            box_fmt,
        )
        worksheet.merge_range(
            row, 2, row, 3,
            'Сессии со скачиванием\n(уникальные session_id)',
            box_fmt_download,
        )
        worksheet.set_row(row, 30)
        row += 1

        worksheet.merge_range(
            row, 0, row, 3,
            '↓ Пересечение обоих множеств → «Конверсия, %».  '
            'Объединение обоих множеств → «Всего сессий».\n'
            '«Количество скачиваний» считается отдельно, напрямую по '
            'сырым событиям скачивания — минуя группировку в сессии '
            '(пользователь, скачавший 5 раз, даёт 5, а не 1).',
            note_fmt,
        )
        worksheet.set_row(row, 40)
        row += 1

        worksheet.write(row, 0, 'Итоговые метрики:', header_fmt)
        worksheet.write(row, 1, 'Конверсия, %', box_fmt)
        worksheet.write(row, 2, 'Всего сессий', box_fmt)
        worksheet.write(row, 3, 'Количество скачиваний', box_fmt_download)
        worksheet.set_row(row, 30)

    row = 0
    worksheet.write(
        row, 0,
        'Пояснительная записка: как считаются метрики в отчёте',
        title_fmt,
    )
    row += 2

    row = write_section(row, 'Общие понятия', [
        (
            'Сессия',
            'Одно непрерывное посещение калькулятора одним и тем же '
            'человеком: все действия подряд, если между ними прошло не '
            'больше 30 минут. Больший перерыв — это уже новая сессия.'
        ),
        (
            'Уникальный пользователь',
            'На платформе калькуляторов (calc.saint-gobain.ru), где '
            'человек авторизован, считается по логину. На остальных '
            'сайтах, а также если логин не указан — по анонимному '
            'идентификатору посетителя.'
        ),
    ])

    row = write_section(row, 'Метрики по каждому сайту', [
        (
            'Топ пользователей по скачиваниям',
            'Пользователи, скачавшие больше всего отчётов — за всё время '
            'и отдельно за последние 30 дней. Считается только для '
            'платформы калькуляторов (calc.saint-gobain.ru), где известен '
            'логин.'
        ),
        (
            'Активности по региону',
            'Количество уникальных пользователей, скачавших отчёт, в '
            'разбивке по федеральным округам.'
        ),
        (
            'Конверсия',
            'Доля посещений (сессий), которые закончились скачиванием '
            'отчёта. "Скачивание без захода" — отдельно указанные случаи, '
            'когда скачивание есть, а самого захода на страницу в этой же '
            'сессии не зафиксировано (обычно повторный визит на уже '
            'открытую страницу); в проценте конверсии они не участвуют, '
            'чтобы не завышать показатель.'
        ),
        (
            'Конверсия по месяцам',
            'То же самое, что "Конверсия", но в динамике по месяцам за '
            'последние 6 месяцев — в отличие от "Конверсия" (за весь период '
            'данных), эти два числа не обязаны совпадать в сумме.'
        ),
        (
            'Количество скачиваний по калькулятору',
            'Общее число скачиваний отчёта — считается каждое скачивание, '
            'а не человек. Если один пользователь скачал отчёт 5 раз за '
            'визит — здесь будет 5. Это другая единица измерения, чем в '
            '"Конверсии": там считаются посещения (сессии), а не отдельные '
            'скачивания.'
        ),
        (
            'Скачивания по месяцам',
            'То же самое, что "Количество скачиваний по калькулятору", но в '
            'динамике по месяцам за последние 6 месяцев.'
        ),
        (
            'Сессии по месяцам',
            'Количество посещений по месяцам, по каждому калькулятору.'
        ),
        (
            'Сессии по месяцам и округам',
            'То же самое, но дополнительно в разбивке по федеральному '
            'округу.'
        ),
    ])

    row = write_section(row, 'Сравнительные метрики (лист "Сравнение")', [
        (
            'Сравнение конверсии между сайтами',
            'Те же данные, что в "Конверсии" на листах по каждому сайту, '
            'собранные вместе — чтобы сравнить сайты между собой.'
        ),
        (
            'Динамика количества сессий по сайтам',
            'То же самое, что "Сессии по месяцам" на листах по каждому '
            'сайту, собранное для сравнения.'
        ),
        (
            'Сравнение количества скачиваний отчетов',
            'То же самое, что "Количество скачиваний по калькулятору" на '
            'листах по каждому сайту, собранное для сравнения.'
        ),
    ])

    row = write_section(row, 'Дата в заголовках', [
        (
            '"от дд.мм.гггг"',
            'Дата самой свежей записи в данных, по которым построен этот '
            'отчёт, — не дата формирования файла. Если отчёт построен за '
            'укороченный период, дата отражает конец этого периода, а не '
            'всех исходных данных.'
        ),
    ])

    write_diagram(row)


# --- конфиг блоков листа: (ключ в tables, заголовок, chart_builder) ---
# Порядок в списке = порядок блоков на листе сверху вниз.
# Добавить новую метрику в отчёт = добавить одну строку сюда,
# а не искать место для вставки write_table_block вручную.
SITE_BLOCKS = [
    ('regions', 'Активности по региону', regions_chart),
    ('conversion', 'Конверсия', conversion_chart),
    ('conversion_by_month', 'Конверсия по месяцам', conversion_by_month_chart),
    (
        'calculator_downloads_by_month',
        'Скачивания по месяцам',
        downloads_by_month_chart,
    ),
    ('sessions_by_month', 'Сессии по месяцам', sessions_by_month_chart),
    (
        'sessions_by_month_district',
        'Сессии по месяцам и округам',
        sessions_district_chart,
    ),
]

TOP_BLOCKS = [
    ('top', 'Топ пользователей'),
    ('top_30d', 'Топ-5 за последние 30 дней'),
]

COMPARISON_BLOCKS = [
    (
        'conversion_by_calc',
        'Сравнение конверсии между сайтами',
        conversion_by_calculator_chart,
    ),
    (
        'sessions_by_calc_month',
        'Динамика количества сессий по сайтам',
        sessions_by_calculator_chart,
    ),
    (
        'downloads_by_calc',
        'Сравнение количества скачиваний отчетов',
        downloads_by_calculator_chart,
    ),
]


def export_site(
    workbook,
    site_key: str,
    tables: dict,
    report_date: str = '',
) -> None:
    """
    site_key — служебный ключ (calc/hub/vetonit), как раньше идёт в имя
    вкладки. site_label — человекочитаемое имя того же сайта
    (SITE_LABELS), подставляется только в заголовки таблиц/графиков.
    """
    worksheet = workbook.add_worksheet(site_key)
    calc_name = tables.get('calculator_name', '')
    site_label = SITE_LABELS.get(site_key, site_key)
    row = 0

    if tables.get('top') is not None:
        for key, title in TOP_BLOCKS:
            row = write_table_block(
                workbook, worksheet, tables[key],
                _with_calc(title, calc_name, site_label, report_date),
                row, top_chart, calc_name, site_label, report_date,
            )

    for key, title, chart_fn in SITE_BLOCKS:
        row = write_table_block(
            workbook, worksheet, tables[key],
            _with_calc(title, calc_name, site_label, report_date),
            row, chart_fn, calc_name, site_label, report_date,
        )


def export_comparison(workbook, tables: dict, report_date: str = '') -> None:
    worksheet = workbook.add_worksheet('Сравнение')
    calc_name = tables.get('calculator_name', '')
    row = 0

    for key, title, chart_fn in COMPARISON_BLOCKS:
        row = write_table_block(
            workbook, worksheet, tables.get(key),
            _with_calc(title, calc_name, report_date=report_date),
            row, chart_fn, calc_name, '', report_date,
        )


def export_to_excel(
    results: dict,
    df: pd.DataFrame,
    comparison: dict | None = None,
    output_path: str | None = None,
) -> None:
    if output_path is None:
        output_path = os.path.join('output', build_output_filename(df))
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    report_date = get_report_date(df)

    workbook = xlsxwriter.Workbook(output_path)
    export_legend(workbook)
    for site_label, tables in results.items():
        export_site(workbook, site_label, tables, report_date)
    if comparison:
        export_comparison(workbook, comparison, report_date)
    workbook.close()
    print(f'Отчёт сохранён: {output_path}')
