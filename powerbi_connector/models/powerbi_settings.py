from odoo import api, fields, models, _
import secrets
import requests
import logging

_logger = logging.getLogger(__name__)


class PowerBISettings(models.Model):
    _name = 'powerbi.settings'
    _description = 'Paramètres Power BI'
    _rec_name = 'name'

    name = fields.Char(string='Nom', default='Configuration Power BI', required=True)
    token = fields.Char(string='Token API', readonly=True, help='Token d\'authentification pour les requêtes API')
    allowed_models = fields.Text(
        string='Modèles autorisés',
        help='Liste des modèles Odoo autorisés (un par ligne). Exemple:\nres.partner\naccount.move\nsale.order',
        default='res.partner\naccount.move'
    )
    is_active = fields.Boolean(string='Actif', default=True, help='Activer/désactiver le connecteur')
    max_records = fields.Integer(
        string='Nombre max de records',
        default=1000,
        help='Nombre maximum d\'enregistrements retournés par requête'
    )
    created_date = fields.Datetime(string='Date de création', default=fields.Datetime.now, readonly=True)
    last_used = fields.Datetime(string='Dernière utilisation', readonly=True)

    # Azure AD / Power BI REST API
    tenant_id = fields.Char(string='Azure AD Tenant ID')
    client_id = fields.Char(string='Azure AD Client ID')
    client_secret = fields.Char(string='Azure AD Client Secret')
    default_access_level = fields.Selection(
        [('view', 'View'), ('edit', 'Edit')],
        string='Niveau d’accès par défaut',
        default='view'
    )

    def _get_aad_token(self):
        """Obtenir un jeton AAD pour l’API Power BI via client_credentials."""
        self.ensure_one()
        if not (self.tenant_id and self.client_id and self.client_secret):
            raise ValueError(_('Veuillez configurer Tenant ID, Client ID et Client Secret.'))
        token_url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        data = {
            'grant_type': 'client_credentials',
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'scope': 'https://analysis.windows.net/powerbi/api/.default',
        }
        try:
            resp = requests.post(token_url, data=data, timeout=20)
            resp.raise_for_status()
            return resp.json().get('access_token')
        except Exception as exc:
            raise ValueError(_('Echec de récupération du token AAD: %s') % exc)

    def _pbi_headers(self, aad_token):
        return {
            'Authorization': f'Bearer {aad_token}',
            'Content-Type': 'application/json',
        }

    def generate_report_embed_token(self, workspace_id, report_id, dataset_id=None, access_level=None):
        """Générer un embed token pour un rapport Power BI."""
        self.ensure_one()
        aad = self._get_aad_token()
        url = (
            f"https://api.powerbi.com/v1.0/myorg/groups/{workspace_id}/"
            f"reports/{report_id}/GenerateToken"
        )
        payload = {
            'accessLevel': (access_level or self.default_access_level or 'view').capitalize(),
        }
        if dataset_id:
            payload['datasetId'] = dataset_id
        try:
            resp = requests.post(url, json=payload, headers=self._pbi_headers(aad), timeout=20)
            resp.raise_for_status()
            return resp.json().get('token')
        except Exception as exc:
            raise ValueError(_('Echec de génération du token d’intégration: %s') % exc)

    def get_report_details(self, workspace_id, report_id):
        """Récupérer les métadonnées du rapport (embedUrl, name, id, datasetId)."""
        self.ensure_one()
        aad = self._get_aad_token()
        url = f"https://api.powerbi.com/v1.0/myorg/groups/{workspace_id}/reports/{report_id}"
        try:
            resp = requests.get(url, headers=self._pbi_headers(aad), timeout=20)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            raise ValueError(_('Echec de récupération des détails du rapport: %s') % exc)

    def action_generate_token(self):
        """Générer un nouveau token d'authentification"""
        self.ensure_one()
        new_token = secrets.token_urlsafe(32)
        self.write({'token': new_token})
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Token généré'),
                'message': _('Nouveau token généré avec succès. Copiez-le et conservez-le en sécurité.'),
                'type': 'success',
                'sticky': True,
            },
        }

    def action_test_connection(self):
        """Tester la connexion API"""
        self.ensure_one()
        if not self.token:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Erreur',
                    'message': 'Générez d\'abord un token d\'authentification.',
                    'type': 'danger',
                    'sticky': False,
                },
            }
        
        # Test de connexion Power BI
        try:
            aad_token = self._get_aad_token()
            if not aad_token:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Erreur AAD',
                        'message': 'Impossible d\'obtenir le token Azure AD. Vérifiez tenant_id, client_id et client_secret.',
                        'type': 'danger',
                        'sticky': True,
                    },
                }
            
            # Test de l'API Power BI
            workspaces = self.get_workspaces()
            workspace_count = len(workspaces) if workspaces else 0
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Test réussi',
                    'message': f'Connexion Power BI OK. {workspace_count} workspace(s) accessible(s). Token AAD: {aad_token[:10]}...',
                    'type': 'success',
                    'sticky': True,
                },
            }
            
        except Exception as exc:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Erreur Power BI',
                    'message': f'Erreur de connexion: {str(exc)}',
                    'type': 'danger',
                    'sticky': True,
                },
            }

    def action_test_aad_connection(self):
        """Tester spécifiquement la connexion Azure AD"""
        self.ensure_one()
        try:
            aad_token = self._get_aad_token()
            if aad_token:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Token AAD OK',
                        'message': f'Token Azure AD obtenu avec succès: {aad_token[:20]}...',
                        'type': 'success',
                        'sticky': True,
                    },
                }
            else:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Erreur AAD',
                        'message': 'Aucun token AAD retourné. Vérifiez les credentials.',
                        'type': 'danger',
                        'sticky': True,
                    },
                }
        except Exception as exc:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Erreur AAD',
                    'message': f'Erreur lors de l\'obtention du token AAD: {str(exc)}',
                    'type': 'danger',
                    'sticky': True,
                },
            }

    @api.model
    def get_active_settings(self):
        """Récupérer les paramètres actifs"""
        return self.search([('is_active', '=', True)], limit=1)

    @api.model
    def get_allowed_models_list(self):
        """Récupérer la liste des modèles autorisés"""
        settings = self.get_active_settings()
        if not settings:
            return []
        
        models_text = settings.allowed_models or ''
        return [model.strip() for model in models_text.split('\n') if model.strip()]

    @api.model
    def validate_token(self, provided_token):
        """Valider un token fourni"""
        settings = self.get_active_settings()
        if not settings or not settings.token:
            return False
        return provided_token == settings.token

    def update_last_used(self):
        """Mettre à jour la date de dernière utilisation"""
        self.write({'last_used': fields.Datetime.now()})

    def get_workspaces(self):
        """Récupérer la liste des workspaces accessibles"""
        self.ensure_one()
        aad = self._get_aad_token()
        url = "https://api.powerbi.com/v1.0/myorg/groups"
        try:
            resp = requests.get(url, headers=self._pbi_headers(aad), timeout=20)
            resp.raise_for_status()
            return resp.json().get('value', [])
        except Exception as exc:
            raise ValueError(_('Echec de récupération des workspaces: %s') % exc)

    def get_reports_in_workspace(self, workspace_id):
        """Récupérer la liste des rapports dans un workspace"""
        self.ensure_one()
        aad = self._get_aad_token()
        url = f"https://api.powerbi.com/v1.0/myorg/groups/{workspace_id}/reports"
        try:
            resp = requests.get(url, headers=self._pbi_headers(aad), timeout=20)
            resp.raise_for_status()
            return resp.json().get('value', [])
        except Exception as exc:
            raise ValueError(_('Echec de récupération des rapports: %s') % exc)

    def action_sync_workspaces(self):
        """Action pour synchroniser les workspaces et rapports"""
        self.ensure_one()
        try:
            workspaces = self.get_workspaces()
            if not workspaces:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Aucun workspace',
                        'message': 'Aucun workspace accessible trouvé.',
                        'type': 'warning',
                    },
                }
            
            # Créer ou mettre à jour les workspaces et rapports associés
            report_model = self.env['powerbi.report']
            workspace_model = self.env['powerbi.workspace']
            created_count = 0
            updated_count = 0
            
            for workspace in workspaces:
                workspace_id = workspace.get('id')
                workspace_name = workspace.get('name', 'Unknown')
                is_on_capacity = bool(workspace.get('isOnDedicatedCapacity'))

                # Upsert workspace
                workspace_rec = workspace_model.search([('workspace_id', '=', workspace_id)], limit=1)
                if workspace_rec:
                    workspace_rec.write({
                        'name': workspace_name,
                        'is_on_dedicated_capacity': is_on_capacity,
                        'state': 'active',
                    })
                else:
                    workspace_rec = workspace_model.create({
                        'name': workspace_name,
                        'workspace_id': workspace_id,
                        'is_on_dedicated_capacity': is_on_capacity,
                        'state': 'active',
                    })
                
                try:
                    reports = self.get_reports_in_workspace(workspace_id)
                    for report in reports:
                        report_id = report.get('id')
                        report_name = report.get('name', 'Unknown')
                        
                        # Chercher si le rapport existe déjà
                        existing_report = report_model.search([
                            ('workspace_id', '=', workspace_id),
                            ('report_id', '=', report_id)
                        ], limit=1)
                        
                        if existing_report:
                            # Mettre à jour
                            existing_report.write({
                                'name': report_name,
                                'url': report.get('embedUrl', ''),
                                'dataset_id': report.get('datasetId', ''),
                                'workspace_ref_id': workspace_rec.id,
                            })
                            updated_count += 1
                        else:
                            # Créer nouveau
                            report_model.create({
                                'name': f"{report_name} ({workspace_name})",
                                'workspace_id': workspace_id,
                                'report_id': report_id,
                                'url': report.get('embedUrl', ''),
                                'dataset_id': report.get('datasetId', ''),
                                'workspace_ref_id': workspace_rec.id,
                            })
                            created_count += 1
                            
                except Exception as exc:
                    _logger.warning(f"Erreur lors de la récupération des rapports du workspace {workspace_name}: {exc}")
                    continue
            
            message = f"Synchronisation terminée: {created_count} nouveaux rapports créés, {updated_count} mis à jour."
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Synchronisation réussie',
                    'message': message,
                    'type': 'success',
                },
            }
            
        except Exception as exc:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Erreur de synchronisation',
                    'message': str(exc),
                    'type': 'danger',
                },
            }
