from django.test import SimpleTestCase
from rest_framework import serializers
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny
from rest_framework.test import APIRequestFactory

from apps.common.pagination import StandardPagination


class _ItemSerializer(serializers.Serializer):
    value = serializers.IntegerField()


class _ListView(ListAPIView):
    permission_classes = [AllowAny]
    authentication_classes: list = []
    pagination_class = StandardPagination
    serializer_class = _ItemSerializer
    queryset = [{"value": i} for i in range(150)]


class StandardPaginationTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = _ListView.as_view()

    def test_envelope_shape(self):
        response = self.view(self.factory.get("/items/"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.data.keys()), {"data", "meta"})
        self.assertEqual(set(response.data["meta"].keys()), {"count", "next", "previous"})
        self.assertEqual(response.data["meta"]["count"], 150)
        self.assertEqual(len(response.data["data"]), 20)
        self.assertIsNone(response.data["meta"]["previous"])
        self.assertIsNotNone(response.data["meta"]["next"])

    def test_page_and_page_size_params(self):
        response = self.view(self.factory.get("/items/", {"page": 2, "page_size": 10}))
        self.assertEqual(len(response.data["data"]), 10)
        self.assertEqual(response.data["data"][0]["value"], 10)
        self.assertIsNotNone(response.data["meta"]["previous"])

    def test_page_size_capped_at_max(self):
        response = self.view(self.factory.get("/items/", {"page_size": 1000}))
        self.assertEqual(len(response.data["data"]), 100)
