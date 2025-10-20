# batch_payment/__manifest__.py
{
    'name': 'Batch Payment',
    'version': '17.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Create batch payments for multiple invoices',
    'description': """
        Batch Payment Module for Odoo 17 Community
        ===========================================
        * Create batch payments for multiple vendor bills
        * Create batch payments for multiple customer invoices
        * Track payment status and reconciliation
        * Generate batch payment reports
        * Support for multiple payment methods
    """,
    'author': 'Concept Solutions ',
    'website': 'https://www.csloman.com',
    'license': 'LGPL-3',
    'depends': [
        'account'
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/account_batch_payment_sequence.xml',
        'views/account_batch_payment_views.xml',
        'views/account_payment_views.xml',
        'views/menu_views.xml',
        'reports/batch_payment_report.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}