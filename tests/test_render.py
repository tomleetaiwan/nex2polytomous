import unittest
from html.parser import HTMLParser

import nex2polytomous as app


class TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []
        self.tags = []
        self.in_cell = False

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        if tag == "tr":
            self.rows.append([])
        elif tag in {"th", "td"}:
            self.rows[-1].append("")
            self.in_cell = True

    def handle_endtag(self, tag):
        if tag in {"th", "td"}:
            self.in_cell = False

    def handle_data(self, data):
        if self.in_cell:
            self.rows[-1][-1] += data


class RenderKeyHtmlTests(unittest.TestCase):
    def test_optional_notes_column_is_blank_between_state_and_result(self):
        rows = [
            ("1a", "Feature", "狀態為 0", "前往步驟編號 2", 0),
            ("1b", "Feature", "狀態為 1", ["Species A"], 0),
            ("", "", "", ["Species B", "Species C"], 0),
        ]

        for include_notes in (False, True):
            with self.subTest(include_notes=include_notes):
                parser = TableParser()
                parser.feed(app.render_key_html(rows, include_notes=include_notes))
                expected_headers = ["編號", "特徵", "狀態", "結果"]
                if include_notes:
                    expected_headers.insert(3, "註解")
                self.assertEqual(expected_headers, parser.rows[0])
                self.assertTrue(all(len(row) == len(expected_headers) for row in parser.rows))
                self.assertEqual(
                    ["👉 Species B / Species C", "前往步驟編號 2", "👉 Species A"],
                    [row[-1] for row in parser.rows[1:]],
                )
                if include_notes:
                    self.assertTrue(all(row[3] == "" for row in parser.rows[1:]))

    def test_html_table_sorts_rows_and_escapes_data(self):
        rows = [
            ("10a", "Later feature", "狀態為 0", ["Species C"], 1),
            ("2a", '<script>alert("x")</script>', "A & B < C", ["A < B", "C & D"], 1),
            ("1b", "Feature", "狀態為 1", ["Species B"], 0),
            ("1a", "Feature", "狀態為 0", "前往步驟編號 2", 0),
        ]

        rendered = app.render_key_html(rows)
        parser = TableParser()
        parser.feed(rendered)

        self.assertEqual(["編號", "特徵", "狀態", "結果"], parser.rows[0])
        self.assertEqual(["1a", "1b", "2a", "10a"], [row[0] for row in parser.rows[1:]])
        self.assertTrue(all(len(row) == 4 for row in parser.rows))
        self.assertEqual("前往步驟編號 2", parser.rows[1][3])
        self.assertEqual(
            ["2a", '<script>alert("x")</script>', "A & B < C", "👉 A < B / C & D"],
            parser.rows[3],
        )
        self.assertNotIn("script", parser.tags)
        self.assertIn("<strong><em>A &lt; B</em></strong>", rendered)
        self.assertIn("<strong><em>C &amp; D</em></strong>", rendered)

    def test_html_table_preserves_terminal_row_without_steps(self):
        rendered = app.render_key_html([("", "", "", ["Species A", "Species B"], 0)])
        parser = TableParser()
        parser.feed(rendered)

        self.assertEqual(["", "", "", "👉 Species A / Species B"], parser.rows[1])


class RenderKeyMarkdownTests(unittest.TestCase):
    def test_optional_notes_column_is_blank_between_state_and_result(self):
        rows = [
            ("1a", "Feature", "狀態為 0", "前往步驟編號 2", 0),
            ("1b", "Feature", "狀態為 1", ["Species A"], 0),
            ("", "", "", ["Species B", "Species C"], 0),
        ]

        for include_notes in (False, True):
            with self.subTest(include_notes=include_notes):
                rendered = app.render_key_markdown(rows, "table", include_notes=include_notes)
                cells = [
                    [cell.strip() for cell in line.split("|")[1:-1]]
                    for line in rendered.splitlines()
                ]
                expected_headers = ["編號", "特徵", "狀態", "結果"]
                if include_notes:
                    expected_headers.insert(3, "註解")
                self.assertEqual(expected_headers, cells[0])
                self.assertTrue(all(len(row) == len(expected_headers) for row in cells))
                self.assertEqual(["---"] * len(expected_headers), cells[1])
                self.assertEqual(
                    ["👉 ***Species B*** / ***Species C***", "前往步驟編號 2", "👉 ***Species A***"],
                    [row[-1] for row in cells[2:]],
                )
                if include_notes:
                    self.assertTrue(all(row[3] == "" for row in cells[2:]))

    def test_notes_option_does_not_change_indented_output(self):
        rows = [("1a", "Feature", "狀態為 0", ["Species A"], 0)]

        self.assertEqual(
            app.render_key_markdown(rows, "indented"),
            app.render_key_markdown(rows, "indented", include_notes=True),
        )

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
