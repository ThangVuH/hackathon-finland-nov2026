"""Rules for scope, question type, arbitration and the selective curve."""

from __future__ import annotations

import unittest

from arbitrate import arbitrate, reliability_score, selective_table, to_milli
from questions import question_type
from scope import assess


def box(kind: str, xmin: int, ymin: int, xmax: int, ymax: int, score: float = 0.9) -> dict:
    return {
        "kind": kind,
        "label": kind,
        "xmin": xmin,
        "ymin": ymin,
        "xmax": xmax,
        "ymax": ymax,
        "score": score,
    }


class QuestionTests(unittest.TestCase):
    def test_kinds(self):
        self.assertEqual(question_type("How many windows?"), "window")
        self.assertEqual(question_type("Combien de portes ?"), "door")
        self.assertEqual(question_type("Count the doors and the windows"), "both")
        self.assertEqual(question_type("How many rooms?"), "other")
        self.assertEqual(question_type("Count the doorways without a leaf"), "other")


class ScopeTests(unittest.TestCase):
    def test_filename_refusals(self):
        self.assertIn("IFC", assess("block.ifc") or "")
        self.assertIn("PDF", assess("level.pdf") or "")
        self.assertIn("sheet", assess("al1276_sheet_00001.jpg").lower())
        self.assertIn("Archive", assess("data/habs/plan.jpg") or "")
        self.assertIsNone(assess("high_quality-11459.png"))

    def test_a_dark_floor_plan_image_stays_in_scope(self):
        self.assertIsNone(assess("high_quality_architectural-10491.png"))
        self.assertIsNotNone(assess("data/finna/scan.jpg"))


class ArbitrateTests(unittest.TestCase):
    def test_milli_scale(self):
        self.assertEqual(to_milli([0, 0, 50, 100], 100, 200), {"xmin": 0, "ymin": 0, "xmax": 500, "ymax": 500})
        thin = to_milli([0, 0, 1, 40], 5000, 5000)
        self.assertGreater(thin["xmax"], thin["xmin"])
        self.assertGreater(thin["ymax"], thin["ymin"])

    def test_agreement_is_reliable(self):
        detected = [box("window", 10, 10, 40, 40)]
        vision = {"available": True, "object_type": "Window", "items": [box("window", 12, 12, 42, 42)], "answer": "1"}
        result = arbitrate("window", detected, 0.8, vision)
        self.assertEqual(result["verdict"], "reliable")
        self.assertEqual(result["count"], 1)
        self.assertFalse(result["items"][0]["disputed"])
        self.assertEqual(result["items"][0]["source"], "both")

    def test_same_total_different_place_is_review(self):
        detected = [box("window", 10, 10, 40, 40)]
        vision = {"available": True, "object_type": "Window", "items": [box("window", 700, 700, 900, 900)]}
        result = arbitrate("window", detected, 0.8, vision)
        self.assertEqual(result["verdict"], "review")
        self.assertEqual(result["count"], 1)
        self.assertTrue(result["items"][0]["disputed"])
        extras = [item for item in result["items"] if item["source"] == "vision"]
        self.assertEqual(len(extras), 1)
        self.assertFalse(extras[0]["included"])

    def test_count_mismatch_highlights_the_extra(self):
        detected = [box("door", 10, 10, 40, 40), box("door", 100, 100, 140, 140, score=0.4)]
        vision = {"available": True, "object_type": "Door", "items": [box("door", 10, 10, 40, 40)]}
        result = arbitrate("door", detected, 0.7, vision)
        self.assertEqual(result["verdict"], "review")
        self.assertEqual(result["count"], 2)
        disputed = [item for item in result["items"] if item["disputed"]]
        self.assertEqual(len(disputed), 1)

    def test_missing_vision_is_not_reliable(self):
        result = arbitrate("window", [box("window", 10, 10, 40, 40)], 0.6, None)
        self.assertEqual(result["verdict"], "review")
        self.assertIn("did not confirm", result["answer"])

    def test_both_empty_is_reliable(self):
        result = arbitrate("door", [], 1.0, {"available": True, "object_type": "Door", "items": []})
        self.assertEqual(result["verdict"], "reliable")
        self.assertEqual(result["count"], 0)

    def test_other_question_is_unverified(self):
        vision = {
            "available": True,
            "object_type": "Room",
            "answer": "There are 3 rooms.",
            "count": 1,
            "items": [box("Room", 0, 0, 100, 100)],
        }
        result = arbitrate("other", [], 0, vision)
        self.assertEqual(result["verdict"], "unverified")
        self.assertIn("vision model alone", result["warning"])

    def test_score_and_curve(self):
        agreed = [box("window", 0, 0, 20, 20)]
        self.assertEqual(reliability_score(agreed, [box("window", 0, 0, 20, 20)]), 1.0)
        self.assertLess(reliability_score(agreed, []), 1.0)
        plans = [
            {"exact": True, "score": 1.0},
            {"exact": True, "score": 1.0},
            {"exact": False, "score": 1.0},
            {"exact": False, "score": 0.2},
        ]
        table = {row["threshold"]: row for row in selective_table(plans)}
        self.assertEqual(table[1.0]["accepted"], 3)
        self.assertAlmostEqual(table[1.0]["coverage"], 0.75)
        self.assertAlmostEqual(table[1.0]["precision"], 2 / 3)
        self.assertEqual(table[0.0]["accepted"], 4)


class ServiceTests(unittest.TestCase):
    def test_pdf_is_refused_before_the_model_runs(self):
        from fastapi.testclient import TestClient

        from server import app

        client = TestClient(app)
        response = client.post(
            "/detect",
            files={"file": ("level.pdf", b"not a drawing", "application/pdf")},
            data={"question": "How many windows?"},
        )
        body = response.json()
        self.assertEqual(body["scope"], "out_of_scope")
        self.assertIn("PDF", body["reason"])

    def test_arbitrate_over_http(self):
        from fastapi.testclient import TestClient

        from server import app

        client = TestClient(app)
        response = client.post(
            "/arbitrate",
            json={
                "question_type": "window",
                "confidence": 0.8,
                "detector_items": [box("window", 10, 10, 40, 40)],
                "vision": {"available": True, "object_type": "Window", "items": [box("window", 12, 12, 38, 38)]},
            },
        )
        body = response.json()
        self.assertEqual(body["verdict"], "reliable")
        self.assertEqual(body["count"], 1)


if __name__ == "__main__":
    unittest.main()
