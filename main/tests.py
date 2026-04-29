from django.test import TestCase
from django.urls import reverse


class MainViewTests(TestCase):
    def test_index_page_is_available(self):
        response = self.client.get(reverse('index'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Maker Space')
