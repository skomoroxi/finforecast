"""Two-factor login for the admin (TECHNICAL-TASK §14).

After the password, staff enter a code from an authenticator app. The first time, they scan a QR
code and get one-time recovery codes. To recover a locked-out account see docs/DEPLOY.md.
"""

import base64
import secrets

import qrcode
import qrcode.image.svg
from django.conf import settings
from django.shortcuts import redirect, render
from django.urls import reverse
from django_otp import login as otp_login
from django_otp import match_token
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
from django_otp.plugins.otp_totp.models import TOTPDevice

RECOVERY_CODES = 8


class RequireTwoFactor:
    """Signed-in staff get nowhere in the admin until this session has passed the second step."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if settings.ADMIN_2FA and self.must_stop(request):
            name = "two_factor_verify" if self.has_device(request.user) else "two_factor_setup"
            return redirect(name)
        return self.get_response(request)

    @staticmethod
    def has_device(user) -> bool:
        return TOTPDevice.objects.filter(user=user, confirmed=True).exists()

    @staticmethod
    def must_stop(request) -> bool:
        admin_root = "/" + settings.ADMIN_URL
        if not request.path.startswith(admin_root):
            return False
        rest = request.path[len(admin_root) :]
        if rest.startswith(("login", "logout", "2fa/")):
            return False
        user = request.user
        return user.is_authenticated and user.is_staff and not user.is_verified()


def qr_svg(url: str) -> str:
    image = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage, box_size=8, border=2)
    return image.to_string(encoding="unicode")


def two_factor_setup(request):
    user = request.user
    if not (user.is_authenticated and user.is_staff):
        return redirect("admin:login")
    if RequireTwoFactor.has_device(user):
        return redirect("two_factor_verify")

    device, _ = TOTPDevice.objects.get_or_create(user=user, confirmed=False, defaults={"name": "authenticator"})
    error = ""
    if request.method == "POST":
        if device.verify_token(request.POST.get("token", "").strip()):
            device.confirmed = True
            device.save(update_fields=["confirmed"])
            otp_login(request, device)
            recovery, _ = StaticDevice.objects.get_or_create(user=user, name="recovery")
            recovery.token_set.all().delete()
            codes = [secrets.token_hex(5) for _ in range(RECOVERY_CODES)]
            StaticToken.objects.bulk_create(StaticToken(device=recovery, token=code) for code in codes)
            return render(request, "core/two_factor.html", {"mode": "codes", "codes": codes})
        error = "That code did not match. Check the time on your phone and try again."
    return render(
        request,
        "core/two_factor.html",
        {
            "mode": "setup",
            "qr": qr_svg(device.config_url),
            "secret": base64.b32encode(device.bin_key).decode(),
            "error": error,
        },
    )


def two_factor_verify(request):
    user = request.user
    if not (user.is_authenticated and user.is_staff):
        return redirect("admin:login")
    error = ""
    if request.method == "POST":
        device = match_token(user, request.POST.get("token", "").strip())
        if device is not None:
            otp_login(request, device)
            return redirect(reverse("admin:index"))
        error = "That code did not match, or too many tries. Wait a moment and try again."
    return render(request, "core/two_factor.html", {"mode": "verify", "error": error})
