from rest_framework.generics import CreateAPIView, RetrieveUpdateAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated

from .serializers import RegistroSerializer, UsuarioSerializer


class MeView(RetrieveUpdateAPIView):
    serializer_class = UsuarioSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "patch", "head", "options"]

    def get_object(self):
        return self.request.user


class RegistroView(CreateAPIView):
    serializer_class = RegistroSerializer
    permission_classes = [AllowAny]
