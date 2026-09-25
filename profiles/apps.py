from django.apps import AppConfig


class ProfilesConfig(AppConfig):
    name = 'profiles'
    verbose_name = 'Perfis'

    def ready(self):
        import profiles.signals  # noqa: F401
