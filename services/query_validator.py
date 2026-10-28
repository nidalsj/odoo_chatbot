from dataclasses import dataclass, field as dc_field
from zoneinfo import ZoneInfo
from odoo import fields as odoo_fields
from .date_resolver import resolve_between, resolve_period, to_utc_naive
from .errors import QueryError

UNREADABLE = "I couldn't understand that request. Could you rephrase it?"
NOT_AVAILABLE = "That data isn't available to you, or it isn't enabled for the chatbot."

OP_ALIASES = {
    '==': '=', 'eq': '=', '<>': '!=', 'ne': '!=',
    'like': 'ilike', 'contains': 'ilike', 'not like': 'not ilike',
}
VALID_OPS = {'=', '!=', '<', '<=', '>', '>=', 'in', 'not in', 'ilike', 'not ilike', 'between'}
NUMERIC = {'integer', 'float', 'monetary'}
DATES = {'date', 'datetime'}
GROUPABLE = {'many2one', 'selection', 'boolean', 'date', 'datetime', 'char'}
GRANULARITIES = ('day', 'week', 'month', 'quarter', 'year')
AGG_FUNCS = ('sum', 'avg', 'min', 'max')
MAX_FILTERS, MAX_COLUMNS, MAX_ORDER, MAX_GROUPBY, MAX_AGGREGATES = 15, 12, 3, 2, 4
MAX_LIST_VALUES, MAX_TEXT = 50, 200


@dataclass
class ValidatedQuery:
    intent: str
    model: str = ''
    domain: list = dc_field(default_factory=list)
    fields: list = dc_field(default_factory=list)
    order: str = ''
    limit: int = 0
    groupby: list = dc_field(default_factory=list)
    aggregates: list = dc_field(default_factory=list)
    message: str = ''


def validate_spec(env, spec, schema, max_rows):
    """Check LLM's spec against the schema and return a
    ValidatedQuery. Anything not explicitly allowed raises querry errors"""
    if not isinstance(spec, dict):
        raise QueryError(UNREADABLE)
    intent = str(spec.get('intent', '')).lower()

    if intent in ('clarify', 'unsupported'):
        default = ('Could you give me a bit more detail?' if intent == 'clarify'
                   else 'I can only answer questions about the data in this database.')
        text = str(spec.get('message') or '').strip()[:500] or default
        return ValidatedQuery(intent='message', message=text)
    if intent not in ('list', 'count', 'aggregate'):
        raise QueryError(UNREADABLE)

    model_name = spec.get('model')
    if not isinstance(model_name, str) or model_name not in schema:
        raise QueryError(NOT_AVAILABLE)
    info = schema[model_name]['fields']
    today = odoo_fields.Date.context_today(env.user)
    tz = _user_tz(env)

    domain = []
    for flt in _items(spec.get('filters'), MAX_FILTERS):
        domain.extend(_filter_terms(flt, info, today, tz))

    groupby = [_groupby_spec(g, info) for g in _items(spec.get('groupby'), MAX_GROUPBY)]
    aggregates = []
    for item in _items(spec.get('aggregates'), MAX_AGGREGATES):
        agg = _aggregate_item(item, info)
        if agg not in aggregates:
            aggregates.append(agg)

    if intent == 'count':
        aggregates = [(None, 'count')]
        if groupby:
            intent = 'aggregate'
    elif intent == 'aggregate':
        aggregates = aggregates or [(None, 'count')]
    else:
        groupby, aggregates = [], []

    columns, order = [], ''
    if intent == 'list':
        columns = _columns(spec.get('fields'), info, schema[model_name]['default_fields'])
        order = _list_order(spec.get('order'), info)
    elif intent == 'aggregate':
        order = _aggregate_order(spec.get('order'), groupby, aggregates)

    return ValidatedQuery(
        intent=intent, model=model_name, domain=domain, fields=columns, order=order,
        limit=_limit(spec.get('limit'), max_rows), groupby=groupby, aggregates=aggregates,
    )


# FOLLOWING FUNCTION ARE SOME HELPERS FOR VALIDATE_SPEC, NOT USED OUTSIDE THIS FILE
# THIS IS VERY IMPORTANT: DO NOT CHANGE THEM WITHOUT TESTING, THEY ARE THE CORE OF THE QUERY VALIDATION
# AFTER CHANGING THEM, RUN THE TESTS IN odoo_chatbot/tests/test_query_pipeline.py TO MAKE SURE THEY STILL WORK

def _user_tz(env):
    name = env.context.get('tz') or env.user.tz or 'UTC'
    try:
        return ZoneInfo(name)
    except (KeyError, ValueError):
        return ZoneInfo('UTC')


def _items(value, maximum):
    if value is None:
        return []
    if isinstance(value, (dict, str)):
        value = [value]
    if not isinstance(value, list):
        raise QueryError(UNREADABLE)
    if len(value) > maximum:
        raise QueryError('That request has too many conditions. Please simplify it.')
    return value


def _limit(raw, max_rows):
    try:
        limit = int(raw)
    except (TypeError, ValueError):
        return max_rows
    return max_rows if limit < 1 else min(limit, max_rows)


def _op(raw):
    text = str(raw).strip().lower()
    op = OP_ALIASES.get(text, text)
    if op not in VALID_OPS:
        raise QueryError(f"I don't support the operator '{raw}'.")
    return op


def _require_op(op, allowed, label):
    if op not in allowed:
        raise QueryError(f"I can't use '{op}' with {label}.")


def _list(value, label):
    if not isinstance(value, (list, tuple)) or not value or len(value) > MAX_LIST_VALUES:
        raise QueryError(f'{label} needs a short list of values.')
    return list(value)


def _pair(value, label):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise QueryError(f'{label} needs two values (from and to).')
    return value


def _text(value, label):
    if isinstance(value, (bool, dict, list, tuple)) or value is None:
        raise QueryError(f'{label} needs a text value.')
    text = str(value).strip()
    if not text or len(text) > MAX_TEXT:
        raise QueryError(f'{label} needs a text value of up to {MAX_TEXT} characters.')
    return text


def _number(value, ftype, label):
    if isinstance(value, bool):
        raise QueryError(f'{label} needs a number.')
    if isinstance(value, str):
        value = value.replace(',', '').strip()
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise QueryError(f"{label} needs a number, not '{value}'.") from None
    if number != number or number in (float('inf'), float('-inf')):
        raise QueryError(f'{label} needs a normal number.')
    return int(number) if number.is_integer() else number


def _record_id(value, label):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise QueryError(f'{label} needs record ids when using a list.')
    return value


def _selection_key(value, finfo):
    options = finfo['selection']
    text = str(value).strip()
    lowered = text.lower()
    for key, label in options:
        if text == str(key) or lowered in (str(key).lower(), str(label).lower()):
            return key
    valid = ', '.join(str(label) for _key, label in options[:12])
    raise QueryError(f"'{text}' is not a valid value for {finfo['label']}. Valid values: {valid}.")


def _bound(ftype, day, tz):
    return day if ftype == 'date' else to_utc_naive(day, tz)


def _range_terms(fname, ftype, start, end, tz):
    return [(fname, '>=', _bound(ftype, start, tz)), (fname, '<', _bound(ftype, end, tz))]


def _date_terms(flt, fname, ftype, label, today, tz):
    if 'period' in flt:
        start, end = resolve_period(flt['period'], today)
        return _range_terms(fname, ftype, start, end, tz)
    op = _op(flt.get('op', '='))
    _require_op(op, {'=', '<', '<=', '>', '>=', 'between'}, label)
    value = flt.get('value')
    if op == 'between':
        low, high = _pair(value, label)
        start, end = resolve_between(low, high)
        return _range_terms(fname, ftype, start, end, tz)
    start, end = resolve_period(value, today)   # a single ISO date -> that whole day
    if op == '=':
        return _range_terms(fname, ftype, start, end, tz)
    if op == '>=':
        return [(fname, '>=', _bound(ftype, start, tz))]
    if op == '>':
        return [(fname, '>=', _bound(ftype, end, tz))]
    if op == '<':
        return [(fname, '<', _bound(ftype, start, tz))]
    return [(fname, '<', _bound(ftype, end, tz))]   # '<='


def _filter_terms(flt, info, today, tz):
    if not isinstance(flt, dict):
        raise QueryError(UNREADABLE)
    fname = flt.get('field')
    if not isinstance(fname, str) or fname not in info:
        raise QueryError(f"I can't filter by '{fname}'.")
    finfo = info[fname]
    ftype, label = finfo['type'], finfo['label']

    if ftype in DATES:
        return _date_terms(flt, fname, ftype, label, today, tz)
    op = _op(flt.get('op', '='))
    if 'value' not in flt:
        raise QueryError(f'Please give a value for {label}.')
    value = flt['value']

    if ftype in NUMERIC:
        _require_op(op, {'=', '!=', '<', '<=', '>', '>=', 'in', 'not in', 'between'}, label)
        if op in ('in', 'not in'):
            return [(fname, op, [_number(v, ftype, label) for v in _list(value, label)])]
        if op == 'between':
            low, high = (_number(v, ftype, label) for v in _pair(value, label))
            return [(fname, '>=', low), (fname, '<=', high)]
        return [(fname, op, _number(value, ftype, label))]

    if ftype == 'boolean':
        _require_op(op, {'=', '!='}, label)
        text = str(value).strip().lower()
        if isinstance(value, bool):
            flag = value
        elif text in ('true', 'yes', '1'):
            flag = True
        elif text in ('false', 'no', '0'):
            flag = False
        else:
            raise QueryError(f'{label} must be yes or no.')
        return [(fname, op, flag)]

    if ftype == 'selection':
        _require_op(op, {'=', '!=', 'in', 'not in'}, label)
        if op in ('in', 'not in'):
            return [(fname, op, [_selection_key(v, finfo) for v in _list(value, label)])]
        return [(fname, op, _selection_key(value, finfo))]

    if ftype == 'char':
        _require_op(op, {'=', '!=', 'ilike', 'not ilike', 'in', 'not in'}, label)
        if op in ('in', 'not in'):
            return [(fname, op, [_text(v, label) for v in _list(value, label)])]
        return [(fname, op, _text(value, label))]

    if ftype == 'many2one':
        _require_op(op, {'=', '!=', 'ilike', 'not ilike', 'in', 'not in'}, label)
        if op in ('in', 'not in'):
            return [(fname, op, [_record_id(v, label) for v in _list(value, label)])]
        if isinstance(value, int) and not isinstance(value, bool):
            _require_op(op, {'=', '!='}, label)
            return [(fname, op, value)]
        # A name: match it loosely ("Deco" finds "Deco Addict").
        return [(fname, {'=': 'ilike', '!=': 'not ilike'}.get(op, op), _text(value, label))]

    raise QueryError(f"I can't filter by '{label}'.")


def _columns(raw, info, defaults):
    names = []
    for name in (raw if isinstance(raw, list) else [])[:MAX_COLUMNS]:
        if isinstance(name, str) and name in info and name not in names:
            names.append(name)  # unknown columns are dropped, not fatal
    return names or [n for n in defaults if n in info] or list(info)[:5]


def _order_item(item):
    if not isinstance(item, dict):
        return None, 'asc'
    direction = 'desc' if str(item.get('direction', 'asc')).lower() == 'desc' else 'asc'
    return item.get('field'), direction


def _list_order(raw, info):
    terms = []
    for item in _items(raw, MAX_ORDER):
        fname, direction = _order_item(item)
        if isinstance(fname, str) and fname in info:
            terms.append(f'{fname} {direction}')
    if not any(term.split()[0] == 'id' for term in terms):
        terms.append('id desc')   # stable tie-breaker, newest first
    return ', '.join(terms)


def _groupby_spec(raw, info):
    if isinstance(raw, dict):
        fname, gran = raw.get('field'), raw.get('granularity')
    else:
        fname, _sep, gran = str(raw).partition(':')
    if not isinstance(fname, str) or fname not in info or info[fname]['type'] not in GROUPABLE:
        raise QueryError(f"I can't group results by '{fname}'.")
    if info[fname]['type'] in DATES:
        gran = str(gran or 'month').lower()
        return f'{fname}:{gran if gran in GRANULARITIES else "month"}'
    return fname


def _aggregate_item(item, info):
    if not isinstance(item, dict):
        raise QueryError(UNREADABLE)
    func = str(item.get('func', 'sum')).lower()
    if func == 'count':
        return (None, 'count')
    fname = item.get('field')
    if func not in AGG_FUNCS:
        raise QueryError(f"I can't calculate '{func}'.")
    if not isinstance(fname, str) or fname not in info or info[fname]['type'] not in NUMERIC:
        raise QueryError(f"I can't calculate a {func} of '{fname}'.")
    return (fname, func)


def _aggregate_order(raw, groupby, aggregates):
    terms = []
    for item in _items(raw, MAX_ORDER):
        fname, direction = _order_item(item)
        if fname in ('count', '__count'):
            key = '__count'
        else:
            key = next((f'{f}:{func}' for f, func in aggregates if f == fname), None) \
                or next((g for g in groupby if g.split(':')[0] == fname), None)
        if key:
            terms.append(f'{key} {direction}')
    if terms:
        return ', '.join(terms)
    if not groupby:
        return ''
    if ':' in groupby[0]:                      # grouped by date: chronological
        return f'{groupby[0]} asc'
    first = next((f'{f}:{func}' for f, func in aggregates if f), '__count')
    return f'{first} desc'                     # otherwise biggest first