import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from main import _load_az_env, _parse_args


class TestMain(unittest.TestCase):
    def test_parse_args_accepts_project_path_and_resume(self):
        args = _parse_args(
            ["--resume", "019e688c-77a0-7d4a-8f50-0a8a0cddd48b", "--project-path", "."]
        )

        self.assertEqual(args.resume, "019e688c-77a0-7d4a-8f50-0a8a0cddd48b")
        self.assertEqual(args.project_path, ".")

    def test_parse_args_defaults_project_path_to_none(self):
        args = _parse_args([])

        self.assertIsNone(args.project_path)

    def test_parse_args_accepts_az_home(self):
        args = _parse_args(["--az-home", "/tmp/az-home"])

        self.assertEqual(args.az_home, "/tmp/az-home")

    def test_parse_args_supports_web_mode(self):
        args = _parse_args(["web", "--host", "0.0.0.0", "--port", "8080"])

        self.assertEqual(args.mode, "web")
        self.assertEqual(args.host, "0.0.0.0")
        self.assertEqual(args.port, 8080)

    def test_load_az_env_reads_env_from_selected_home(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            az_home = Path(temp_dir)
            (az_home / ".env").write_text(
                "DEEPSEEK_API_KEY=test-key\nAZ_HOME=/ignored-home\n",
                encoding="utf-8",
            )

            with patch.dict(os.environ, {}, clear=True):
                loaded_home = _load_az_env(str(az_home))

                self.assertEqual(loaded_home, az_home.resolve())
                self.assertEqual(os.environ["DEEPSEEK_API_KEY"], "test-key")
                self.assertEqual(os.environ["AZ_HOME"], str(az_home.resolve()))


if __name__ == "__main__":
    unittest.main()
