{
    'name': 'Odoo AI Chatbot',
    'version': '20.0.1.0.0',
    'summary': 'Ask questions about your Odoo data in plain English',
    'category': 'Productivity',
    'author': 'Nidal SJ',
    'website': 'nidalsj.vercel.app',
    'license': 'LGPL-3',
    'depends': ['base', 'web','account', 'sale', 'purchase', 'stock', 'crm'],
    'data': [
        'security/security.xml',
        'security/ir.access.csv',
        'data/chatbot_allowed_model_data.xml',
        'views/chatbot_allowed_model_views.xml',
        'views/chatbot_client_action.xml',
        'views/res_config_settings_views.xml',
        'views/chatbot_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'odoo_chatbot/static/src/**/*',
        ],
    },
    'application': True,
    'installable': True,
    'auto_install': False,
}