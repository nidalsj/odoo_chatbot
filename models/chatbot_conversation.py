from odoo import fields, models


class ChatbotConversation(models.Model):
    _name = 'chatbot.conversation'
    _description = 'Chatbot Conversation'
    _order = 'create_date desc, id desc'

    name = fields.Char(string='Title', required=True, default='New chat')
    user_id = fields.Many2one(
        'res.users', string='Owner', required=True, index=True,
        default=lambda self: self.env.user, ondelete='cascade',
    )
    company_id = fields.Many2one(
        'res.company', string='Company', required=True, index=True,
        default=lambda self: self.env.company, ondelete='cascade',
    )
    message_ids = fields.One2many('chatbot.message', 'conversation_id', string='Messages')