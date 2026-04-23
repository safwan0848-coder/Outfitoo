from django.apps import AppConfig

class WalletConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'user_side.wallet'

    def ready(self):
        import user_side.wallet.signals  # noqa: F401