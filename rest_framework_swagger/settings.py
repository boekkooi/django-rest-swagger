from django.conf import settings
from rest_framework.settings import perform_import

USER_SETTINGS = getattr(settings, 'SWAGGER_SETTINGS', None)

DEFAULTS = {
    'exclude_namespaces': [],
    'api_version': '',
    'api_path': '/',
    'api_key': '',
    'enabled_methods': ['get', 'post', 'put', 'patch', 'delete'],
    'is_authenticated': False,
    'is_superuser': False,

    'DEFAULT_DOCUMENTATION_PARSER_CLASSES': 'rest_framework_swagger.docparsers.SimpleDocumentationParser',
    'DEFAULT_URL_PARSER_CLASSES': 'rest_framework_swagger.urlparser.UrlParser'
}

# List of settings that may be in string import notation.
IMPORT_STRINGS = (
    'DEFAULT_DOCUMENTATION_PARSER_CLASSES',
    'DEFAULT_URL_PARSER_CLASSES',
)


class SwaggerSettings(object):
    """
    A settings object, that allows API settings to be accessed as properties.
    For example:

        from rest_framework.settings import api_settings
        print api_settings.DEFAULT_RENDERER_CLASSES

    Any setting with string import paths will be automatically resolved
    and return the class, rather than the string literal.
    """
    def __init__(self, user_settings=None, defaults=None, import_strings=None):
        self.user_settings = user_settings or {}
        self.defaults = defaults or {}
        self.import_strings = import_strings or ()

    def __getattr__(self, attr):
        if attr not in self.defaults.keys():
            raise AttributeError("Invalid SWAGGER setting: '%s'" % attr)

        try:
            # Check if present in user settings
            val = self.user_settings[attr]
        except KeyError:
            # Fall back to defaults
            val = self.defaults[attr]

        # Coerce import strings into classes
        if val and attr in self.import_strings:
            val = perform_import(val, attr)

        # Cache the result
        setattr(self, attr, val)
        return val

swagger_settings = SwaggerSettings(USER_SETTINGS, DEFAULTS, IMPORT_STRINGS)