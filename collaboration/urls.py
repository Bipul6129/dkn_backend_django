# collaboration/urls.py
from django.urls import path

from . import views

urlpatterns = [
    # projects
    path("projects/", views.ProjectListCreateView.as_view(), name="project-list-create"),
    path("projects/mine/", views.MyProjectsView.as_view(), name="my-projects"),
    path("projects/<int:project_id>/", views.ProjectDetailView.as_view(), name="project-detail"),

    # team assignments
    path(
        "projects/<int:project_id>/assignments/",
        views.ProjectAssignmentsView.as_view(),
        name="project-assignments",
    ),
    path(
        "projects/<int:project_id>/assignments/<int:user_id>/",
        views.ProjectAssignmentDeleteView.as_view(),
        name="project-assignment-delete",
    ),

    # collaboration spaces
    path(
        "projects/<int:project_id>/spaces/",
        views.CollaborationSpaceListCreateView.as_view(),
        name="project-spaces",
    ),
    path(
        "spaces/<int:space_id>/",
        views.CollaborationSpaceDetailView.as_view(),
        name="space-detail",
    ),


    path(
        "projects/<int:project_id>/spaces/",
        views.CollaborationSpaceListCreateView.as_view(),
        name="project-spaces",
    ),
    path(
        "spaces/<int:space_id>/",
        views.CollaborationSpaceDetailView.as_view(),
        name="space-detail",
    ),

    # NEW: posts inside a space
    path(
        "spaces/<int:space_id>/posts/",
        views.CollaborationSpacePostsView.as_view(),
        name="space-posts",
    ),
    path(
        "spaces/<int:space_id>/posts/<int:post_id>/",
        views.CollaborationPostDetailView.as_view(),
        name="space-post-detail",
    ),

    path(
        "projects/<int:project_id>/available-users/",
        views.ProjectAvailableUsersView.as_view(),
        name="project-available-users",
    ),
]
