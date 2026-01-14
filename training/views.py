from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Region
from .models import (
    TrainingCourse,
    TrainingMaterial,
    TrainingQuestion,
    TrainingOption,
    TrainingAttempt,
    TrainingAttemptAnswer,
)
from .serializers import (
    TrainingCourseListSerializer,
    TrainingCourseDetailSerializer,
    TrainingMaterialSerializer,
    TrainingQuestionSerializer,
    TrainingAttemptSerializer,
    QuizSubmitSerializer,
    TrainingQuestionManageSerializer,
    TrainingOptionManageSerializer
)


# Utility: check champion
def is_champion(user):
    # you already use user.role in other apps
    return getattr(user, "role", None) == "CHAMPION"


class TrainingCourseListCreateView(APIView):
    """
    GET /api/training/courses/
        - Employees: list PUBLISHED courses in their region (or GLOBAL)
        - Champions: list ALL courses they created, plus PUBLISHED courses in region/GLOBAL
    POST /api/training/courses/
        - Champions: create a new training course
    """

    permission_classes = [IsAuthenticated]

    def get_queryset_for_user(self, user):
        base_qs = TrainingCourse.objects.all().select_related("created_by")

        region = getattr(user, "region", None)

        # Champion view
        if is_champion(user):
            # Champion always sees their own courses (any status)
            own_courses_q = Q(created_by=user)

            # And also region-based published courses (so they see what employees see)
            if region:
                region_published_q = Q(
                    status=TrainingCourse.Status.PUBLISHED,
                    region__in=[region, Region.GLOBAL],
                )
            else:
                region_published_q = Q(
                    status=TrainingCourse.Status.PUBLISHED,
                    region=Region.GLOBAL,
                )

            return base_qs.filter(own_courses_q | region_published_q)

        # Employee (or other non-champion roles) – published courses only, region-based
        qs = base_qs.filter(status=TrainingCourse.Status.PUBLISHED)
        if region:
            qs = qs.filter(Q(region=region) | Q(region=Region.GLOBAL))
        else:
            qs = qs.filter(region=Region.GLOBAL)

        return qs

    def get(self, request):
        qs = self.get_queryset_for_user(request.user)
        serializer = TrainingCourseListSerializer(qs, many=True)
        return Response(serializer.data)

    def post(self, request):
        # Only Champions can create courses
        if not is_champion(request.user):
            return Response(
                {"detail": "Only Champions can create training courses."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = TrainingCourseListSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(created_by=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class TrainingCourseDetailView(APIView):
    """
    GET /api/training/courses/<id>/
        - Employee: only if PUBLISHED and region-compatible
        - Champion: can see if they created it
    PATCH / DELETE (Champion only, creator)
    """

    permission_classes = [IsAuthenticated]

    def get_object(self, request, pk):
        course = get_object_or_404(
            TrainingCourse.objects.select_related("created_by"),
            id=pk,
        )

        user = request.user

        # champion who created it can always see/edit
        if is_champion(user) and course.created_by_id == user.id:
            return course

        # others (employees etc.): only published & region
        region = getattr(user, "region", None)
        if (
            course.status == TrainingCourse.Status.PUBLISHED
            and (
                course.region == Region.GLOBAL
                or (region and course.region == region)
            )
        ):
            return course

        # otherwise, forbidden
        raise get_object_or_404(TrainingCourse, id=0)  # hack to return 404

    def get(self, request, pk):
        try:
            course = self.get_object(request, pk)
        except Exception:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = TrainingCourseDetailSerializer(course)
        return Response(serializer.data)

    def patch(self, request, pk):
        course = get_object_or_404(TrainingCourse, id=pk)

        if not (is_champion(request.user) and course.created_by_id == request.user.id):
            return Response(
                {"detail": "Only the Champion who created this course can edit it."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = TrainingCourseDetailSerializer(
            course, data=request.data, partial=True
        )
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        course = get_object_or_404(TrainingCourse, id=pk)

        if not (is_champion(request.user) and course.created_by_id == request.user.id):
            return Response(
                {"detail": "Only the Champion who created this course can delete it."},
                status=status.HTTP_403_FORBIDDEN,
            )

        course.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class TrainingMaterialListCreateView(APIView):
    """
    GET /api/training/courses/<course_id>/materials/
    POST /api/training/courses/<course_id>/materials/
        - only Champion who created the course can POST
    """

    permission_classes = [IsAuthenticated]

    def get_course(self, request, course_id):
        return get_object_or_404(TrainingCourse, id=course_id)

    def get(self, request, course_id):
        course = self.get_course(request, course_id)

        user = request.user
        # same visibility rule as course detail
        if not (
            is_champion(user)
            and course.created_by_id == user.id
        ):
            region = getattr(user, "region", None)
            if not (
                course.status == TrainingCourse.Status.PUBLISHED
                and (
                    course.region == Region.GLOBAL
                    or (region and course.region == region)
                )
            ):
                return Response(
                    {"detail": "You do not have access to this course materials."},
                    status=status.HTTP_403_FORBIDDEN,
                )

        materials = course.materials.all()
        serializer = TrainingMaterialSerializer(materials, many=True)
        return Response(serializer.data)

    @transaction.atomic
    def post(self, request, course_id):
        course = self.get_course(request, course_id)

        if not (is_champion(request.user) and course.created_by_id == request.user.id):
            return Response(
                {"detail": "Only the Champion who created this course can add materials."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = TrainingMaterialSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(course=course)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class TrainingMaterialDetailView(APIView):
    """
    DELETE /api/training/materials/<material_id>/
        - only Champion who created the course can delete materials
    """

    permission_classes = [IsAuthenticated]

    def delete(self, request, material_id):
        material = get_object_or_404(TrainingMaterial, id=material_id)
        course = material.course

        if not (is_champion(request.user) and course.created_by_id == request.user.id):
            return Response(
                {"detail": "Only the Champion who created this course can delete materials."},
                status=status.HTTP_403_FORBIDDEN,
            )

        material.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

# -------- Quiz views --------

class TrainingQuizView(APIView):
    """
    GET /api/training/courses/<course_id>/quiz/
    Returns questions + options (without revealing correct answers).
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, course_id):
        course = get_object_or_404(TrainingCourse, id=course_id)

        user = request.user
        region = getattr(user, "region", None)

        if not (
            course.status == TrainingCourse.Status.PUBLISHED
            and (
                course.region == Region.GLOBAL
                or (region and course.region == region)
            )
        ):
            return Response(
                {"detail": "You do not have access to this quiz."},
                status=status.HTTP_403_FORBIDDEN,
            )

        questions = course.questions.prefetch_related("options")
        serializer = TrainingQuestionSerializer(questions, many=True)
        return Response(serializer.data)


class SubmitQuizView(APIView):
    """
    POST /api/training/courses/<course_id>/quiz/submit/
    Payload: { "answers": [ { "question": <id>, "option": <id> }, ... ] }
    """

    permission_classes = [IsAuthenticated]

    PASS_PERCENTAGE = 70  # e.g. pass if >= 70%

    @transaction.atomic
    def post(self, request, course_id):
        course = get_object_or_404(TrainingCourse, id=course_id)

        user = request.user
        region = getattr(user, "region", None)

        if not (
            course.status == TrainingCourse.Status.PUBLISHED
            and (
                course.region == Region.GLOBAL
                or (region and course.region == region)
            )
        ):
            return Response(
                {"detail": "You do not have access to this quiz."},
                status=status.HTTP_403_FORBIDDEN,
            )

        quiz_serializer = QuizSubmitSerializer(data=request.data)
        if not quiz_serializer.is_valid():
            return Response(
                quiz_serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )

        # load full question + options for this course
        questions = list(
            course.questions.prefetch_related("options").all()
        )
        question_map = {q.id: q for q in questions}
        total_questions = len(questions)

        if total_questions == 0:
            return Response(
                {"detail": "This course has no quiz questions configured."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        answers_data = quiz_serializer.validated_data["answers"]

        # map of question_id -> selected option_id
        answer_map = {}
        for item in answers_data:
            q_id = item["question"]
            opt_id = item["option"]
            # ignore answers for questions not in this course
            if q_id in question_map:
                answer_map[q_id] = opt_id

        score = 0
        # compute score
        for q in questions:
            selected_opt_id = answer_map.get(q.id)
            if not selected_opt_id:
                continue
            # find selected option
            try:
                opt = next(o for o in q.options.all() if o.id == selected_opt_id)
            except StopIteration:
                continue
            if opt.is_correct:
                score += 1

        percent = (score / total_questions) * 100
        is_passed = percent >= self.PASS_PERCENTAGE

        # save attempt + answer rows
        attempt = TrainingAttempt.objects.create(
            user=user,
            course=course,
            score=score,
            total_questions=total_questions,
            is_passed=is_passed,
        )

        # store answers only for questions they attempted
        for q_id, opt_id in answer_map.items():
            q = question_map[q_id]
            # ensure option belongs to question
            try:
                selected_option = q.options.get(id=opt_id)
            except TrainingOption.DoesNotExist:
                continue

            TrainingAttemptAnswer.objects.create(
                attempt=attempt,
                question=q,
                selected_option=selected_option,
            )

        return Response(
            {
                "course": course.id,
                "score": score,
                "total_questions": total_questions,
                "percent": round(percent, 2),
                "passed": is_passed,
                "attempt_id": attempt.id,
            },
            status=status.HTTP_200_OK,
        )


class MyTrainingAttemptsView(APIView):
    """
    Optional: GET /api/training/my-attempts/
    For showing progress / future leaderboard.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = TrainingAttempt.objects.filter(user=request.user).select_related(
            "course"
        )
        serializer = TrainingAttemptSerializer(qs, many=True)
        return Response(serializer.data)


# -------- Quiz Management (Champion only) --------

class TrainingQuestionListCreateView(APIView):
    """
    Champion API to manage questions for a course.

    GET  /api/training/courses/<course_id>/questions/
        -> list questions (with options, including is_correct)

    POST /api/training/courses/<course_id>/questions/
        body: { "text": "What is ...?", "order": 1 }
    """

    permission_classes = [IsAuthenticated]

    def get_course(self, course_id):
        return get_object_or_404(TrainingCourse, id=course_id)

    def check_champion_owner(self, request, course):
        if not (is_champion(request.user) and course.created_by_id == request.user.id):
            return Response(
                {"detail": "Only the Champion who created this course can manage its quiz."},
                status=status.HTTP_403_FORBIDDEN,
            )

    def get(self, request, course_id):
        course = self.get_course(course_id)
        deny = self.check_champion_owner(request, course)
        if deny:
            return deny

        qs = course.questions.prefetch_related("options")
        serializer = TrainingQuestionManageSerializer(qs, many=True)
        return Response(serializer.data)

    @transaction.atomic
    def post(self, request, course_id):
        course = self.get_course(course_id)
        deny = self.check_champion_owner(request, course)
        if deny:
            return deny

        data = request.data.copy()
        # default order if not provided
        if "order" not in data:
            # simple naive order: after last
            last = course.questions.order_by("-order").first()
            data["order"] = (last.order + 1) if last else 1

        serializer = TrainingQuestionManageSerializer(data=data)
        if serializer.is_valid():
            question = serializer.save(course=course)
            return Response(
                TrainingQuestionManageSerializer(question).data,
                status=status.HTTP_201_CREATED,
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class TrainingQuestionDetailManageView(APIView):
    """
    Champion API to update/delete a single question.

    PATCH /api/training/courses/<course_id>/questions/<question_id>/
    DELETE /api/training/courses/<course_id>/questions/<question_id>/
    """

    permission_classes = [IsAuthenticated]

    def get_course_and_question(self, course_id, question_id):
        course = get_object_or_404(TrainingCourse, id=course_id)
        question = get_object_or_404(
            TrainingQuestion, id=question_id, course=course
        )
        return course, question

    def check_champion_owner(self, request, course):
        if not (is_champion(request.user) and course.created_by_id == request.user.id):
            return Response(
                {"detail": "Only the Champion who created this course can manage its quiz."},
                status=status.HTTP_403_FORBIDDEN,
            )

    def patch(self, request, course_id, question_id):
        course, question = self.get_course_and_question(course_id, question_id)
        deny = self.check_champion_owner(request, course)
        if deny:
            return deny

        serializer = TrainingQuestionManageSerializer(
            question, data=request.data, partial=True
        )
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, course_id, question_id):
        course, question = self.get_course_and_question(course_id, question_id)
        deny = self.check_champion_owner(request, course)
        if deny:
            return deny

        question.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class TrainingOptionListCreateView(APIView):
    """
    Champion API to manage options for a given question.

    GET  /api/training/courses/<course_id>/questions/<question_id>/options/
    POST /api/training/courses/<course_id>/questions/<question_id>/options/
        body: { "text": "Option text", "is_correct": true/false }
    """

    permission_classes = [IsAuthenticated]

    def get_course_question(self, course_id, question_id):
        course = get_object_or_404(TrainingCourse, id=course_id)
        question = get_object_or_404(
            TrainingQuestion, id=question_id, course=course
        )
        return course, question

    def check_champion_owner(self, request, course):
        if not (is_champion(request.user) and course.created_by_id == request.user.id):
            return Response(
                {"detail": "Only the Champion who created this course can manage its quiz."},
                status=status.HTTP_403_FORBIDDEN,
            )

    def get(self, request, course_id, question_id):
        course, question = self.get_course_question(course_id, question_id)
        deny = self.check_champion_owner(request, course)
        if deny:
            return deny

        qs = question.options.all()
        serializer = TrainingOptionManageSerializer(qs, many=True)
        return Response(serializer.data)

    @transaction.atomic
    def post(self, request, course_id, question_id):
        course, question = self.get_course_question(course_id, question_id)
        deny = self.check_champion_owner(request, course)
        if deny:
            return deny

        serializer = TrainingOptionManageSerializer(data=request.data)
        if serializer.is_valid():
            option = serializer.save(question=question)
            return Response(
                TrainingOptionManageSerializer(option).data,
                status=status.HTTP_201_CREATED,
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class TrainingOptionDetailManageView(APIView):
    """
    Champion API to update/delete a single option.

    PATCH /api/training/courses/<course_id>/questions/<question_id>/options/<option_id>/
    DELETE /api/training/courses/<course_id>/questions/<question_id>/options/<option_id>/
    """

    permission_classes = [IsAuthenticated]

    def get_course_question_option(self, course_id, question_id, option_id):
        course = get_object_or_404(TrainingCourse, id=course_id)
        question = get_object_or_404(
            TrainingQuestion, id=question_id, course=course
        )
        option = get_object_or_404(
            TrainingOption, id=option_id, question=question
        )
        return course, question, option

    def check_champion_owner(self, request, course):
        if not (is_champion(request.user) and course.created_by_id == request.user.id):
            return Response(
                {"detail": "Only the Champion who created this course can manage its quiz."},
                status=status.HTTP_403_FORBIDDEN,
            )

    def patch(self, request, course_id, question_id, option_id):
        course, question, option = self.get_course_question_option(
            course_id, question_id, option_id
        )
        deny = self.check_champion_owner(request, course)
        if deny:
            return deny

        serializer = TrainingOptionManageSerializer(
            option, data=request.data, partial=True
        )
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, course_id, question_id, option_id):
        course, question, option = self.get_course_question_option(
            course_id, question_id, option_id
        )
        deny = self.check_champion_owner(request, course)
        if deny:
            return deny

        option.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
