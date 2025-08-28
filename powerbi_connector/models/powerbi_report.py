from odoo import models, fields


class PowerBIReport(models.Model):
    _name = 'powerbi.report'
    _description = 'Rapports Power BI intégrés'

    name = fields.Char(string="Nom du Rapport", required=True)
    url = fields.Char(string="Lien Power BI (embed)", required=True)
    workspace_id = fields.Char(string="Workspace ID")
    workspace_ref_id = fields.Many2one(
        comodel_name='powerbi.workspace',
        string='Workspace',
        ondelete='set null',
        index=True,
    )
    report_id = fields.Char(string="Report ID")
    dataset_id = fields.Char(string="Dataset ID")
    embed_html = fields.Html(
        string="Aperçu",
        compute="_compute_embed_html",
     
        sanitize=False,
        readonly=True,
    )

    def action_open_viewer(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': self.url or '',
            'target': 'new',
        }

    def _compute_embed_html(self):
        for record in self:
            if record.url:
                # Render an iframe using the provided embed URL
                record.embed_html = (
                    f"<div style=\"width:100%; height:800px;\">"
                    f"<iframe title=\"Power BI Report\" width=\"100%\" height=\"100%\" "
                    f"src=\"{record.url}\" frameborder=\"0\" allow=\"clipboard-write; autoplay 'none'\" allowfullscreen=\"true\"></iframe>"
                    f"</div>"
                )
            else:
                record.embed_html = ""

    def action_sync_from_powerbi(self):
        """Récupère les métadonnées (embedUrl, datasetId) depuis Power BI pour ce rapport.
        Requiert un enregistrement actif dans `powerbi.settings` avec credentials AAD.
        """
        self.ensure_one()
        settings = self.env['powerbi.settings'].get_active_settings()
        if not settings:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Configuration manquante',
                    'message': "Aucune configuration Power BI active trouvée.",
                    'type': 'danger',
                },
            }
        if not (self.workspace_id and self.report_id):
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Champs requis',
                    'message': "Renseignez Workspace ID et Report ID, puis relancez la synchronisation.",
                    'type': 'warning',
                },
            }

        try:
            details = settings.get_report_details(self.workspace_id, self.report_id)
            embed_url = details.get('embedUrl') or details.get('webUrl') or ''
            dataset_id = details.get('datasetId') or ''
            vals = {
                'url': embed_url or self.url,
                'dataset_id': dataset_id or self.dataset_id,
                'name': details.get('name') or self.name,
            }
            self.write(vals)
            # Recompute preview html
            self._compute_embed_html()
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Synchronisation réussie',
                    'message': 'Les métadonnées du rapport ont été mises à jour.',
                    'type': 'success',
                },
            }
        except Exception as exc:  # pragma: no cover
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Erreur Power BI',
                    'message': str(exc),
                    'type': 'danger',
                },
            }
