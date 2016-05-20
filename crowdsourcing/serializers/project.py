from datetime import datetime
from django.db.models import Count
from django.db.models.query_utils import Q

from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from crowdsourcing import models
from crowdsourcing.serializers.dynamic import DynamicFieldsModelSerializer
from crowdsourcing.serializers.template import TemplateSerializer
from crowdsourcing.serializers.task import TaskSerializer, TaskCommentSerializer
from crowdsourcing.serializers.requester import RequesterSerializer
from crowdsourcing.serializers.message import CommentSerializer
from crowdsourcing.utils import generate_random_id
from crowdsourcing.serializers.file import BatchFileSerializer
# from mturk.tasks import mturk_update_status


class CategorySerializer(DynamicFieldsModelSerializer):
    class Meta:
        model = models.Category
        fields = ('id', 'name', 'parent')

    def update(self, instance, validated_data):
        instance.name = validated_data.get('name', instance.name)
        instance.parent = validated_data.get('parent', instance.parent)
        instance.save()
        return instance

    def delete(self, instance):
        instance.deleted = True
        instance.save()
        return instance


class ProjectSerializer(DynamicFieldsModelSerializer):
    deleted = serializers.BooleanField(read_only=True)
    templates = TemplateSerializer(many=True, required=False)
    total_tasks = serializers.SerializerMethodField()
    total_tasks_pending_review = serializers.SerializerMethodField()
    file_id = serializers.IntegerField(write_only=True, allow_null=True, required=False)
    age = serializers.SerializerMethodField()
    has_comments = serializers.SerializerMethodField()
    available_tasks = serializers.SerializerMethodField()
    allowed_levels = serializers.SerializerMethodField()
    num_accepted_worker_tasks = serializers.SerializerMethodField()
    num_worker_reviews = serializers.SerializerMethodField()
    num_task_rejections = serializers.SerializerMethodField()
    num_review_rejections = serializers.SerializerMethodField()
    comments = serializers.SerializerMethodField()
    name = serializers.CharField(default='Untitled Project')
    status = serializers.IntegerField(default=1)
    owner = RequesterSerializer(fields=('alias', 'profile', 'id', 'user_id'), read_only=True)
    batch_files = BatchFileSerializer(many=True, read_only=True,
                                      fields=('id', 'name', 'size', 'column_headers', 'format', 'number_of_rows'))
    num_rows = serializers.IntegerField(write_only=True, allow_null=True, required=False)
    requester_rating = serializers.FloatField(read_only=True, required=False)
    raw_rating = serializers.IntegerField(read_only=True, required=False)
    deadline = serializers.DateTimeField(required=False)

    class Meta:
        model = models.Project
        fields = ('id', 'name', 'owner', 'description', 'status', 'repetition', 'deadline', 'timeout', 'templates',
                  'batch_files', 'deleted', 'created_timestamp', 'last_updated', 'price', 'has_data_set',
                  'data_set_location', 'total_tasks', 'total_tasks_pending_review', 'file_id', 'age', 'is_micro',
                  'is_prototype', 'task_time', 'allowed_levels', 'num_accepted_worker_tasks', 'num_worker_reviews',
                  'allow_feedback', 'feedback_permissions', 'min_rating', 'has_comments',
                  'num_task_rejections', 'num_review_rejections',
                  'available_tasks', 'comments', 'num_rows', 'requester_rating', 'raw_rating', 'post_mturk', 'level')
        read_only_fields = (
            'created_timestamp', 'last_updated', 'deleted', 'owner', 'has_comments', 'available_tasks',
            'comments', 'templates', 'level', 'allowed_levels', 'num_accepted_worker_tasks', 'num_worker_reviews',
            'num_task_rejections', 'num_review_rejections',)

    def create(self, with_defaults=True, **kwargs):
        templates = self.validated_data.pop('templates') if 'templates' in self.validated_data else []
        template_items = templates[0]['template_items'] if templates else []

        project = models.Project.objects.create(deleted=False, owner=kwargs['owner'].requester, **self.validated_data)
        template = {
            "name": 't_' + generate_random_id(),
            "template_items": template_items
        }
        template_serializer = TemplateSerializer(data=template)
        if template_serializer.is_valid():
            template = template_serializer.create(with_defaults=with_defaults, owner=kwargs['owner'])
        else:
            raise ValidationError(template_serializer.errors)
        models.ProjectTemplate.objects.get_or_create(project=project, template=template)
        if not with_defaults:
            project.status = models.Project.STATUS_IN_PROGRESS
            project.published_time = datetime.now()
            project.save()
            self.create_task(project.id)
        return project

    def delete(self, instance):
        instance.deleted = True
        instance.save()
        return instance

    @staticmethod
    def get_age(model):
        from crowdsourcing.utils import get_time_delta

        if model.status == 1:
            return "Saved " + get_time_delta(model.last_updated)
        else:
            return "Posted " + get_time_delta(model.published_time)

    @staticmethod
    def get_total_tasks(obj):
        return obj.project_tasks.all().count()

    def get_num_accepted_worker_tasks(self, obj):
        return models.TaskWorker.objects.filter(task_status=models.TaskWorker.STATUS_ACCEPTED,
                                                worker__profile__user=self.context.get('request').user,
                                                task__project=obj).count()

    def get_num_worker_reviews(self, obj):
        return models.Review.objects.filter(
            Q(task_worker__worker__profile__user=self.context.get('request').user,
              parent__isnull=True) |
            Q(parent__isnull=False,
              parent__reviewer__profile__user=self.context.get('request').user),
            task_worker__task__project=obj,
            status=models.Review.STATUS_SUBMITTED
        ).count()

    def get_num_task_rejections(self, obj):
        return models.Rejection.objects.filter(project=obj).count()

    def get_num_review_rejections(self, obj):
        return models.Rejection.objects.filter(review__task_worker__task__project=obj).count()

    @staticmethod
    def get_total_tasks_pending_review(obj):
        return models.TaskWorker.objects.filter(task__project=obj, task_status=models.TaskWorker.STATUS_SUBMITTED)\
            .count()

    @staticmethod
    def get_has_comments(obj):
        return obj.projectcomment_project.count() > 0

    def get_available_tasks(self, obj):
        available_task_count = models.Project.objects.values('id').raw('''
          SELECT COUNT(*) id from (
            SELECT
              "crowdsourcing_task"."id"
            FROM "crowdsourcing_task"
              INNER JOIN "crowdsourcing_project" ON ("crowdsourcing_task"."project_id" = "crowdsourcing_project"."id")
              LEFT OUTER JOIN "crowdsourcing_taskworker" ON ("crowdsourcing_task"."id" =
                "crowdsourcing_taskworker"."task_id" and task_status not in (4,6))
            WHERE ("crowdsourcing_task"."project_id" = %s AND NOT (
              ("crowdsourcing_task"."id" IN (SELECT U1."task_id" AS Col1
              FROM "crowdsourcing_taskworker" U1 WHERE U1."worker_id" = %s and U1.task_status<>6))))
            GROUP BY "crowdsourcing_task"."id", "crowdsourcing_project"."repetition"
            HAVING "crowdsourcing_project"."repetition" > (COUNT("crowdsourcing_taskworker"."id"))) available_tasks
            ''', params=[obj.id, self.context['request'].user.userprofile.worker.id])[0].id
        return available_task_count

    def get_comments(self, obj):
        if obj:
            comments = []
            tasks = obj.project_tasks.all()
            for task in tasks:
                task_comments = task.taskcomment_task.all()
                for task_comment in task_comments:
                    comments.append(task_comment)
            serializer = TaskCommentSerializer(many=True, instance=comments, read_only=True)
            return serializer.data
        return []

    def update(self, *args, **kwargs):
        status = self.validated_data.get('status', self.instance.status)
        num_rows = self.validated_data.get('num_rows', 0)
        if self.instance.status != status and status == 2:
            if self.instance.templates.all()[0].template_items.count() == 0:
                raise ValidationError('At least one template item is required')
            if self.instance.batch_files.count() == 0:
                self.create_task(self.instance.id)
            else:
                batch_file = self.instance.batch_files.first()
                data = batch_file.parse_csv()
                count = 0
                for row in data:
                    if count == num_rows:
                        break
                    task = {
                        'project': self.instance.id,
                        'data': row
                    }
                    task_serializer = TaskSerializer(data=task)
                    if task_serializer.is_valid():
                        task_serializer.create(**kwargs)
                        count += 1
                    else:
                        raise ValidationError(task_serializer.errors)
            self.instance.published_time = datetime.now()
            status += 1

        self.instance.name = self.validated_data.get('name', self.instance.name)
        self.instance.price = self.validated_data.get('price', self.instance.price)
        self.instance.repetition = self.validated_data.get('repetition', self.instance.repetition)
        self.instance.deadline = self.validated_data.get('deadline', self.instance.deadline)
        self.instance.timeout = self.validated_data.get('timeout', self.instance.timeout)
        self.instance.post_mturk = self.validated_data.get('post_mturk', self.instance.post_mturk)
        if status != self.instance.status \
            and status in (models.Project.STATUS_PAUSED, models.Project.STATUS_IN_PROGRESS) and \
                self.instance.status in (models.Project.STATUS_PAUSED, models.Project.STATUS_IN_PROGRESS):
            # mturk_update_status.delay({'id': self.instance.id, 'status': status})
            pass
        self.instance.status = status
        self.instance.save()
        return self.instance

    @staticmethod
    def create_task(project_id):
        task_data = {
            "project": project_id,
            "status": 1,
            "data": {}
        }
        task_serializer = TaskSerializer(data=task_data)
        if task_serializer.is_valid():
            task_serializer.create()
        else:
            raise ValidationError(task_serializer.errors)

    def fork(self, *args, **kwargs):
        templates = self.instance.templates.all()
        categories = self.instance.categories.all()
        batch_files = self.instance.batch_files.all()

        project = self.instance
        project.name += ' (copy)'
        project.status = 1
        project.is_prototype = False
        project.parent = models.Project.objects.get(pk=self.instance.id)
        project.id = None
        project.save()

        for template in templates:
            project_template = models.ProjectTemplate(project=project, template=template)
            project_template.save()
        for category in categories:
            project_category = models.ProjectCategory(project=project, category=category)
            project_category.save()
        for batch_file in batch_files:
            project_batch_file = models.ProjectBatchFile(project=project, batch_file=batch_file)
            project_batch_file.save()

    def get_allowed_levels(self, *args, **kwargs):
        user = None
        request = self.context.get("request")
        if request and hasattr(request, "user"):
            user = request.user
        worker_level_distribution = models.Worker.objects \
            .exclude(profile__user=user) \
            .values('level') \
            .order_by('level') \
            .annotate(count=Count('level'))
        levels = []
        for level in worker_level_distribution:
            if level['count'] > 0:
                levels.append(level['level'])
        return levels


class QualificationApplicationSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Qualification


class QualificationItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.QualificationItem


class ProjectCommentSerializer(DynamicFieldsModelSerializer):
    comment = CommentSerializer()

    class Meta:
        model = models.ProjectComment
        fields = ('id', 'project', 'comment')
        read_only_fields = ('project',)

    def create(self, **kwargs):
        comment_data = self.validated_data.pop('comment')
        comment_serializer = CommentSerializer(data=comment_data)
        if comment_serializer.is_valid():
            comment = comment_serializer.create(sender=kwargs['sender'])
            project_comment = models.ProjectComment.objects.create(project_id=kwargs['project'], comment_id=comment.id)
            return {'id': project_comment.id, 'comment': comment}


class ProjectBatchFileSerializer(DynamicFieldsModelSerializer):
    class Meta:
        model = models.ProjectBatchFile
        fields = ('id', 'project', 'batch_file')
        read_only_fields = ('project',)

    def create(self, project=None, **kwargs):
        project_file = models.ProjectBatchFile.objects.create(project_id=project, **self.validated_data)
        return project_file
