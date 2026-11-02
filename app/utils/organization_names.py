import unicodedata


def organization_key(value):
    return " ".join(unicodedata.normalize("NFC", value).split()).casefold()


def compare_organization_names(left, right):
    left, right = organization_key(left), organization_key(right)
    return (left > right) - (left < right)
