# batch_payment/models/account_batch_payment.py

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class AccountBatchPayment(models.Model):
    _name = 'account.batch.payment'
    _description = 'Batch Payment'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    name = fields.Char(
        string='Reference',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New')
    )
    
    date = fields.Date(
        string='Batch Date',
        required=True,
        default=fields.Date.context_today,
        tracking=True,
        readonly=True,
        states={'draft': [('readonly', False)]}
    )
    
    journal_id = fields.Many2one(
        'account.journal',
        string='Bank Journal',
        required=True,
        domain="[('type', 'in', ('bank', 'cash'))]",
        tracking=True,
        readonly=True,
        states={'draft': [('readonly', False)]}
    )
    
    payment_ids = fields.One2many(
        'account.payment',
        'batch_payment_id',
        string='Payments',
        readonly=True,
        states={'draft': [('readonly', False)]}
    )
    
    payment_method_id = fields.Many2one(
        'account.payment.method',
        string='Payment Method',
        required=True,
        tracking=True,
        readonly=True,
        states={'draft': [('readonly', False)]},
        domain="[('payment_type', '=', batch_type)]"
    )
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('validated', 'Validated'),
        ('reconciled', 'Reconciled')
    ], string='Status', default='draft', required=True, tracking=True,
       compute='_compute_state', store=True, readonly=True)
    
    batch_type = fields.Selection([
        ('outbound', 'Vendor Payments'),
        ('inbound', 'Customer Payments')
    ], string='Type', required=True, 
       tracking=True, readonly=True, states={'draft': [('readonly', False)]})
    
    amount_total = fields.Monetary(
        string='Total Amount',
        compute='_compute_amount_total',
        store=True,
        currency_field='currency_id'
    )
    
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        required=True,
        default=lambda self: self.env.company.currency_id,
        readonly=True, states={'draft': [('readonly', False)]}
    )
    
    payment_count = fields.Integer(
        string='Payment Count',
        compute='_compute_payment_count',
        store=True
    )
    
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        readonly=True,
        default=lambda self: self.env.company
    )

    @api.depends('payment_ids')
    def _compute_payment_count(self):
        for batch in self:
            batch.payment_count = len(batch.payment_ids)

    @api.depends('payment_ids.amount')
    def _compute_amount_total(self):
        for batch in self:
            batch.amount_total = sum(batch.payment_ids.mapped('amount'))

    @api.depends('payment_ids.is_reconciled', 'payment_ids.state')
    def _compute_state(self):
        """
        Compute the state of the batch payment based on payment reconciliation.
        - draft: Has no validated payments or batch is new.
        - validated: All payments are posted/validated.
        - reconciled: All payments are reconciled.
        """
        for batch in self:
            if not batch.payment_ids:
                batch.state = 'draft'
                continue
                
            # Check if all payments are posted
            all_posted = all(p.state == 'posted' for p in batch.payment_ids)
            
            # Check if all payments are reconciled
            all_reconciled = all(p.is_reconciled for p in batch.payment_ids)
            
            if all_reconciled:
                batch.state = 'reconciled'
            elif all_posted:
                batch.state = 'validated'
            else:
                batch.state = 'draft'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                seq_code = 'account.batch.payment.out' if vals.get('batch_type') == 'outbound' else 'account.batch.payment.in'
                vals['name'] = self.env['ir.sequence'].next_by_code(seq_code) or _('New')
        return super().create(vals_list)

    def action_view_payments(self):
        """Open the list of payments in the batch"""
        self.ensure_one()
        return {
            'name': _('Payments'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', self.payment_ids.ids)],
            'context': {'default_batch_payment_id': self.id}
        }
    
    def action_print_batch_payment(self):
        """Print batch payment report"""
        self.ensure_one()
        return self.env.ref('batch_payment.action_report_batch_payment').report_action(self)

    def unlink(self):
        """Prevent deletion of non-draft batch payments"""
        for batch in self:
            if batch.state != 'draft':
                raise UserError(_('You cannot delete a batch payment that is not in draft state.'))
            # Unlink payments from batch
            batch.payment_ids.write({'batch_payment_id': False, 'batch_payment_state': False})
        return super().unlink()

    @api.constrains('payment_ids', 'journal_id', 'currency_id', 'batch_type', 'payment_method_id')
    def _check_payment_ids(self):
        """Ensure all payments added to a batch match the batch settings."""
        for batch in self:
            if not batch.payment_ids:
                continue

            # Check currency
            currencies = batch.payment_ids.mapped('currency_id')
            if len(currencies) > 1 or (batch.currency_id and batch.currency_id not in currencies):
                raise ValidationError(_('All payments in a batch must have the same currency as the batch.'))
            
            # Check payment type
            payment_types = batch.payment_ids.mapped('payment_type')
            if len(payment_types) > 1 or (batch.batch_type and batch.batch_type not in payment_types):
                raise ValidationError(_('Payment type must match batch type.'))
            
            # Check journal
            journals = batch.payment_ids.mapped('journal_id')
            if len(journals) > 1 or (batch.journal_id and batch.journal_id not in journals):
                 raise ValidationError(_('All payments in a batch must have the same journal as the batch.'))

            # Check payment method
            methods = batch.payment_ids.mapped('payment_method_id')
            if len(methods) > 1 or (batch.payment_method_id and batch.payment_method_id not in methods):
                 raise ValidationError(_('All payments in a batch must have the same payment method as the batch.'))