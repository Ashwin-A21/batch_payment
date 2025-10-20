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
        states={'draft': [('readonly', False)]}
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
    
    move_id = fields.Many2one(
        'account.move',
        string='Journal Entry',
        copy=False,
        readonly=True,
        help='The journal entry created for this batch for reconciliation.'
    )

    @api.depends('payment_ids')
    def _compute_payment_count(self):
        for batch in self:
            batch.payment_count = len(batch.payment_ids)

    @api.depends('payment_ids.amount')
    def _compute_amount_total(self):
        for batch in self:
            batch.amount_total = sum(batch.payment_ids.mapped('amount'))

    @api.depends('move_id.payment_state', 'move_id.state')
    def _compute_state(self):
        """
        Compute the state of the batch payment based on its journal entry.
        - draft: No move_id or move_id is in draft.
        - validated: A move_id is present and posted.
        - reconciled: The move_id is posted and reconciled (paid/in_payment).
        """
        for batch in self:
            if batch.move_id:
                if batch.move_id.payment_state in ('paid', 'in_payment'):
                    batch.state = 'reconciled'
                elif batch.move_id.state == 'posted':
                    batch.state = 'validated'
                else:
                    batch.state = 'draft' # move_id is in draft
            else:
                batch.state = 'draft'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                seq_code = 'account.batch.payment.out' if vals.get('batch_type') == 'outbound' else 'account.batch.payment.in'
                vals['name'] = self.env['ir.sequence'].next_by_code(seq_code) or _('New')
        return super().create(vals_list)

    def _get_batch_move_account_line(self):
        """
        Get the debit and credit accounts for the batch journal entry.
        This is the core of the Enterprise-style batch payment.
        """
        self.ensure_one()
        
        if self.batch_type == 'inbound':
            # Customer Payment:
            # Debit: Bank (from Journal)
            # Credit: Outstanding Receipts (from Payment Method)
            debit_account = self.journal_id.default_account_id
            credit_account = self.payment_method_id.payment_account_id
            if not credit_account:
                raise UserError(_("Payment method '%s' is missing a Payment Account (Outstanding Receipts Account).", self.payment_method_id.name))
            if not debit_account:
                raise UserError(_("Journal '%s' is missing a Default Account (Bank Account).", self.journal_id.name))
        else:
            # Vendor Payment:
            # Debit: Outstanding Payments (from Payment Method)
            # Credit: Bank (from Journal)
            debit_account = self.payment_method_id.payment_account_id
            if not debit_account:
                raise UserError(_("Payment method '%s' is missing a Payment Account (Outstanding Payments Account).", self.payment_method_id.name))
            credit_account = self.journal_id.default_account_id
            if not credit_account:
                raise UserError(_("Journal '%s' is missing a Default Account (Bank Account).", self.journal_id.name))
                
        return debit_account, credit_account

    def _create_batch_journal_entry(self):
        """
        Create and post a single journal entry for the batch total.
        This entry moves the total amount from the outstanding account to the bank.
        """
        self.ensure_one()
        debit_account, credit_account = self._get_batch_move_account_line()
        
        move_vals = {
            'journal_id': self.journal_id.id,
            'date': self.date,
            'ref': self.name,
            'line_ids': [
                # Debit line
                (0, 0, {
                    'name': self.name,
                    'account_id': debit_account.id,
                    'debit': self.amount_total,
                    'credit': 0,
                    'currency_id': self.currency_id.id,
                }),
                # Credit line
                (0, 0, {
                    'name': self.name,
                    'account_id': credit_account.id,
                    'debit': 0,
                    'credit': self.amount_total,
                    'currency_id': self.currency_id.id,
                }),
            ],
        }
        move = self.env['account.move'].create(move_vals)
        move.action_post()
        return move

    def action_validate_batch(self):
        """
        Validate the batch:
        1. Create and post the batch journal entry.
        2. Set the batch state to 'validated'.
        (The individual payments are already posted)
        """
        self.ensure_one()
        if not self.payment_ids:
            raise UserError(_('Please add at least one payment to the batch.'))
        
        if any(p.state != 'posted' for p in self.payment_ids):
            raise UserError(_('All payments in the batch must be in a "Posted" state.'))
        
        move = self._create_batch_journal_entry()
        
        self.write({
            'state': 'validated',
            'move_id': move.id
        })
        return True

    def action_draft(self):
        """
        Reset batch payment to draft:
        1. Unpost and delete the batch journal entry.
        2. Set batch state to 'draft'.
        (This does NOT affect the individual payments, which remain posted)
        """
        self.ensure_one()
        
        # Unpost and delete the batch journal entry
        if self.move_id:
            if self.move_id.state == 'posted':
                self.move_id.button_draft()
            self.move_id.unlink()
            
        self.write({'state': 'draft', 'move_id': False})
        return True

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