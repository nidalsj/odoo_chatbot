from datetime import datetime

from odoo.tools.misc import format_amount, format_date, format_datetime, formatLang

from .query_executor import currency_field

NUMERIC = ('integer', 'float', 'monetary')
FUNC_WORDS = {'sum': 'sum', 'avg': 'average', 'min': 'minimum', 'max': 'maximum', 'count': 'count'}


def format_result(env, vq, raw, schema):
    """Turn raw query output into a JSON-safe dict the UI can render."""
    model_schema = schema[vq.model]
    info, title = model_schema['fields'], model_schema['label']
    if raw['kind'] == 'count':
        return _count_result(env, raw, title)
    if raw['kind'] == 'list':
        return _list_result(env, vq, raw, info, title)
    return _aggregate_result(env, vq, raw, info, title)


def _plain_number(env, value, ftype, digits=None):
    value = value or 0
    if digits is None:
        digits = 0 if ftype == 'integer' else 2
    return formatLang(env, value, digits=digits)


def _cell(env, value, finfo, fname, currency=None):
    ftype = finfo['type']
    if ftype == 'boolean':
        return 'Yes' if value else 'No'
    if ftype in NUMERIC:
        if fname == 'id':
            return str(value)
        if ftype == 'monetary' and currency:
            return format_amount(env, value or 0, currency)
        return _plain_number(env, value, ftype)
    if not value:
        return ''
    if ftype == 'many2one':
        # Same approach Odoo's own UI uses: the name of a referenced record
        # is readable even when the record itself is restricted.
        return value.sudo().display_name or ''
    if ftype == 'selection':
        return str(dict(finfo['selection']).get(value, value))
    if ftype == 'date':
        return format_date(env, value)
    if ftype == 'datetime':
        return format_datetime(env, value)
    return str(value)


def _count_result(env, raw, title):
    count = raw['count']
    return {
        'type': 'table', 'title': title,
        'summary': f'{count:,} matching {title.lower()}.',
        'columns': [{'name': 'count', 'label': 'Count', 'align': 'right'}],
        'rows': [[formatLang(env, count, digits=0)]],
        'total': count, 'truncated': False,
    }


def _list_result(env, vq, raw, info, title):
    Model = env[vq.model]
    columns = [
        {'name': f, 'label': info[f]['label'],
         'align': 'right' if info[f]['type'] in NUMERIC else 'left'}
        for f in vq.fields
    ]
    rows = []
    for rec in raw['records']:
        row = []
        for fname in vq.fields:
            cname = currency_field(Model, Model._fields[fname]) \
                if info[fname]['type'] == 'monetary' else None
            row.append(_cell(env, rec[fname], info[fname], fname, rec[cname] if cname else None))
        rows.append(row)
    total, shown = raw['total'], len(rows)
    if not shown:
        summary = f'No {title.lower()} found.'
    elif shown < total:
        summary = f'Showing {shown} of {total:,} {title.lower()}.'
    else:
        summary = f'{total:,} {title.lower()} found.'
    return {
        'type': 'table', 'title': title, 'summary': summary,
        'columns': columns, 'rows': rows, 'total': total, 'truncated': shown < total,
    }


def _group_cell(env, value, finfo, gran):
    ftype = finfo['type']
    if ftype == 'boolean':
        return 'Yes' if value else 'No'
    if value in (None, False, ''):
        return 'Undefined'
    if ftype == 'many2one':
        return value.sudo().display_name or 'Undefined'
    if ftype == 'selection':
        return str(dict(finfo['selection']).get(value, value))
    if ftype in ('date', 'datetime'):
        day = value.date() if isinstance(value, datetime) else value
        if gran == 'year':
            return str(day.year)
        if gran == 'quarter':
            return f'Q{(day.month - 1) // 3 + 1} {day.year}'
        if gran == 'month':
            return day.strftime('%b %Y')
        if gran == 'week':
            return f'Week of {format_date(env, day)}'
        return format_date(env, day)
    return str(value)


def _aggregate_result(env, vq, raw, info, title):
    columns = []
    grans = []
    for spec in vq.groupby:
        fname, _sep, gran = spec.partition(':')
        grans.append(gran)
        label = info[fname]['label'] + (f' ({gran})' if gran else '')
        columns.append({'name': spec, 'label': label, 'align': 'left'})
    for fname, func in vq.aggregates:
        label = 'Count' if fname is None else f"{info[fname]['label']} ({FUNC_WORDS[func]})"
        columns.append({'name': f'{fname}:{func}', 'label': label, 'align': 'right'})

    n_group = len(vq.groupby)
    rows = []
    for tup in raw['rows']:
        row = [
            _group_cell(env, tup[i], info[vq.groupby[i].split(':')[0]], grans[i])
            for i in range(n_group)
        ]
        for j, (fname, func) in enumerate(vq.aggregates):
            value = tup[n_group + j]
            ftype = 'integer' if fname is None else info[fname]['type']
            digits = 2 if func == 'avg' or ftype in ('float', 'monetary') else 0
            row.append(_plain_number(env, value, ftype, digits))
        rows.append(row)

    truncated = bool(vq.groupby) and len(rows) >= vq.limit
    summary = f'{len(rows)} group{"" if len(rows) == 1 else "s"}'
    summary += f' (first {vq.limit} shown).' if truncated else '.'
    if not vq.groupby:
        summary = f'{title}: summary of all matching records.'
    if _mixes_currencies(env, vq, info):
        summary += ' Amounts are added up as stored, without currency conversion.'
    return {
        'type': 'table', 'title': title, 'summary': summary,
        'columns': columns, 'rows': rows, 'total': len(rows), 'truncated': truncated,
    }


def _mixes_currencies(env, vq, info):
    has_money = any(f and info[f]['type'] == 'monetary' for f, _func in vq.aggregates)
    return has_money and env['res.currency'].search_count([('active', '=', True)]) > 1