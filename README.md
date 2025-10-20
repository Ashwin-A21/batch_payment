# Batch Payment Module for Odoo 17 Community

This module adds **Enterprise-style batch payment functionality** to Odoo 17 Community Edition. It allows you to group multiple vendor bills or customer invoices into a single batch, generate a detailed deposit slip, and use the batch reference during bank reconciliation to easily find and match all corresponding payments.

## Features

- **Create Batch Payments**: Group multiple payments into a single batch with a unique reference.
- **Support for Both Payment Types**: 
  - Vendor payments (outbound)
  - Customer payments (inbound)
- **Automated Workflow**: Draft → Validated → Reconciled (State is computed automatically).
- **Automated Validation**: Validates (posts) all payments in the batch with one click.
- **Bank Reconciliation Support**: Use the batch reference to find and reconcile all included payments at once.
- **Payment Tracking**: Track which payments belong to which batch.
- **Reporting**: Generate PDF reports for batch payments (deposit slips).
- **Access Control**: Proper security groups and permissions.

## Key Benefits

✅ **Simplify Bank Reconciliation**: Use the batch reference to match a single bank statement line to many individual payments.
✅ **Process Multiple Payments at Once**: Validate and post all payments in a batch with one click.
✅ **Better Organization**: Group related payments together.
✅ **Audit Trail**: Track payment batches with a complete history.

## Installation

1. **Copy the module** to your Odoo addons directory:
   ```bash
   cp -r batch_payment /path/to/odoo/addons/