# collaboration/serializers.py
from rest_framework import serializers
from django.contrib.auth import get_user_model

from .models import Project, ProjectAssignment, CollaborationSpace, CollaborationPost

User = get_user_model()


class SimpleUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "email"]


class ProjectAssignmentSerializer(serializers.ModelSerializer):
    user = SimpleUserSerializer(read_only=True)
    user_id = serializers.PrimaryKeyRelatedField(
        source="user",
        queryset=User.objects.all(),
        write_only=True
    )

    class Meta:
        model = ProjectAssignment
        fields = [
            "id",
            "project",
            "user",
            "user_id",
            "role",
            "assigned_at",
        ]
        read_only_fields = ["id", "project", "user", "assigned_at"]


class ProjectListSerializer(serializers.ModelSerializer):
    lead = SimpleUserSerializer(read_only=True)
    members_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Project
        fields = [
            "id",
            "name",
            "client",
            "status",
            "region",
            "lead",
            "members_count",
            "created_at",
        ]


class ProjectDetailSerializer(serializers.ModelSerializer):
    lead = SimpleUserSerializer(read_only=True)
    assignments = ProjectAssignmentSerializer(many=True, read_only=True)

    class Meta:
        model = Project
        fields = [
            "id",
            "name",
            "client",
            "description",
            "status",
            "region",
            "created_by",
            "lead",
            "assignments",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_by", "lead", "assignments",
                            "created_at", "updated_at"]


class CollaborationSpaceSerializer(serializers.ModelSerializer):
    class Meta:
        model = CollaborationSpace
        fields = [
            "id",
            "project",
            "title",
            "description",
            "created_by",
            "is_default",
            "created_at",
        ]
        read_only_fields = ["id", "project", "created_by", "created_at"]



class CollaborationPostSerializer(serializers.ModelSerializer):
    author = SimpleUserSerializer(read_only=True)

    class Meta:
        model = CollaborationPost
        fields = [
            "id",
            "space",
            "author",
            "message",
            "file",
            "created_at",
        ]
        read_only_fields = ["id", "space", "author", "created_at"]

    def validate(self, attrs):
        """
        Require at least a message or a file.
        """
        message = attrs.get("message", "").strip()
        file = attrs.get("file")

        if not message and not file:
            raise serializers.ValidationError(
                "You must provide a message, a file, or both."
            )
        return attrs

class UserMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "email"]
