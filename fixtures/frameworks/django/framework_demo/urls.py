import os

from django.http import JsonResponse
from django.urls import path


def index(request):
    marker = os.environ.get("OPENPYCHARM_FRAMEWORK_PROBE", "manual")
    return JsonResponse({"framework": "django", "marker": marker})


urlpatterns = [path("", index)]
