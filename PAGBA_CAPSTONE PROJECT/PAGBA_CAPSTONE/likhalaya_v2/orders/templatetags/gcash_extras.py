from django import template

register = template.Library()


@register.filter
def mask_gcash_name(value):
    """Displays a GCash account name as "First Last" — first name shown in
    full, last name shown as just its first letter plus a single asterisk
    (any middle names in between are dropped from the display entirely).

    "Deniel Bryan Perea" -> "Deniel P*"
    "Pedro Penduko"      -> "Pedro P*"
    "Cher"               -> "Cher" (nothing to mask with just one word)
    """
    if not value:
        return ''

    words = [w for w in value.split(' ') if w]
    if len(words) < 2:
        return value.strip()

    first_name = words[0]
    last_name = words[-1]

    trailing = ''
    core = last_name
    while core and not core[-1].isalnum():
        trailing = core[-1] + trailing
        core = core[:-1]

    if not core:
        return f"{first_name} {last_name}"

    masked_last = core[0] + '*' + trailing
    return f"{first_name} {masked_last}"