import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import nex2polytomous as app


class CommandLineTests(unittest.TestCase):
    def test_main_writes_selected_format_and_defaults_to_markdown(self):
        df = app.pd.DataFrame({"Feature": [0, 1]}, index=["Species A", "Species B"])
        cases = [
            ([], "md", "| 編號 | 特徵 | 狀態 | 結果 |"),
            (["-f", "table"], "md", "| 編號 | 特徵 | 狀態 | 結果 |"),
            (["-f", "indented"], "md", "1a. Feature：狀態為 0"),
            (["--output-format", "html-table"], "html", "<table>"),
            (["-f", "html-table"], "html", "<table>"),
            (["--notes"], "md", "| 編號 | 特徵 | 狀態 | 註解 | 結果 |"),
            (["-n"], "md", "| 編號 | 特徵 | 狀態 | 註解 | 結果 |"),
            (["-f", "html-table", "--notes"], "html", "<th>狀態</th><th>註解</th><th>結果</th>"),
            (["-f", "html-table", "-n"], "html", "<th>狀態</th><th>註解</th><th>結果</th>"),
            (["-f", "indented", "--notes"], "md", "1a. Feature：狀態為 0"),
            (["-f", "indented", "-n"], "md", "1a. Feature：狀態為 0"),
        ]
        for argv, extension, expected in cases:
            with self.subTest(argv=argv), tempfile.TemporaryDirectory() as directory:
                md_path = Path(directory) / "generated" / "key.md"
                html_path = md_path.with_suffix(".html")
                output = io.StringIO()
                with patch.object(
                    app, "parse_nexus_to_dataframe", return_value=(df, ["Feature"], {})
                ), patch.object(
                    app, "prompt_required_features", return_value=[]
                ), patch.object(
                    app, "OUTPUT_MD_PATH", str(md_path)
                ), patch.object(
                    app, "OUTPUT_HTML_PATH", str(html_path)
                ), contextlib.redirect_stdout(output):
                    app.main(argv)

                output_path = html_path if extension == "html" else md_path
                unused_path = md_path if extension == "html" else html_path
                content = output_path.read_text(encoding="utf-8")
                self.assertIn(expected, content)
                self.assertIn(str(output_path), output.getvalue())
                self.assertFalse(unused_path.exists())
                if not any(flag in argv for flag in ("--notes", "-n")) or "indented" in argv:
                    self.assertNotIn("註解", content)
                if extension == "html":
                    self.assertTrue(content.startswith("<!DOCTYPE html>"))
                    self.assertIn('<meta charset="utf-8">', content)
                    self.assertIn("<strong><em>Species A</em></strong>", content)
                    self.assertTrue(content.endswith("</html>\n"))
                else:
                    self.assertTrue(content.startswith("# "))
                    self.assertIn("👉 ***Species A***", content)

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
