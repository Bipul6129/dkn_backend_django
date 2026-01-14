from django.urls import path
from .views import (
    KnowledgeResourceUploadView,
    SubmitForReviewView,
    ReviewQueueView,
    ReviewDecisionView,
    UploadNewVersionView,
    PublishResourceView,
    UnpublishResourceView,
    KnowledgeResourceDetailView,
    MyResourcesView,
    PublishedResourcesView,
    TagListView,
    MyReviewActionsView
)

urlpatterns = [
    # Create resource (v1)
    path("upload/", KnowledgeResourceUploadView.as_view(), name="resource-create"),

    # Upload new version (v2+)
    path("resources/<int:resource_id>/versions/", UploadNewVersionView.as_view(), name="resource-version-upload"),

    # Submit latest version for review
    path("resources/<int:resource_id>/submit/", SubmitForReviewView.as_view(), name="resource-submit"),

    # Stage queue
    path("review-queue/", ReviewQueueView.as_view(), name="review-queue"),

    # Decision at stage
    path("resources/<int:resource_id>/decision/", ReviewDecisionView.as_view(), name="resource-decision"),

    #Publish
    path("resources/<int:resource_id>/publish/", PublishResourceView.as_view(), name="resource-publish"),
    path("resources/published/", PublishedResourcesView.as_view(), name="resources-published"),

    #unpublish
    path("resources/<int:resource_id>/unpublish/", UnpublishResourceView.as_view(), name="resource-unpublish"),

    #knowledge_detail
    path("resources/<int:resource_id>/", KnowledgeResourceDetailView.as_view(), name="resource-detail"),

    #mine knowledge
    path("resources/mine/", MyResourcesView.as_view(), name="my-resources"),

    #TAGSS_VIEW
    path("tags/", TagListView.as_view(), name="tag-list"),

    #myactionreview
    path("review-actions/mine/",MyReviewActionsView.as_view(),name="my_review_actions",),


]
