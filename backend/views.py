from distutils.util import strtobool

from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import IntegrityError
from django.db.models import Q, Sum, F
from django.http import JsonResponse
from requests import get
from rest_framework.authtoken.models import Token
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.views import APIView
from yaml import load as load_yaml, Loader

from backend.models import Shop, Category, Product, ProductInfo, Parameter, ProductParameter, Order, OrderItem, \
    Contact, ConfirmEmailToken, USER_TYPE_CHOICES, ORDER_STATE_CHOICES
from backend.serializers import UserSerializer, CategorySerializer, ShopSerializer, ShopSerializerExtended, \
    ProductInfoSerializer, OrderItemSerializer, OrderSerializer, ContactSerializer
from backend.tasks import on_new_user_registered, on_order_state_changed


class RegisterAccount(APIView):
    """
    Для регистрации пользователей
    """

    def post(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return JsonResponse({'Status': False,
                                 'Error': 'Вы уже авторизованы'},
                                status=400,
                                json_dumps_params={'ensure_ascii': False})
        # проверяем обязательные аргументы
        if {'email', 'password', 'type'}.issubset(request.data.keys()):
            try:
                validate_password(request.data['password'])
            except Exception as password_error:
                error_array = [item for item in password_error]
                return JsonResponse({'Status': False,
                                     'Errors': {'password': error_array}},
                                    status=400,
                                    json_dumps_params={'ensure_ascii': False})
            else:
                if not [True for type_choice in USER_TYPE_CHOICES if (request.data['type'] == type_choice[0])]:
                    return JsonResponse({'Status': False,
                                         'Errors': 'Неверно указаны аргументы'},
                                        status=400,
                                        json_dumps_params={'ensure_ascii': False})
                if request.data['type'] == USER_TYPE_CHOICES[2][0]:
                    return JsonResponse({'Status': False,
                                         'Errors': 'Невозможно создать администратора через этот интерфейс.'},
                                        status=403,
                                        json_dumps_params={'ensure_ascii': False})
                user_serializer = UserSerializer(data=request.data)
                if user_serializer.is_valid():
                    # сохраняем пользователя
                    user = user_serializer.save()
                    user.set_password(request.data['password'])
                    user.save()
                    token, _ = ConfirmEmailToken.objects.get_or_create(user_id=user.id)
                    on_new_user_registered.delay(self.request.data['email'], token.key)
                    # new_user_registered.send(sender=self.__class__, instance=self, token=token)
                    return JsonResponse({'Status': True}, status=201)
                else:
                    return JsonResponse({'Status': False,
                                         'Errors': user_serializer.errors},
                                        status=400,
                                        json_dumps_params={'ensure_ascii': False})
        return JsonResponse({'Status': False,
                             'Errors': 'Не указаны все необходимые аргументы'},
                            status=400,
                            json_dumps_params={'ensure_ascii': False})


class ConfirmAccount(APIView):
    """
    Класс для подтверждения почтового адреса
    """

    def post(self, request, *args, **kwargs):
        # проверяем обязательные аргументы
        if {'email', 'token'}.issubset(request.data):
            token = ConfirmEmailToken.objects.filter(user__email=request.data['email'],
                                                     key=request.data['token']).first()
            if token:
                token.user.is_active = True
                token.user.save()
                token.delete()
                return JsonResponse({'Status': True}, status=201)
            else:
                return JsonResponse({'Status': False,
                                     'Errors': 'Неверно указан токен или email'},
                                    status=400,
                                    json_dumps_params={'ensure_ascii': False})
        return JsonResponse({'Status': False,
                             'Errors': 'Не указаны все необходимые аргументы'},
                            status=400,
                            json_dumps_params={'ensure_ascii': False})


class LoginAccount(APIView):
    """
    Класс для авторизации пользователей
    """

    # авторизация
    def post(self, request, *args, **kwargs):
        """
        Вход в аккаунт с указанием "password" и "email"
        """
        if {'email', 'password'}.issubset(request.data):
            user = authenticate(request, username=request.data['email'], password=request.data['password'])
            if user is not None:
                if user.is_active:
                    token, _ = Token.objects.get_or_create(user=user)
                    return JsonResponse({'Status': True,
                                         'Token': token.key})
            return JsonResponse({'Status': False,
                                 'Errors': 'Не удалось авторизовать'},
                                status=403,
                                json_dumps_params={'ensure_ascii': False})
        return JsonResponse({'Status': False,
                             'Errors': 'Не указаны все необходимые аргументы'},
                            status=400,
                            json_dumps_params={'ensure_ascii': False})

    # logout
    def delete(self, request, *args, **kwargs):
        """
        Выход из аккаунта
        """
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False,
                                 'Error': 'Необходима авторизация'},
                                status=403,
                                json_dumps_params={'ensure_ascii': False})
        token = Token.objects.get(user_id=request.user.id)
        if token:
            token.delete()
            return JsonResponse({'Status': True}, status=204)
        else:
            return JsonResponse({'Status': False}, status=400)


class AccountDetails(APIView):
    """
    Класс для работы данными пользователя
    """

    # получить данные
    def get(self, request, *args, **kwargs):
        """
        Получить данные пользователя
        """
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False,
                                 'Error': 'Необходима авторизация'},
                                status=403,
                                json_dumps_params={'ensure_ascii': False})
        serializer = UserSerializer(request.user)
        return Response(serializer.data)

    # изменение данных пользователя
    def post(self, request, *args, **kwargs):
        """
        Изменить данные пользователя, передав изменяемые параметры
        """
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False,
                                 'Error': 'Необходима авторизация'},
                                status=403,
                                json_dumps_params={'ensure_ascii': False})
        if len(request.data) == 0:
            return JsonResponse({'Status': False,
                                 'Errors': 'Не переданы аргументы'},
                                status=400,
                                json_dumps_params={'ensure_ascii': False})
        if request.data.get('type'):
            return JsonResponse({'Status': False,
                                 'Errors': 'Нельзя сменить тип аккаунта'},
                                status=403,
                                json_dumps_params={'ensure_ascii': False})
        if 'password' in request.data:
            try:
                validate_password(request.data['password'])
            except Exception as password_error:
                error_array = [item for item in password_error]
                return JsonResponse({'Status': False,
                                     'Errors': {'password': error_array}}, status=400)
            else:
                request.user.set_password(request.data['password'])
        if 'email' in request.data:
            return JsonResponse({'Status': False,
                                 'Errors': 'Email изменять нельзя'},
                                status=403,
                                json_dumps_params={'ensure_ascii': False})
        # проверяем остальные данные
        user_serializer = UserSerializer(request.user, data=request.data, partial=True)
        if user_serializer.is_valid():
            user_serializer.save()
            return JsonResponse({'Status': True}, status=201)
        else:
            return JsonResponse({'Status': False,
                                 'Errors': user_serializer.errors}, status=400)


class ContactView(APIView):
    """
    Класс для работы с контактами покупателей
    """

    # получить контакты пользователя
    def get(self, request, *args, **kwargs):
        """
        Получить контакты пользователя.
        """
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False,
                                 'Error': 'Необходима авторизация'},
                                status=403,
                                json_dumps_params={'ensure_ascii': False})
        contact = Contact.objects.filter(user_id=request.user.id)
        serializer = ContactSerializer(contact,
                                       many=True)
        return Response(serializer.data)

    # добавить новый контакт
    def post(self, request, *args, **kwargs):
        """
        Создать контакт пользователя.
        Обязательные параметры: "city", "street", "phone", "house".
        """
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False,
                                 'Error': 'Необходима авторизация'},
                                status=403,
                                json_dumps_params={'ensure_ascii': False})
        if {'city', 'street', 'house', 'phone'}.issubset(request.data):
            if len(Contact.objects.filter(user=request.user)) >= 5:
                return JsonResponse({'Status': False,
                                     'Errors': 'Создано максимальное количество контактов'},
                                    status=400,
                                    json_dumps_params={'ensure_ascii': False})
            request.data.update({'user': request.user.id})
            serializer = ContactSerializer(data=request.data)
            if serializer.is_valid():
                serializer.save()
                return JsonResponse({'Status': True},
                                    status=201)
            else:
                JsonResponse({'Status': False,
                              'Errors': serializer.errors})
        return JsonResponse({'Status': False,
                             'Errors': 'Не указаны все необходимые аргументы'},
                            status=400,
                            json_dumps_params={'ensure_ascii': False})

    # редактировать контакт
    def put(self, request, *args, **kwargs):
        """
        Изменить контакт пользователя.
        """
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False,
                                 'Error': 'Необходима авторизация'},
                                status=403,
                                json_dumps_params={'ensure_ascii': False})
        if 'id' in request.data:
            if request.data['id'].isdigit():
                contact = Contact.objects.filter(id=request.data['id'],
                                                 user_id=request.user.id).first()
                if contact:
                    serializer = ContactSerializer(contact,
                                                   data=request.data,
                                                   partial=True)
                    if serializer.is_valid():
                        serializer.save()
                        return JsonResponse({'Status': True},
                                            status=201)
                    else:
                        JsonResponse({'Status': False,
                                      'Errors': serializer.errors})
        return JsonResponse({'Status': False,
                             'Errors': 'Не указаны все необходимые аргументы'},
                            status=400,
                            json_dumps_params={'ensure_ascii': False})

    # удалить контакт
    def delete(self, request, *args, **kwargs):
        """
        Удалить контакт(ы) пользователя.
        Ожидаемый параметр - "items" - список id контактов через запятую.
        """
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False,
                                 'Error': 'Необходима авторизация'},
                                status=403,
                                json_dumps_params={'ensure_ascii': False})
        items_string = request.data.get('items')
        if items_string:
            items_list = [item.strip() for item in items_string.split(',')]
            query = Q()
            objects_deleted = False
            for contact_id in items_list:
                if contact_id.isdigit():
                    query = query | Q(user_id=request.user.id, id=contact_id)
                    objects_deleted = True
            if objects_deleted:
                deleted_count = Contact.objects.filter(query).delete()[0]
                return JsonResponse({'Status': True,
                                     'Удалено объектов': deleted_count},
                                    status=204,
                                    json_dumps_params={'ensure_ascii': False})
        return JsonResponse({'Status': False,
                             'Errors': 'Не указаны все необходимые аргументы'},
                            status=400,
                            json_dumps_params={'ensure_ascii': False})


class ShopInfo(ListAPIView):
    """
    Класс для просмотра/создания/обновления магазина
    """

    def get(self, request, *args, **kwargs):
        """
        Получить данные своего магазина
        """
        shop_id = request.query_params.get('id')
        if shop_id:
            shop = Shop.objects.filter(id=shop_id)
            serializer = ShopSerializer
        elif request.user.is_authenticated and (request.user.type == USER_TYPE_CHOICES[0][0]):
            shop = Shop.objects.filter(user_id=request.user.id)
            serializer = ShopSerializerExtended
        else:
            return JsonResponse({'Status': False,
                                 'Error': 'Указаны не все параметры'},
                                status=400,
                                json_dumps_params={'ensure_ascii': False})
        if shop:
            shop_serializer = serializer(shop, many=True)
            return Response(shop_serializer.data)
        else:
            return JsonResponse({'Status': False,
                                 'Error': 'Магазин не существует'},
                                status=404,
                                json_dumps_params={'ensure_ascii': False})

    def post(self, request, *args, **kwargs):
        """
        Создать магазин.
        Ожидаемые параметры: "url", "name", "state".
        """
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False,
                                 'Error': 'Необходима авторизация'},
                                status=403,
                                json_dumps_params={'ensure_ascii': False})
        if request.user.type != USER_TYPE_CHOICES[0][0]:
            return JsonResponse({'Status': False,
                                 'Error': 'Только для магазинов'},
                                status=403,
                                json_dumps_params={'ensure_ascii': False})
        # определяем какие переданы параметры
        shop_params = {}
        if request.data.get('name'):
            shop_params['name'] = request.data.get('name')
        if request.data.get('state'):
            shop_params['state'] = strtobool(request.data.get('state'))
        url = request.data.get('url')
        if url:
            validate_url = URLValidator()
            try:
                validate_url(url)
            except ValidationError as error:
                return JsonResponse({'Status': False,
                                     'Error': str(error)}, status=400)
            else:
                stream = get(url).content
                data = load_yaml(stream, Loader=Loader)
                shop_params['url'] = url
                shop_params['name'] = data['shop']
        if (len(shop_params) == 0) or ('name' not in shop_params):
            return JsonResponse({'Status': False,
                                 'Errors': 'Не указаны все необходимые аргументы'},
                                status=400,
                                json_dumps_params={'ensure_ascii': False})
        else:
            shop_params['user'] = request.user
            if not Shop.objects.filter(user_id=request.user.id):
                shop = Shop.objects.create(**shop_params)
            else:
                return JsonResponse({'Status': False,
                                     'Errors': 'У этого пользователя уже есть магазин'},
                                    status=400,
                                    json_dumps_params={'ensure_ascii': False})
            if url:
                # добавляем товары из url в БД
                for category in data['categories']:
                    category_object, _ = Category.objects.get_or_create(id=category['id'], name=category['name'])
                    category_object.shops.add(shop.id)
                    category_object.save()
                for item in data['goods']:
                    product, _ = Product.objects.get_or_create(name=item['name'], category_id=item['category'])
                    product_info = ProductInfo.objects.create(product_id=product.id,
                                                              external_id=item['id'],
                                                              model=item['model'],
                                                              price=item['price'],
                                                              price_rrc=item['price_rrc'],
                                                              quantity=item['quantity'],
                                                              shop_id=shop.id)
                    for name, value in item['parameters'].items():
                        parameter_object, _ = Parameter.objects.get_or_create(name=name)
                        ProductParameter.objects.create(product_info_id=product_info.id,
                                                        parameter_id=parameter_object.id,
                                                        value=value)
            return JsonResponse({'Status': True}, status=201)

    def put(self, request, *args, **kwargs):
        """
        Обновить данные магазина.
        Ожидаемые параметры: "url", "name", "state".
        """
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False,
                                 'Error': 'Необходима авторизация'},
                                status=403,
                                json_dumps_params={'ensure_ascii': False})
        if request.user.type != USER_TYPE_CHOICES[0][0]:
            return JsonResponse({'Status': False,
                                 'Error': 'Только для магазинов'},
                                status=403,
                                json_dumps_params={'ensure_ascii': False})
        shop = Shop.objects.filter(user=request.user)
        shop_id = shop.first().id
        if not shop:
            return JsonResponse({'Status': False,
                                 'Errors': 'Магазин еще не создан'},
                                status=400,
                                json_dumps_params={'ensure_ascii': False})
        # определяем какие переданы параметры
        shop_params = {}
        if request.data.get('name'):
            shop_params['name'] = request.data.get('name')
        if request.data.get('state'):
            shop_params['state'] = strtobool(request.data.get('state'))
        url = request.data.get('url')

        if url:
            validate_url = URLValidator()
            try:
                validate_url(url)
            except ValidationError as error:
                return JsonResponse({'Status': False,
                                     'Error': str(error)}, status=400)
            else:
                stream = get(url).content
                data = load_yaml(stream, Loader=Loader)
                shop_params['url'] = url
                shop_params['name'] = data['shop']
        # обновляем магазин если был передан хотя бы один параметр
        if len(shop_params) == 0:
            return JsonResponse({'Status': False,
                                 'Errors': 'Не указаны аргументы'},
                                status=400,
                                json_dumps_params={'ensure_ascii': False})
        else:
            shop.update(**shop_params)
            if url:
                # удаляем старые записи о товарах, относящиеся к магазину
                ProductInfo.objects.filter(shop_id=shop_id).delete()
                # добавляем товары из url в БД
                for category in data['categories']:
                    category_object, _ = Category.objects.get_or_create(id=category['id'], name=category['name'])
                    category_object.shops.add(shop_id)
                    category_object.save()
                for item in data['goods']:
                    product, _ = Product.objects.get_or_create(name=item['name'], category_id=item['category'])
                    product_info = ProductInfo.objects.create(product_id=product.id,
                                                              external_id=item['id'],
                                                              model=item['model'],
                                                              price=item['price'],
                                                              price_rrc=item['price_rrc'],
                                                              quantity=item['quantity'],
                                                              shop_id=shop_id)
                    for name, value in item['parameters'].items():
                        parameter_object, _ = Parameter.objects.get_or_create(name=name)
                        ProductParameter.objects.create(product_info_id=product_info.id,
                                                        parameter_id=parameter_object.id,
                                                        value=value)
            return JsonResponse({'Status': True}, status=201)


class Shops(ListAPIView):
    """
    Класс для просмотра списка магазинов
    """

    queryset = Shop.objects.filter(state=True)
    serializer_class = ShopSerializer


class CategoryView(ListAPIView):
    """
    Класс для просмотра категорий
    """

    queryset = Category.objects.all()
    serializer_class = CategorySerializer


class ProductInfoView(APIView):
    """
    Класс для поиска товаров
    """

    def get(self, request, *args, **kwargs):
        query = Q(shop__state=True)
        shop_id = request.query_params.get('shop_id')
        category_id = request.query_params.get('category_id')
        if shop_id:
            query = query & Q(shop_id=shop_id)
        if category_id:
            query = query & Q(product__category_id=category_id)
        # фильтруем и отбрасываем дубликаты
        queryset = ProductInfo.objects.filter(query).select_related(
            'shop', 'product__category').prefetch_related(
            'product_parameters__parameter').distinct()
        serializer = ProductInfoSerializer(queryset, many=True)
        return Response(serializer.data)


class BasketView(APIView):
    """
    Класс для работы с корзиной
    """

    # получить корзину
    def get(self, request, *args, **kwargs):
        """
        Получить корзину
        """
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False,
                                 'Error': 'Необходима авторизация'},
                                status=403,
                                json_dumps_params={'ensure_ascii': False})
        if request.user.type != USER_TYPE_CHOICES[1][0]:
            return JsonResponse({'Status': False,
                                 'Error': 'Только для покупателей'},
                                status=403,
                                json_dumps_params={'ensure_ascii': False})
        basket = Order.objects.filter(
            user_id=request.user.id, state=ORDER_STATE_CHOICES[0][0]).prefetch_related(
            'ordered_items__product_info__product__category',
            'ordered_items__product_info__product_parameters__parameter').annotate(
            total_sum=Sum(F('ordered_items__quantity') * F('ordered_items__product_info__price'))).distinct()
        serializer = OrderSerializer(basket, many=True)
        return Response(serializer.data)

    # добавить товар в корзину
    def post(self, request, *args, **kwargs):
        """
        Добавить товар в корзину.
        Обязательные параметры: "product_info", "quantity"
        """
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False,
                                 'Error': 'Необходима авторизация'},
                                status=403,
                                json_dumps_params={'ensure_ascii': False})
        if request.user.type != USER_TYPE_CHOICES[1][0]:
            return JsonResponse({'Status': False,
                                 'Error': 'Только для покупателей'},
                                status=403,
                                json_dumps_params={'ensure_ascii': False})
        if {'product_info', 'quantity'}.issubset(request.data) and \
                (type(request.data['product_info']) is int) and \
                (type(request.data['quantity']) is int):
            basket, _ = Order.objects.get_or_create(user_id=request.user.id,
                                                    state=ORDER_STATE_CHOICES[0][0])
            request.data.update({'order': basket.id})
            serializer = OrderItemSerializer(data=request.data)
            if serializer.is_valid():
                try:
                    serializer.save()
                except IntegrityError as error:
                    return JsonResponse({'Status': False,
                                         'Errors': str(error)},
                                        status=400)
                else:
                    return JsonResponse({'Status': True},
                                        status=201, )
            else:
                return JsonResponse({'Status': False,
                                     'Errors': serializer.errors},
                                    status=400)
        return JsonResponse({'Status': False,
                             'Errors': 'Не указаны все необходимые аргументы'},
                            status=400,
                            json_dumps_params={'ensure_ascii': False})

    # изменить количество товара в корзине
    def put(self, request, *args, **kwargs):
        """
        Изменить количество товара в корзине.
        Обязательные параметры: "id", "quantity"
        """
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Необходима авторизация'},
                                status=403,
                                json_dumps_params={'ensure_ascii': False})
        if request.user.type != USER_TYPE_CHOICES[1][0]:
            return JsonResponse({'Status': False,
                                 'Error': 'Только для покупателей'},
                                status=403,
                                json_dumps_params={'ensure_ascii': False})
        if {'id', 'quantity'}.issubset(request.data) and \
                (type(request.data['id']) == int) and \
                (type(request.data['quantity']) == int):
            basket, _ = Order.objects.get_or_create(user_id=request.user.id,
                                                    state=ORDER_STATE_CHOICES[0][0])
            updated_count = OrderItem.objects.filter(
                order_id=basket.id,
                id=request.data['id']).update(quantity=request.data['quantity'])
            if updated_count > 0:
                result = True
                status = 201
            else:
                result = False
                status = 400
            return JsonResponse({'Status': result},
                                status=status)
        else:
            return JsonResponse({'Status': False,
                                 'Errors': 'Не указаны все необходимые аргументы'},
                                status=400,
                                json_dumps_params={'ensure_ascii': False})

    # удалить товар из корзины / очистить корзину
    def delete(self, request, *args, **kwargs):
        """
        Удалить товар из корзины.
        Обязательныы параметр "id", для удаления всех товаров из корзины - указать значение "all"
        """
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Необходима авторизация'},
                                status=403,
                                json_dumps_params={'ensure_ascii': False})
        if request.user.type != USER_TYPE_CHOICES[1][0]:
            return JsonResponse({'Status': False,
                                 'Error': 'Только для покупателей'},
                                status=403,
                                json_dumps_params={'ensure_ascii': False})
        if {'id'}.issubset(request.data):
            basket, _ = Order.objects.get_or_create(user_id=request.user.id,
                                                    state=ORDER_STATE_CHOICES[0][0])
            query = Q(order_id=basket.id)
            if type(request.data['id']) == int:
                query = query & Q(id=request.data['id'])
            elif request.data['id'] != "all":
                return JsonResponse({'Status': False,
                                     'Errors': 'Неверный формат запроса'},
                                    status=400,
                                    json_dumps_params={'ensure_ascii': False})
            deleted_count, deleted_item = OrderItem.objects.filter(query).delete()
            if deleted_count > 0:
                result = True
                status = 204
            else:
                result = False
                status = 400
            return JsonResponse({'Status': result,
                                 'Deleted': f'Удалено {deleted_count} объектов'},
                                status=status,
                                json_dumps_params={'ensure_ascii': False})
        else:
            return JsonResponse({'Status': False,
                                 'Errors': 'Не указаны все необходимые аргументы'},
                                status=400,
                                json_dumps_params={'ensure_ascii': False})


class OrdersView(APIView):
    """
    Класс для получения своих заказов/ заказов своего магазина
    """

    def get(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False,
                                 'Error': 'Необходима авторизация'},
                                status=403,
                                json_dumps_params={'ensure_ascii': False})
        if request.user.type == USER_TYPE_CHOICES[0][0]:
            query = Q(ordered_items__product_info__shop__user_id=request.user.id)
        elif request.user.type == USER_TYPE_CHOICES[1][0]:
            query = Q(user_id=request.user.id)
        else:
            return JsonResponse({'Status': False,
                                 'Error': 'Метод недоступен для администратора'},
                                status=403,
                                json_dumps_params={'ensure_ascii': False})
        orders = Order.objects.filter(query).exclude(
            state=ORDER_STATE_CHOICES[0][0]).prefetch_related(
            'ordered_items__product_info__product__category',
            'ordered_items__product_info__product_parameters__parameter').select_related('contact').annotate(
            total_sum=Sum(F('ordered_items__quantity') * F('ordered_items__product_info__price'))).distinct()
        serializer = OrderSerializer(orders, many=True)
        return Response(serializer.data)


class OrderView(APIView):
    """
    Класс для управления заказами
    """

    # получить данные заказа
    def get(self, request, *args, **kwargs):
        """
        Получить данные заказа по "id"
        """
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False,
                                 'Error': 'Необходима авторизация'},
                                status=403,
                                json_dumps_params={'ensure_ascii': False})
        if {'id'}.issubset(request.query_params):
            try:
                order_id = int(request.query_params['id'])
            except ValueError:
                return JsonResponse({'Status': False,
                                     'Error': 'Неверный формат запроса'},
                                    status=400,
                                    json_dumps_params={'ensure_ascii': False})
            query = Q(id=order_id)  # admin
            if request.user.type == USER_TYPE_CHOICES[0][0]:  # shop
                query = query & Q(ordered_items__product_info__shop__user_id=request.user.id)
            elif request.user.type == USER_TYPE_CHOICES[1][0]:  # buyer
                query = query & Q(user_id=request.user.id)
            order = Order.objects.filter(query).exclude(
                state=ORDER_STATE_CHOICES[0][0]).prefetch_related(
                'ordered_items__product_info__product__category',
                'ordered_items__product_info__product_parameters__parameter').select_related('contact').annotate(
                total_sum=Sum(F('ordered_items__quantity') * F('ordered_items__product_info__price'))).distinct()
            if order.first():
                serializer = OrderSerializer(order.first())
                return Response(serializer.data)
            else:
                return JsonResponse({'Status': False,
                                     'Error': 'Заказ не найден'},
                                    status=400,
                                    json_dumps_params={'ensure_ascii': False})
        else:
            return JsonResponse({'Status': False,
                                 'Error': 'Не переданы все необходимые аргументы'},
                                status=400,
                                json_dumps_params={'ensure_ascii': False})

    # разместить заказ из корзины
    def post(self, request, *args, **kwargs):
        """
        Разместить заказ из корзины.
        Обязательные параметры: "id", "contact"
        """
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False,
                                 'Error': 'Необходима авторизация'},
                                status=403,
                                json_dumps_params={'ensure_ascii': False})
        if request.user.type != USER_TYPE_CHOICES[1][0]:
            return JsonResponse({'Status': False,
                                 'Error': 'Только для покупателей'},
                                status=403,
                                json_dumps_params={'ensure_ascii': False})
        if {'id', 'contact'}.issubset(request.data):
            if (type(request.data['id']) is int) and \
                    (type(request.data['contact']) is int):
                try:
                    is_updated = Order.objects.filter(
                        user_id=request.user.id,
                        id=request.data['id']).update(
                        contact_id=request.data['contact'],
                        state=ORDER_STATE_CHOICES[1][0])
                except IntegrityError:
                    return JsonResponse({'Status': False,
                                         'Errors': 'Неверно указаны аргументы'},
                                        status=400,
                                        json_dumps_params={'ensure_ascii': False})
                else:
                    if is_updated:
                        on_order_state_changed.delay(request.data['id'], request.user.id, ORDER_STATE_CHOICES[1][0])
                        return JsonResponse({'Status': True}, status=201)
        return JsonResponse({'Status': False,
                             'Errors': 'Не указаны все необходимые аргументы'},
                            status=400,
                            json_dumps_params={'ensure_ascii': False})

    # изменить статус заказа
    def put(self, request, *args, **kwargs):
        """
        Изменить статус заказа (для администратора)
        Обязательные параметры: "id", "state"
        """
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False,
                                 'Error': 'Необходима авторизация'},
                                status=403,
                                json_dumps_params={'ensure_ascii': False})
        if request.user.type != USER_TYPE_CHOICES[2][0]:
            return JsonResponse({'Status': False,
                                 'Error': 'Только для администратора'},
                                status=403,
                                json_dumps_params={'ensure_ascii': False})
        if {'id', 'state'}.issubset(request.data):
            if type(request.data['id']) is int:
                try:
                    order = Order.objects.filter(id=request.data['id']).exclude(state=ORDER_STATE_CHOICES[0][0])
                    order_owner = order.first().user.id
                    is_updated = order.update(state=request.data['state'])
                except (IntegrityError, ValueError):
                    return JsonResponse({'Status': False,
                                         'Errors': 'Неверно указаны аргументы'},
                                        status=400,
                                        json_dumps_params={'ensure_ascii': False})
                else:
                    if is_updated:
                        on_order_state_changed.delay(order_owner, request.data['id'], request.data['state'])
                        return JsonResponse({'Status': True},
                                            status=201)
        return JsonResponse({'Status': False,
                             'Errors': 'Не указаны все необходимые аргументы'},
                            status=400,
                            json_dumps_params={'ensure_ascii': False})
