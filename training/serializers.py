# serializers.py
from rest_framework import serializers

from .models import (
    TrainingCourse,
    TrainingMaterial,
    TrainingQuestion,
    TrainingOption,
    TrainingAttempt,
)


class TrainingMaterialSerializer(serializers.ModelSerializer):
    class Meta:
        model = TrainingMaterial
        fields = [
            "id",
            "title",
            "description",
            "file",
            "link_url",
            "order",
            "created_at",
        ]


class TrainingCourseListSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(
        source="created_by.username", read_only=True
    )
    # 👇 expose creator id for frontend checks
    created_by = serializers.IntegerField(
        source="created_by.id", read_only=True
    )

    class Meta:
        model = TrainingCourse
        fields = [
            "id",
            "title",
            "description",
            "status",
            "region",
            "created_by",       # 👈 added
            "created_by_name",
            "created_at",
            "updated_at",
        ]


class TrainingCourseDetailSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(
        source="created_by.username", read_only=True
    )
    created_by = serializers.IntegerField(
        source="created_by.id", read_only=True
    )
    materials = TrainingMaterialSerializer(many=True, read_only=True)

    class Meta:
        model = TrainingCourse
        fields = [
            "id",
            "title",
            "description",
            "status",
            "region",
            "created_by",       # 👈 added
            "created_by_name",
            "created_at",
            "updated_at",
            "materials",
        ]


# -------- Quiz serializers --------

class TrainingOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = TrainingOption
        fields = ["id", "text"]  # deliberately exclude is_correct


class TrainingQuestionSerializer(serializers.ModelSerializer):
    options = TrainingOptionSerializer(many=True, read_only=True)

    class Meta:
        model = TrainingQuestion
        fields = ["id", "text", "order", "options"]


class TrainingAttemptSerializer(serializers.ModelSerializer):
    course_title = serializers.CharField(source="course.title", read_only=True)

    class Meta:
        model = TrainingAttempt
        fields = [
            "id",
            "course",
            "course_title",
            "score",
            "total_questions",
            "is_passed",
            "submitted_at",
        ]


class QuizAnswerInputSerializer(serializers.Serializer):
    question = serializers.IntegerField()
    option = serializers.IntegerField()


class QuizSubmitSerializer(serializers.Serializer):
    """
    Expected payload: { "answers": [ { "question": 1, "option": 5 }, ... ] }
    """
    answers = QuizAnswerInputSerializer(many=True)


# --- EXTRA SERIALIZERS FOR MANAGING QUIZ (Champion use) ---

class TrainingOptionManageSerializer(serializers.ModelSerializer):
    """
    Used by Champions to create/update options, including is_correct.
    """

    class Meta:
        model = TrainingOption
        fields = ["id", "text", "is_correct"]


class TrainingQuestionManageSerializer(serializers.ModelSerializer):
    """
    For Champions when managing questions.
    Includes options with is_correct.
    """
    options = TrainingOptionManageSerializer(many=True, read_only=True)

    class Meta:
        model = TrainingQuestion
        fields = ["id", "text", "order", "options"]

class CourseLeaderboardEntrySerializer(serializers.ModelSerializer):
    """
    One row in the course leaderboard, based on a single best attempt per user.
    """
    user_id = serializers.IntegerField(source="user.id", read_only=True)
    username = serializers.CharField(source="user.username", read_only=True)
    percent = serializers.SerializerMethodField()

    class Meta:
        model = TrainingAttempt
        fields = [
            "user_id",
            "username",
            "score",
            "total_questions",
            "percent",
            "is_passed",
            "submitted_at",
        ]

    def get_percent(self, obj):
        if not obj.total_questions:
            return 0.0
        return round((obj.score / obj.total_questions) * 100.0, 2)