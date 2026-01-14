# collaboration/views.py
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404

from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Project, ProjectAssignment, CollaborationSpace,CollaborationPost
from .serializers import (
    ProjectListSerializer,
    ProjectDetailSerializer,
    ProjectAssignmentSerializer,
    CollaborationSpaceSerializer,
    CollaborationPostSerializer,
)
from rest_framework.parsers import MultiPartParser, FormParser
from django.contrib.auth import get_user_model
from .models import Project
from .serializers import UserMiniSerializer

User = get_user_model()



class IsAuthenticated(permissions.IsAuthenticated):
    pass


# --------- helper functions ---------

def is_project_member(project: Project, user) -> bool:
    return ProjectAssignment.objects.filter(project=project, user=user).exists()


# collaboration/utils.py (or in views.py directly)

def is_project_lead(project, user):
    # In your real model, the "lead" is the creator
    return project.created_by_id == user.id


# collaboration/utils.py (or in views.py directly)


# --------- Project list / create / mine ---------

class ProjectListCreateView(APIView):
    """
    GET /api/collab/projects/       -> list all projects (for now)
    POST /api/collab/projects/      -> create project (creator becomes LEAD)
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        qs = (
            Project.objects
            .filter(
                Q(assignments__user=user) | Q(created_by=user)
            )
            .annotate(members_count=Count("assignments"))
            .select_related("created_by")
            .distinct()
        )


        serializer = ProjectListSerializer(qs, many=True)
        return Response(serializer.data)

    @transaction.atomic
    def post(self, request):
        data = request.data.copy()
        data["created_by"] = request.user.id

        serializer = ProjectDetailSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        project = serializer.save(created_by=request.user)

        # creator becomes lead
        ProjectAssignment.objects.create(
            project=project,
            user=request.user,
            role=ProjectAssignment.Role.LEAD,
        )

        # re-serialize with assignments
        out = ProjectDetailSerializer(project)
        return Response(out.data, status=status.HTTP_201_CREATED)


class MyProjectsView(APIView):
    """
    GET /api/collab/projects/mine/
    -> projects where current user is a member (lead or member).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = (
            Project.objects
            .filter(assignments__user=request.user)
            .annotate(members_count=Count("assignments"))
            .distinct()
        )
        serializer = ProjectListSerializer(qs, many=True)
        return Response(serializer.data)


class ProjectDetailView(APIView):
    """
    GET    /api/collab/projects/{project_id}/
    PATCH  /api/collab/projects/{project_id}/
    DELETE /api/collab/projects/{project_id}/
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, project_id):
        project = get_object_or_404(
            Project.objects.select_related("created_by"),
            id=project_id,
        )

        if not is_project_member(project, request.user):
            return Response(
                {"detail": "You are not a member of this project."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = ProjectDetailSerializer(project)
        return Response(serializer.data)

    @transaction.atomic
    def patch(self, request, project_id):
        project = get_object_or_404(
            Project.objects.select_related("created_by"),
            id=project_id,
        )

        if not is_project_lead(project, request.user):
            return Response(
                {"detail": "Only the project lead can update the project."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = ProjectDetailSerializer(project, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @transaction.atomic
    def delete(self, request, project_id):
        project = get_object_or_404(
            Project.objects.select_related("created_by"),
            id=project_id,
        )

        if not is_project_lead(project, request.user):
            return Response(
                {"detail": "Only the project lead can delete this project."},
                status=status.HTTP_403_FORBIDDEN,
            )

        project.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# --------- Team membership (ProjectAssignment) ---------

class ProjectAssignmentsView(APIView):
    """
    GET  /api/collab/projects/{project_id}/assignments/   -> list team
    POST /api/collab/projects/{project_id}/assignments/   -> add/update member
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, project_id):
        project = get_object_or_404(Project, id=project_id)

        if not is_project_member(project, request.user):
            return Response(
                {"detail": "You are not a member of this project."},
                status=status.HTTP_403_FORBIDDEN,
            )

        qs = project.assignments.select_related("user")
        serializer = ProjectAssignmentSerializer(qs, many=True)
        return Response(serializer.data)

    @transaction.atomic
    def post(self, request, project_id):
        project = get_object_or_404(Project, id=project_id)

        # only the lead can manage team for now
        if not is_project_lead(project, request.user):
            return Response(
                {"detail": "Only the project lead can manage team members."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = ProjectAssignmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]

        role = serializer.validated_data.get("role", ProjectAssignment.Role.MEMBER)

        # upsert: if already assigned, just update role
        assignment, created = ProjectAssignment.objects.update_or_create(
            project=project,
            user=user,
            defaults={"role": role},
        )

        # if they tried to set a second LEAD, DB will raise IntegrityError
        # but we give a nicer message:
        if role == ProjectAssignment.Role.LEAD:
            # check if there is another lead with a different user
            other_lead = (
                ProjectAssignment.objects
                .filter(project=project, role=ProjectAssignment.Role.LEAD)
                .exclude(user=user)
                .exists()
            )
            if other_lead:
                return Response(
                    {"detail": "This project already has a different lead."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        out = ProjectAssignmentSerializer(assignment)
        return Response(
            out.data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class ProjectAssignmentDeleteView(APIView):
    """
    DELETE /api/collab/projects/{project_id}/assignments/{user_id}/
    """
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def delete(self, request, project_id, user_id):
        project = get_object_or_404(Project, id=project_id)

        if not is_project_lead(project, request.user):
            return Response(
                {"detail": "Only the project lead can remove team members."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # prevent removing yourself if you are the only lead
        assignment = get_object_or_404(
            ProjectAssignment,
            project=project,
            user_id=user_id,
        )

        if assignment.role == ProjectAssignment.Role.LEAD:
            return Response(
                {"detail": "You cannot remove the current project lead."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        assignment.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# --------- Collaboration spaces ---------

class CollaborationSpaceListCreateView(APIView):
    """
    GET  /api/collab/projects/{project_id}/spaces/   -> list spaces
    POST /api/collab/projects/{project_id}/spaces/   -> create space
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, project_id):
        project = get_object_or_404(Project, id=project_id)

        if not is_project_member(project, request.user):
            return Response(
                {"detail": "You are not a member of this project."},
                status=status.HTTP_403_FORBIDDEN,
            )

        qs = project.spaces.all()
        serializer = CollaborationSpaceSerializer(qs, many=True)
        return Response(serializer.data)

    @transaction.atomic
    def post(self, request, project_id):
        project = get_object_or_404(Project, id=project_id)

        if not is_project_member(project, request.user):
            return Response(
                {"detail": "Only project members can create spaces."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = CollaborationSpaceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        space = serializer.save(
            project=project,
            created_by=request.user,
        )

        out = CollaborationSpaceSerializer(space)
        return Response(out.data, status=status.HTTP_201_CREATED)


class CollaborationSpaceDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, space_id):
        space = get_object_or_404(
            CollaborationSpace.objects.select_related("project", "project__created_by"),
            id=space_id,
        )
        project = space.project

        if not is_project_member(project, request.user):
            return Response(
                {"detail": "You are not a member of this project."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = CollaborationSpaceSerializer(space)
        return Response(serializer.data)

    @transaction.atomic
    def patch(self, request, space_id):
        space = get_object_or_404(
            CollaborationSpace.objects.select_related("project", "project__created_by"),
            id=space_id,
        )
        project = space.project

        if not is_project_lead(project, request.user):
            return Response(
                {"detail": "Only the project lead can update this space."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = CollaborationSpaceSerializer(space, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @transaction.atomic
    def delete(self, request, space_id):
        space = get_object_or_404(
            CollaborationSpace.objects.select_related("project", "project__created_by"),
            id=space_id,
        )
        project = space.project

        if not is_project_lead(project, request.user):
            return Response(
                {"detail": "Only the project lead can delete this space."},
                status=status.HTTP_403_FORBIDDEN,
            )

        space.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

# collaboration/views.py  (add near the CollaborationSpace views)

class CollaborationSpacePostsView(APIView):
    """
    GET  /api/collab/spaces/{space_id}/posts/   -> list posts in a space
    POST /api/collab/spaces/{space_id}/posts/   -> create message/file post
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]  # to handle file uploads

    def get(self, request, space_id):
        space = get_object_or_404(
            CollaborationSpace.objects.select_related("project"),
            id=space_id,
        )

        if not is_project_member(space.project, request.user):
            return Response(
                {"detail": "You are not a member of this project."},
                status=status.HTTP_403_FORBIDDEN,
            )

        qs = space.posts.select_related("author").all()
        serializer = CollaborationPostSerializer(qs, many=True)
        return Response(serializer.data)

    @transaction.atomic
    def post(self, request, space_id):
        space = get_object_or_404(
            CollaborationSpace.objects.select_related("project"),
            id=space_id,
        )

        if not is_project_member(space.project, request.user):
            return Response(
                {"detail": "Only project members can post in this space."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = CollaborationPostSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        post = serializer.save(space=space, author=request.user)
        out = CollaborationPostSerializer(post)
        return Response(out.data, status=status.HTTP_201_CREATED)


class CollaborationPostDetailView(APIView):
    """
    DELETE /api/collab/spaces/{space_id}/posts/{post_id}/
    -> author or project lead can delete
    """
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def delete(self, request, space_id, post_id):
        space = get_object_or_404(
            CollaborationSpace.objects.select_related("project"),
            id=space_id,
        )
        project = space.project

        post = get_object_or_404(
            CollaborationPost.objects.select_related("author", "space"),
            id=post_id,
            space=space,
        )

        if not (
            post.author_id == request.user.id or is_project_lead(project, request.user)
        ):
            return Response(
                {"detail": "Only the author or project lead can delete this post."},
                status=status.HTTP_403_FORBIDDEN,
            )

        post.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)



class ProjectAvailableUsersView(APIView):
    """
    List users who are NOT yet assigned to this project.
    Only the project lead can see this.
    """
    permission_classes = [IsAuthenticated]  # add your custom perms if you like

    def get(self, request, project_id):
        project = get_object_or_404(Project, id=project_id)

        # Only lead can view available users
        if not project.lead != request.user.id:
            return Response(
                {"detail": "Only the project lead can view available users."},
                status=403,
            )

        assigned_user_ids = project.assignments.values_list("user_id", flat=True)
        qs = User.objects.exclude(id__in=assigned_user_ids).order_by("username")

        serializer = UserMiniSerializer(qs, many=True)
        return Response(serializer.data, status=200)