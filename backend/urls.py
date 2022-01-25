from django.urls import path
from django_rest_passwordreset.views import reset_password_request_token, reset_password_confirm

from backend.views import RegisterAccount, LoginAccount, CategoryView, Shops, ShopInfo, ProductInfoView, \
    BasketView, \
    AccountDetails, ContactView, OrderView, Shops, OrdersView, ConfirmAccount

app_name = 'backend'
urlpatterns = [
    path('user/register', RegisterAccount.as_view(), name='user-register'),
    path('user/register/confirm', ConfirmAccount.as_view(), name='user-register-confirm'),
    path('user/details', AccountDetails.as_view(), name='user-details'),
    path('user/contact', ContactView.as_view(), name='user-contact'),
    path('user/login', LoginAccount.as_view(), name='user-login'),
    path('user/password_reset', reset_password_request_token, name='password-reset'),
    path('user/password_reset/confirm', reset_password_confirm, name='password-reset-confirm'),
    path('shops', Shops.as_view(), name='shops'),
    path('shop/info', ShopInfo.as_view(), name='shop-data'),
    path('orders', OrdersView.as_view(), name='shop-orders'),
    path('categories', CategoryView.as_view(), name='categories'),
    path('products', ProductInfoView.as_view(), name='products'),
    path('basket', BasketView.as_view(), name='basket'),
    path('order', OrderView.as_view(), name='order'),
]
