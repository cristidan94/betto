from __future__ import annotations

import unittest
from unittest.mock import patch

from core.vendor import should_use_vendor


class VendorTests(unittest.TestCase):
    def test_vendor_is_default_on_windows(self) -> None:
        with patch("core.vendor.sys.platform", "win32"), patch.dict("core.vendor.os.environ", {}, clear=True):
            self.assertTrue(should_use_vendor())

    def test_vendor_is_opt_in_on_linux(self) -> None:
        with patch("core.vendor.sys.platform", "linux"), patch.dict("core.vendor.os.environ", {}, clear=True):
            self.assertFalse(should_use_vendor())

    def test_vendor_dir_env_enables_vendor_on_linux(self) -> None:
        with patch("core.vendor.sys.platform", "linux"), patch.dict("core.vendor.os.environ", {"BETTO_VENDOR_DIR": "/tmp/vendor"}, clear=True):
            self.assertTrue(should_use_vendor())


if __name__ == "__main__":
    unittest.main()
