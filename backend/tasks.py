from netology_pd_diplom.celery import app
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from backend.models import User, USER_TYPE_CHOICES, ORDER_STATE_CHOICES, OrderItem
from django.template.loader import render_to_string
import sys


@app.task
def on_new_user_registered(email, token):
    """
    отправляем письмо с подтверждением почты
    """
    text_content = f'This is an important message.\n' \
                   f'Your email confirmation token: {token}'
    msg = EmailMultiAlternatives(
        subject=f"Email confirmation for your account",
        body=text_content,
        from_email=settings.EMAIL_HOST_USER,
        to=[email]
    )
    msg.send()


@app.task
def on_reset_password_token_created(token, email):
    """
    Отправляем письмо с токеном для сброса пароля
    """

    text_content = f'This is an important message.\n' \
                   f'Your password reset token: {token}'
    msg = EmailMultiAlternatives(
        subject=f"Password reset token for your account",
        body=text_content,
        from_email=settings.EMAIL_HOST_USER,
        to=[email]
    )
    msg.send()


@app.task
def on_post_password_reset(email):
    """
    Отправляем сообщение о сбросе пароля
    """
    text_content = f'This is an important message.\n' \
                   f'Your password has been successfully reset.'
    msg = EmailMultiAlternatives(
        subject=f"Password reset",
        body=text_content,
        from_email=settings.EMAIL_HOST_USER,
        to=[email]
    )
    if 'test' not in sys.argv:
        msg.send()


@app.task
def on_order_state_changed(order_id, user_id, state):
    """
    отправяем письма при изменении статуса заказа
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
