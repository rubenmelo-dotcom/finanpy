from django import template
from django.template.defaultfilters import floatformat

register = template.Library()


@register.filter
def currency(value):
    """Format a value as BRL, with the minus sign before the symbol."""
    if value in (None, ''):
        return ''
    formatted = f'R$\u00a0{floatformat(abs(value), 2)}'
    return f'−{formatted}' if value < 0 else formatted
