"""App settings: paths and config."""
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# User places inventory CSV here; default to example if not present
INVENTORY_PATH = os.environ.get("PERGEN_INVENTORY_PATH") or os.path.join(
    BASE_DIR, "inventory", "inventory.csv"
)
EXAMPLE_INVENTORY_PATH = os.path.join(BASE_DIR, "inventory", "example_inventory.csv")
INSTANCE_DIR = os.environ.get("PERGEN_INSTANCE_DIR") or os.path.join(BASE_DIR, "instance")
os.makedirs(INSTANCE_DIR, exist_ok=True)
