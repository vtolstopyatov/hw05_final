import shutil
import tempfile
from django import forms
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from posts.models import Group, Post
from django.core.cache import cache
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile

User = get_user_model()

TEMP_MEDIA_ROOT = tempfile.mkdtemp(dir=settings.BASE_DIR)


class PostsPagesTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Group.objects.bulk_create([
            Group(
                title='Тестовая группа 1',
                description='Тестовое описание',
                slug='test-slug'
            ),
            Group(
                title='Тестовая группа 2',
                description='Тестовое описание группы 2',
                slug='test-second_slug'
            ),
        ])
        cls.group = Group.objects.get(slug='test-slug')
        cls.group_2 = Group.objects.get(slug='test-second_slug')
        cls.user = User.objects.create_user(username='HasNoName')
        cls.another_user = User.objects.create_user(username='Стас Барецкий')
        count_of_creating_post = 13
        objs = [
            Post(text='Тестовый пост %s' % i, author=cls.user, group=cls.group)
            for i in range(count_of_creating_post)
        ]
        objs.extend([
            Post(
                text='Тестовый пост другого пользователя',
                author=cls.another_user,
                group=cls.group,
            ),
            Post(
                text='Тестовый пост в другой группе',
                author=cls.another_user,
                group=cls.group_2,
            ),
        ])
        Post.objects.bulk_create(objs)

    def setUp(self):
        self.authorized_client = Client()
        self.authorized_client.force_login(self.user)
        self.another_authorized_client = Client()
        self.another_authorized_client.force_login(self.another_user)
        cache.clear()

    def test_pages_uses_correct_template(self):
        """URL-адрес использует соответствующий шаблон."""
        pages_templates_names = {
            reverse('posts:posts_main'): 'posts/index.html',
            reverse(
                'posts:group_list',
                kwargs={'slug': 'test-slug'}
            ): 'posts/group_list.html',
            reverse('posts:profile', args={'HasNoName'}): 'posts/profile.html',
            reverse('posts:post_detail', args={'1'}): 'posts/post_detail.html',
            reverse('posts:post_create'): 'posts/create_post.html',
            reverse('posts:post_edit', args={'1'}): 'posts/create_post.html',
        }
        for reverse_name, template in pages_templates_names.items():
            with self.subTest(reverse_name=reverse_name):
                response = self.authorized_client.get(reverse_name)
                self.assertTemplateUsed(response, template)

    def test_paginator_records(self):
        posts_on_second_page = {
            reverse('posts:posts_main'): 5,
            reverse(
                'posts:group_list',
                kwargs={'slug': 'test-slug'}
            ): 4,
            reverse('posts:profile', args={'HasNoName'}): 3,
        }
        for reverse_name, count in posts_on_second_page.items():
            with self.subTest(reverse_name=reverse_name):
                response = self.authorized_client.get(reverse_name)
                """Проверка: количество постов на первой странице равно 10."""
                self.assertEqual(len(response.context['page_obj']), 10)
                response = self.authorized_client.get(reverse_name + '?page=2')
                """Проверка:
                 количество постов на второй странице совпадает с ожидаемым."""
                self.assertEqual(len(response.context['page_obj']), count)

    def test_post_detail_page_show_correct_context(self):
        """Шаблон post_detail сформирован с правильным контекстом."""
        post = Post.objects.get(text='Тестовый пост в другой группе')
        response = self.authorized_client.get(
            reverse('posts:post_detail', args={post.id})
        )
        post_object = response.context['post']
        self.assertEqual(post_object, post)

    def test_create_post_page_show_correct_context(self):
        """Шаблон create_post сформирован с правильным контекстом."""
        response = self.authorized_client.get(reverse('posts:post_create'))
        form_fields = {
            'text': forms.fields.CharField,
            'group': forms.fields.ChoiceField,
        }

        for value, expected in form_fields.items():
            with self.subTest(value=value):
                form_field = response.context.get('form').fields.get(value)
                self.assertIsInstance(form_field, expected)

    def test_post_edit_page_show_correct_context(self):
        """Шаблон post_edit сформирован с правильным контекстом."""
        response = self.authorized_client.get(
            reverse('posts:post_edit', args={'1'})
        )
        form_fields = {
            'text': forms.fields.CharField,
            'group': forms.fields.ChoiceField,
        }

        for value, expected in form_fields.items():
            with self.subTest(value=value):
                form_field = response.context.get('form').fields.get(value)
                self.assertIsInstance(form_field, expected)

    def test_group_2_must_be_clear(self):
        """В группе 2 только нужные посты"""
        response = self.authorized_client.get(
            reverse(
                'posts:group_list',
                kwargs={'slug': 'test-second_slug'}
            )
        )
        first_object = response.context['page_obj'][0]
        post_text_0 = first_object.text
        self.assertEqual(post_text_0, 'Тестовый пост в другой группе')
        self.assertEqual(len(response.context['page_obj']), 1)

    def test_cache_index_page(self):
        """Cache главной страницы работает корректно"""
        Post.objects.create(
            text='Тест кеша',
            author=self.user
        )
        cache.clear()
        response = self.authorized_client.get(
            reverse('posts:posts_main')
        )
        before_delete = response.content
        Post.objects.get(text='Тест кеша').delete()
        response = self.authorized_client.get(
            reverse('posts:posts_main')
        )
        after_delete = response.content
        self.assertEqual(before_delete, after_delete)
        cache.clear()
        response = self.authorized_client.get(
            reverse('posts:posts_main')
        )
        after_clear = response.content
        self.assertNotEqual(before_delete, after_clear)

    def test_subscribe_service_work_correctly(self):
        """Подписка на авторов работает корректно"""
        user = self.user
        # Без подписки постов нет
        response = self.another_authorized_client.get(
            reverse('posts:follow_index')
        )
        follows = response.context.get('page_obj')
        self.assertEqual(len(follows), 0)
        # Подписка
        response = self.another_authorized_client.get(
            reverse('posts:profile_follow', args={user}), follow=True
        )
        self.assertRedirects(
            response, reverse('posts:profile', args={user})
        )
        # После подписки стало 10 постов на странице
        response = self.another_authorized_client.get(
            reverse('posts:follow_index')
        )
        follows = response.context.get('page_obj')
        self.assertEqual(len(follows), 10)
        # У пользователя без подписок страница пуста
        response = self.authorized_client.get(
            reverse('posts:follow_index')
        )
        follows = response.context.get('page_obj')
        self.assertEqual(len(follows), 0)
        # Атписка
        response = self.another_authorized_client.get(
            reverse('posts:profile_unfollow', args={user}), follow=True
        )
        self.assertRedirects(
            response, reverse('posts:profile', args={user})
        )
        # После отписки постов снова нет
        response = self.another_authorized_client.get(
            reverse('posts:follow_index')
        )
        follows = response.context.get('page_obj')
        self.assertEqual(len(follows), 0)


class PostsPagesImagesTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        small_gif = (
            b'\x47\x49\x46\x38\x39\x61\x02\x00'
            b'\x01\x00\x80\x00\x00\x00\x00\x00'
            b'\xFF\xFF\xFF\x21\xF9\x04\x00\x00'
            b'\x00\x00\x00\x2C\x00\x00\x00\x00'
            b'\x02\x00\x01\x00\x00\x02\x02\x0C'
            b'\x0A\x00\x3B'
        )
        uploaded = SimpleUploadedFile(
            name='small.gif',
            content=small_gif,
            content_type='image/gif'
        )
        Group.objects.create(
            title='Тестовая группа 1',
            description='Тестовое описание',
            slug='test-slug',
        )
        cls.group = Group.objects.get(slug='test-slug')
        cls.user = User.objects.create_user(username='HasNoName')
        Post.objects.create(
            text='Тестовый пост с картинкой',
            author=cls.user,
            group=cls.group,
            image=uploaded,
        )

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.authorized_client = Client()
        self.authorized_client.force_login(self.user)
        cache.clear()

    def test_image_in_context(self):
        """Изображение передаётся в контексте"""
        image = Post.objects.get(text='Тестовый пост с картинкой').image
        paginator_fields = {
            reverse('posts:posts_main'): 'page_obj',
            reverse(
                'posts:group_list',
                kwargs={'slug': 'test-slug'}
            ): 'page_obj',
            reverse('posts:profile', args={'HasNoName'}): 'page_obj',
        }

        for value, name in paginator_fields.items():
            with self.subTest(value=value):
                response = self.authorized_client.get(value)
                form_field = response.context.get(name)[0].image
                self.assertEqual(str(form_field), image)

        response = self.authorized_client.get(
            reverse('posts:post_detail', args={'1'})
        )
        form_field = response.context.get('post').image
        self.assertEqual(str(form_field), image)
