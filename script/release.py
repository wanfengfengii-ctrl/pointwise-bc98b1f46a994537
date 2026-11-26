from script.catalog import EditionCatalog
from script.order import validate_script_order
from script.parse import parse_script


def release_edition(catalog: EditionCatalog, payload):
    draft = validate_script_order(parse_script(payload))
    return {'edition': catalog.create(draft).edition}
