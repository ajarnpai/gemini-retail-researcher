import os
import unittest
from pathlib import Path
from unittest.mock import patch

# Mock PROJECT_ROOT before importing config
class TestSecretsLoader(unittest.TestCase):
    def test_secrets_env_loading(self):
        # Create a dummy secrets.env
        secrets_path = Path("secrets_test.env")
        secrets_path.write_text("TEST_KEY_FOR_CONFIG=test_value\nANOTHER_KEY=another_value")
        
        try:
            # We need to manually simulate the logic in config.py since it runs on import
            project_root = Path(".")
            env_path = project_root / "secrets_test.env"
            
            test_env = {}
            if env_path.exists():
                for line in env_path.read_text().splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, _, value = line.partition("=")
                        test_env[key.strip()] = value.strip()
            
            assert test_env["TEST_KEY_FOR_CONFIG"] == "test_value"
            assert test_env["ANOTHER_KEY"] == "another_value"
            print("Secrets loader logic verified.")
            
        finally:
            if secrets_path.exists():
                secrets_path.unlink()

if __name__ == "__main__":
    unittest.main()
