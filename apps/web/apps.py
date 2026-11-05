from django.apps import AppConfig


class WebConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.web"
    label = "web"
    verbose_name = "Public site"

    def ready(self):
        from django.db.models.signals import post_delete, post_save

        from apps.content import models as content

        from .caching import bump

        def changed(**kwargs):
            bump()

        watched = (
            content.Override,
            content.Template,
            content.CustomBlock,
            content.AnalystTarget,
            content.Page,
            content.Comparison,
            content.Reviewer,
            content.ReviewerBio,
        )
        for model in watched:
            post_save.connect(changed, sender=model, weak=False, dispatch_uid=f"bump-save-{model.__name__}")
            post_delete.connect(changed, sender=model, weak=False, dispatch_uid=f"bump-delete-{model.__name__}")
