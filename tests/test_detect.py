import unittest

from omawin.detect import (
    class_from_desktop,
    describe_state,
    infer_mode_from_props,
    matches_query,
    parse_window_rules,
    render_lua,
)


class DetectTests(unittest.TestCase):
    def test_parse_float_and_tile_rules(self):
        text = """
        o.window("steam", { float = true, idle_inhibit = "fullscreen" })
        o.window({ class = "steam", title = "Steam" }, { float = false })
        o.window("fanctl", { float = true, center = true, size = { 420, 220 } })
        """
        rules = parse_window_rules(text)
        self.assertEqual(rules["steam"], "tiled")
        self.assertEqual(rules["fanctl"], "center")

    def test_render_skips_default(self):
        lua = render_lua(
            {
                "steam.desktop": {"class": "steam", "mode": "tiled"},
                "ignore.desktop": {"class": "x", "mode": "default"},
            }
        )
        self.assertIn('o.window("steam", { float = false })', lua)
        self.assertNotIn("ignore", lua)

    def test_live_state_beats_rule(self):
        clients = [{"class": "steam", "floating": False, "fullscreen": 0}]
        mode, source = describe_state("steam", "float", {"steam": "float"}, clients)
        self.assertEqual(mode, "tiled")
        self.assertEqual(source, "open now")

    def test_infer_fullscreen(self):
        self.assertEqual(infer_mode_from_props("fullscreen = true"), "fullscreen")

    def test_steam_games_do_not_use_client_class(self):
        class Info:
            def get_commandline(self):
                return "steam steam://rungameid/284160"

            def get_executable(self):
                return "/usr/bin/steam"

            def get_startup_wm_class(self):
                return "steam"

            def get_id(self):
                return "steam.desktop.BeamNG.desktop"

        self.assertEqual(class_from_desktop(Info()), "steam_app_284160")

    def test_search_steam_skips_games(self):
        class Game:
            def get_name(self):
                return "BeamNG.drive"

            def get_id(self):
                return "BeamNG.drive.desktop"

            def get_commandline(self):
                return "steam steam://rungameid/284160"

            def get_executable(self):
                return "/usr/bin/steam"

        class Client:
            def get_name(self):
                return "Steam"

            def get_id(self):
                return "steam.desktop"

            def get_commandline(self):
                return "/home/ruegen/.local/bin/steam-omarchy %U"

            def get_executable(self):
                return "/home/ruegen/.local/bin/steam-omarchy"

        self.assertTrue(matches_query(Client(), "steam", "steam"))
        self.assertFalse(matches_query(Game(), "steam_app_284160", "steam"))
        self.assertTrue(matches_query(Game(), "steam_app_284160", "beam"))


if __name__ == "__main__":
    unittest.main()
