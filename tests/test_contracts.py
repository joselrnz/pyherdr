import unittest

from pydantic import ValidationError

from pyherdr.contracts.api import ApiError, ApiRequest, ApiResponse


class ApiContractTests(unittest.TestCase):
    def test_api_request_defaults_params(self):
        request = ApiRequest(id="1", method="ping")

        self.assertEqual(request.params, {})

    def test_api_request_rejects_empty_method(self):
        with self.assertRaises(ValidationError):
            ApiRequest(id="1", method=" ")

    def test_api_response_allows_result_or_error(self):
        ok = ApiResponse(id="1", result={"type": "pong"})
        err = ApiResponse(id="1", error=ApiError(code="bad", message="nope"))

        self.assertEqual(ok.result["type"], "pong")
        self.assertEqual(err.error.code, "bad")


if __name__ == "__main__":
    unittest.main()
