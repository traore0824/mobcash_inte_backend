from django.apps import AppConfig


class MobcashInteConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'mobcash_inte'
    def ready(self):
        import mobcash_inte.signals
