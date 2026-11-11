def layer_count(value):
    value = str(value or '').strip()
    known = {'两层': 2, '三层': 3, '五层': 5}
    if value in known:
        return known[value]
    number = value.removesuffix('层')
    if not number.isascii() or not number.isdigit():
        return None
    count = int(number)
    return count if 1 <= count <= 2147483647 else None


def canonical_rack_type(count):
    return {2: '两层', 3: '三层', 5: '五层'}.get(count, f'{count}层')
