import json
import logging
from datetime import datetime

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class PowerBIController(http.Controller):
    """Contrôleur pour l'API Power BI"""

    def _get_token_from_request(self):
        """Récupérer le token depuis la requête (header ou paramètre)"""
        # Vérifier dans les en-têtes HTTP
        token = request.httprequest.headers.get('X-PowerBI-Token')
        if not token:
            # Vérifier dans les paramètres d'URL
            token = request.httprequest.args.get('token')
        return token

    def _validate_request(self):
        """Valider la requête (token et configuration active)"""
        # Récupérer le token
        token = self._get_token_from_request()
        if not token:
            return False, "Token manquant. Utilisez l'en-tête X-PowerBI-Token ou le paramètre ?token="
        
        # Valider le token
        if not request.env['powerbi.settings'].sudo().validate_token(token):
            return False, "Token invalide"
        
        # Vérifier qu'une configuration active existe
        settings = request.env['powerbi.settings'].sudo().get_active_settings()
        if not settings:
            return False, "Aucune configuration Power BI active"
        
        return True, settings

    def _format_response(self, success=True, data=None, message="", status_code=200):
        """Formater la réponse JSON"""
        response_data = {
            "success": success,
            "timestamp": datetime.now().isoformat(),
            "message": message
        }
        
        if data is not None:
            response_data["data"] = data
        
        response = request.make_response(
            json.dumps(response_data, ensure_ascii=False, default=str),
            [('Content-Type', 'application/json; charset=utf-8')]
        )
        response.status_code = status_code
        return response

    @http.route('/powerbi/api/health', type='http', auth='public', methods=['GET'], csrf=False)
    def health_check(self, **kwargs):
        """Endpoint de vérification de santé de l'API"""
        try:
            is_valid, result = self._validate_request()
            if is_valid:
                return self._format_response(
                    success=True,
                    data={"status": "healthy", "version": "1.0"},
                    message="API Power BI opérationnelle"
                )
            else:
                return self._format_response(
                    success=False,
                    message=result,
                    status_code=401
                )
        except Exception as e:
            _logger.error(f"Erreur health check: {str(e)}")
            return self._format_response(
                success=False,
                message="Erreur interne du serveur",
                status_code=500
            )

    @http.route('/powerbi/api/models', type='http', auth='public', methods=['GET'], csrf=False)
    def list_models(self, **kwargs):
        """Lister les modèles autorisés"""
        try:
            is_valid, result = self._validate_request()
            if not is_valid:
                return self._format_response(
                    success=False,
                    message=result,
                    status_code=401
                )
            
            settings = result
            allowed_models = settings.get_allowed_models_list()
            
            # Mettre à jour la dernière utilisation
            settings.update_last_used()
            
            return self._format_response(
                success=True,
                data={
                    "models": allowed_models,
                    "count": len(allowed_models)
                },
                message=f"{len(allowed_models)} modèles autorisés"
            )
            
        except Exception as e:
            _logger.error(f"Erreur list_models: {str(e)}")
            return self._format_response(
                success=False,
                message="Erreur lors de la récupération des modèles",
                status_code=500
            )

    @http.route('/powerbi/embed_config/<int:report_rec_id>', type='json', auth='user', methods=['POST'], csrf=False)
    def get_embed_config(self, report_rec_id, **kwargs):
        """Retourner la config d’intégration (embedUrl, embedToken, reportId)."""
        report = request.env['powerbi.report'].sudo().browse(report_rec_id)
        if not report.exists():
            return {'error': 'report_not_found'}
        settings = request.env['powerbi.settings'].sudo().get_active_settings()
        if not settings:
            return {'error': 'no_active_settings'}
        try:
            details = settings.get_report_details(report.workspace_id, report.report_id)
            embed_token = settings.generate_report_embed_token(
                report.workspace_id,
                report.report_id,
                dataset_id=report.dataset_id or details.get('datasetId'),
                access_level=report.access_level or settings.default_access_level or 'view',
            )
            return {
                'reportId': details.get('id') or report.report_id,
                'embedUrl': details.get('embedUrl'),
                'embedToken': embed_token,
                'name': details.get('name') or report.name,
            }
        except Exception as exc:
            _logger.error('Embed config error: %s', exc)
            return {'error': 'embed_error', 'message': str(exc)}

    @http.route('/powerbi/view/<int:report_rec_id>', type='http', auth='user', website=False, csrf=False)
    def view_report(self, report_rec_id, **kwargs):
        """Page simple qui embarque le rapport via powerbi-client."""
        html = f"""
<!DOCTYPE html>
<html>
  <head>
    <meta charset=\"utf-8\"/>
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"/>
    <title>Power BI</title>
    <script src=\"https://cdn.jsdelivr.net/npm/powerbi-client@2.23.1/dist/powerbi.min.js\"></script>
    <style>
      html, body, #reportContainer {{ height: 100%; width: 100%; margin: 0; }}
    </style>
  </head>
  <body>
    <div id=\"reportContainer\"></div>
    <script>
      async function load() {{
        const resp = await fetch('/powerbi/embed_config/{report_rec_id}', {{ method: 'POST', headers: {{'Content-Type': 'application/json'}}, credentials: 'same-origin' }});
        const cfg = await resp.json();
        if (cfg.error) {{
          document.body.innerHTML = '<pre style="padding:16px;color:#b00">'+ (cfg.message || cfg.error) +'</pre>';
          return;
        }}
        const models = window['powerbi-client'].models;
        const embedConfig = {{
          type: 'report',
          id: cfg.reportId,
          embedUrl: cfg.embedUrl,
          accessToken: cfg.embedToken,
          tokenType: models.TokenType.Embed,
          settings: {{ panes: {{ filters: {{ visible: false }} }}, navContentPaneEnabled: true }}
        }};
        const container = document.getElementById('reportContainer');
        powerbi.reset(container);
        powerbi.embed(container, embedConfig);
      }}
      load();
    </script>
  </body>
</html>
        """
        return request.make_response(html, headers=[('Content-Type', 'text/html; charset=utf-8')])

    @http.route('/powerbi/api/<string:model_name>', type='http', auth='public', methods=['GET'], csrf=False)
    def get_model_data(self, model_name, **kwargs):
        """Récupérer les données d'un modèle spécifique"""
        try:
            is_valid, result = self._validate_request()
            if not is_valid:
                return self._format_response(
                    success=False,
                    message=result,
                    status_code=401
                )
            
            settings = result
            
            # Vérifier que le modèle est autorisé
            allowed_models = settings.get_allowed_models_list()
            if model_name not in allowed_models:
                return self._format_response(
                    success=False,
                    message=f"Modèle '{model_name}' non autorisé",
                    status_code=403
                )
            
            # Récupérer les paramètres de la requête
            fields_param = kwargs.get('fields', '')
            domain_param = kwargs.get('domain', '[]')
            limit_param = kwargs.get('limit', settings.max_records)
            offset_param = kwargs.get('offset', 0)
            order_param = kwargs.get('order', 'id')
            
            try:
                # Parser les champs
                fields_list = []
                if fields_param:
                    fields_list = [f.strip() for f in fields_param.split(',') if f.strip()]
                
                # Parser le domaine
                domain = []
                if domain_param and domain_param != '[]':
                    try:
                        domain = json.loads(domain_param)
                    except json.JSONDecodeError:
                        return self._format_response(
                            success=False,
                            message="Format de domaine invalide (JSON requis)",
                            status_code=400
                        )
                
                # Parser les limites
                limit = min(int(limit_param), settings.max_records) if limit_param else settings.max_records
                offset = int(offset_param) if offset_param else 0
                
                # Récupérer les données
                model_env = request.env[model_name].sudo()
                records = model_env.search_read(
                    domain=domain,
                    fields=fields_list,
                    limit=limit,
                    offset=offset,
                    order=order_param
                )
                
                # Mettre à jour la dernière utilisation
                settings.update_last_used()
                
                return self._format_response(
                    success=True,
                    data={
                        "model": model_name,
                        "records": records,
                        "count": len(records),
                        "total_count": model_env.search_count(domain),
                        "limit": limit,
                        "offset": offset
                    },
                    message=f"{len(records)} enregistrements récupérés"
                )
                
            except Exception as e:
                _logger.error(f"Erreur lors de la récupération des données: {str(e)}")
                return self._format_response(
                    success=False,
                    message=f"Erreur lors de la récupération des données: {str(e)}",
                    status_code=400
                )
                
        except Exception as e:
            _logger.error(f"Erreur get_model_data: {str(e)}")
            return self._format_response(
                success=False,
                message="Erreur interne du serveur",
                status_code=500
            )

    @http.route('/powerbi/api/<string:model_name>/<int:record_id>', type='http', auth='public', methods=['GET'], csrf=False)
    def get_record(self, model_name, record_id, **kwargs):
        """Récupérer un enregistrement spécifique"""
        try:
            is_valid, result = self._validate_request()
            if not is_valid:
                return self._format_response(
                    success=False,
                    message=result,
                    status_code=401
                )
            
            settings = result
            
            # Vérifier que le modèle est autorisé
            allowed_models = settings.get_allowed_models_list()
            if model_name not in allowed_models:
                return self._format_response(
                    success=False,
                    message=f"Modèle '{model_name}' non autorisé",
                    status_code=403
                )
            
            # Récupérer les champs demandés
            fields_param = kwargs.get('fields', '')
            fields_list = []
            if fields_param:
                fields_list = [f.strip() for f in fields_param.split(',') if f.strip()]
            
            # Récupérer l'enregistrement
            model_env = request.env[model_name].sudo()
            record = model_env.browse(record_id)
            
            if not record.exists():
                return self._format_response(
                    success=False,
                    message=f"Enregistrement {record_id} non trouvé",
                    status_code=404
                )
            
            # Convertir en dictionnaire
            record_data = record.read(fields_list)[0] if fields_list else record.read()[0]
            
            # Mettre à jour la dernière utilisation
            settings.update_last_used()
            
            return self._format_response(
                success=True,
                data={
                    "model": model_name,
                    "record": record_data
                },
                message="Enregistrement récupéré avec succès"
            )
            
        except Exception as e:
            _logger.error(f"Erreur get_record: {str(e)}")
            return self._format_response(
                success=False,
                message="Erreur interne du serveur",
                status_code=500
            )
