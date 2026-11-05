import re

from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()
BOLD = re.compile(r"\*\*(.+?)\*\*")


@register.filter
def strong(text: str) -> str:
    """Turn **figure** in a template's text into <strong>, escaping everything else."""
    return mark_safe(BOLD.sub(r"<strong>\1</strong>", str(escape(text))))


@register.filter
def get_item(mapping, key):
    return mapping.get(key, ())
