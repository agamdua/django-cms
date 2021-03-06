# -*- coding: utf-8 -*-
from cms.exceptions import PluginAlreadyRegistered, PluginNotRegistered
from cms.plugin_base import CMSPluginBase
from cms.utils.django_load import load
from cms.utils.helpers import reversion_register
from cms.utils.placeholder import get_placeholder_conf
from cms.utils.compat.dj import force_unicode
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.conf.urls.defaults import url, patterns, include
from django.contrib.formtools.wizard.views import normalize_name
from django.template.defaultfilters import slugify
from django.utils.translation import get_language, deactivate_all, activate

class PluginPool(object):
    def __init__(self):
        self.plugins = {}
        self.discovered = False

    def discover_plugins(self):
        if self.discovered:
            return
        self.discovered = True
        load('cms_plugins')

    def register_plugin(self, plugin):
        """
        Registers the given plugin(s).

        If a plugin is already registered, this will raise PluginAlreadyRegistered.
        """
        if not issubclass(plugin, CMSPluginBase):
            raise ImproperlyConfigured(
                "CMS Plugins must be subclasses of CMSPluginBase, %r is not."
                % plugin
            )
        plugin_name = plugin.__name__
        if plugin_name in self.plugins:
            raise PluginAlreadyRegistered(
                "Cannot register %r, a plugin with this name (%r) is already "
                "registered." % (plugin, plugin_name)
            )
        plugin.value = plugin_name
        self.plugins[plugin_name] = plugin

        if 'reversion' in settings.INSTALLED_APPS:
            try:
                from reversion.registration import RegistrationError
            except ImportError:
                from reversion.revisions import RegistrationError
            try:
                reversion_register(plugin.model)
            except RegistrationError:
                pass

    def unregister_plugin(self, plugin):
        """
        Unregisters the given plugin(s).

        If a plugin isn't already registered, this will raise PluginNotRegistered.
        """
        plugin_name = plugin.__name__
        if plugin_name not in self.plugins:
            raise PluginNotRegistered(
                'The plugin %r is not registered' % plugin
            )
        del self.plugins[plugin_name]

    def get_all_plugins(self, placeholder=None, page=None, setting_key="plugins", include_page_only=True):
        self.discover_plugins()
        plugins = list(self.plugins.values())
        plugins.sort(key=lambda obj: force_unicode(obj.name))
        final_plugins = []
        if page:
            template = page.get_template()
        else:
            template = None
        allowed_plugins = get_placeholder_conf(
            setting_key,
            placeholder,
            template,
        )
        for plugin in plugins:
            include_plugin = False
            if placeholder:
                if plugin.require_parent:
                    include_plugin = False
                elif allowed_plugins:
                    if plugin.__name__ in allowed_plugins:
                        include_plugin = True
                elif setting_key == "plugins":
                    include_plugin = True
            if plugin.page_only and not include_page_only:
                include_plugin = False
            if include_plugin:
                final_plugins.append(plugin)
                
        if final_plugins:
            plugins = final_plugins

        # plugins sorted by modules
        plugins = sorted(plugins, key=lambda obj: force_unicode(obj.module))
        return plugins

    def get_text_enabled_plugins(self, placeholder, page):
        plugins = self.get_all_plugins(placeholder, page)
        plugins +=self.get_all_plugins(placeholder, page, 'text_only_plugins')
        final = []
        for plugin in plugins:
            if plugin.text_enabled:
                if plugin not in final:
                    final.append(plugin)
        return final

    def get_plugin(self, name):
        """
        Retrieve a plugin from the cache.
        """
        self.discover_plugins()
        return self.plugins[name]
    
    def get_patterns(self):
        self.discover_plugins()

        # We want untranslated name of the plugin for its slug so we deactivate translation
        lang = get_language()
        deactivate_all()

        try:
            url_patterns = []
            for plugin in self.get_all_plugins():
                p = plugin()
                slug = slugify(force_unicode(normalize_name(p.__class__.__name__)))
                url_patterns += patterns('',
                    url(r'^plugin/%s/' % (slug,), include(p.plugin_urls)),
                )
        finally:
            # Reactivate translation
            activate(lang)

        return url_patterns

plugin_pool = PluginPool()

