import time

from rest_framework.test import APITestCase
from rest_framework import status
from backend.models import ConfirmEmailToken, Shop
import json
from tokens import DATA_FILE_URL, TEST_PASSWORD, TEST_EMAIL_1, TEST_EMAIL_2


class TestAPI(APITestCase):

    def test_create_activate_user(self, user_type='buyer', test_email=TEST_EMAIL_1):
        # create
        test_password = TEST_PASSWORD
        url = '/api/v1/user/register'
        data = {'first_name': 'user1_first_name',
                'last_name': 'user1_last_name',
                'email': test_email,
                'password': test_password,
                'type': user_type}
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        # activate
        token = str(ConfirmEmailToken.objects.get(user__email=test_email))
        url = '/api/v1/user/register/confirm'
        data = {'token': token,
                'email': test_email}
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        return test_email, test_password

    def test_login(self, user_type='buyer'):
        # create and activate
        if user_type == 'shop':
            test_email = TEST_EMAIL_2
        elif user_type == 'buyer':
            test_email = TEST_EMAIL_1
        test_email, test_password = self.test_create_activate_user(user_type=user_type, test_email=test_email)
        # login
        url = '/api/v1/user/login'
        data = {'password': test_password,
                'email': test_email}
        response = self.client.post(url, data, format='json')
        response_dict_content = json.loads(response.content.decode("UTF-8"))
        self.assertTrue('Token' in response_dict_content.keys())
        return response_dict_content['Token']

    def test_logout(self):
        # create, activate and login
        test_token = self.test_login(user_type='buyer')
        # logout
        url = '/api/v1/user/login'
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + test_token)
        response = self.client.delete(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_get_user_details(self):
        # create, activate and login
        test_token = self.test_login(user_type='buyer')
        # get user details
        url = '/api/v1/user/details'
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + test_token)
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_change_user_details(self):
        # create, activate and login
        test_token = self.test_login(user_type='buyer')
        # change user details
        url = '/api/v1/user/details'
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + test_token)
        data = {'password': 'new_test_user_password',
                'last_name': 'user1_new_last_name'}
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_user_contact_methods(self):
        # create, activate and login
        test_token = self.test_login(user_type='buyer')
        # create new contact
        url = '/api/v1/user/contact'
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + test_token)
        data = {"city": "Новиград",
                "street": "Ленина",
                "phone": "89051234567",
                "house": "12"
                }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        # get created contact
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_dict_content = json.loads(response.content.decode("UTF-8"))
        self.assertEqual(len(response_dict_content), 1)
        # create one more and update first created contact
        contact_id = response_dict_content[0]['id']
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = {"id": f"{contact_id}",
                "city": "Вызима",
                "street": "Центральная",
                "phone": "89051234567",
                "house": "5"
                }
        response = self.client.put(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        response = self.client.get(url, format='json')
        response_dict_content = json.loads(response.content.decode("UTF-8"))
        self.assertEqual(len(response_dict_content), 2)
        # delete first contact
        data = {"items": f"{contact_id}"}
        response = self.client.delete(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_create_shop_info(self):
        # create, activate and login as shop
        test_token = self.test_login(user_type='shop')
        # create shop for user
        data = {'url': DATA_FILE_URL,
                'name': 'NewShop',
                'state': 'false'}
        url = '/api/v1/shop/info'
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + test_token)
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        return test_token

    def test_update_shop_info(self):
        # create, activate and login as shop
        test_token = self.test_create_shop_info()
        shop = Shop.objects.filter(name='Связной').first()
        self.assertTrue(shop)
        # update shop info
        shop_id = shop.id
        url = '/api/v1/shop/info'
        data = {'name': 'NewShop',
                'state': 'true'}
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + test_token)
        response = self.client.put(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        shops = Shop.objects.all()
        self.assertEqual(len(shops), 1)
        self.assertEqual((shops[0]).id, shop_id)
        return test_token

    def test_get_shop_view(self):
        # create, activate and login as shop
        self.test_update_shop_info()
        # get shop view
        url = '/api/v1/shops'
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        shops = json.loads(response.content.decode("UTF-8"))['results']
        self.assertEqual(len(shops), 1)

    def test_get_category_view(self):
        # create, activate and login as shop
        self.test_update_shop_info()
        # get category view
        url = '/api/v1/categories'
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        categories = json.loads(response.content.decode("UTF-8"))['results']
        self.assertEqual(len(categories), 3)

    def test_get_products_view(self):
        # create, activate and login as shop
        self.test_update_shop_info()
        # get product view
        url = '/api/v1/products'
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        goods = json.loads(response.content.decode("UTF-8"))
        self.assertEqual(len(goods), 4)

    def test_basket_methods(self):
        # create, activate and login as shop
        shop_token = self.test_update_shop_info()
        self.client.credentials()
        # create and activate as buyer
        test_email, test_password = self.test_create_activate_user(test_email=TEST_EMAIL_1)
        # login as buyer
        url = '/api/v1/user/login'
        data = {'password': test_password,
                'email': test_email}
        response = self.client.post(url, data, format='json')
        response_dict_content = json.loads(response.content.decode("UTF-8"))
        self.assertTrue('Token' in response_dict_content.keys())
        buyer_token = response_dict_content['Token']
        # add items to basket
        url = '/api/v1/basket'
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + buyer_token)
        data = {"product_info": 1,
                "quantity": 3}
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        # get basket
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # update quantity
        data = {"id": 1,
                "quantity": 2}
        response = self.client.put(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        return buyer_token, shop_token

    def test_clear_basket(self):
        buyer_token, shop_token = self.test_basket_methods()
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + buyer_token)
        # clear basket
        url = '/api/v1/basket'
        data = {"id": "all"}
        response = self.client.delete(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_order_methods(self):
        buyer_token, shop_token = self.test_basket_methods()
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + buyer_token)
        # create contact
        url = '/api/v1/user/contact'
        data = {"city": "Новиград",
                "street": "Ленина",
                "phone": "89051234567",
                "house": "12"
                }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        # create order
        url = '/api/v1/order'
        data = {
                "id": 1,
                "contact": 1
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        # get buyer's orders
        url = '/api/v1/orders'
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # get buyer's order
        url = '/api/v1/order?id=1'
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # get shop orders
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + shop_token)
        url = '/api/v1/orders'
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # get shop's order
        url = '/api/v1/order?id=1'
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # update order status
        url = '/api/v1/order'
        data = {
                "id": 1,
                "state": "assembled"
        }
        response = self.client.put(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)



