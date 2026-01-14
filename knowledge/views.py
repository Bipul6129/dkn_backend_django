from django.db import transaction
from django.utils import timezone
from django.shortcuts import get_object_or_404
import json
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Q
from accounts.permissions import IsEmployee, IsChampion, IsOfficer, IsAdminRole, IsReviewer, IsGovCouncil
from .models import KnowledgeResource, ReviewStep, KnowledgeResourceVersion, Tag
from .serializers import ReviewDecisionSerializer, KnowledgeResourceCreateSerializer, KnowledgeResourceDetailSerializer, KnowledgeResourceQueueSerializer,MyReviewActionSerializer
from .ai_stub import run_ai_check
from django.db import transaction
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from accounts.models import Region



class SubmitForReviewView(APIView):
    permission_classes = [IsEmployee]

    @transaction.atomic
    def post(self, request, resource_id):
        resource = get_object_or_404(
            KnowledgeResource,
            id=resource_id,
            uploaded_by=request.user
        )

        if resource.status in [KnowledgeResource.Status.APPROVED, KnowledgeResource.Status.PUBLISHED]:
            return Response({"detail": "Cannot submit approved/published resources."}, status=400)

        if resource.status == KnowledgeResource.Status.PENDING_REVIEW:
            return Response({"detail": "Already submitted for review."}, status=400)

        if not resource.latest_version:
            return Response({"detail": "No file version uploaded yet. Upload a version first."}, status=400)

        # ✅ lock which version is being reviewed
        resource.submitted_version = resource.latest_version
        resource.status = KnowledgeResource.Status.PENDING_REVIEW
        resource.current_stage = KnowledgeResource.ReviewStage.CHAMPION
        resource.submitted_at = timezone.now()
        resource.save(update_fields=["submitted_version", "status", "current_stage", "submitted_at", "updated_at"])

        ReviewStep.objects.create(
            resource=resource,
            version=resource.submitted_version,  # ✅ important
            stage=ReviewStep.Stage.CHAMPION,
            decision=ReviewStep.Decision.SUBMITTED,
            reviewer=request.user,
            comment="Submitted for review"
        )

        # ✅ run AI against submitted version (not “latest”)
        run_ai_check(resource, version=resource.submitted_version)

        return Response(
            {"detail": "Submitted for review.", "status": resource.status, "stage": resource.current_stage,
             "submitted_version": resource.submitted_version.version_number},
            status=200
        )

class ReviewQueueView(APIView):
    """
    CHAMPION sees CHAMPION stage queue (only their region + GLOBAL)
    OFFICER sees REGIONAL_OFFICER stage queue (only their region + GLOBAL)
    GOV COUNCIL / ADMIN sees GOV_COUNCIL stage queue (all regions)
    """
    permission_classes = [IsReviewer]  # enforce inside

    def get(self, request):
        user = request.user

        # Determine stage + whether we should region-limit
        if IsChampion().has_permission(request, self):
            stage = KnowledgeResource.ReviewStage.CHAMPION
            limit_by_region = True
        elif IsOfficer().has_permission(request, self):
            stage = KnowledgeResource.ReviewStage.REGIONAL_OFFICER
            limit_by_region = True
        elif IsGovCouncil().has_permission(request, self) or IsAdminRole().has_permission(request, self):
            stage = KnowledgeResource.ReviewStage.GOV_COUNCIL
            limit_by_region = False  # council/admin see all
        else:
            return Response({"detail": "Not allowed."}, status=403)

        qs = KnowledgeResource.objects.filter(
            status=KnowledgeResource.Status.PENDING_REVIEW,
            current_stage=stage,
        )

        # Apply region filter for Champion / Officer
        if limit_by_region:
            user_region = getattr(user, "region", None)

            if user_region:
                # only resources for user's region OR GLOBAL
                qs = qs.filter(
                    Q(region=user_region) | Q(region=Region.GLOBAL)
                )
            else:
                # if somehow user has no region, show only GLOBAL
                qs = qs.filter(region=Region.GLOBAL)

        qs = qs.order_by("-submitted_at", "-created_at")

        return Response(KnowledgeResourceQueueSerializer(qs, many=True).data, status=200)



class ReviewDecisionView(APIView):
    """
    Decision at the current stage.
    APPROVED: advances to next stage, or final APPROVED after GOV_COUNCIL
    REJECTED: final REJECTED
    FLAGGED: final FLAGGED
    CHANGES_REQUESTED: back to DRAFT (optional)
    """
    permission_classes = [IsReviewer]  # enforce inside

    @transaction.atomic
    def post(self, request, resource_id):
        resource = get_object_or_404(KnowledgeResource, id=resource_id)

        if resource.status != KnowledgeResource.Status.PENDING_REVIEW:
            return Response({"detail": "Resource is not pending review."}, status=400)

        serializer = ReviewDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        decision = serializer.validated_data["decision"]
        comments = serializer.validated_data.get("comments", "")

        stage = resource.current_stage

        # ✅ Authorization by stage using your existing roles
        if stage == KnowledgeResource.ReviewStage.CHAMPION and not IsChampion().has_permission(request, self):
            return Response({"detail": "Only Champions can review at this stage."}, status=403)

        if stage == KnowledgeResource.ReviewStage.REGIONAL_OFFICER and not IsOfficer().has_permission(request, self):
            return Response({"detail": "Only Officers can review at this stage."}, status=403)

        if stage == KnowledgeResource.ReviewStage.GOV_COUNCIL and not IsGovCouncil().has_permission(request, self):
            return Response({"detail": "Only Admin (Gov Council) can review at this stage."}, status=403)

        if not resource.submitted_version:
            return Response({"detail": "No submitted_version found for this review. Submit the resource again."}, status=400)

        # ✅ Log step (always)
        ReviewStep.objects.create(
            resource=resource,
            version=resource.submitted_version,   # ✅ use submitted_version
            stage=stage,
            decision=decision,
            reviewer=request.user,
            comment=comments
        )



        # ✅ Apply state transitions
        if decision == ReviewStep.Decision.REJECTED:
            resource.status = KnowledgeResource.Status.REJECTED
            # resource.current_stage = KnowledgeResource.ReviewStage.CHAMPION   # ✅ reset
            resource.submitted_version = None                                 # ✅ clear lock
            resource.save(update_fields=["status", "submitted_version", "updated_at"])
            return Response({"detail": "Resource rejected."}, status=200)


        if decision == ReviewStep.Decision.FLAGGED:
            resource.status = KnowledgeResource.Status.FLAGGED
            # resource.current_stage = KnowledgeResource.ReviewStage.CHAMPION   # ✅ reset
            resource.submitted_version = None                                 # ✅ clear lock
            resource.save(update_fields=["status", "submitted_version", "updated_at"])
            return Response({"detail": "Resource flagged."}, status=200)


        if decision == ReviewStep.Decision.CHANGES_REQUESTED:
            resource.status = KnowledgeResource.Status.DRAFT
            # resource.current_stage = KnowledgeResource.ReviewStage.CHAMPION
            resource.submitted_version = None                                  # ✅ add this
            resource.save(update_fields=["status", "submitted_version", "updated_at"])
            return Response({"detail": "Changes requested. Sent back to draft."}, status=200)


        # APPROVED: advance
        if stage == KnowledgeResource.ReviewStage.CHAMPION:
            resource.current_stage = KnowledgeResource.ReviewStage.REGIONAL_OFFICER
            resource.save(update_fields=["current_stage", "updated_at"])
            return Response({"detail": "Approved. Sent to Officer stage."}, status=200)

        if stage == KnowledgeResource.ReviewStage.REGIONAL_OFFICER:
            resource.current_stage = KnowledgeResource.ReviewStage.GOV_COUNCIL
            resource.save(update_fields=["current_stage", "updated_at"])
            return Response({"detail": "Approved. Sent to Governance Council stage."}, status=200)

        if stage == KnowledgeResource.ReviewStage.GOV_COUNCIL:
            resource.status = KnowledgeResource.Status.APPROVED
            resource.save(update_fields=["status", "updated_at"])
            return Response({"detail": "Approved by Governance Council. Resource approved."}, status=200)

        return Response({"detail": "Unhandled stage."}, status=400)

class KnowledgeResourceUploadView(APIView):
    permission_classes = [IsEmployee]

    def post(self, request):
        serializer = KnowledgeResourceCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        resource = serializer.save()

        return Response(KnowledgeResourceDetailSerializer(resource).data, status=status.HTTP_201_CREATED)
   
class UploadNewVersionView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def _parse_tags_from_request(self, request):
        """
        Same behaviour as KnowledgeResourceCreateSerializer._parse_tags:

        Supports:
        1) form-data repeated keys: tags=one, tags=two  -> QueryDict.getlist('tags')
        2) JSON string: ["one","two"]
        3) comma string: one, two
        """
        data = request.data

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
                    raise ValueError("tags must be a valid JSON list or comma-separated string.")
                if not isinstance(parsed, list):
                    raise ValueError("tags JSON must be a list.")
                return parsed
            # comma separated
            return [t.strip() for t in s.split(",") if t.strip()]

        raise ValueError("Invalid tags format.")

    @transaction.atomic
    def post(self, request, resource_id):
        resource = get_object_or_404(
            KnowledgeResource,
            id=resource_id,
            uploaded_by=request.user
        )

        if resource.status not in [
            KnowledgeResource.Status.DRAFT,
            KnowledgeResource.Status.REJECTED,
            KnowledgeResource.Status.FLAGGED,
            KnowledgeResource.Status.APPROVED,
            KnowledgeResource.Status.CHANGE_REQUESTED
        ]:
            return Response(
                {"detail": "Cannot upload a new version while resource is in review/published."},
                status=400
            )


        # ---------
        # 1) Optional updates to resource fields
        # ---------
        title = request.data.get("title")
        description = request.data.get("description")
        region = request.data.get("region")  # optional, if you allow changing region
        metadata_raw = request.data.get("metadata")

        update_fields = []

        if title is not None:
            resource.title = title
            update_fields.append("title")

        if description is not None:
            resource.description = description
            update_fields.append("description")

        if region is not None:
            valid_regions = {c[0] for c in KnowledgeResource._meta.get_field("region").choices}
            if region not in valid_regions:
                return Response(
                    {"detail": f"Invalid region. Must be one of {sorted(valid_regions)}"},
                    status=400,
                )
            resource.region = region
            update_fields.append("region")

        if metadata_raw is not None:
            # metadata can be dict-like JSON string in multipart
            if metadata_raw in ("", None):
                resource.metadata = {}
            else:
                if isinstance(metadata_raw, str):
                    try:
                        parsed = json.loads(metadata_raw)
                    except json.JSONDecodeError:
                        return Response(
                            {"detail": "metadata must be valid JSON (use double quotes)."},
                            status=400,
                        )
                    if not isinstance(parsed, dict):
                        return Response(
                            {"detail": "metadata JSON must be an object."},
                            status=400,
                        )
                    resource.metadata = parsed
                elif isinstance(metadata_raw, dict):
                    resource.metadata = metadata_raw
                else:
                    return Response({"detail": "Invalid metadata format."}, status=400)
            update_fields.append("metadata")

        # ---------
        # 2) File is required for a new version
        # ---------
        new_file = request.FILES.get("file")
        if not new_file:
            return Response({"detail": "file is required."}, status=400)

        notes = request.data.get("notes", "")

        # ---------
        # 3) Create next version
        # ---------
        latest = resource.versions.order_by("-version_number").first()
        next_number = 1 if not latest else latest.version_number + 1

        new_version = KnowledgeResourceVersion.objects.create(
            resource=resource,
            version_number=next_number,
            file=new_file,
            notes=notes,
            created_by=request.user,
        )

        # ---------
        # 4) Update tags (optional) using same logic as create
        # ---------
        try:
            tags_list = self._parse_tags_from_request(request)
        except ValueError as e:
            return Response({"detail": str(e)}, status=400)

        if tags_list is not None:
            tag_objs = []
            for t in tags_list:
                clean = " ".join(str(t).strip().split()).lower()
                if not clean:
                    continue
                tag, _ = Tag.objects.get_or_create(name=clean)
                tag_objs.append(tag)

            resource.tags.set(tag_objs)  # replaces tags

        # ---------
        # 5) Update resource pointers/status
        # ---------
        resource.current_stage = KnowledgeResource.ReviewStage.CHAMPION
        resource.latest_version = new_version
        resource.status = KnowledgeResource.Status.DRAFT
        resource.submitted_version = None

        update_fields.extend(
            ["latest_version", "status", "submitted_version", "current_stage", "updated_at"]
        )
        resource.save(update_fields=list(set(update_fields)))

        return Response(
            {
                "detail": f"Uploaded version v{next_number}.",
                "latest_version": next_number,
                "resource_id": resource.id,
                "title": resource.title,
                "status": resource.status,
            },
            status=status.HTTP_201_CREATED,
        )



class PublishResourceView(APIView):
    """
    Only uploader can publish.
    Only APPROVED resources can be published.
    Sets status -> PUBLISHED.
    """
    permission_classes = [IsEmployee,IsGovCouncil]

    @transaction.atomic
    def post(self, request, resource_id):
        resource = get_object_or_404(KnowledgeResource, id=resource_id)

        # Only uploader can publish
        if resource.uploaded_by_id != request.user.id and request.user.role != "COUNCIL":
            return Response(
                {"detail": "Only the uploader or Council can publish this resource."},
                status=403,
            )


        if resource.status != KnowledgeResource.Status.APPROVED and resource.status != KnowledgeResource.Status.UNPUBLISHED:
            return Response({"detail": "Only APPROVED resources and unpublished can be published."}, status=400)

        resource.status = KnowledgeResource.Status.PUBLISHED
        resource.save(update_fields=["status", "updated_at"])

        # Optional audit step (recommended)
        ReviewStep.objects.create(
            resource=resource,
            version=resource.latest_version,
            stage=resource.current_stage,
            decision=ReviewStep.Decision.PUBLISHED,
            reviewer=request.user,
            comment="Published by uploader"
        )


        return Response({"detail": "Resource published.", "status": resource.status}, status=200)

# 3) GET /api/knowledge/resources/published/
# Supports filters: ?q=...&region=EU&tag=security
class PublishedResourcesView(APIView):
    permission_classes = [IsAuthenticated]  # you can make this public later if you want

    def get_base_queryset_for_user(self, user):
        """
        Base security filter:
        - Employee / Champion / Officer: only their region + GLOBAL
        - Council / Admin / others: all published
        """
        qs = KnowledgeResource.objects.filter(
            status=KnowledgeResource.Status.PUBLISHED
        )

        role = getattr(user, "role", None)
        region = getattr(user, "region", None)

        if role in ("EMPLOYEE", "CHAMPION", "OFFICER"):
            if region:
                qs = qs.filter(Q(region=region) | Q(region=Region.GLOBAL))
            else:
                # no region set on user → only GLOBAL content
                qs = qs.filter(region=Region.GLOBAL)

        # COUNCIL / ADMIN etc → no extra region restriction here
        return qs

    def get(self, request):
        q = (request.query_params.get("q") or "").strip()
        region_param = (request.query_params.get("region") or "").strip()
        tag = (request.query_params.get("tag") or "").strip().lower()

        # 1) start from base queryset respecting user region/role
        qs = self.get_base_queryset_for_user(request.user)

        # 2) optional extra region filter (only *within* allowed set)
        role = getattr(request.user, "role", None)
        user_region = getattr(request.user, "region", None)

        if region_param:
            if role in ("EMPLOYEE", "CHAMPION", "OFFICER"):
                # they can only filter between their region & GLOBAL
                allowed = {Region.GLOBAL}
                if user_region:
                    allowed.add(user_region)

                if region_param in allowed:
                    qs = qs.filter(region=region_param)
                # if region_param not allowed, just ignore it (stays in allowed qs)
            else:
                # council/admin can freely filter by any region
                qs = qs.filter(region=region_param)

        # 3) text search
        if q:
            qs = qs.filter(
                Q(title__icontains=q) |
                Q(description__icontains=q)
            )

        # 4) tag filter (still within base security constraints)
        if tag:
            qs = qs.filter(tags__name=tag)

        qs = qs.distinct().order_by("-updated_at")

        return Response(
            KnowledgeResourceQueueSerializer(qs, many=True).data,
            status=200,
        )




class UnpublishResourceView(APIView):
    """
    Council/Admin can unpublish.
    Only PUBLISHED resources can be unpublished.
    Sets status -> unpublished.
    """
    permission_classes = [IsGovCouncil]  # we'll allow Admin inside too

    @transaction.atomic
    def post(self, request, resource_id):
        # allow Admin too
        if not (IsGovCouncil().has_permission(request, self) or IsAdminRole().has_permission(request, self)):
            return Response({"detail": "Only Governance Council or Admin can unpublish."}, status=403)

        resource = get_object_or_404(KnowledgeResource, id=resource_id)

        if resource.status != KnowledgeResource.Status.PUBLISHED:
            return Response({"detail": "Only PUBLISHED resources can be unpublished."}, status=400)

        resource.status = KnowledgeResource.Status.UNPUBLISHED
        resource.save(update_fields=["status", "updated_at"])

        # Optional audit step
        ReviewStep.objects.create(
            resource=resource,
            version=resource.latest_version,
            stage=resource.current_stage,
            decision=ReviewStep.Decision.UNPUBLISHED,
            reviewer=request.user,
            comment="Unpublished by governance"
        )

        return Response({"detail": "Resource unpublished.", "status": resource.status}, status=200)

class KnowledgeResourceDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, resource_id):
        resource = get_object_or_404(KnowledgeResource, id=resource_id)
        return Response(KnowledgeResourceDetailSerializer(resource).data, status=200)

    @transaction.atomic
    def delete(self, request, resource_id):
        """
        DELETE /api/knowledge/resources/<resource_id>/
        Only the EMPLOYEE who uploaded the resource can delete it.
        Can't delete while in review / approved / published.
        """
        resource = get_object_or_404(KnowledgeResource, id=resource_id)
        user = request.user

        # Must be uploader AND employee
        if resource.uploaded_by_id != user.id or getattr(user, "role", None) != "EMPLOYEE":
            return Response(
                {"detail": "Only the employee who uploaded this resource can delete it."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Optional safety: don't allow delete in review / approved / published
        if resource.status in [
            KnowledgeResource.Status.PENDING_REVIEW,
            KnowledgeResource.Status.APPROVED,
            KnowledgeResource.Status.PUBLISHED,
        ]:
            return Response(
                {"detail": "You cannot delete a resource that is under review or already approved/published."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        resource.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    
class MyResourcesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = KnowledgeResource.objects.filter(uploaded_by=request.user).order_by("-updated_at")
        return Response(KnowledgeResourceQueueSerializer(qs, many=True).data, status=200)
    
# 4) GET /api/knowledge/tags/
class TagListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = Tag.objects.all().order_by("name")
        data = [{"id": t.id, "name": t.name} for t in qs]
        return Response(data, status=200)
    

class MyReviewActionsView(APIView):
    """
    List resources where the current user has taken a review action
    (Champion / Regional Officer / Gov Council).

    Returns the *latest* step per resource for this reviewer.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        # Optional: lock down to only reviewer roles if you want
        role = getattr(user, "role", None)
        if role not in ("CHAMPION", "OFFICER", "COUNCIL"):
            return Response(
                {"detail": "Only reviewers can access their review actions."},
                status=status.HTTP_403_FORBIDDEN,
            )

        qs = (
            ReviewStep.objects
            .filter(reviewer=user)
            .select_related(
                "resource",
                "resource__latest_version",
                "resource__submitted_version",
                "version",
            )
            .prefetch_related(
                "resource__tags",
                "resource__ai_flags",
            )
            .order_by("resource_id", "-created_at")
        )

        # On Postgres this keeps only the latest step for each (resource, reviewer)
        qs = qs.distinct("resource_id")

        serializer = MyReviewActionSerializer(qs, many=True)
        return Response(serializer.data)
