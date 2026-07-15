"""
escrow/apps.py
"""
from django.apps import AppConfig


class EscrowConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'escrow'
    verbose_name = 'Escrow'

    def ready(self):
        import escrow.signals  # noqa: F401
