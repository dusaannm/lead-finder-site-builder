import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import find_stock_photos
import lead_search

OPTIONS = lead_search.load_settings()["stock_photos"]
HIT = {
    "id": 7,
    "imageWidth": 4000,
    "imageHeight": 2500,
    "tags": "bread, bakery",
    "pageURL": "https://pixabay.com/photos/7",
    "user": "baker",
    "user_id": 9,
    "largeImageURL": "https://pixabay.com/get/7.jpg",
}


class Pixabay(unittest.TestCase):
    def test_a_hit_becomes_the_same_shape_as_a_pexels_photo(self):
        photo = find_stock_photos._photo_from_pixabay(HIT)
        self.assertEqual((photo["id"], photo["width"], photo["alt"]), (7, 4000, "bread, bakery"))
        self.assertEqual(photo["src"]["large"], HIT["largeImageURL"])
        self.assertTrue(find_stock_photos._acceptable(photo, OPTIONS))

    def test_a_repeated_search_is_served_from_the_cache(self):
        reply = mock.Mock(status_code=200)
        reply.json.return_value = {"hits": [HIT]}
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(find_stock_photos, "ROOT", Path(folder)):
            with mock.patch.object(find_stock_photos.requests, "get", return_value=reply) as get:
                first = find_stock_photos._search_pixabay("bread", "key", OPTIONS)
                second = find_stock_photos._search_pixabay("bread", "key", OPTIONS)
        self.assertEqual(get.call_count, 1)
        self.assertEqual(first, second)

    def test_a_refused_key_says_so_without_showing_it(self):
        reply = mock.Mock(status_code=400)
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(find_stock_photos, "ROOT", Path(folder)):
            with mock.patch.object(find_stock_photos.requests, "get", return_value=reply):
                with self.assertRaises(find_stock_photos.StockPhotoError) as caught:
                    find_stock_photos._search_pixabay("bread", "secret", OPTIONS)
        self.assertNotIn("secret", str(caught.exception))


class Provider(unittest.TestCase):
    def test_pixabay_is_used_when_pexels_has_no_key(self):
        keys = {"PEXELS_API_KEY": "", "PIXABAY_API_KEY": "abc"}
        with mock.patch.object(find_stock_photos, "load_dotenv"), mock.patch.dict(find_stock_photos.os.environ, keys):
            self.assertEqual(find_stock_photos._provider(), ("Pixabay", "abc"))


if __name__ == "__main__":
    unittest.main()
