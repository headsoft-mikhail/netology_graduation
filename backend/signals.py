from django.dispatch import receiver, Signal
from django_rest_passwordreset.signals import reset_password_token_created, post_password_reset
from backend.tasks import on_post_password_reset, on_reset_password_token_created, on_new_user_registered


@receiver(reset_password_token_created)
def reset_password_token_created_signal(sender, instance, reset_password_token, **kwargs):
    """
    Добавляем task для оптравки письма с токеном для сброса пароля
    """

    on_reset_password_token_created.delay(reset_password_token.key, reset_password_token.user.email)


@receiver(post_password_reset)
def post_password_reset_signal(sender, user, **kwargs):
    """
    Добавляем task для оптравки сообщения о сбросе пароля
    """

    on_post_password_reset.delay(user.email)


