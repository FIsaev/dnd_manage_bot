"""Tests for the message gate and the reply layout.

Run with: python -m unittest -v test_bot
"""

import inspect
import unittest

import bot
from telegram import Message
from test_dice import FixedRng

import dice


class Gate(unittest.TestCase):
    def test_answers_bare_expressions(self):
        for text in [
            "3d6+1",
            "3d6(+1)",
            "(3d6+1)",
            "d20 + 5",
            "2d6(-1)*2",
            "d%",
            "3к6",
            "4d6kh3",
            "2d20kh1",
            "4d6kl2+1",
        ]:
            with self.subTest(text=text):
                self.assertTrue(bot.looks_like_a_roll(text))

    def test_stays_quiet_in_normal_chat(self):
        for text in [
            "hello",
            "2+2",
            "i rolled 3d6+1 yesterday",
            "d&d tonight?",
            "100%",
            "see you at 3",
            "https://example.com/d20",
        ]:
            with self.subTest(text=text):
                self.assertFalse(bot.looks_like_a_roll(text))

    def test_note_is_split_off(self):
        self.assertEqual(bot.split_note("2d6+3 # sneak attack"), ("2d6+3", "sneak attack"))
        self.assertEqual(bot.split_note("2d6+3"), ("2d6+3", ""))
        self.assertTrue(bot.looks_like_a_roll(bot.split_note("2d6+3 # sneak attack")[0]))


class Layout(unittest.TestCase):
    def test_result_first_then_expandable_quote(self):
        result = dice.roll("3d6(+1)+2", FixedRng([4, 2, 6]))
        text = bot.render(result)
        self.assertEqual(
            text,
            "\U0001f3b2 <b>17</b>  <code>3d6(+1)+2</code>\n"
            "<blockquote expandable>"
            "3d6(+1): 4, 2, 6  (+1 each)  -&gt;  5 + 3 + 7 = 15\n"
            "15 + 2 = 17"
            "</blockquote>",
        )

    def test_note_is_echoed(self):
        result = dice.roll("1d6", FixedRng([6]))
        self.assertIn("<i>sneak attack</i>", bot.render(result, "sneak attack"))

    def test_html_in_a_note_is_escaped(self):
        result = dice.roll("1d6", FixedRng([6]))
        self.assertIn("&lt;b&gt;", bot.render(result, "<b>boom</b>"))


class Wiring(unittest.TestCase):
    def test_reply_text_takes_do_quote(self):
        self.assertIn("do_quote", inspect.signature(Message.reply_text).parameters)

    def test_help_text_mentions_both_bonus_forms(self):
        self.assertIn("3d6+1", bot.HELP)
        self.assertIn("3d6(+1)", bot.HELP)


if __name__ == "__main__":
    unittest.main()
