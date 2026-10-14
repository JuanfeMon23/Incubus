"""Parser tolerante de la trama PDF417 de la cedula de ciudadania colombiana.

Los lectores entregan los campos de ancho fijo separados/rellenos con NUL u
otros no imprimibles. Se extrae por patron: documento (digitos con ceros a la
izquierda), apellidos y nombres (tokens alfabeticos), sexo + fecha AAAAMMDD y RH.
Validar con muestras reales de cada tipo de cedula (amarilla / digital).
"""

import re
from dataclasses import dataclass
from datetime import date

_NAME_TOKEN = re.compile(r"[A-ZÑÁÉÍÓÚÜ][A-ZÑÁÉÍÓÚÜ'\-]*(?: [A-ZÑÁÉÍÓÚÜ'\-]+)*")
_SEX_BIRTH = re.compile(
    r"(?<![A-Z0-9])([MF])((?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01]))"
)
_BLOOD = re.compile(r"(?<![A-Z])(AB|A|B|O)([+-])(?![A-Z0-9])")
_DOC = re.compile(r"(\d{6,15})")
_IGNORED_PREFIXES = ("PUBDSK",)


class CedulaParseError(ValueError):
    pass


@dataclass(frozen=True)
class CedulaData:
    document_number: str
    first_last_name: str
    second_last_name: str | None
    first_name: str
    second_name: str | None
    sex: str
    birth_date: date
    blood_type: str | None


def parse_cedula_barcode(raw: str) -> CedulaData:
    text = re.sub(r"[^\x20-\x7EñÑáéíóúÁÉÍÓÚ]+", "\n", raw).upper()
    sb = _SEX_BIRTH.search(text)
    if sb is None:
        raise CedulaParseError("No se encontro sexo y fecha de nacimiento.")
    head = text[: sb.start()]
    doc_match = None
    for m in _DOC.finditer(head):
        doc_match = m
    if doc_match is None:
        raise CedulaParseError("No se encontro el numero de documento.")
    document = doc_match.group(1).lstrip("0")
    if not document:
        raise CedulaParseError("Numero de documento invalido.")
    names = [
        t.strip()
        for t in _NAME_TOKEN.findall(head[doc_match.end() :])
        if t.strip() and not t.strip().startswith(_IGNORED_PREFIXES)
    ]
    if len(names) < 2:
        raise CedulaParseError("No se encontraron apellidos y nombres.")
    birth = sb.group(2)
    tail = text[sb.end() :]
    blood = _BLOOD.search(tail)
    first_last = names[0]
    # 2 tokens: apellido + nombre; 3: + segundo apellido; 4: completo.
    if len(names) == 2:
        second_last, first, second = None, names[1], None
    elif len(names) == 3:
        second_last, first, second = names[1], names[2], None
    else:
        second_last, first, second = names[1], names[2], names[3]
    try:
        birth_date = date(int(birth[:4]), int(birth[4:6]), int(birth[6:]))
    except ValueError as exc:
        raise CedulaParseError("Fecha de nacimiento invalida.") from exc
    return CedulaData(
        document_number=document,
        first_last_name=first_last,
        second_last_name=second_last,
        first_name=first,
        second_name=second,
        sex=sb.group(1),
        birth_date=birth_date,
        blood_type=f"{blood.group(1)}{blood.group(2)}" if blood else None,
    )
