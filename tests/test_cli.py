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

        parse_nexus.assert_called_once_with(
            "custom.nex",
            species_selector=app.prompt_species_selection,
        )

    def test_main_uses_default_nexus_file_without_argument(self):
        with patch.object(
            app,
            "parse_nexus_to_dataframe",
            return_value=(None, None, None),
        ) as parse_nexus, contextlib.redirect_stdout(io.StringIO()):
            app.main([])

        parse_nexus.assert_called_once_with(
            app.NEXUS_FILE_PATH,
            species_selector=app.prompt_species_selection,
        )

    def test_species_prompt_defaults_to_all_species(self):
        output = []

        selected = app.prompt_species_selection(
            ["Species A", "Species B"],
            input_fn=lambda _prompt: "",
            output_fn=output.append,
        )

        self.assertEqual(["Species A", "Species B"], selected)
        self.assertIn("已選擇全部 2 個物種。", output)

    def test_species_prompt_accepts_selected_numbers_after_invalid_input(self):
        answers = iter(["1,1", "1，3"])
        output = []

        selected = app.prompt_species_selection(
            ["Species A", "Species B", "Species C"],
            input_fn=lambda _prompt: next(answers),
            output_fn=output.append,
        )

        self.assertEqual(["Species A", "Species C"], selected)
        self.assertIn("物種序號不可重複，請重新輸入。", output)

    def test_species_prompt_expands_continuous_ranges(self):
        species = [f"Species {number}" for number in range(1, 13)]

        selected = app.prompt_species_selection(
            species,
            input_fn=lambda _prompt: "1,3-9,12",
            output_fn=lambda _message: None,
        )

        self.assertEqual(
            [
                "Species 1",
                "Species 3",
                "Species 4",
                "Species 5",
                "Species 6",
                "Species 7",
                "Species 8",
                "Species 9",
                "Species 12",
            ],
            selected,
        )

    def test_species_prompt_rejects_descending_ranges(self):
        answers = iter(["9-3", "2"])
        output = []

        selected = app.prompt_species_selection(
            ["Species A", "Species B", "Species C"],
            input_fn=lambda _prompt: next(answers),
            output_fn=output.append,
        )

        self.assertEqual(["Species B"], selected)
        self.assertTrue(any("輸入格式錯誤" in message for message in output))


if __name__ == "__main__":
    unittest.main()
