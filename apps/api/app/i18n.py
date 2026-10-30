from app.config_loader import default_strings

BN_DIGITS = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")


def _child(node: object, part: str) -> object:
    if not isinstance(node, dict):
        return None
    if part in node:
        return node[part]
    if part.isdigit():
        return node.get(int(part))
    return None


def t(key: str, lang: str = "bn", **values: object) -> str:
    node: object = default_strings()
    for part in key.split("."):
        node = _child(node, part)
        if node is None:
            raise KeyError(f"Missing i18n key: {key}")
    if not isinstance(node, dict) or lang not in node:
        raise KeyError(f"Missing i18n language '{lang}' for key: {key}")
    return str(node[lang]).format(**values)


def to_bn_digits(text: str) -> str:
    return text.translate(BN_DIGITS)
