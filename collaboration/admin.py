from django.contrib import admin
from .models import Project, ProjectAssignment, CollaborationSpace, CollaborationPost


class ProjectAssignmentInline(admin.TabularInline):
    model = ProjectAssignment
    extra = 1


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "client", "status", "region", "lead", "created_at")
    list_filter = ("status", "region")
    search_fields = ("name", "client")
    inlines = [ProjectAssignmentInline]


@admin.register(CollaborationSpace)
class CollaborationSpaceAdmin(admin.ModelAdmin):
    list_display = ("title", "project", "is_default", "created_at")
    list_filter = ("is_default", "project__region")
    search_fields = ("title", "project__name")

@admin.register(CollaborationPost)
class CollaborationPostAdmin(admin.ModelAdmin):
    list_display = ("space","author","message","file")