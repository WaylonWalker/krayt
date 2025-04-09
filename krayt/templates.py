from jinja2 import Environment, FileSystemLoader
from pathlib import Path

# Get the two template directories
template_dirs = [
    Path(__file__).resolve().parents[0] / "templates",
    Path.home() / ".config" / "krayt" / "templates",
]

# Create the Jinja environment
env = Environment(loader=FileSystemLoader([str(path) for path in template_dirs]))
