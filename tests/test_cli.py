import contextlib
import io
import unittest
from unittest.mock import patch

import nex2polytomous as app


class CommandLineTests(unittest.TestCase):
    def test_main_uses_nexus_file_argument(self):
        with patch.object(
            app,
            "parse_nexus_to_dataframe",
            return_value=(None, None, None),
        ) as parse_nexus, contextlib.redirect_stdout(io.StringIO()):
            app.main(["custom.nex"])

        parse_nexus.assert_called_once_with("custom.nex")

    def test_main_uses_default_nexus_file_without_argument(self):
        with patch.object(
            app,
            "parse_nexus_to_dataframe",
            return_value=(None, None, None),
        ) as parse_nexus, contextlib.redirect_stdout(io.StringIO()):
            app.main([])

        parse_nexus.assert_called_once_with(app.NEXUS_FILE_PATH)


if __name__ == "__main__":
    unittest.main()
