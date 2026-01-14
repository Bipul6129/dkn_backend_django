from django.urls import path

from .views import (
    TrainingCourseListCreateView,
    TrainingCourseDetailView,
    TrainingMaterialListCreateView,
    TrainingQuizView,
    SubmitQuizView,
    MyTrainingAttemptsView,
    TrainingQuestionListCreateView,
    TrainingQuestionDetailManageView,
    TrainingOptionListCreateView,
    TrainingOptionDetailManageView,
    TrainingMaterialDetailView,
    CourseLeaderboardView
)


urlpatterns = [
    path("courses/", TrainingCourseListCreateView.as_view(), name="training-course-list"),
    path("courses/<int:pk>/", TrainingCourseDetailView.as_view(), name="training-course-detail"),

    path(
        "courses/<int:course_id>/materials/",
        TrainingMaterialListCreateView.as_view(),
        name="training-materials",
    ),

    path(
        "materials/<int:material_id>/",
        TrainingMaterialDetailView.as_view(),
        name="training-material-detail",
    ),

    # learner quiz APIs
    path(
        "courses/<int:course_id>/quiz/",
        TrainingQuizView.as_view(),
        name="training-quiz",
    ),
    path(
        "courses/<int:course_id>/quiz/submit/",
        SubmitQuizView.as_view(),
        name="training-quiz-submit",
    ),

    # champion quiz management
    path(
        "courses/<int:course_id>/questions/",
        TrainingQuestionListCreateView.as_view(),
        name="training-question-list-create",
    ),
    path(
        "courses/<int:course_id>/questions/<int:question_id>/",
        TrainingQuestionDetailManageView.as_view(),
        name="training-question-detail-manage",
    ),
    path(
        "courses/<int:course_id>/questions/<int:question_id>/options/",
        TrainingOptionListCreateView.as_view(),
        name="training-option-list-create",
    ),
    path(
        "courses/<int:course_id>/questions/<int:question_id>/options/<int:option_id>/",
        TrainingOptionDetailManageView.as_view(),
        name="training-option-detail-manage",
    ),

    path("my-attempts/", MyTrainingAttemptsView.as_view(), name="training-my-attempts"),

    # 🏆 leaderboard
    path(
        "courses/<int:course_id>/leaderboard/",
        CourseLeaderboardView.as_view(),
        name="training-course-leaderboard",
    ),
]
