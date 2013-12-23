"""Handles the instrospection of REST Framework Views and ViewSets."""
from abc import ABCMeta, abstractmethod
from django.utils import importlib
import re

from rest_framework.views import get_view_name

from rest_framework_swagger.settings import swagger_settings

documentation_parser = getattr(swagger_settings, 'DEFAULT_DOCUMENTATION_PARSER_CLASSES')()


class IntrospectorHelper(object):
    __metaclass__ = ABCMeta

    @staticmethod
    def get_serializer_name(serializer):
        if serializer is None:
            return None

        return serializer.__name__

    @staticmethod
    def resolve_documentation_information(callback, documentation):
        if 'serializer' in documentation and isinstance(documentation['serializer'], str):
            documentation['serializer'] = IntrospectorHelper.import_from_string(documentation['serializer'], callback)
        if 'deserializer' in documentation and isinstance(documentation['deserializer'], str):
            documentation['deserializer'] = IntrospectorHelper.import_from_string(documentation['deserializer'], callback)
        return documentation

    @staticmethod
    def import_from_string(name, callback):
        if not name or not callback or not hasattr(callback, '__module__'):
            return None

        # TODO add support for import names (`from .. import .. as ..`) maybe use ModuleFinder?
        if name.find('.') == -1:
            # within current module/file
            class_name = name
            module_path = callback.__module__
        else:
            # relative lookup?
            if name[0] == '.':
                module_path = callback.__module__
                while name[0] == '.':
                    idx = module_path.rfind('.')
                    if idx == -1:
                        if module_path == '':
                            return None
                        module_path = ''
                    else:
                        module_path = module_path[:idx]

                    name = name[1:]
                    if len(name) <= 1:
                        return None

                if module_path:
                    name = module_path + '.' + name

            # extract class and module
            parts = name.split('.')
            module_path, class_name = '.'.join(parts[:-1]), parts[-1]

        try:
            module = importlib.import_module(module_path)
            if hasattr(module, class_name):
                return getattr(module, class_name)
        except ImportError as e:
            pass
        return None


class BaseViewIntrospector(object):
    __metaclass__ = ABCMeta

    def __init__(self, callback, path, pattern):
        self.callback = callback
        self.path = path
        self.pattern = pattern

        self.documentation = IntrospectorHelper.resolve_documentation_information(
            self.callback,
            documentation_parser.parse(self.callback.__doc__ or '')
        )

    @abstractmethod
    def __iter__(self):
        pass

    def get_iterator(self):
        return self.__iter__()

    def get_serializer_class(self):
        if hasattr(self.callback, 'get_serializer_class'):
            return self.callback().get_serializer_class()

    def get_deserializer_class(self):
        if 'deserializer' in self.documentation and self.documentation['deserializer'] is not None:
            return self.documentation['deserializer']
        return self.get_serializer_class()

    def get_description(self):
        return self.documentation['description']

    def get_summary(self):
        """
        Returns the first sentence of the first line of the class docstring
        """
        return self.documentation['summary']


class BaseMethodIntrospector(object):
    __metaclass__ = ABCMeta

    def __init__(self, view_introspector, method):
        self.method = method
        self.parent = view_introspector
        self.callback = view_introspector.callback
        self.path = view_introspector.path

        self.documentation = IntrospectorHelper.resolve_documentation_information(
            self.callback,
            documentation_parser.parse(self.retrieve_docstring())
        )

    def get_serializer_class(self):
        if 'serializer' in self.documentation and self.documentation['serializer'] is not None:
            return self.documentation['serializer']
        return self.parent.get_serializer_class()

    def get_deserializer_class(self):
        if 'deserializer' in self.documentation and self.documentation['deserializer'] is not None:
            return self.documentation['deserializer']
        if 'serializer' in self.documentation and self.documentation['serializer'] is not None:
            return self.documentation['serializer']
        return self.parent.get_deserializer_class()

    def get_http_method(self):
        return self.method

    def get_nickname(self):
        """ Returns the APIView's nickname """
        return get_view_name(self.callback).replace(' ', '_')

    def get_summary(self):
        if 'summary' in self.documentation and self.documentation['summary'] is not None:
            return self.documentation['summary']

        # If there is no docstring on the method, get class docs
        return self.parent.get_summary()

    def get_notes(self):
        """
        Returns the body of the docstring trimmed before any parameters are
        listed. First, get the class docstring and then get the method's. The
        methods will always inherit the class comments.
        """
        docstring = ""

        if 'description' in self.parent.documentation and self.parent.documentation['description'] is not None:
            docstring += self.parent.documentation['description'] + '\n'

        if 'description' in self.documentation and self.documentation['description'] is not None:
            docstring += self.documentation['description']

        docstring = docstring.strip().replace("\n\n", "<br/>")

        return docstring

    def retrieve_docstring(self):
        """
        Attempts to fetch the docs for a class method. Returns None
        if the method does not exist
        """
        method = str(self.method).lower()
        if not hasattr(self.callback, method):
            return None
        return getattr(self.callback, method).__doc__

    def get_parameters(self):
        """
        Returns parameters for an API. Parameters are a combination of HTTP
        query parameters as well as HTTP body parameters that are defined by
        the DRF serializer fields
        """
        params = []

        params += self.build_path_parameters()
        params += self.build_query_params()

        if self.get_http_method() in ["GET", "DELETE"]:
            return params

        form_params = self.build_form_parameters()
        params += form_params

        if not form_params:
            body_params = self.build_body_parameters()
            if body_params is not None:
                params.append(body_params)

        return params

    def build_form_parameters(self):
        """
        Builds form parameters from the serializer class
        """
        if 'post' in self.documentation and self.documentation['post'] is not None:
            return self.documentation['post']
        else:
            return self.build_form_deserializer_parameters()

    def build_form_deserializer_parameters(self):
        data = []
        serializer = self.get_deserializer_class()

        if serializer is None:
            return data

        fields = serializer().get_fields()

        for name, field in fields.items():

            if getattr(field, 'read_only', False):
                continue

            data_type = field.type_label
            max_length = getattr(field, 'max_length', None)
            min_length = getattr(field, 'min_length', None)
            allowable_values = None

            if max_length is not None or min_length is not None:
                allowable_values = {
                    'max': max_length,
                    'min': min_length,
                    'valueType': 'RANGE'
                }

            data.append({
                'paramType': 'form',
                'name': name,
                'dataType': data_type,
                'allowableValues': allowable_values,
                'description': getattr(field, 'help_text', ''),
                'defaultValue': getattr(field, 'default', None),
                'required': getattr(field, 'required', None)
            })

        return data

    def build_body_parameters(self):
        serializer = self.get_deserializer_class()
        if serializer is None:
            return None

        return {
            'name': serializer.__name__,
            'dataType': serializer.__name__,
            'paramType': 'body',
        }

    def build_path_parameters(self):
        """
        Gets the parameters from the URL
        """
        url_params = re.findall('/{([^}]*)}', self.path)
        params = []

        for param in url_params:
            params.append({
                'name': param,
                'dataType': 'string',
                'paramType': 'path',
                'required': True
            })

        return params

    def build_query_params(self):
        params = []

        if 'query' in self.documentation and self.documentation['query'] is not None:
            params += self.documentation['query']

        if 'query' in self.parent.documentation and self.parent.documentation['query'] is not None:
            params += self.parent.documentation['query']

        return params


class APIViewIntrospector(BaseViewIntrospector):
    def __iter__(self):
        methods = self.callback().allowed_methods
        for method in methods:
            yield APIViewMethodIntrospector(self, method)


class APIViewMethodIntrospector(BaseMethodIntrospector):
    def get_docs(self):
        """
        Attempts to retrieve method specific docs for an
        endpoint. If none are available, the class docstring
        will be used
        """
        return self.retrieve_docstring()


class ViewSetIntrospector(BaseViewIntrospector):
    """Handle ViewSet introspection."""

    def __iter__(self):
        methods = self._resolve_methods()
        for method in methods:
            yield ViewSetMethodIntrospector(self, methods[method], method)

    def _resolve_methods(self):
        if not hasattr(self.pattern.callback, 'func_code') or \
                not hasattr(self.pattern.callback, 'func_closure') or \
                not hasattr(self.pattern.callback.func_code, 'co_freevars') or \
                'actions' not in self.pattern.callback.func_code.co_freevars:
            raise RuntimeError('Unable to use callback invalid closure/function specified.')

        idx = self.pattern.callback.func_code.co_freevars.index('actions')
        return self.pattern.callback.func_closure[idx].cell_contents if not None else []


class ViewSetMethodIntrospector(BaseMethodIntrospector):
    """Handle ViewSet method introspection."""

    def __init__(self, view_introspector, method, http_method):
        super(ViewSetMethodIntrospector, self).__init__(view_introspector, method)
        self.http_method = http_method.upper()

    def get_http_method(self):
        return self.http_method
