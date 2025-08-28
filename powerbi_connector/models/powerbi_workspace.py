from odoo import models, fields, api


class PowerBIWorkspace(models.Model):
    _name = 'powerbi.workspace'
    _description = 'Workspaces Power BI'

    name = fields.Char(string='Nom du Workspace', required=True)
    workspace_id = fields.Char(string='Workspace ID', required=True, index=True)
    is_on_dedicated_capacity = fields.Boolean(string='Capacité dédiée')
    state = fields.Selection([
        ('active', 'Actif'),
        ('deleted', 'Supprimé'),
    ], string='Statut', default='active')

    report_ids = fields.One2many(
        comodel_name='powerbi.report',
        inverse_name='workspace_ref_id',
        string='Rapports'
    )

    report_count = fields.Integer(string='Nombre de rapports', compute='_compute_report_count')

    _sql_constraints = [
        ('workspace_unique', 'unique(workspace_id)', 'Workspace ID doit être unique'),
    ]

    @api.depends('report_ids')
    def _compute_report_count(self):
        for rec in self:
            rec.report_count = len(rec.report_ids)

    def action_view_reports(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Rapports',
            'res_model': 'powerbi.report',
            'view_mode': 'list,form',
            'domain': [('workspace_ref_id', '=', self.id)],
            'context': {'default_workspace_ref_id': self.id, 'default_workspace_id': self.workspace_id},
        }

