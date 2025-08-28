{
    'name': 'Power BI Connector',
    'version': '18.0.1.0.0',
    'summary': 'Connecteur Odoo pour Power BI - API sécurisée',
    'description': """
        Module pour exposer les données Odoo via une API sécurisée pour Power BI.
        Fonctionnalités:
        - Génération de tokens d'authentification
        - Configuration des modèles autorisés
        - Endpoints API REST sécurisés
        - Interface d'administration
    """,
    'author': 'Votre Nom',
    'website': 'https://example.com',
    'category': 'Tools',
    'license': 'LGPL-3',
    'depends': ['base', 'web'],
    'data': [
        'security/powerbi_security.xml',
        'security/ir.model.access.csv',
        'views/powerbi_views.xml',
        'views/powerbi_report_views.xml',
        'views/powerbi_workspace_views.xml',
    ],
    'images': ['static/description/icon.svg'],
    'application': True,
    'installable': True,
    'auto_install': False,
}
