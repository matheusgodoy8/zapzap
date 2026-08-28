"""Tests for checkout launcher target selection."""

from pathlib import Path
import sys
import unittest
from unittest.mock import patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

import run


class RunEntrypointTests(unittest.TestCase):
    def test_default_target_is_local_and_forwards_arguments(self):
        with (
            patch.object(run.sys, "argv", ["run.py", "--hideStart"]),
            patch.object(run, "local", return_value=17) as local,
            patch.object(run, "flatpak") as flatpak,
        ):
            result = run.main()

        self.assertEqual(result, 17)
        local.assert_called_once_with(["--hideStart"])
        flatpak.assert_not_called()

    def test_flatpak_target_must_be_requested_explicitly(self):
        with (
            patch.object(
                run.sys,
                "argv",
                ["run.py", "--flatpak", "--hideStart"],
            ),
            patch.object(run, "local") as local,
            patch.object(run, "flatpak", return_value=23) as flatpak,
        ):
            result = run.main()

        self.assertEqual(result, 23)
        flatpak.assert_called_once_with(["--hideStart"])
        local.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
