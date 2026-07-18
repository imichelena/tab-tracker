"""Pure Jinja2 environment — bypasses Starlette Jinja2Templates cache bug."""
from jinja2 import Environment, FileSystemLoader
from pathlib import Path

TEMPLATES_DIR = Path(__file__).parent / "templates"

_jinja_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=True,
)

def _render(name: str, **context) -> str:
    template = _jinja_env.get_template(name)
    return template.render(**context)
