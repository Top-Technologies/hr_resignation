from odoo import models, fields, api, _
from odoo.exceptions import UserError

class HrClearance(models.Model):
    _name = 'hr.clearance'
    _description = 'Employee Clearance'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'employee_id'

    employee_id = fields.Many2one('hr.employee', string='Employee', required=True)
    resignation_id = fields.Many2one('hr.resignation', string='Resignation Reference')
    checklist_type_ids = fields.Many2many(
        "hr.clearance.checklist.type",
        string="Branch",
    )
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
        # Use selected branches (from resignation) if available; otherwise fallback to all
        checklist_types = self.checklist_type_ids or self.env['hr.clearance.checklist.type'].search([])
        unique_lines = {}  # Key: (name, responsible_user_id), Value: vals dict
        
        import logging
        _logger = logging.getLogger(__name__)
        _logger.info("Antigravity: Generating checklist lines...")
        
        for c_type in checklist_types:
            # Fallback logic for Responsible User (type level)
            responsible = c_type.responsible_user_id
            if not responsible:
                # Try Employee's Manager
                if self.employee_id.parent_id and self.employee_id.parent_id.user_id:
                    responsible = self.employee_id.parent_id.user_id
                # Fallback to Current User (HR/Admin processing this)
                else:
                    responsible = self.env.user
                
                # Ultimate Fallback: If for some reason env.user is failing or not set, use Administrator
                if not responsible:
                    responsible = self.env.ref('base.user_admin', raise_if_not_found=False)
                if not responsible:
                     # Very unlikely, but just in case
                     responsible = self.env['res.users'].search([], limit=1)

            type_lines = c_type.line_ids.filtered(lambda l: l.active)
            if type_lines:
                for t_line in type_lines.sorted(lambda r: (r.sequence, r.id)):
                    line_responsible = t_line.responsible_user_ids[:1] or responsible
                    key = (t_line.name, line_responsible.id)
                    if key not in unique_lines:
                        unique_lines[key] = {
                            'name': t_line.name,
                            'responsible_user_id': line_responsible.id,
                            'status': 'pending',
                            'remarks': '',
                        }
            else:
                name = c_type.business_unit_name or c_type.name
                key = (name, responsible.id)
                if key not in unique_lines:
                    unique_lines[key] = {
                        'name': name,
                        'responsible_user_id': responsible.id,
                        'status': 'pending',
                        'remarks': '',
                    }
        
        # Check for assets and add a specific Item if assets exist
        assets = self.env['maintenance.equipment'].search([('employee_id', '=', self.employee_id.id)])
        if assets:
            asset_line_name = _('Return Assets: %s') % ", ".join(assets.mapped('name')[:3])
            key = (asset_line_name, self.env.user.id)
            if key not in unique_lines:
                 unique_lines[key] = {
                    'name': asset_line_name,
                    'responsible_user_id': self.env.user.id, # Should be Asset Manager
                    'status': 'pending',
                    'remarks': 'Auto-detected assets',
                }
            
        lines = [(0, 0, vals) for vals in unique_lines.values()]
        self.write({'checklist_ids': lines})

        # Notify responsible users via activities
        responsible_user_ids = set()
        for line_cmd in lines:
            if line_cmd[2].get('responsible_user_id'):
                responsible_user_ids.add(line_cmd[2]['responsible_user_id'])
        
        for user_id in responsible_user_ids:
            self.activity_schedule(
                'mail.mail_activity_data_todo',
                summary=_('Clearance Checklist: %s') % self.employee_id.name,
                note=_('Please review and complete the clearance checklist items assigned to you for %s.') % self.employee_id.name,
                user_id=user_id
            )

class HrClearanceListType(models.Model):
    _name = 'hr.clearance.checklist.type'
    _description = 'Clearance Checklist Type'
    _rec_name = "business_unit_name"

    # Keep legacy "name" for backward compatibility (existing data/XML),
    # but use Branch as the primary field in the UI.
    name = fields.Char(string='Name')
    business_unit_name = fields.Char(string="Branch", required=True)
    tag_ids = fields.Many2many(
        "hr.employee.category",
        "hr_clearance_checklist_type_hr_employee_category_rel",
        "type_id",
        "category_id",
        string="Tags",
    )
    responsible_user_id = fields.Many2one('res.users', string='Default Responsible')
    responsible_user_ids = fields.Many2many(
        "res.users",
        "hr_clearance_checklist_type_res_users_rel",
        "type_id",
        "user_id",
        string="Responsible Users",
        domain=[("share", "=", False)],
    )
    line_ids = fields.One2many(
        "hr.clearance.checklist.type.line",
        "type_id",
        string="Checklist Lines",
        copy=True,
    )


class HrClearanceListTypeLine(models.Model):
    _name = "hr.clearance.checklist.type.line"
    _description = "Clearance Checklist Type Line"
    _order = "sequence, id"

    type_id = fields.Many2one(
        "hr.clearance.checklist.type",
        string="Checklist Type",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(default=10)
    name = fields.Char(string="Departments", required=True, translate=True)
    responsible_user_ids = fields.Many2many(
        "res.users",
        "hr_clearance_checklist_type_line_res_users_rel",
        "line_id",
        "user_id",
        string="Responsible Users",
        domain=[("share", "=", False)],
    )
    active = fields.Boolean(default=True)

class HrClearanceLine(models.Model):
    _name = 'hr.clearance.line'
    _description = 'Clearance Checklist Line'

    clearance_id = fields.Many2one('hr.clearance', string='Clearance')
    name = fields.Char(string='Departments', required=True)
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
