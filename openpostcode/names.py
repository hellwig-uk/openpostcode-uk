"""Display-name and postcode normalisation."""


def is_blank(value):
    if value is None:
        return True
    try:
        import pandas as pd

        if pd.isna(value):
            return True
    except TypeError, ValueError:
        pass
    return str(value).strip() == ""


def text_or_none(value):
    if is_blank(value):
        return None
    return str(value).strip()


def pick_bilingual(primary, secondary):
    second = text_or_none(secondary)
    if second is not None:
        return second
    return text_or_none(primary)


def road_label(name_1, name_2, classification_number):
    name = pick_bilingual(name_1, name_2)
    if name is not None:
        return name, 0
    number = text_or_none(classification_number)
    if number is not None:
        return number, 0
    return "unnamed", 1


def place_label(name1, name2):
    name = pick_bilingual(name1, name2)
    if name is None:
        return "unnamed"
    return name


def normalise_postcode(value):
    return "".join(str(value).split()).upper()
