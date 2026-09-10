from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthView(APIView):
    """Unauthenticated liveness probe used by Docker / load balancers."""

    authentication_classes: list = []
    permission_classes = [AllowAny]

    @extend_schema(
        responses={200: {"type": "object", "properties": {"status": {"type": "string"}}}}
    )
    def get(self, request):
        return Response({"status": "ok"})
