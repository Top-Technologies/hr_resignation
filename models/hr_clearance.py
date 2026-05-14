from odoo import models, fields, api, _
from odoo.exceptions import UserError

class HrClearance(models.Model):
    _name = 'hr.clearance'
    _description = 'Employee Clearance'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'employee_id'

    company_id = fields.Many2one('res.company', string='Company',
        default=lambda self: self.env.company)
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

    header_image = fields.Selection([
        ('header1', 'Header 1'),
        ('header2', 'Header 2'),
    ], string='Header Image', default='header1')

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

    def sync_checklist_lines(self):
        """Reconciles the current checklist lines with the current configuration."""
        for rec in self:
            if rec.state != 'draft':
                continue

            # 1. Define the ideal state
            checklist_types = rec.checklist_type_ids or self.env['hr.clearance.checklist.type'].search([])
            ideal_lines = {}  # Key: checklist_type_line_id, Value: vals

            for c_type in checklist_types:
                # Template lines
                type_lines = c_type.line_ids.filtered(lambda l: l.active)
                for t_line in type_lines:
                    # Follow existing responsible user logic
                    responsible = t_line.responsible_user_ids[:1]
                    if not responsible:
                        # Fallback to type level
                        responsible = c_type.responsible_user_id
                        if not responsible:
                            if rec.employee_id.parent_id and rec.employee_id.parent_id.user_id:
                                responsible = rec.employee_id.parent_id.user_id
                            else:
                                responsible = self.env.user

                    ideal_lines[t_line.id] = {
                        'name': t_line.name,
                        'responsible_user_id': responsible.id if responsible else False,
                    }

                # If type has no lines, it should at least have one line based on the type name (legacy/fallback)
                if not type_lines:
                    name = c_type.business_unit_name or c_type.name
                    # We don't have a checklist_type_line_id for this fallback case,
                    # so we handle it separately or ignore if it's just a fallback.
                    # To avoid complexity and duplication, we'll only sync explicitly defined template lines.
                    pass

            # 2. Remove obsolete lines
            current_lines = rec.checklist_ids
            for line in current_lines:
                if line.checklist_type_line_id and line.checklist_type_line_id.id not in ideal_lines:
                    line.unlink()

            # 3. Add missing lines
            existing_type_line_ids = current_lines.mapped('checklist_type_line_id').filtered(lambda x: x).ids
            for t_line_id, vals in ideal_lines.items():
                if t_line_id not in existing_type_line_ids:
                    self.env['hr.clearance.line'].create({
                        'clearance_id': rec.id,
                        'checklist_type_line_id': t_line_id,
                        'name': vals['name'],
                        'responsible_user_id': vals['responsible_user_id'],
                        'status': 'pending',
                    })

            # 4. Update existing lines (names/responsibles)
            for line in rec.checklist_ids:
                if line.checklist_type_line_id and line.checklist_type_line_id.id in ideal_lines:
                    vals = ideal_lines[line.checklist_type_line_id.id]
                    if line.name != vals['name'] or line.responsible_user_id.id != vals['responsible_user_id']:
                        line.write({
                            'name': vals['name'],
                            'responsible_user_id': vals['responsible_user_id'],
                        })

    def _backfill_checklist_links(self):
        """Links existing clearance lines to template lines based on name and responsible user."""
        for rec in self:
            if rec.state != 'draft':
                continue

            template_lines = self.env['hr.clearance.checklist.type.line'].search([])
            for line in rec.checklist_ids:
                if not line.checklist_type_line_id:
                    # Try to find a matching template line
                    match = template_lines.filtered(
                        lambda l: l.name == line.name and
                        (l.responsible_user_ids[:1].id == line.responsible_user_id.id or
                         not l.responsible_user_ids and line.responsible_user_id.id == 0) # simple fallback
                    )
                    if match:
                        line.checklist_type_line_id = match[0].id

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
                            'checklist_type_line_id': t_line.id,
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

    def write(self, vals):
        res = super(HrClearanceListType, self).write(vals)
        if 'responsible_user_id' in vals:
            # Sync changes to all draft clearances using this type
            clearances = self.env['hr.clearance'].search([
                ('checklist_type_ids', 'in', self.ids),
                ('state', '=', 'draft')
            ])
            clearances.sync_checklist_lines()
        return res


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

    def write(self, vals):
        res = super(HrClearanceListTypeLine, self).write(vals)
        if 'name' in vals or 'responsible_user_ids' in vals:
            # Trigger comprehensive sync for all affected draft clearances
            # This is safer than manual updates as it handles all reconciliation
            clearances = self.env['hr.clearance'].search([
                ('state', '=', 'draft'),
                ('checklist_ids.checklist_type_line_id', '=', self.id)
            ])
            if clearances:
                clearances.sync_checklist_lines()
        return res

    def unlink(self):
        for line in self:
            # Trigger sync for all draft clearances using this line
            clearances = self.env['hr.clearance'].search([
                ('state', '=', 'draft'),
                ('checklist_ids.checklist_type_line_id', '=', line.id)
            ])
            if clearances:
                clearances.sync_checklist_lines()
        return super(HrClearanceListTypeLine, self).unlink()

class HrClearanceLine(models.Model):
    _name = 'hr.clearance.line'
    _description = 'Clearance Checklist Line'

    clearance_id = fields.Many2one('hr.clearance', string='Clearance')
    checklist_type_line_id = fields.Many2one('hr.clearance.checklist.type.line', string='Template Line')
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
