"""Tests for scripts/places_normalize.py."""

import csv
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable


def run_normalize(*args):
    result = subprocess.run(
        [PYTHON, "scripts/places_normalize.py", *args],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    return json.loads(result.stdout), result.returncode


def write_temp_json(data):
    handle = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    json.dump(data, handle)
    handle.close()
    return handle.name


class TestGoogleNormalization:
    def test_normalize_google_place(self):
        google_data = {
            "places": [
                {
                    "id": "ChIJ_test123",
                    "displayName": {"text": "Test Apparel"},
                    "primaryType": "clothing_store",
                    "types": ["clothing_store", "store", "point_of_interest"],
                    "rating": 4.2,
                    "userRatingCount": 500,
                    "priceLevel": "PRICE_LEVEL_MODERATE",
                    "formattedAddress": "123 Test Rd, New York, NY",
                    "location": {"latitude": 40.7412, "longitude": -73.9896},
                }
            ]
        }
        path = write_temp_json(google_data)
        try:
            out, code = run_normalize("--input", path, "--source", "google", "--area-label", "Flatiron")
            assert code == 0
            assert out["status"] == "ok"
            assert out["total_normalized"] == 1
            place = out["places"][0]
            assert place["place_id"] == "ChIJ_test123"
            assert place["name"] == "Test Apparel"
            assert place["primary_category"] == "clothing_store"
            assert place["price_level"] == "mid"
            assert place["area_label"] == "Flatiron"
            assert place["rating"] == 4.2
            assert place["review_count"] == 500
            assert "clothing_store" in place["tags"]
            assert "concept_type" not in place
            assert "is_chain" not in place
        finally:
            os.unlink(path)

    def test_google_fallback_summary_uses_inferred_area(self):
        google_data = {
            "places": [
                {
                    "id": "ChIJ_test456",
                    "displayName": {"text": "Fallback Mall"},
                    "primaryType": "shopping_mall",
                    "primaryTypeDisplayName": {"text": "Shopping Mall"},
                    "formattedAddress": "1 Test Rd, Si Lom, Bangkok",
                    "shortFormattedAddress": "1 Test Rd, Si Lom",
                    "addressDescriptor": {
                        "areas": [
                            {
                                "displayName": {"text": "Si Lom"},
                                "containment": "WITHIN",
                            }
                        ]
                    },
                    "location": {"latitude": 13.72, "longitude": 100.54},
                }
            ]
        }
        path = write_temp_json(google_data)
        try:
            out, code = run_normalize("--input", path, "--source", "google")
            assert code == 0
            place = out["places"][0]
            assert place["area_label"] == "Si Lom"
            assert place["summary"] == "Shopping Mall in Si Lom"
        finally:
            os.unlink(path)

    def test_google_area_prefers_address_components_over_landmarks(self):
        google_data = {
            "places": [
                {
                    "id": "ChIJ_test789",
                    "displayName": {"text": "Area Priority Mall"},
                    "primaryType": "shopping_mall",
                    "primaryTypeDisplayName": {"text": "Shopping Mall"},
                    "formattedAddress": "946 Rama IV Rd, Si Lom, Bangkok",
                    "addressComponents": [
                        {"shortText": "Si Lom", "types": ["sublocality_level_2", "political"]},
                        {"shortText": "Bang Rak", "types": ["sublocality_level_1", "political"]},
                    ],
                    "addressDescriptor": {
                        "areas": [
                            {"displayName": {"text": "Lumphini Park"}, "containment": "NEAR"}
                        ]
                    },
                    "location": {"latitude": 13.72, "longitude": 100.54},
                }
            ]
        }
        path = write_temp_json(google_data)
        try:
            out, code = run_normalize("--input", path, "--source", "google")
            assert code == 0
            place = out["places"][0]
            assert place["area_label"] == "Si Lom"
            assert place["summary"] == "Shopping Mall in Si Lom"
        finally:
            os.unlink(path)

    def test_drops_place_missing_id(self):
        google_data = {"places": [{"displayName": {"text": "No ID Place"}}]}
        path = write_temp_json(google_data)
        try:
            out, code = run_normalize("--input", path, "--source", "google")
            assert code == 0
            assert out["total_dropped"] == 1
            assert out["total_normalized"] == 0
        finally:
            os.unlink(path)


class TestCSVNormalization:
    def test_normalize_csv(self):
        handle = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="")
        writer = csv.DictWriter(
            handle,
            fieldnames=["place_id", "name", "category", "rating", "review_count", "price_level", "address", "lat", "lng"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "place_id": "csv_001",
                "name": "CSV Place",
                "category": "shoe_store",
                "rating": "4.0",
                "review_count": "100",
                "price_level": "mid",
                "address": "456 Test St",
                "lat": "40.73",
                "lng": "-73.99",
            }
        )
        handle.close()
        try:
            out, code = run_normalize("--input", handle.name, "--source", "csv")
            assert code == 0
            assert out["total_normalized"] == 1
            assert out["places"][0]["name"] == "CSV Place"
        finally:
            os.unlink(handle.name)


class TestJSONFallbackNormalization:
    def test_normalize_user_json(self):
        user_data = [{"place_id": "uj_001", "name": "User Place", "category": "book_store", "rating": 4.5}]
        path = write_temp_json(user_data)
        try:
            out, code = run_normalize("--input", path, "--source", "json")
            assert code == 0
            assert out["total_normalized"] == 1
        finally:
            os.unlink(path)
