from django.contrib.auth import logout
from django.shortcuts import redirect
from django.urls import reverse


class InactiveUserMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)

        if user is not None and user.is_authenticated and not user.is_active:
            logout(request)
            return redirect(reverse("atendimento:login"))

        return self.get_response(request)