from django import template

register = template.Library()

@register.filter
def peso(value):
    try:
        return "₱{:,.2f}".format(float(value))
    except (ValueError, TypeError):
        return value


@register.filter
def inventory_unit(unit):
    return 'L' if unit == 'ml' else unit


@register.filter
def inventory_quantity(value, unit):
    try:
        quantity = float(value)
    except (ValueError, TypeError):
        return value
    if unit == 'ml':
        quantity = quantity / 1000
    return f"{quantity:,.0f}"
