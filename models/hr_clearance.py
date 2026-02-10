from odoo import models, fields, api, _
from odoo.exceptions import UserError

class HrClearance(models.Model):
    _name = 'hr.clearance'
    _description = 'Employee Clearance'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'employee_id'

    employee_id = fields.Many2one('hr.employee', string='Employee', required=True)
    resignation_id = fields.Many2one('hr.resignation', string='Resignation Reference')
    checklist_ids = fields.One2many('hr.clearance.line', 'clearance_id', string='Checklists')
    
    state = fields.Selection([
        ('draft', 'Pending'),
        ('done', 'Completed')
    ], string='Status', default='draft', tracking=True)

    def update_state(self):
        for rec in self:
            # Check if all checklist items are completed
            all_completed = rec.checklist_ids and all(line.status == 'completed' for line in rec.checklist_ids)
            
            # Check for unreturned assets
            assets_count = self.env['maintenance.equipment'].search_count([('employee_id', '=', rec.employee_id.id)])
            
            if all_completed and assets_count == 0:
                if rec.state != 'done':
                    rec.write({'state': 'done'})
                    rec._process_employee_exit()
                    # Also mark Resignation as Done
                    if rec.resignation_id:
                        rec.resignation_id.write({'state': 'done'})
            else:
                if rec.state != 'draft':
                    rec.write({'state': 'draft'})

    def write(self, vals):
        res = super(HrClearance, self).write(vals)
        # If writing directly to clearance (e.g. manually changing something), check state logic if needed
        # But primarily rely on update_state being called from lines or checks
        return res

    def _process_employee_exit(self):
        # 1. Mark as Exited (Archive)
        # 2. Set departure info if available
        departure_reason = self.env.ref('hr.departure_resigned', raise_if_not_found=False)
        if not departure_reason:
            departure_reason = self.env['hr.departure.reason'].search([], limit=1)
            
        self.employee_id.write({
            'departure_reason_id': departure_reason.id if departure_reason else False,
            'departure_date': fields.Date.today(),
            'active': False,
        })
        self.message_post(body=_("Employee archived and marked as exited associated with this clearance."))
        
    def _oncreate_populate_checklist(self):
        # Fetch configured checklist types
        checklist_types = self.env['hr.clearance.checklist.type'].search([])
        lines = []
        import logging
        _logger = logging.getLogger(__name__)
        _logger.info("Antigravity: Generating checklist lines...")
        for c_type in checklist_types:
            # Fallback logic for Responsible User
            responsible = c_type.responsible_user_id
            if not responsible:
                # Try Employee's Manager
                if self.employee_id.parent_id and self.employee_id.parent_id.user_id:
                    responsible = self.employee_id.parent_id.user_id
                # Fallback to Current User (HR/Admin processing this)
                else:
                    responsible = self.env.user
                
                # Ultimate Fallback: If for some reasonenv.user is failing or not set, use Administrator
                if not responsible:
                    responsible = self.env.ref('base.user_admin', raise_if_not_found=False)
                if not responsible:
                     # Very unlikely, but just in case
                     responsible = self.env['res.users'].search([], limit=1)

            lines.append((0, 0, {
                'name': c_type.name,
                'responsible_user_id': responsible.id,
                'status': 'pending',
                'remarks': '',
            }))
        
        # Check for assets and add a specific Item if assets exist
        assets = self.env['maintenance.equipment'].search([('employee_id', '=', self.employee_id.id)])
        if assets:
             lines.append((0, 0, {
                'name': _('Return Assets: %s') % ", ".join(assets.mapped('name')[:3]), # Limit names
                'responsible_user_id': self.env.user.id, # Should be Asset Manager
                'status': 'pending',
                'remarks': 'Auto-detected assets',
            }))
            
        self.write({'checklist_ids': lines})

class HrClearanceListType(models.Model):
    _name = 'hr.clearance.checklist.type'
    _description = 'Clearance Checklist Type'

    name = fields.Char(string='Name', required=True)
    responsible_user_id = fields.Many2one('res.users', string='Default Responsible')

class HrClearanceLine(models.Model):
    _name = 'hr.clearance.line'
    _description = 'Clearance Checklist Line'

    clearance_id = fields.Many2one('hr.clearance', string='Clearance')
    name = fields.Char(string='Item', required=True)
    responsible_user_id = fields.Many2one('res.users', string='Responsible')
    status = fields.Selection([
        ('pending', 'Pending'),
        ('blocked', 'Blocked'),
        ('completed', 'Completed')
    ], string='Status', default='pending', required=True)
    remarks = fields.Text(string='Remarks')
    completion_date = fields.Date(string='Completion Date')

    def action_approve(self):
        self.write({
            'status': 'completed',
            'completion_date': fields.Date.today()
        })

    def write(self, vals):
        if 'status' in vals and vals['status'] == 'completed':
            for line in self:
                if line.responsible_user_id and line.responsible_user_id != self.env.user:
                    raise UserError(_("Only the assigned user (%s) can approve this item.") % line.responsible_user_id.name)
                if not line.responsible_user_id and not self.env.user.has_group('hr.group_hr_manager'):
                    raise UserError(_("Only the HR Manager can approve items with no responsible user."))
                
                # Log in the chatter
                if line.status != 'completed':
                    line.clearance_id.message_post(body=_("Checklist item <b>%s</b> confirmed by %s.") % (line.name, self.env.user.name))

        res = super(HrClearanceLine, self).write(vals)
        if 'status' in vals:
            for line in self:
                line.clearance_id.update_state()
        return res

    @api.model
    def create(self, vals):
        line = super(HrClearanceLine, self).create(vals)
        line.clearance_id.update_state()
        return line
