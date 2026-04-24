from django.apps import AppConfig
import os


class BankmanagementConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'bankmanagement'
    
    def ready(self):
        from .scheduler import run
        run()
