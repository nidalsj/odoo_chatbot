import re

from odoo import api, fields, models
from odoo.exceptions import ValidationError

# Models the chatbot must never expose, even if an admin adds them by mistake
# This is a very important security measure
FORBIDDEN_PREFIXES = ('ir.', 'chatbot.', 'bus.', 'res.users', 'res.groups')


class ChatbotAllowedModel(models.Model):
    _name = 'chatbot.allowed.model'
    _description = 'Chatbot Allowed Model'
    _order = 'sequence, id'

    _model_name_uniq = models.Constraint(
        'UNIQUE(model_name)', 'This model is already registered.',
    )

    name = fields.Char(string='Display Name', required=True, translate=True)
    model_name = fields.Char(string='Technical Name', required=True, help='e.g. sale.order')
    default_field_names = fields.Char(
        string='Default Columns',
        help='Comma-separated field names shown when the question does not specify columns.',
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    is_available = fields.Boolean(
        string='Installed', compute='_compute_is_available',
        help='False when the app providing this model is not installed.',
    )

    def _compute_is_available(self):
        for rec in self:
            rec.is_available = rec.model_name in self.env

    def get_default_fields(self):
        self.ensure_one()
        return [f.strip() for f in (self.default_field_names or '').split(',') if f.strip()]

    @api.constrains('model_name')
    def _check_model_name(self):
        for rec in self:
            name = rec.model_name or ''
            if not re.fullmatch(r'[a-z0-9_.]+', name):
                raise ValidationError(
                    "Technical name must contain only lowercase letters, digits, '_' and '.'."
                )
            if name.startswith(FORBIDDEN_PREFIXES):
                raise ValidationError(f"The model '{name}' cannot be exposed to the chatbot.")

    @api.constrains('model_name', 'default_field_names')
    def _check_default_fields(self):
        for rec in self:
            if rec.model_name not in self.env:
                continue  # app not installed: nothing to validate
            fields_map = self.env[rec.model_name]._fields
            missing = [f for f in rec.get_default_fields() if f not in fields_map]
            if missing:
                raise ValidationError(
                    f"Unknown field(s) on {rec.model_name}: {', '.join(missing)}"
                )