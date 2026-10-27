from odoo import fields, models


class ChatbotMessage(models.Model):
    _name = 'chatbot.message'
    _description = 'Chatbot Message'
    _order = 'id'

    conversation_id = fields.Many2one(
        'chatbot.conversation', required=True, index=True, ondelete='cascade',
    )
    # Stored related fields keep the record rules simple and fast.
    user_id = fields.Many2one(related='conversation_id.user_id', store=True, index=True)
    company_id = fields.Many2one(related='conversation_id.company_id', store=True, index=True)

    role = fields.Selection([('user', 'User'), ('bot', 'Bot')], required=True)
    text = fields.Text()
    query_spec = fields.Json(string='Query Spec')
    result = fields.Json(string='Result')
    status = fields.Selection([('ok', 'OK'), ('error', 'Error')], default='ok', required=True)
    error_message = fields.Text()