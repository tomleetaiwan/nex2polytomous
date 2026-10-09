import unittest

import nex2polytomous as app


class RenderKeyMarkdownTests(unittest.TestCase):
    def test_indented_format_adds_markdown_hard_breaks(self):
        rows = [
            ("1a", "Feature one", "狀態為 0", "前往步驟 2", 0),
            ("1b", "Feature one", "狀態為 1", ["Species A"], 0),
        ]

        rendered = app.render_key_markdown(rows, "indented")

        self.assertEqual(2, len(rendered.splitlines()))
        lines = rendered.splitlines()
        self.assertTrue(lines[0].endswith("\\"))
        self.assertFalse(lines[-1].endswith("\\"))

    def test_single_indented_line_has_no_trailing_hard_break(self):
        rows = [("", "", "", ["Species A"], 0)]

        rendered = app.render_key_markdown(rows, "indented")

        self.assertEqual("👉 ***Species A***", rendered)

    def test_table_format_does_not_add_trailing_spaces(self):
        rows = [("1a", "Feature one", "狀態為 0", ["Species A"], 0)]

        rendered = app.render_key_markdown(rows, "table")

        self.assertFalse(any(line.endswith("\\") for line in rendered.splitlines()))


if __name__ == "__main__":
    unittest.main()
