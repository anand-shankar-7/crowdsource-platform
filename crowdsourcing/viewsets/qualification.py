from rest_framework import status, viewsets
from rest_framework.decorators import detail_route, list_route
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from crowdsourcing.models import Qualification, QualificationItem, \
    WorkerAccessControlEntry, RequesterAccessControlGroup
from crowdsourcing.serializers.qualification import QualificationSerializer, QualificationItemSerializer, \
    WorkerACESerializer, RequesterACGSerializer


class QualificationViewSet(viewsets.ModelViewSet):
    queryset = Qualification.objects.all()
    serializer_class = QualificationSerializer
    permission_classes = [IsAuthenticated]
    item_queryset = QualificationItem.objects.all()
    item_serializer_class = QualificationItemSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid():
            serializer.create(owner=request.user.userprofile.requester)
            return Response(data={"message": "Successfully created"}, status=status.HTTP_201_CREATED)
        else:
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def list(self, request, *args, **kwargs):
        queryset = self.queryset.filter(owner=request.user.userprofile.requester)
        serializer = self.serializer_class(instance=queryset, many=True)
        return Response(data=serializer.data, status=status.HTTP_200_OK)

    @detail_route(methods=['post'], url_path='create-item')
    def create_item(self, request, pk=None, *args, **kwargs):
        serializer = self.item_serializer_class(data=request.data)
        if serializer.is_valid():
            item = serializer.create(qualification=pk)
            return Response({'id': item.id}, status=status.HTTP_201_CREATED)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @detail_route(methods=['get'], url_path='list-items')
    def list_items(self, request, pk=None, *args, **kwargs):
        queryset = self.item_queryset.filter(qualification_id=pk)
        serializer = self.item_serializer_class(instance=queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class QualificationItemViewSet(viewsets.ModelViewSet):
    queryset = QualificationItem.objects.all()
    serializer_class = QualificationItemSerializer


class WorkerACEViewSet(viewsets.ModelViewSet):
    queryset = WorkerAccessControlEntry.objects.all()
    serializer_class = WorkerACESerializer

    def create(self, request, *args, **kwargs):
        data = request.data
        serializer = self.serializer_class(data=data)
        existing = request.user.userprofile.requester.access_groups.filter(id=data.get('group', -1)).first()
        if not existing:
            return Response(data={"message": "Invalid group id"}, status=status.HTTP_400_BAD_REQUEST)
        if serializer.is_valid():
            instance = serializer.create()
            return Response(data=self.serializer_class(instance=instance).data, status=status.HTTP_201_CREATED)
        else:
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @list_route(methods=['get'], url_path='list-by-group')
    def list_by_group(self, request, *args, **kwargs):
        group = request.query_params.get('group', -1)

        entries = self.queryset.filter(group_id=group, group__requester=request.user.userprofile.requester)
        serializer = self.serializer_class(instance=entries, many=True)
        return Response(data=serializer.data, status=status.HTTP_200_OK)

    def destroy(self, request, pk=None, *args, **kwargs):
        self.get_object().delete()
        return Response(data={"pk": pk}, status=status.HTTP_200_OK)


class RequesterACGViewSet(viewsets.ModelViewSet):
    queryset = RequesterAccessControlGroup.objects.all()
    serializer_class = RequesterACGSerializer

    def create(self, request, *args, **kwargs):
        data = request.data
        is_global = data.get('is_global', True)
        type = data.get('type', 'deny')
        existing_group = request.user.userprofile.requester.access_groups.filter(type=type,
                                                                                 is_global=is_global).first()
        if existing_group and is_global:
            return Response(data={"message": "Already exists"}, status=status.HTTP_200_OK)

        serializer = self.serializer_class(data=data)
        if serializer.is_valid():
            serializer.create(requester=request.user.userprofile.requester)
            return Response(data={"message": "OK"}, status=status.HTTP_201_CREATED)
        else:
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @list_route(methods=['get'], url_path='retrieve-global')
    def retrieve_global(self, request, *args, **kwargs):
        entry_type = request.query_params.get('type', 'deny')
        group = self.queryset.filter(is_global=True, type=entry_type,
                                     requester=request.user.userprofile.requester).first()
        serializer = self.serializer_class(instance=group)
        return Response(serializer.data, status=status.HTTP_200_OK)
