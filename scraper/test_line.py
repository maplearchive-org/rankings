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


if __name__ == "__main__":
    unittest.main()
