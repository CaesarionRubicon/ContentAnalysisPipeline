# tests/conftest.py
import sys
import os

# Add project root (one level up from tests/) to Python path
root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if root not in sys.path:
    sys.path.insert(0, root)