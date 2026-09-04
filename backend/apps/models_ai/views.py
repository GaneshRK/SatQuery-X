from rest_framework import permissions, views
from rest_framework.response import Response
from apps.agent.registry import list_models_info, load_registry_config


class ModelRegistryListView(views.APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return Response(list_models_info())


class ModelRegistryDetailView(views.APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, model_id):
        cfg = load_registry_config()
        info = cfg.get(model_id)
        if not info:
            return Response({"error": f"Model {model_id} not found"}, status=404)
        return Response({
            "id": model_id,
            **info,
        })
