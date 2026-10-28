import logging
from odoo.exceptions import AccessError, UserError
from .errors import QueryError
_logger = logging.getLogger(__name__)


def currency_field(Model, fld):
    name = getattr(fld, 'currency_field', None)
    if name:
        return name
    return 'currency_id' if 'currency_id' in Model._fields else None


def execute(env, vq):
    """Run a ValidatedQuery as the current user with no sudo. The savepoint keeps
    the transaction usable if postgres rejects the query"""
    Model = env[vq.model]
    try:
        with env.cr.savepoint():
            if vq.intent == 'count':
                return {'kind': 'count', 'count': Model.search_count(vq.domain)}
            if vq.intent == 'list':
                return _run_list(Model, vq)
            return _run_aggregate(Model, vq)
    except AccessError as exc:
        raise QueryError("You don't have access to some of the data this question needs.") from exc
    except UserError as exc:
        raise QueryError(str(exc)) from exc
    except Exception as exc:
        _logger.exception('Chatbot query failed')
        raise QueryError("I couldn't run that query. Try rephrasing your question.") from exc


def _run_list(Model, vq):
    fetch = list(vq.fields)
    for fname in vq.fields:
        fld = Model._fields[fname]
        if fld.type == 'monetary':
            cname = currency_field(Model, fld)
            if cname and cname not in fetch:
                fetch.append(cname)
    records = Model.search_fetch(vq.domain, fetch, order=vq.order, limit=vq.limit)
    total = len(records) if len(records) < vq.limit else Model.search_count(vq.domain)
    return {'kind': 'list', 'records': records, 'total': total}


def _run_aggregate(Model, vq):
    specs = ['__count' if f is None else f'{f}:{func}' for f, func in vq.aggregates]
    rows = Model._read_group(
        vq.domain, vq.groupby, specs, order=vq.order or None, limit=vq.limit,
    )
    return {'kind': 'aggregate', 'rows': rows}