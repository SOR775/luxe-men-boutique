from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.generic import DetailView, ListView

from .models import BlogPost, NewsletterSubscriber


def marketing_home(request):
    posts = BlogPost.objects.filter(is_published=True)[:3]
    return render(request, 'marketing/home.html', {'posts': posts})


class BlogListView(ListView):
    model = BlogPost
    template_name = 'marketing/blog_list.html'
    context_object_name = 'posts'
    paginate_by = 6

    def get_queryset(self):
        return BlogPost.objects.filter(is_published=True)


class BlogDetailView(DetailView):
    model = BlogPost
    template_name = 'marketing/blog_detail.html'
    context_object_name = 'post'

    def get_queryset(self):
        return BlogPost.objects.filter(is_published=True)


def newsletter_subscribe(request):
    if request.method == 'POST':
        email = (request.POST.get('email') or '').strip().lower()
        if email:
            NewsletterSubscriber.objects.get_or_create(email=email)
            messages.success(request, 'Thanks for subscribing to our newsletter.')
        else:
            messages.error(request, 'Please provide a valid email address.')
    return redirect(request.META.get('HTTP_REFERER', '/'))

