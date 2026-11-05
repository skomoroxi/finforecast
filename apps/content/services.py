"""All writes to templates and manual values, so every one lands in the history."""

from django.db import transaction

from .models import Draft, Override, Revision, Template


@transaction.atomic
def save_template(asset_class, language, field, body, user=None, note="") -> Template:
    template, _ = Template.objects.update_or_create(
        asset_class=asset_class, language=language, field=field, defaults={"body": body}
    )
    Revision.objects.create(
        kind=Revision.Kind.TEMPLATE,
        asset_class=asset_class,
        language=language,
        field=field,
        value=body,
        user=user,
        note=note,
    )
    return template


@transaction.atomic
def save_override(asset, language, field, value, user=None, note="") -> Override:
    override, _ = Override.objects.update_or_create(
        asset=asset, language=language, field=field, defaults={"value": value, "updated_by": user}
    )
    Revision.objects.create(
        kind=Revision.Kind.OVERRIDE, asset=asset, language=language, field=field, value=value, user=user, note=note
    )
    return override


@transaction.atomic
def reset_override(override: Override, user=None) -> None:
    """Back to the template. The history keeps the value that was removed."""
    Revision.objects.create(
        kind=Revision.Kind.OVERRIDE,
        asset=override.asset,
        language=override.language,
        field=override.field,
        value=override.value,
        removed=True,
        user=user,
        note="reset to template",
    )
    override.delete()


def roll_back(revision: Revision, user=None) -> None:
    note = f"rollback to {revision.created_at:%Y-%m-%d %H:%M}"
    if revision.kind == Revision.Kind.TEMPLATE:
        save_template(revision.asset_class, revision.language, revision.field, revision.value, user, note)
    else:
        save_override(revision.asset, revision.language, revision.field, revision.value, user, note)


@transaction.atomic
def approve_draft(draft: Draft, user=None) -> Override:
    """A reviewed draft becomes an ordinary manual value."""
    override = save_override(
        draft.asset, draft.language, draft.field, draft.value, user, f"AI draft, {draft.model_name}"
    )
    draft.delete()
    return override
