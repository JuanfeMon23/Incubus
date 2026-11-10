from pydantic import BaseModel


class CatalogItem(BaseModel):
    """Elemento de un catalogo de categoria. Las columnas propias de cada catalogo
    (`is_terminal`, `variant`, `show_in_report`, `category`) solo salen en el suyo."""

    code: str
    name: str
    sort_order: int
    is_active: bool = True
    is_terminal: bool | None = None  # queue-statuses
    variant: str | None = None  # result-flags: success | warning | danger
    show_in_report: bool | None = None  # result-flags
    category: str | None = None  # trace-steps
