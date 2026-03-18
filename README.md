# Employee Resignation & Clearance Management

**Version**: 18.0.1.0.0  
**Category**: Human Resources  
**Author**: Top Technologies  
**License**: LGPL-3

## Overview

This module provides a comprehensive solution for managing employee resignations and the subsequent clearance process within Odoo. It streamlines the workflow from the initial resignation request to the final exit interview and asset return.

## Features

- **Resignation Request Management**: Allows employees to submit resignation requests which are then tracked through the system.
- **Approval Workflow**: Configurable approval workflow involving Line Managers and HR Officers.
- **Automated Clearance Process**: Automatically triggers a clearance process upon acceptance of resignation.
- **Departmental Checklists**: Supports clearance checklists for various departments (e.g., IT, Finance, Administration) to ensure all dues are cleared and assets are returned.
- **Asset Return Tracking**: Integration with maintenance/asset management to track returned items.
- **Exit Process**: Formalizes the employee exit process.

## Dependencies

This module depends on the following Odoo modules:
- `hr` (Employees)
- `mail` (Discuss)
- `hr_contract` (Contracts)
- `maintenance` (Maintenance)
- `approvals` (Approvals)

## Installation

1. Place the `hr_resignation` user module in your Odoo addons path.
2. Restart the Odoo service.
3. Go to **Apps**, click **Update Apps List**.
4. Search for "Employee Resignation & Clearance Management" and click **Activate**.

## Usage

### 1. Submitting a Resignation
Employees can create a new resignation request via the Resignation menu. The request includes details such as the reason for resignation and the expected last day.

### 2. Approval Process
- The request is first submitted for review.
- It requires approval from the employee's manager and the HR department.
- Approvals can be managed via the standard Odoo approvals app integration or the custom workflow buttons.

### 3. Clearance Process
Once the resignation is approved:
- A clearance record is generated.
- Relevant departments are notified to complete their specific clearance checklists (e.g., collecting laptops, settling accounts).
- The final clearance status is updated once all checklists are completed.
