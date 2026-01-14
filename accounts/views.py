from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from .serializers import UserProfileSerializer
from .models import Region

class ProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserProfileSerializer(request.user).data)

class RegionListView(APIView):
    permission_classes = [IsAuthenticated]  # or allow any if needed

    def get(self, request):
        regions = [
            {"value": choice.value, "label": choice.label}
            for choice in Region
        ]
        return Response(regions)