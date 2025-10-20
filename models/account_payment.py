# batch_payment/models/account_payment.py

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    batch_payment_id = fields.Many2one(
        'account.batch.payment',
        string='Batch Payment',
        copy=False,
        readonly=True,
        ondelete='set null', # Use ondelete='set null'
        help='The batch payment to which this payment belongs'
    )
    
    batch_payment_state = fields.Selection(
        related='batch_payment_id.state',
        string='Batch Status',
        store=True,
        readonly=True
    )

    def action_create_batch_payment(self):
        """
        Create a batch payment (or multiple) from selected POSTED payments.
        This now groups payments by key properties and creates a batch for each group.
        """
        # 1. Filter for valid payments (MUST BE POSTED)
        valid_payments = self.filtered(lambda p: p.state == 'posted')
        if not valid_payments:
            raise UserError(_('Only payments in "Posted" state can be added to a batch.'))
        
        if len(valid_payments) != len(self):
            raise UserError(_('Some selected payments are not in "Posted" state. Please filter for Posted payments.'))
        
        if any(p.batch_payment_id for p in valid_payments):
            raise UserError(_('Some selected payments are already in a batch. Please remove them first.'))
        
        if any(p.payment_type == 'internal' for p in valid_payments):
            raise UserError(_('Internal transfers cannot be added to a batch payment.'))

        # 2. Check for payment type homogeneity
        payment_types = valid_payments.mapped('payment_type')
        if len(set(payment_types)) > 1:
            raise UserError(_('All selected payments must be of the same type (inbound or outbound).'))
        batch_type = payment_types[0]

        # 3. Group by (Journal, Payment Method, Currency)
        batches_data = {}
        for payment in valid_payments:
            key = (
                payment.journal_id,
                payment.payment_method_id,
                payment.currency_id,
            )
            if key not in batches_data:
                batches_data[key] = self.env['account.payment']
            batches_data[key] |= payment

        # 4. Create batches
        batch_payments = self.env['account.batch.payment']
        for (journal, method, currency), payments in batches_data.items():
            if not journal or not method or not currency:
                raise UserError(_('Some payments are missing a Journal, Payment Method, or Currency. Please check all selected payments.'))
            
            batch = self.env['account.batch.payment'].create({
                'batch_type': batch_type,
                'journal_id': journal.id,
                'payment_method_id': method.id,
                'currency_id': currency.id,
                'date': fields.Date.context_today(self),
            })
            
            # Link payments to the new batch
            payments.write({'batch_payment_id': batch.id})
            batch_payments |= batch

        # 5. Return action to view the created batch(es)
        if len(batch_payments) == 1:
            return {
                'name': _('Batch Payment'),
                'type': 'ir.actions.act_window',
                'res_model': 'account.batch.payment',
                'view_mode': 'form',
                'res_id': batch_payments.id,
                'target': 'current',
            }
        else:
            return {
                'name': _('Batch Payments'),
                'type': 'ir.actions.act_window',
                'res_model': 'account.batch.payment',
                'view_mode': 'tree,form',
                'domain': [('id', 'in', batch_payments.ids)],
            }

    def action_remove_from_batch(self):
        """Remove payment from a DRAFT batch"""
        for payment in self:
            if payment.batch_payment_id and payment.batch_payment_id.state != 'draft':
                raise UserError(_('You cannot remove a payment from a batch that is not in draft state.'))
            payment.write({
                'batch_payment_id': False,
                'batch_payment_state': False
            })
        return True