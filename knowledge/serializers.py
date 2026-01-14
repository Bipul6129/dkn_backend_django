import json
from rest_framework import serializers
from .models import KnowledgeResource, Tag, AIFlag, ReviewStep, KnowledgeResourceVersion

class AIFlagSerializer(serializers.ModelSerializer):
    version_number = serializers.IntegerField(source="version.version_number", read_only=True)

    class Meta:
        model = AIFlag
        fields = ["id", "flag_type", "severity", "message", "version_number", "created_at"]



class ReviewStepSerializer(serializers.ModelSerializer):
    reviewer_name = serializers.CharField(source="reviewer.username", read_only=True)
    version_number = serializers.IntegerField(source="version.version_number", read_only=True)

    class Meta:
        model = ReviewStep
        fields = ["id", "stage", "decision", "reviewer_name", "version_number", "comment", "created_at"]


class KnowledgeResourceCreateSerializer(serializers.ModelSerializer):
    file = serializers.FileField(write_only=True)

    # ✅ accept tags as string or list (multipart safe)
    tags = serializers.CharField(required=False, allow_blank=True, write_only=True)
    tags_display = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = KnowledgeResource
        fields = [
            "id",
            "title",
            "description",
            "region",        # still returned in response
            "metadata",
            "file",
            "tags",
            "tags_display",
            "status",
            "current_stage",
            "created_at",
        ]
        read_only_fields = [
            "status",
            "current_stage",
            "created_at",
            "tags_display",
            "region",       # 👈 IMPORTANT: region is now read-only
        ]

    def get_tags_display(self, obj):
        return list(obj.tags.values_list("name", flat=True))

    def _parse_tags(self):
        """
        Supports:
        1) form-data repeated keys: tags=one, tags=two  -> QueryDict.getlist('tags')
        2) JSON string: ["one","two"]
        3) comma string: one, two
        """
        data = self.initial_data

        # 1) repeated keys in multipart
        if hasattr(data, "getlist"):
            vals = data.getlist("tags")
            # if user only sent a single string, getlist returns ["tag1, tag2"] or ['["a","b"]']
            if len(vals) > 1:
                return vals

        raw = data.get("tags")
        if raw in (None, "", []):
            return []

        if isinstance(raw, list):
            return raw

        if isinstance(raw, str):
            s = raw.strip()
            if s.startswith("["):
                try:
                    parsed = json.loads(s)
                except json.JSONDecodeError:
                    raise serializers.ValidationError("tags must be a valid JSON list or comma-separated string.")
                if not isinstance(parsed, list):
                    raise serializers.ValidationError("tags JSON must be a list.")
                return parsed
            # comma separated
            return [t.strip() for t in s.split(",") if t.strip()]

        raise serializers.ValidationError("Invalid tags format.")

    def create(self, validated_data):
        file = validated_data.pop("file")
        tags_list = validated_data.pop("tags", [])
        metadata = validated_data.pop("metadata", {})

        user = self.context["request"].user

        # ✅ force region from the user's profile
        user_region = user.region
        if not user_region:
            raise serializers.ValidationError(
                {"region": "Your profile does not have a region configured."}
            )

        # make sure region is not coming from client
        validated_data.pop("region", None)

        resource = KnowledgeResource.objects.create(
            uploaded_by=user,
            metadata=metadata,
            region=user_region,   # 👈 set here
            **validated_data,
        )

        # ✅ tags handling (unchanged)
        if isinstance(tags_list, str):
            raw = tags_list.strip()
            if raw.startswith("["):
                try:
                    tags_list = json.loads(raw)
                except json.JSONDecodeError:
                    tags_list = [raw]
            else:
                tags_list = [t.strip() for t in raw.split(",") if t.strip()]

        if isinstance(tags_list, list) and len(tags_list) == 1 and isinstance(tags_list[0], str):
            raw = tags_list[0].strip()
            if raw.startswith("["):
                try:
                    parsed = json.loads(raw)
                    if isinstance(parsed, list):
                        tags_list = parsed
                except json.JSONDecodeError:
                    pass

        tag_objs = []
        for raw in tags_list:
            clean = " ".join(str(raw).strip().split()).lower()
            if clean:
                tag, _ = Tag.objects.get_or_create(name=clean)
                tag_objs.append(tag)

        resource.tags.set(tag_objs)

        # create v1 (unchanged)
        v1 = KnowledgeResourceVersion.objects.create(
            resource=resource,
            version_number=1,
            file=file,
            created_by=user,
        )
        resource.latest_version = v1
        resource.save(update_fields=["latest_version"])

        return resource



class ReviewDecisionSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(
        choices=["APPROVED", "REJECTED", "FLAGGED", "CHANGES_REQUESTED"]
    )
    comments = serializers.CharField(required=False, allow_blank=True, max_length=2000)

class KnowledgeResourceVersionSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source="created_by.username", read_only=True)

    class Meta:
        model = KnowledgeResourceVersion
        fields = ["id", "version_number", "file", "notes", "created_by_name", "created_at"]


class KnowledgeResourceDetailSerializer(serializers.ModelSerializer):
    tags_display = serializers.SerializerMethodField()

    # ✅ show exactly what is under review
    submitted_file = serializers.FileField(source="submitted_version.file", read_only=True)
    submitted_version_number = serializers.IntegerField(source="submitted_version.version_number", read_only=True)

    # (optional) still show latest
    latest_file = serializers.FileField(source="latest_version.file", read_only=True)

    versions = KnowledgeResourceVersionSerializer(many=True, read_only=True)
    ai_flags = serializers.SerializerMethodField()
    review_steps = ReviewStepSerializer(many=True, read_only=True)


    def get_ai_flags(self, obj):
        qs = obj.ai_flags.all()
        if obj.submitted_version_id:
            qs = qs.filter(version_id=obj.submitted_version_id)
        return AIFlagSerializer(qs, many=True).data


    class Meta:
        model = KnowledgeResource
        fields = [
            "id", "title", "description", "region", "metadata",
            "status", "current_stage", "submitted_at",
            "tags_display",
            "submitted_version_number", "submitted_file",   # ✅
            "latest_file",
            "versions",
            "ai_flags",
            "created_at", "updated_at","review_steps"
        ]

    def get_tags_display(self, obj):
        return list(obj.tags.values_list("name", flat=True))

class KnowledgeResourceQueueSerializer(serializers.ModelSerializer):
    tags_display = serializers.SerializerMethodField()
    submitted_file = serializers.FileField(
        source="submitted_version.file", read_only=True
    )
    submitted_version_number = serializers.IntegerField(
        source="submitted_version.version_number", read_only=True
    )
    latest_file = serializers.FileField(
        source="latest_version.file", read_only=True
    )
    latest_version_number = serializers.IntegerField(
        source="latest_version.version_number", read_only=True
    )
    ai_flags = serializers.SerializerMethodField()

    class Meta:
        model = KnowledgeResource
        fields = [
            "id", "title", "description", "region", "metadata",
            "status", "current_stage", "submitted_at",
            "tags_display",
            "submitted_version_number", "submitted_file",
            "latest_version_number", "latest_file",
            "ai_flags",
            "created_at", "updated_at",
        ]


    def get_tags_display(self, obj):
        return list(obj.tags.values_list("name", flat=True))

    def get_ai_flags(self, obj):
        qs = obj.ai_flags.all()
        if obj.submitted_version_id:
            qs = qs.filter(version_id=obj.submitted_version_id)
        return AIFlagSerializer(qs, many=True).data
    

class MyReviewActionSerializer(serializers.ModelSerializer):
    # ---- fields from related resource ----
    resource_id = serializers.IntegerField(source="resource.id", read_only=True)
    title = serializers.CharField(source="resource.title", read_only=True)
    region = serializers.CharField(source="resource.region", read_only=True)
    status = serializers.CharField(source="resource.status", read_only=True)
    current_stage = serializers.CharField(source="resource.current_stage", read_only=True)

    submitted_version_number = serializers.SerializerMethodField()
    latest_version_number = serializers.SerializerMethodField()

    tags_display = serializers.SerializerMethodField()
    submitted_file = serializers.SerializerMethodField()
    latest_file = serializers.SerializerMethodField()
    ai_flags = serializers.SerializerMethodField()

    version_number = serializers.SerializerMethodField()

    class Meta:
        model = ReviewStep
        fields = [
            # review-step info
            "id",
            "stage",
            "decision",
            "comment",
            "created_at",
            "version_number",

            # resource summary
            "resource_id",
            "title",
            "region",
            "status",
            "current_stage",
            "submitted_version_number",
            "latest_version_number",
            "tags_display",
            "submitted_file",
            "latest_file",
            "ai_flags",
        ]

    # ---------- review-step helpers ----------

    def get_version_number(self, obj):
        if obj.version_id and obj.version:
          return obj.version.version_number
        return None

    # ---------- resource helpers ----------

    def get_submitted_version_number(self, obj):
        r = obj.resource
        if r.submitted_version_id and r.submitted_version:
            return r.submitted_version.version_number
        return None

    def get_latest_version_number(self, obj):
        r = obj.resource
        if r.latest_version_id and r.latest_version:
            return r.latest_version.version_number
        return None

    def get_tags_display(self, obj):
        return list(obj.resource.tags.values_list("name", flat=True))

    def get_submitted_file(self, obj):
        r = obj.resource
        sv = getattr(r, "submitted_version", None)
        if not sv or not sv.file:
            return None
        try:
            return sv.file.url
        except ValueError:
            return None

    def get_latest_file(self, obj):
        r = obj.resource
        lv = getattr(r, "latest_version", None)
        if not lv or not lv.file:
            return None
        try:
            return lv.file.url
        except ValueError:
            return None

    def get_ai_flags(self, obj):
        """
        Simple inline serializer for AI flags associated with this resource.
        If there is a submitted_version, we only show flags for that version.
        Otherwise, we show all flags.
        """
        r = obj.resource
        qs = r.ai_flags.all()
        if r.submitted_version_id:
            qs = qs.filter(version_id=r.submitted_version_id)

        return [
            {
                "id": f.id,
                "flag_type": f.flag_type,
                "severity": f.severity,
                "message": f.message,
                "version_number": f.version.version_number if f.version_id else None,
                "created_at": f.created_at,
            }
            for f in qs.order_by("-created_at")
        ]
