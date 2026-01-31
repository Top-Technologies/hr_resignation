from odoo import models, fields, api, _

class ApprovalRequest(models.Model):
    _inherit = 'approval.request'

    def action_approve(self, approver=None):
        res = super(ApprovalRequest, self).action_approve(approver)
        # Check if this request is linked to a resignation
        # Since we don't have a direct back-link field on approval.request unless we add one (which is cleaner),
        # or we search. Searching is safer if we want to avoid modifying approval.request schema too much,
        # BUT adding a field is better for performance.
        # Let's search for now to minimize intrusion, or rely on the category name?
        # A better approach: The user wants integration. 
        # Search is fine since resignation volume is low.
        
        for request in self:
            resignation = self.env['hr.resignation'].search([('approval_request_id', '=', request.id)], limit=1)
            if resignation:
                if request.request_status == 'approved':
                    # Final Approval (Assumed to be HR or final step)
                    resignation.action_approve()
                else:
                    # Check for intermediate Manager approval
                    # We check if the manager is in the list of approvers who have approved
                    manager_user = resignation.manager_id.user_id
                    if manager_user:
                        is_manager_approved = any(
                            approver.user_id == manager_user and approver.status == 'approved'
                            for approver in request.approver_ids
                        )
                        if is_manager_approved and resignation.state == 'submitted':
                            resignation.write({'state': 'approved_manager'})
        return res

    def action_refuse(self, approver=None):
        res = super(ApprovalRequest, self).action_refuse(approver)
        for request in self:
            if request.request_status == 'refused':
                 resignation = self.env['hr.resignation'].search([('approval_request_id', '=', request.id)], limit=1)
                 if resignation:
                     resignation.action_reject()
        return res
