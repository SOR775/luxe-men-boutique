# config/__init__.py

# Compatibility shim for Django 5.0.x on Python 3.14.
# The default BaseContext.__copy__ implementation uses copy(super()), which
# breaks under this runtime when Django tries to copy template contexts.
try:
    from django.template import context as template_context

    def _compat_basecontext_copy(self):
        duplicate = self.__class__.__new__(self.__class__)
        duplicate.__dict__.update(self.__dict__)
        duplicate.dicts = self.dicts[:]
        return duplicate

    if getattr(template_context.BaseContext.__copy__, '__module__', None) == 'django.template.context':
        template_context.BaseContext.__copy__ = _compat_basecontext_copy
except Exception:
    pass
