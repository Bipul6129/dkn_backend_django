from django.contrib import admin
from .models import (
    TrainingCourse,
    TrainingMaterial,
    TrainingQuestion,
    TrainingOption,
    TrainingAttempt,
    TrainingAttemptAnswer,
)


class TrainingMaterialInline(admin.TabularInline):
    model = TrainingMaterial
    extra = 0


class TrainingQuestionInline(admin.TabularInline):
    model = TrainingQuestion
    extra = 0


@admin.register(TrainingCourse)
class TrainingCourseAdmin(admin.ModelAdmin):
    list_display = ("title", "region", "status", "created_by", "created_at")
    list_filter = ("region", "status")
    search_fields = ("title", "description")
    inlines = [TrainingMaterialInline, TrainingQuestionInline]


@admin.register(TrainingQuestion)
class TrainingQuestionAdmin(admin.ModelAdmin):
    list_display = ("text", "course", "order")
    inlines = []


@admin.register(TrainingOption)
class TrainingOptionAdmin(admin.ModelAdmin):
    list_display = ("text", "question", "is_correct")


@admin.register(TrainingMaterial)
class TrainingMaterialAdmin(admin.ModelAdmin):
    list_display = ("title", "course", "order")


@admin.register(TrainingAttempt)
class TrainingAttemptAdmin(admin.ModelAdmin):
    list_display = ("user", "course", "score", "total_questions", "is_passed", "submitted_at")
    list_filter = ("is_passed", "course")


@admin.register(TrainingAttemptAnswer)
class TrainingAttemptAnswerAdmin(admin.ModelAdmin):
    list_display = ("attempt", "question", "selected_option")
