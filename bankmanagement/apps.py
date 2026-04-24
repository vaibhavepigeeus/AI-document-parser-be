from django.apps import AppConfig


class BankmanagementConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'bankmanagement'
    
    def ready(self):
        """
        Called when the app is ready.
        Starts the background scheduler for processing new files.
        """
        try:
            from bankmanagement.services.scheduler import run
            run()
        except Exception as e:
            print(f"Failed to start scheduler: {str(e)}")
