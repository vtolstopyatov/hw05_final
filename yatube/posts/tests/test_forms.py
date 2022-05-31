import shutil
import tempfile
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from posts.models import Group, Post
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile

User = get_user_model()

TEMP_MEDIA_ROOT = tempfile.mkdtemp(dir=settings.BASE_DIR)


class PostFormTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Group.objects.create(
            title='Тестовая группа',
            description='Тестовое описание',
            slug='test-slug'
        )
        cls.group = Group.objects.get(slug='test-slug')
        cls.user = User.objects.create_user(username='HasNoName')
        Post.objects.create(
            text='Тестовый пост',
            author=cls.user,
            group=cls.group
        )

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.authorized_client = Client()
        self.authorized_client.force_login(self.user)

    def test_create_post(self):
        """Валидная форма создает запись в Post."""
        posts_count = Post.objects.count()

        form_data = {
            'text': 'Тест создания поста',
            'group': 1,
        }
        response = self.authorized_client.post(
            reverse('posts:post_create'),
            data=form_data,
            follow=True
        )
        self.assertRedirects(
            response, reverse('posts:profile', args={self.user})
        )
        self.assertEqual(Post.objects.count(), posts_count + 1)

    def test_edit_post(self):
        """Валидная форма изменяет запись в Post."""
        form_data = {
            'text': 'Тест изменения поста',
        }
        post = Post.objects.get(text='Тестовый пост')
        response = self.authorized_client.post(
            reverse('posts:post_edit', args=str(post.id)),
            data=form_data,
            follow=True
        )
        self.assertRedirects(
            response, reverse('posts:post_detail', args=str(post.id))
        )
        post = Post.objects.get(id=post.id)
        self.assertEqual(post.text, form_data['text'])

    def test_form_create_post_with_image(self):
        """Форма создания поста отправляет картинку"""
        post_not_exist = Post.objects.filter(
            text='Пост с картинкой'
        ).exists()
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
        form_data = {
            'text': 'Пост с картинкой',
            'image': uploaded,
        }
        response = self.authorized_client.post(
            reverse('posts:post_create'),
            data=form_data,
            follow=True
        )
        self.assertRedirects(
            response, reverse('posts:profile', args={self.user})
        )
        post_exist = Post.objects.filter(text='Пост с картинкой').exists()
        self.assertFalse(post_not_exist)
        self.assertTrue(post_exist)

    def test_comment_form_create_comment(self):
        """После отправки коммент появится на странице поста"""
        post = Post.objects.get(text='Тестовый пост')
        form_data = {'text': 'Коммент'}
        response = self.authorized_client.post(
            reverse('posts:add_comment', args={post.id}),
            data=form_data,
            follow=True,
        )
        comments = response.context.get('comments')
        comment_on_page = comments.filter(text='Коммент').exists()
        self.assertTrue(comment_on_page)
