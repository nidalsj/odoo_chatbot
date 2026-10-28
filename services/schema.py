import re

ALLOWED_TYPES = {
    'char', 'integer', 'float', 'monetary', 'boolean',
    'date', 'datetime', 'selection', 'many2one',
}
SKIP_PREFIXES = ('message_', 'activity_', 'website_message', 'access_', 'has_message')
SENSITIVE = re.compile(r'password|passwd|token|secret|api_key|private_key|signature', re.IGNORECASE)
ALWAYS_KEEP = ('id', 'create_date')
TYPE_RANK = {
    'monetary': 0, 'date': 1, 'datetime': 1, 'selection': 2, 'many2one': 3,
    'float': 4, 'integer': 4, 'char': 5, 'boolean': 6,
}
# Keeps the prompt small bcs free tiers have tight tokens per minute limits.
MAX_FIELDS_PER_MODEL = 40
FIELD_ATTRIBUTES = ['string', 'type', 'relation', 'selection', 'store', 'required']


def get_schema(env):
    """The models and fields the CURRENT USER may query:
    {model: {'label', 'default_fields', 'fields': {name: info}}}.
    Everything runs as the calling user, so access rights decide what appears.
    Used by the prompt builder and, in 4B, by the validator."""
    readable = {}

    def can_read(model_name):
        if model_name not in readable:
            readable[model_name] = bool(model_name) and model_name in env \
                and env[model_name].has_access('read')
        return readable[model_name]

    schema = {}
    for reg in env['chatbot.allowed.model'].search([('active', '=', True)]):
        if not can_read(reg.model_name):
            continue
        raw = env[reg.model_name].fields_get(attributes=FIELD_ATTRIBUTES)
        defaults = [f for f in reg.get_default_fields() if f in raw]

        info = {}
        for fname, meta in raw.items():
            if _usable(fname, meta, can_read):
                info[fname] = {
                    'label': meta['string'],
                    'type': meta['type'],
                    'relation': meta.get('relation'),
                    'selection': meta.get('selection') or [],
                    'required': bool(meta.get('required')),
                }

        def sort_key(fname):
            return (
                0 if fname in ALWAYS_KEEP else 1,
                0 if fname in defaults else 1,
                0 if info[fname]['required'] else 1,
                TYPE_RANK[info[fname]['type']],
                fname,
            )

        keep = sorted(info, key=sort_key)[:MAX_FIELDS_PER_MODEL]
        schema[reg.model_name] = {
            'label': reg.name,
            'default_fields': defaults,
            'fields': {fname: info[fname] for fname in keep},
        }
    return schema


def _usable(fname, meta, can_read):
    if not meta.get('store') or meta['type'] not in ALLOWED_TYPES:
        return False
    if fname.startswith(SKIP_PREFIXES) or SENSITIVE.search(fname):
        return False
    if meta['type'] == 'many2one' and not can_read(meta.get('relation')):
        return False  # the user could not see the related record's name anyway
    return True