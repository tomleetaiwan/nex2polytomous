import contextlib
import io
import tempfile
import unittest
from pathlib import Path

import nex2polytomous as app


class NexusParserTests(unittest.TestCase):
    def write_nexus(self, content):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        path = Path(temporary_directory.name) / "matrix.nex"
        path.write_text(content, encoding="utf-8")
        return path

    def test_project_sample_is_parsed_without_biopython(self):
        species, features, rows, missing = app._parse_nexus(app.NEXUS_FILE_PATH)

        self.assertEqual(29, len(species))
        self.assertEqual(40, len(features))
        self.assertEqual("'Marginulation'", features[31])
        self.assertEqual({40}, {len(row) for row in rows.values()})
        self.assertEqual({"?", "-"}, missing)

    def test_comments_and_escaped_quotes_are_parsed(self):
        path = self.write_nexus(
            """#NEXUS
            [A comment containing a ; semicolon]
            BEGIN TAXA;
                DIMENSIONS NTAX=2;
                TAXLABELS 'O''Brien taxon' plain_taxon;
            END;
            BEGIN CHARACTERS;
                DIMENSIONS NCHAR=2;
                FORMAT DATATYPE=STANDARD MISSING=? GAP=- SYMBOLS="01";
                CHARLABELS 'Length''s value' Shape;
                STATELABELS 1 absent present, 2 round square;
                MATRIX
                    'O''Brien taxon' 01
                    plain_taxon      10
                ;
            END;
            """
        )

        species, features, rows, missing = app._parse_nexus(path)

        self.assertEqual(["O'Brien taxon", "plain_taxon"], species)
        self.assertEqual(["Length's value", "Shape"], features)
        self.assertEqual(["0", "1"], rows["O'Brien taxon"])
        self.assertEqual(["1", "0"], rows["plain_taxon"])
        self.assertEqual({"?", "-"}, missing)

    def test_matrix_row_length_must_match_nchar(self):
        path = self.write_nexus(
            """#NEXUS
            BEGIN TAXA;
                DIMENSIONS NTAX=1;
                TAXLABELS Taxon;
            END;
            BEGIN CHARACTERS;
                DIMENSIONS NCHAR=2;
                FORMAT DATATYPE=STANDARD MISSING=? GAP=- SYMBOLS="01";
                CHARLABELS First Second;
                STATELABELS 1 absent present, 2 round square;
                MATRIX Taxon 0;
            END;
            """
        )

        with self.assertRaisesRegex(ValueError, "Taxon.*1.*NCHAR=2"):
            app._parse_nexus(path)

    def test_interleaved_matrix_is_rejected_explicitly(self):
        path = self.write_nexus(
            """#NEXUS
            BEGIN TAXA;
                DIMENSIONS NTAX=1;
                TAXLABELS Taxon;
            END;
            BEGIN CHARACTERS;
                DIMENSIONS NCHAR=2;
                FORMAT DATATYPE=STANDARD INTERLEAVE MISSING=? GAP=- SYMBOLS="01";
                CHARLABELS First Second;
                STATELABELS 1 absent present, 2 round square;
                MATRIX Taxon 01;
            END;
            """
        )

        with self.assertRaisesRegex(ValueError, "INTERLEAVE"):
            app._parse_nexus(path)

    def test_charlabels_is_required(self):
        path = self.write_nexus(
            """#NEXUS
            BEGIN TAXA;
                DIMENSIONS NTAX=1;
                TAXLABELS Taxon;
            END;
            BEGIN CHARACTERS;
                DIMENSIONS NCHAR=1;
                FORMAT DATATYPE=STANDARD MISSING=? GAP=- SYMBOLS="01";
                STATELABELS 1 absent present;
                MATRIX Taxon 0;
            END;
            """
        )

        with self.assertRaisesRegex(ValueError, "CHARLABELS"):
            app._parse_nexus(path)

    def test_statelabels_is_required(self):
        path = self.write_nexus(
            """#NEXUS
            BEGIN TAXA;
                DIMENSIONS NTAX=1;
                TAXLABELS Taxon;
            END;
            BEGIN CHARACTERS;
                DIMENSIONS NCHAR=1;
                FORMAT DATATYPE=STANDARD MISSING=? GAP=- SYMBOLS="01";
                CHARLABELS Feature;
                MATRIX Taxon 0;
            END;
            """
        )

        with self.assertRaisesRegex(ValueError, "STATELABELS"):
            app._parse_nexus(path)

    def test_charlabels_count_must_match_nchar(self):
        path = self.write_nexus(
            """#NEXUS
            BEGIN TAXA;
                DIMENSIONS NTAX=1;
                TAXLABELS Taxon;
            END;
            BEGIN CHARACTERS;
                DIMENSIONS NCHAR=2;
                FORMAT DATATYPE=STANDARD MISSING=? GAP=- SYMBOLS="01";
                CHARLABELS Only_one;
                STATELABELS 1 absent present, 2 round square;
                MATRIX Taxon 01;
            END;
            """
        )

        with self.assertRaisesRegex(ValueError, "CHARLABELS.*1.*NCHAR=2"):
            app._parse_nexus(path)

    def test_selected_species_determine_which_missing_features_are_removed(self):
        path = self.write_nexus(
            """#NEXUS
            BEGIN TAXA;
                DIMENSIONS NTAX=3;
                TAXLABELS Complete_A Complete_B Fossil;
            END;
            BEGIN CHARACTERS;
                DIMENSIONS NCHAR=2;
                FORMAT DATATYPE=STANDARD MISSING=? GAP=- SYMBOLS="01";
                CHARLABELS Fragile_feature Stable_feature;
                STATELABELS 1 absent present, 2 round square;
                MATRIX
                    Complete_A 00
                    Complete_B 11
                    Fossil     ?0
                ;
            END;
            """
        )

        with contextlib.redirect_stdout(io.StringIO()):
            all_df, all_features, _ = app.parse_nexus_to_dataframe(path)
            selected_df, selected_features, _ = app.parse_nexus_to_dataframe(
                path,
                species_selector=lambda _species: ["Complete_A", "Complete_B"],
            )

        self.assertEqual(["Stable_feature"], all_features)
        self.assertEqual(["Fragile_feature", "Stable_feature"], selected_features)
        self.assertEqual(["Complete_A", "Complete_B"], list(selected_df.index))
        self.assertEqual((3, 1), all_df.shape)
        self.assertEqual((2, 2), selected_df.shape)


if __name__ == "__main__":
    unittest.main()
