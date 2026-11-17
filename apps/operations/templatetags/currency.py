from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
from django import template

register = template.Library()

@register.filter
def cop(value):
    """Display-only COP formatting; preserve missing-price labels and Decimal precision."""
    if value is None or value == '':
        return 'Pendiente'
    try:
        number = Decimal(str(value))
        if not number.is_finite():
            return 'Pendiente'
        with localcontext() as ctx:
            ctx.prec = max(28, len(number.as_tuple().digits) + 4)
            number = number.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        return '$ ' + format(number, ',.2f').translate(str.maketrans({',': '.', '.': ','}))
    except (InvalidOperation, ValueError, TypeError):
        return str(value)
