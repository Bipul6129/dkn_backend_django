from django.urls import path
from .views import ProfileView,RegionListView

urlpatterns = [
    path("profile/", ProfileView.as_view(), name="profile"),
    path("regions/", RegionListView.as_view(), name="region-list"),
]
