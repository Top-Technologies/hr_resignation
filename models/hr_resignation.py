from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import timedelta

class HrResignation(models.Model):
    _name = 'hr.resignation'
    _description = 'Employee Resignation'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'employee_id'

    employee_id = fields.Many2one('hr.employee', string='Employee', required=True, default=lambda self: self.env.user.employee_id)
    department_id = fields.Many2one('hr.department', string='Department', related='employee_id.department_id', store=True)
    job_id = fields.Many2one('hr.job', string='Job Position', related='employee_id.job_id', store=True)
    manager_id = fields.Many2one('hr.employee', string='Manager', related='employee_id.parent_id', store=True)
    
    resignation_date = fields.Date(string='Resignation Date', default=fields.Date.today, required=True)
    last_working_day = fields.Date(string='Last Working Day', required=True)
    notice_period = fields.Integer(string='Notice Period (Days)', compute='_compute_notice_period', store=True)
    reason = fields.Text(string='Reason', required=True)
    remarks = fields.Text(string='Remarks')

    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('approved_manager', 'Manager Approved'),
        ('approved_hr', 'HR Approved'),
        ('rejected', 'Rejected'),
        ('done', 'Done'),
        ('cancel', 'Cancelled')
    ], string='Status', default='draft', tracking=True)

    @api.depends('resignation_date', 'last_working_day')
    def _compute_notice_period(self):
        for rec in self:
            if rec.resignation_date and rec.last_working_day:
                delta = rec.last_working_day - rec.resignation_date
                rec.notice_period = delta.days
            else:
                rec.notice_period = 0

    approval_request_id = fields.Many2one('approval.request', string='Approval Request', readonly=True)

    def action_submit(self):
        self.ensure_one()
        if self.approval_request_id:
             return

        category = self.env.ref('hr_resignation.approval_category_resignation', raise_if_not_found=False)
        if not category:
             category = self.env['approval.category'].search([('name', '=', 'Resignation')], limit=1)
        
        if category:
            request = self.env['approval.request'].create({
                'name': _('Resignation: %s') % self.employee_id.name,
                'category_id': category.id,
                'request_owner_id': self.employee_id.user_id.id or self.env.user.id,
                'request_status': 'new',
                'date': self.resignation_date,
                'reason': self.reason,
            })
            request.action_confirm() 
            self.write({'state': 'submitted', 'approval_request_id': request.id})
        else:
             # Fallback if approval module config missing, though we want to enforce it.
             # For now, just mark submitted.
             self.write({'state': 'submitted'})

    def action_approve(self):
        """Called when the linked Approval Request is fully approved."""
        self.write({'state': 'approved_hr'}) # We keep 'approved_hr' state as 'Final Approved' for now to match view
        self.create_clearance_request()

    def action_reject(self):
        """Called when Local Approval Request is refused."""
        self.write({'state': 'rejected'})

    def action_cancel(self):
        self.write({'state': 'cancel'})
        
    def action_reset_to_draft(self):
        self.write({'state': 'draft'})

    def create_clearance_request(self):
        if not self.env['hr.clearance'].search([('resignation_id', '=', self.id)]):
            clearance = self.env['hr.clearance'].create({
                'employee_id': self.employee_id.id,
                'resignation_id': self.id,
            })
            clearance._oncreate_populate_checklist()
            return clearance
