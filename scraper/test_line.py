import unittest

from line import slice_line


class SliceLine(unittest.TestCase):
    def test_the_body_is_spliced_in_without_being_touched(self):
        body = b'{"totalCount":7019330,"ranks":[{"exp":795025135043493,"rank":1}]}'

        self.assertEqual(slice_line(1, body), b'{"o":1,"r":' + body + b"}")

    def test_the_exact_digits_of_a_huge_exp_survive(self):
        # 9007199254740993 is the archive's JavaScript hazard: parsed as a
        # number there it becomes ...92. Nothing here parses it, and nothing
        # here decodes it either, so the bytes are the bytes the API sent.
        body = b'{"ranks":[{"exp":9007199254740993}]}'

        self.assertIn(b"9007199254740993", slice_line(1, body))

    def test_a_body_containing_a_newline_is_refused(self):
        with self.assertRaisesRegex(ValueError, "newline"):
            slice_line(1, b'{\n"ranks":[]}')

    def test_a_body_containing_a_carriage_return_is_refused(self):
        with self.assertRaisesRegex(ValueError, "newline"):
            slice_line(1, b'{\r"ranks":[]}')

    def test_a_trailing_newline_is_stripped_rather_than_refused(self):
        # Since 2026-09-18 the API ends every response with one \n after the
        # closing brace. It is not pretty-printing: the JSON in front of it is
        # as compact as it ever was, and every rank is present. A newline the
        # line format is about to add itself cannot break that format, so it
        # is dropped rather than treated as a corrupt page.
        body = b'{"totalCount":1,"ranks":[{"rank":1}]}'

        self.assertEqual(slice_line(1, body + b"\n"), b'{"o":1,"r":' + body + b"}")

    def test_a_trailing_carriage_return_newline_is_stripped_too(self):
        body = b'{"totalCount":1,"ranks":[{"rank":1}]}'

        self.assertEqual(slice_line(1, body + b"\r\n"), b'{"o":1,"r":' + body + b"}")

    def test_stripping_the_trailing_newline_does_not_decode_the_body(self):
        # The guarantee the whole byte-splicing format exists for: a digit
        # that any decode/re-encode round trip would change survives a body
        # that arrived with the API's trailing newline on it.
        body = b'{"ranks":[{"exp":9007199254740993}]}'

        self.assertIn(b"9007199254740993", slice_line(1, body + b"\n"))


if __name__ == "__main__":
    unittest.main()
