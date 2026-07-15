from django import template

register = template.Library()


@register.filter
def subtract(value, arg):
    """Subtracts the arg from the value."""
    try:
        return float(value) - float(arg)
    except (ValueError, TypeError):
        return ''


@register.filter
def get_item(value, key):
    """Return an item from a dictionary-like object by key."""
    if value is None:
        return ''
    if hasattr(value, 'get'):
        return value.get(key, '')
    try:
        return value[key]
    except (KeyError, IndexError, TypeError):
        return ''
