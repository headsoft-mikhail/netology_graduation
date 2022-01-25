from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.dispatch import receiver, Signal
from django_rest_passwordreset.signals import reset_password_token_created, post_password_reset
from backend.models import ConfirmEmailToken, User, USER_TYPE_CHOICES, ORDER_STATE_CHOICES, OrderItem
from django.template.loader import render_to_string

new_user_registered = Signal()
order_state_changed = Signal()


@receiver(new_user_registered)
def new_user_registered_signal(sender, instance, user_id, **kwargs):
    """
    отправляем письмо с подтверждением почты
    """

    token, _ = ConfirmEmailToken.objects.get_or_create(user_id=user_id)
    text_content = f'This is an important message.\n' \
                   f'Your email confirmation token: {token}'
    msg = EmailMultiAlternatives(
        subject=f"Email confirmation for your account",
        body=text_content,
        from_email=settings.EMAIL_HOST_USER,
        to=[instance.request.data['email']]
    )
    msg.send()


@receiver(reset_password_token_created)
def reset_password_token_created_signal(sender, instance, reset_password_token, **kwargs):
    """
    Отправляем письмо с токеном для сброса пароля
    """

    text_content = f'This is an important message.\n' \
                   f'Your password reset token: {reset_password_token.key}'
    msg = EmailMultiAlternatives(
        subject=f"Password reset token for your account",
        body=text_content,
        from_email=settings.EMAIL_HOST_USER,
        to=[reset_password_token.user.email]
    )
    msg.send()


@receiver(post_password_reset)
def post_password_reset_signal(sender, user, **kwargs):
    """
    Отправляем сообщение о сбросе пароля
    """
    text_content = f'This is an important message.\n' \
                   f'Your password has been successfully reset.'
    msg = EmailMultiAlternatives(
        subject=f"Password reset",
        body=text_content,
        from_email=settings.EMAIL_HOST_USER,
        to=[user.email]
    )
    msg.send()


@receiver(order_state_changed)
def order_state_changed_signal(sender, order_id, user_id, state, **kwargs):
    """
    отправяем письмо при изменении статуса заказа
    """

    state = [states_t[1] for states_t in ORDER_STATE_CHOICES if state in states_t][0]
    user = User.objects.get(id=user_id)
    ordered_items = OrderItem.objects.filter(order_id=order_id)
    split_invoice = {}
    invoice = []
    for item in ordered_items:
        if item.product_info.shop.user.email not in split_invoice.keys():
            split_invoice.update({item.product_info.shop.user.email: []})
        split_invoice[item.product_info.shop.user.email].append((item.product_info.id,
                                                                 item.product_info.external_id,
                                                                 item.product_info.model,
                                                                 item.product_info.price,
                                                                 item.quantity))
        invoice.append((item.product_info.id,
                        item.product_info.external_id,
                        item.product_info.model,
                        item.product_info.price,
                        item.quantity))
    # сообщение покупателю
    context = {
        'invoice': invoice,
        'order_id': order_id,
        'additional_text': 'Спасибо за использование нашего сервиса!'
    }
    text_content = render_to_string('order_template.html', context)
    msg = EmailMultiAlternatives(
        subject=f"{state} заказ №{order_id}",
        body=None,
        from_email=settings.EMAIL_HOST_USER,
        to=[user.email]
    )
    msg.attach_alternative(text_content, 'text/html')
    msg.send()
    # сообщение администраторам
    context = {
        'invoice': invoice,
        'order_id': order_id,
        'additional_text': ''
    }
    text_content = render_to_string('order_template.html', context)
    msg = EmailMultiAlternatives(
        subject=f"{state} заказ №{order_id}",
        body=None,
        from_email=settings.EMAIL_HOST_USER,
        to=[admin.email for admin in User.objects.filter(type=USER_TYPE_CHOICES[2][0])]
    )
    msg.attach_alternative(text_content, 'text/html')
    msg.send()
    # сообщение магазинам
    for shop in split_invoice.keys():
        context = {
            'invoice': split_invoice[shop],
            'order_id': order_id,
            'additional_text': ''
        }
        text_content = render_to_string('order_template.html', context)
        msg = EmailMultiAlternatives(
            subject=f"{state} заказ №{order_id}",
            body=None,
            from_email=settings.EMAIL_HOST_USER,
            to=[shop]
        )
        msg.attach_alternative(text_content, 'text/html')
        msg.send()

