from django.contrib import admin
from .models import KnowledgeResource, Tag, AIFlag, ReviewStep, KnowledgeResourceVersion

admin.site.register(KnowledgeResource)
admin.site.register(Tag)
admin.site.register(AIFlag)
admin.site.register(ReviewStep)
admin.site.register(KnowledgeResourceVersion)
