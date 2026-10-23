"""Tests for the dice engine. Run with: python -m unittest -v test_dice"""

import random
import unittest
from fractions import Fraction

import dice


class FixedRng(random.Random):
    """Hands out a scripted sequence of faces so rolls are predictable."""

    def __init__(self, faces):
        super().__init__()
        self.faces = list(faces)

    def randint(self, a, b):
        face = self.faces.pop(0)
        assert a <= face <= b, "scripted face %d outside d%d" % (face, b)
        return face


class BonusPlacement(unittest.TestCase):
    def test_bonus_outside_brackets_hits_the_total_once(self):
        result = dice.roll("3d6+1", FixedRng([4, 2, 6]))
        self.assertEqual(result.total, 13)
        self.assertEqual([t.faces for t in result.terms], [[4, 2, 6]])
        self.assertEqual(result.terms[0].per_die, 0)

    def test_bonus_attached_in_brackets_hits_every_die(self):
        result = dice.roll("3d6(+1)", FixedRng([4, 2, 6]))
        self.assertEqual(result.total, 15)
        self.assertEqual(result.terms[0].per_die, 1)

    def test_bonus_inside_a_group_hits_every_die(self):
        result = dice.roll("(3d6+1)", FixedRng([4, 2, 6]))
        self.assertEqual(result.total, 15)
        self.assertEqual(result.terms[0].src, "3d6(+1)")

    def test_debuff_in_brackets_hits_every_die(self):
        result = dice.roll("3d6(-2)", FixedRng([4, 2, 6]))
        self.assertEqual(result.total, 6)

    def test_per_die_debuff_stops_at_zero(self):
        result = dice.roll("2d4(-5)", FixedRng([1, 2]))
        self.assertEqual(result.total, 0)
        self.assertEqual(result.terms[0].modified, [0, 0])
        self.assertTrue(result.terms[0].floored)

    def test_only_the_dice_below_zero_are_floored(self):
        result = dice.roll("3d6(-3)", FixedRng([1, 4, 6]))
        self.assertEqual(result.terms[0].modified, [0, 1, 3])
        self.assertEqual(result.total, 4)

    def test_exactly_zero_does_not_count_as_floored(self):
        result = dice.roll("2d6(-2)", FixedRng([2, 5]))
        self.assertEqual(result.terms[0].modified, [0, 3])
        self.assertFalse(result.terms[0].floored)

    def test_floor_applies_to_a_debuff_folded_out_of_brackets(self):
        result = dice.roll("(2d4-5)", FixedRng([1, 2]))
        self.assertEqual(result.total, 0)
        self.assertEqual(result.terms[0].src, "2d4(-5)")

    def test_the_floor_is_per_die_so_the_total_can_still_go_negative(self):
        result = dice.roll("1d4-10", FixedRng([2]))
        self.assertEqual(result.total, -8)
        self.assertFalse(result.terms[0].floored)

    def test_floored_dice_still_scale_with_the_rest_of_the_maths(self):
        result = dice.roll("(2d4-5)*3", FixedRng([1, 2]))
        self.assertEqual(result.total, 0)

    def test_several_bonuses_in_one_bracket_add_up(self):
        result = dice.roll("2d6(+3-1)", FixedRng([5, 5]))
        self.assertEqual(result.total, 14)
        self.assertEqual(result.terms[0].src, "2d6(+2)")

    def test_per_die_and_final_bonus_together(self):
        result = dice.roll("2d6(+1)-3", FixedRng([3, 4]))
        self.assertEqual(result.total, 6)

    def test_group_with_two_dice_terms_is_plain_grouping(self):
        result = dice.roll("(2d6+1d4)*2", FixedRng([6, 6, 4]))
        self.assertEqual(result.total, 32)
        self.assertEqual([t.per_die for t in result.terms], [0, 0])

    def test_group_that_only_scales_is_untouched(self):
        result = dice.roll("(2d6)*3", FixedRng([2, 3]))
        self.assertEqual(result.total, 15)

    def test_bonus_folded_out_of_a_scaled_group(self):
        # (2d6+1)*2 -> each die +1, then double the total
        result = dice.roll("(2d6+1)*2", FixedRng([2, 3]))
        self.assertEqual(result.total, 14)


class Arithmetic(unittest.TestCase):
    def test_implicit_single_die(self):
        result = dice.roll("d20+5", FixedRng([14]))
        self.assertEqual(result.total, 19)
        self.assertEqual(result.terms[0].src, "d20")

    def test_percent_die_is_d100(self):
        result = dice.roll("d%", FixedRng([77]))
        self.assertEqual(result.total, 77)
        self.assertEqual(result.terms[0].sides, 100)

    def test_multiplication_before_addition(self):
        result = dice.roll("2+1d6*3", FixedRng([4]))
        self.assertEqual(result.total, 14)

    def test_division_stays_exact(self):
        result = dice.roll("1d6/4", FixedRng([5]))
        self.assertEqual(result.total, Fraction(5, 4))
        self.assertEqual(result.total_text, "1.25")

    def test_leading_minus(self):
        result = dice.roll("-d4+10", FixedRng([3]))
        self.assertEqual(result.total, 7)

    def test_whitespace_and_caps_are_fine(self):
        result = dice.roll("  2 D 6 + 1 ", FixedRng([1, 1]))
        self.assertEqual(result.total, 3)

    def test_cyrillic_dice_letter(self):
        result = dice.roll("3к6+2", FixedRng([1, 2, 3]))
        self.assertEqual(result.total, 8)

    def test_no_dice_is_still_valid_maths(self):
        result = dice.roll("2+2*2", FixedRng([]))
        self.assertEqual(result.total, 6)
        self.assertEqual(result.terms, [])


class Explaining(unittest.TestCase):
    def test_calc_path_for_per_die_bonus(self):
        result = dice.roll("3d6(+1)+2", FixedRng([4, 2, 6]))
        self.assertEqual(
            result.detail_lines(),
            ["3d6(+1): 4, 2, 6  (+1 each)  ->  5 + 3 + 7 = 15", "15 + 2 = 17"],
        )

    def test_calc_path_for_final_bonus(self):
        result = dice.roll("3d6+1", FixedRng([4, 2, 6]))
        self.assertEqual(
            result.detail_lines(),
            ["3d6: 4, 2, 6  ->  sum = 12", "12 + 1 = 13"],
        )

    def test_calc_path_marks_the_floor(self):
        result = dice.roll("2d4(-5)+1", FixedRng([1, 2]))
        self.assertEqual(
            result.detail_lines(),
            ["2d4(-5): 1, 2  (-5 each, min 0)  ->  0 + 0 = 0", "0 + 1 = 1"],
        )

    def test_calc_path_stays_quiet_when_nothing_was_floored(self):
        result = dice.roll("2d6(-1)", FixedRng([3, 4]))
        self.assertEqual(result.detail_lines(), ["2d6(-1): 3, 4  (-1 each)  ->  2 + 3 = 5"])

    def test_single_die_has_no_redundant_sum_line(self):
        result = dice.roll("d20", FixedRng([14]))
        self.assertEqual(result.detail_lines(), ["d20: 14"])

    def test_grouping_is_kept_in_the_calc_path(self):
        result = dice.roll("(2d6+1d4)*2", FixedRng([6, 6, 4]))
        self.assertEqual(result.detail_lines()[-1], "(12 + 4) * 2 = 32")

    def test_several_terms_are_listed_in_order(self):
        result = dice.roll("1d4+2d6", FixedRng([3, 1, 2]))
        self.assertEqual([line.split(":")[0] for line in result.detail_lines()[:2]], ["1d4", "2d6"])


class Rejections(unittest.TestCase):
    def bad(self, text):
        with self.assertRaises(dice.DiceError):
            dice.roll(text, FixedRng([1] * 20))

    def test_syntax_errors(self):
        for text in ["3d", "d", "3d6+", "(3d6", "3d6)", "3d6 2d6", "", "   ", "3x6", "2(d6+1)"]:
            with self.subTest(text=text):
                self.bad(text)

    def test_silly_numbers(self):
        for text in ["0d6", "3d1", "3d0", "999d6", "3d99999", "1d6/0"]:
            with self.subTest(text=text):
                self.bad(text)

    def test_too_many_dice_across_terms(self):
        self.bad("+".join(["100d6"] * 6))

    def test_too_long(self):
        self.bad("1d6+" * 60 + "1d6")


class Gate(unittest.TestCase):
    def test_accepts_dice_looking_text(self):
        for text in ["3d6+1", "d20", "2D6(+1)", "d%", "3к6"]:
            with self.subTest(text=text):
                self.assertTrue(dice.has_dice(text))

    def test_rejects_plain_text(self):
        for text in ["2+2", "hello", "dd", "d"]:
            with self.subTest(text=text):
                self.assertFalse(dice.has_dice(text))


class Fairness(unittest.TestCase):
    def test_faces_stay_in_range(self):
        rng = random.Random(1)
        for _ in range(200):
            result = dice.roll("8d6(+2)", rng)
            for face in result.terms[0].faces:
                self.assertTrue(1 <= face <= 6)
            self.assertEqual(result.total, sum(result.terms[0].faces) + 16)


if __name__ == "__main__":
    unittest.main()
