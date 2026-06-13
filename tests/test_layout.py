import unittest

from pyherdr.layout import (
    Direction,
    NavDirection,
    PaneNode,
    Rect,
    SplitNode,
    TileLayout,
    build_custom_layout,
    build_template_layout,
    export_custom_layout,
    layout_template_records,
    split_rect,
)


class LayoutTests(unittest.TestCase):
    def build_nested_layout(self) -> TileLayout:
        layout = TileLayout.single("a")
        self.assertTrue(layout.split_pane("a", "b", Direction.HORIZONTAL, 0.6))
        self.assertTrue(layout.split_pane("a", "c", Direction.VERTICAL, 0.25))
        self.assertTrue(layout.split_pane("b", "d", Direction.VERTICAL, 0.5))
        return layout

    def test_split_rect_clamps_ratio_and_preserves_area(self):
        area = Rect(10, 20, 10, 5)

        first, second = split_rect(area, Direction.HORIZONTAL, 0.95)

        self.assertEqual(first, Rect(10, 20, 9, 5))
        self.assertEqual(second, Rect(19, 20, 1, 5))

        first, second = split_rect(area, Direction.VERTICAL, -1.0)

        self.assertEqual(first, Rect(10, 20, 10, 1))
        self.assertEqual(second, Rect(10, 21, 10, 4))

    def test_split_tree_geometry_and_split_borders(self):
        layout = self.build_nested_layout()
        area = Rect(0, 0, 100, 50)

        panes = layout.panes(area)
        splits = layout.splits(area)

        self.assertEqual(
            [(pane.pane_id, pane.rect, pane.is_focused) for pane in panes],
            [
                ("a", Rect(0, 0, 60, 12), False),
                ("c", Rect(0, 12, 60, 38), False),
                ("b", Rect(60, 0, 40, 25), False),
                ("d", Rect(60, 25, 40, 25), True),
            ],
        )
        self.assertEqual(
            [(split.pos, split.direction, split.ratio, split.area, split.path) for split in splits],
            [
                (60, Direction.HORIZONTAL, 0.6, Rect(0, 0, 100, 50), ()),
                (12, Direction.VERTICAL, 0.25, Rect(0, 0, 60, 50), (False,)),
                (25, Direction.VERTICAL, 0.5, Rect(60, 0, 40, 50), (True,)),
            ],
        )

    def test_close_reflows_sibling_subtree_and_focuses_next_pane(self):
        layout = self.build_nested_layout()
        layout.focus_pane("b")

        self.assertTrue(layout.close_focused())

        self.assertEqual(layout.focus, "d")
        self.assertEqual(layout.pane_ids(), ["a", "c", "d"])
        self.assertEqual(
            [(pane.pane_id, pane.rect, pane.is_focused) for pane in layout.panes(Rect(0, 0, 100, 50))],
            [
                ("a", Rect(0, 0, 60, 12), False),
                ("c", Rect(0, 12, 60, 38), False),
                ("d", Rect(60, 0, 40, 50), True),
            ],
        )

    def test_close_refuses_last_or_missing_pane(self):
        layout = TileLayout.single("only")

        self.assertFalse(layout.close_pane("missing"))
        self.assertFalse(layout.close_focused())
        self.assertEqual(layout.pane_ids(), ["only"])
        self.assertEqual(layout.focus, "only")

    def test_directional_neighbour_uses_overlap_and_nearest_geometry(self):
        layout = self.build_nested_layout()
        area = Rect(0, 0, 100, 50)

        layout.focus_pane("a")
        self.assertEqual(layout.find_in_direction(NavDirection.RIGHT, area), "b")
        self.assertEqual(layout.find_in_direction(NavDirection.DOWN, area), "c")
        self.assertIsNone(layout.find_in_direction(NavDirection.LEFT, area))

        layout.focus_pane("c")
        self.assertEqual(layout.find_in_direction(NavDirection.RIGHT, area), "d")
        self.assertEqual(layout.find_in_direction(NavDirection.UP, area), "a")
        self.assertTrue(layout.focus_in_direction(NavDirection.RIGHT, area))
        self.assertEqual(layout.focus, "d")

    def test_swap_panes_exchanges_leaf_ids_and_keeps_focus_id(self):
        layout = self.build_nested_layout()
        area = Rect(0, 0, 100, 50)

        self.assertTrue(layout.swap_panes("a", "d"))

        self.assertEqual(layout.focus, "d")
        self.assertEqual(
            [(pane.pane_id, pane.rect, pane.is_focused) for pane in layout.panes(area)],
            [
                ("d", Rect(0, 0, 60, 12), True),
                ("c", Rect(0, 12, 60, 38), False),
                ("b", Rect(60, 0, 40, 25), False),
                ("a", Rect(60, 25, 40, 25), False),
            ],
        )
        self.assertFalse(layout.swap_panes("a", "missing"))
        self.assertFalse(layout.swap_panes("a", "a"))

    def test_ratio_updates_and_keyboard_resize_are_clamped(self):
        layout = TileLayout.single("left")
        self.assertTrue(layout.split_pane("left", "right", Direction.HORIZONTAL, 0.5))
        area = Rect(0, 0, 100, 20)

        layout.focus_pane("left")
        self.assertTrue(layout.resize_focused(NavDirection.RIGHT, 0.2, area))
        self.assertAlmostEqual(layout.to_dict()["root"]["ratio"], 0.7)

        layout.focus_pane("right")
        self.assertTrue(layout.resize_focused(NavDirection.RIGHT, 0.3, area))
        self.assertAlmostEqual(layout.to_dict()["root"]["ratio"], 0.4)

        self.assertTrue(layout.resize_focused(NavDirection.LEFT, 1.0, area))
        self.assertEqual(layout.to_dict()["root"]["ratio"], 0.9)
        self.assertFalse(layout.resize_focused(NavDirection.DOWN, 0.1, area))

        self.assertFalse(layout.set_ratio_at((True,), 0.5))
        self.assertTrue(layout.set_ratio_at((), -5.0))
        self.assertEqual(layout.to_dict()["root"]["ratio"], 0.1)

    def test_serialization_round_trip_clamps_ratios_and_recovers_invalid_focus(self):
        layout = TileLayout.from_dict(
            {
                "root": {
                    "kind": "split",
                    "direction": "horizontal",
                    "ratio": 1.5,
                    "first": {"kind": "pane", "pane_id": "left"},
                    "second": {"kind": "pane", "pane_id": "right"},
                },
                "focus": "missing",
            }
        )

        self.assertEqual(layout.focus, "left")
        self.assertEqual(layout.pane_ids(), ["left", "right"])
        self.assertEqual(
            layout.to_dict(),
            {
                "root": {
                    "kind": "split",
                    "direction": "horizontal",
                    "ratio": 0.9,
                    "first": {"kind": "pane", "pane_id": "left"},
                    "second": {"kind": "pane", "pane_id": "right"},
                },
                "focus": "left",
            },
        )

    def test_layout_template_records_expose_builtin_shapes(self):
        records = layout_template_records()

        self.assertEqual(
            [record["id"] for record in records],
            ["single", "columns-2", "rows-2", "grid-2x2", "main-left", "main-top"],
        )
        self.assertEqual(records[3]["pane_count"], 4)

    def test_grid_template_builds_even_two_by_two_layout(self):
        layout = build_template_layout("grid-2x2", ["a", "b", "c", "d"])

        self.assertEqual(layout.pane_ids(), ["a", "b", "c", "d"])
        self.assertEqual(layout.focus, "a")
        self.assertEqual(
            [(pane.pane_id, pane.rect) for pane in layout.panes(Rect(0, 0, 100, 40))],
            [
                ("a", Rect(0, 0, 50, 20)),
                ("b", Rect(50, 0, 50, 20)),
                ("c", Rect(0, 20, 50, 20)),
                ("d", Rect(50, 20, 50, 20)),
            ],
        )

    def test_main_left_template_allocates_primary_pane_and_side_stack(self):
        layout = build_template_layout("main-left", ["main", "top", "bottom"])

        self.assertEqual(
            [(pane.pane_id, pane.rect) for pane in layout.panes(Rect(0, 0, 100, 40))],
            [
                ("main", Rect(0, 0, 65, 40)),
                ("top", Rect(65, 0, 35, 20)),
                ("bottom", Rect(65, 20, 35, 20)),
            ],
        )

    def test_template_builder_rejects_unknown_template_or_too_few_panes(self):
        with self.assertRaises(ValueError):
            build_template_layout("missing", ["a"])
        with self.assertRaises(ValueError):
            build_template_layout("grid-2x2", ["a", "b", "c"])

    def test_custom_layout_export_and_rebuild_remaps_panes(self):
        layout = TileLayout(
            SplitNode(Direction.HORIZONTAL, 0.6, PaneNode("left"), PaneNode("right")),
            "right",
        )

        record = export_custom_layout("wide", layout, label="Wide pair")
        rebuilt = build_custom_layout(record, ["api", "logs", "shell"])

        self.assertEqual(record["id"], "wide")
        self.assertEqual(record["label"], "Wide pair")
        self.assertEqual(record["pane_count"], 2)
        self.assertEqual(record["layout"]["focus"], "pane_2")
        self.assertEqual(rebuilt.pane_ids(), ["api", "logs", "shell"])
        self.assertEqual(rebuilt.focus, "logs")
        self.assertEqual(
            [(pane.pane_id, pane.rect) for pane in rebuilt.panes(Rect(0, 0, 100, 20))],
            [
                ("api", Rect(0, 0, 45, 20)),
                ("logs", Rect(45, 0, 30, 20)),
                ("shell", Rect(75, 0, 25, 20)),
            ],
        )


if __name__ == "__main__":
    unittest.main()
