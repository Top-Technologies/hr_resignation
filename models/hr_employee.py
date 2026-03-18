from odoo import models, fields, api

class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    resignation_count = fields.Integer(compute='_compute_resignation_count')
    clearance_count = fields.Integer(compute='_compute_clearance_count')

    def _compute_resignation_count(self):
        for employee in self:
            employee.resignation_count = self.env['hr.resignation'].search_count([('employee_id', '=', employee.id)])

    def _compute_clearance_count(self):
        for employee in self:
            employee.clearance_count = self.env['hr.clearance'].search_count([('employee_id', '=', employee.id)])

    def action_view_resignations(self):
        return {
            'name': 'Resignations',
            'type': 'ir.actions.act_window',
            'res_model': 'hr.resignation',
            'view_mode': 'list,form',
            'domain': [('employee_id', '=', self.id)],
            'context': {'default_employee_id': self.id},
        }

    def action_view_clearances(self):
        return {
            'name': 'Clearances',
            'type': 'ir.actions.act_window',
            'res_model': 'hr.clearance',
            'view_mode': 'list,form',
            'domain': [('employee_id', '=', self.id)],
            'context': {'default_employee_id': self.id},
        }
