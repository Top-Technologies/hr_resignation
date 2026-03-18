{
    'name': 'Employee Resignation & Clearance Management',
    'version': '18.0.1.0.0',
    'summary': 'Manage Employee Resignation and Clearance Process',
    'description': """
        Employee Resignation & Clearance Management
        ===========================================
        - Employee Resignation Request
        - Approval Workflow (Manager -> HR)
        - Automatic Clearance Process
        - Clearance Checklists (IT, Finance, Admin, etc.)
        - Asset Return Tracking
        - Exit Handling
    """,
    'category': 'Human Resources',
    'author': 'Top Technologies',
    'depends': ['hr', 'mail', 'hr_contract', 'maintenance', 'approvals'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'security/record_rules.xml',
        'data/approval_category_data.xml',
        'views/hr_resignation_views.xml',
        'reports/hr_clearance_report.xml',
        'views/hr_clearance_views.xml',
        'views/hr_employee_views.xml',
<<<<<<< HEAD
=======
        'data/clearance_checklist_data.xml',
>>>>>>> origin/main
    ],
    'assets': {
        'web.assets_backend': [
            'hr_resignation/static/src/js/notification_sound.js',
        ],
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
