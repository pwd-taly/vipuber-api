import os
import unittest

os.environ.setdefault("VIPUBER_EMAIL", "test@example.com")
os.environ.setdefault("VIPUBER_PASSWORD", "test")
os.environ.setdefault("API_KEY", "test-key")

from fastapi import HTTPException

import main
import parsers
from models import BookTransferRequest


class FakeSession:
    def __init__(self, vehicle_html=None):
        self.vehicle_html = vehicle_html or """
            <input value="1" name="aracid" checked>
            <input value="2500" name="fiyatal1">
            <input value="MERCEDES VITO" name="baslikal1">
            <label for="aracid1">Mercedes Vito</label>
        """
        self.posts = []

    def post(self, path, data):
        self.posts.append((path, data.copy()))
        if path == "/modul/rezer/ajax.php":
            return self.vehicle_html
        if path == "/modul/rezer/tamamla.php":
            return "<html>ok</html>"
        if path == "/modul/rezer/ajaxislem.php":
            return '<div class="tamam_div">Reservation saved</div>'
        return ""


def request():
    return BookTransferRequest(
        pickup="İSTANBUL HAVALİMANI",
        destination="BEŞİKTAŞ",
        date="25.07.2026",
        time="14:30",
        first_name="Ada",
        last_name="Lovelace",
        phone="+905551112233",
        passenger_count=1,
        payment_method="1",
        currency="1",
    )


class BookingPipelineTests(unittest.TestCase):
    def setUp(self):
        self.original_get_session = main._get_session_or_raise
        main._booking_dedup.clear()

    def tearDown(self):
        main._get_session_or_raise = self.original_get_session
        main._booking_dedup.clear()

    def test_vehicle_parser_accepts_value_before_name(self):
        html = """
            <input value="7" checked name="aracid">
            <input value="3150" name="fiyatal7">
            <input value="VIP VAN" name="baslikal7">
            <label for="aracid7">VIP Van</label>
        """

        vehicles = parsers.parse_vehicle_options(html)

        self.assertEqual(vehicles[0]["id"], "7")
        self.assertEqual(vehicles[0]["price"], "3150")
        self.assertTrue(vehicles[0]["is_selected"])

    def test_book_transfer_submits_php_date_and_price_fields(self):
        fake = FakeSession()
        main._get_session_or_raise = lambda *args, **kwargs: fake

        result = main.book_transfer(request())

        self.assertEqual(result["status"], "success")
        final_payload = next(data for path, data in fake.posts if path == "/modul/rezer/ajaxislem.php")
        self.assertEqual(final_payload["alistarihi"], "2026-07-25")
        self.assertEqual(final_payload["totalucret"], "2500")
        self.assertEqual(final_payload["ucret"], "2500")

        with self.assertRaises(HTTPException) as ctx:
            main.book_transfer(request())
        self.assertEqual(ctx.exception.status_code, 409)

    def test_failed_booking_attempt_does_not_poison_retry_cache(self):
        empty_vehicle_session = FakeSession(vehicle_html="<html>No vehicles</html>")
        main._get_session_or_raise = lambda *args, **kwargs: empty_vehicle_session

        with self.assertRaises(HTTPException) as ctx:
            main.book_transfer(request())
        self.assertEqual(ctx.exception.status_code, 502)

        working_session = FakeSession()
        main._get_session_or_raise = lambda *args, **kwargs: working_session
        result = main.book_transfer(request())

        self.assertEqual(result["status"], "success")


if __name__ == "__main__":
    unittest.main()
