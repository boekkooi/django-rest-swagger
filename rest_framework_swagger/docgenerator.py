""" Generates API documentation by introspection. """
import inspect
import re
from django.http import HttpRequest

from rest_framework import viewsets
from rest_framework.relations import PrimaryKeyRelatedField
from rest_framework.serializers import BaseSerializer

from .settings import swagger_settings
from .introspectors import APIViewIntrospector, \
    ViewSetIntrospector, BaseMethodIntrospector, SerializerIntrospector

formatter = getattr(swagger_settings, 'DOCUMENTATION_FORMATTER')().format


class DocumentationGenerator(object):
    def generate(self, apis):
        """
        Returns documentation for a list of APIs
        """
        apis_docs = []
        models_docs = {}
        for api in apis:
            api_info = self._retrieve_api_info(api)

            apis_docs.append({
                'description': formatter(api_info['description']),
                'path': api['path'],
                'operations': api_info['operations'],
            })

            if len(api_info['models']) > 0:
                models_docs = dict(models_docs, **api_info['models'])

        return {
            'apis': apis_docs,
            'models': models_docs,
        }

    def _retrieve_api_info(self, api):
        """
        Returns docs for the allowed methods of an API endpoint
        """
        introspector = self._resolve_api_introspector(api)

        operations = []
        models = ModelGenerator()

        for method_introspector in introspector:
            if not isinstance(method_introspector, BaseMethodIntrospector) or \
                    method_introspector.get_http_method() == "OPTIONS":
                continue  # No one cares. I impose JSON.

            # Generate the operation information
            operations.append(self._generate_method_operation(method_introspector))

            # Generate the model information (if needed)
            serializer = method_introspector.get_serializer_class()
            if serializer is not None:
                models.register(serializer)

            deserializer = method_introspector.get_deserializer_class()
            if deserializer is not None:
                models.register(deserializer)

        return {
            'description': formatter(introspector.get_description()),
            'operations': operations,
            'models': models.generate()
        }

    def _resolve_api_introspector(self, api):
        """
        Returns a api introspector based on the provided api information.
        """
        path = api['path']
        pattern = api['pattern']
        callback = api['callback']
        callback.request = HttpRequest()

        if issubclass(callback, viewsets.ViewSetMixin):
            return ViewSetIntrospector(callback, path, pattern)
        else:
            return APIViewIntrospector(callback, path, pattern)

    def _generate_method_operation(self, introspector):
        serializer = introspector.get_serializer_class()
        serializer_name = SerializerIntrospector.get_identifier(serializer)

        operation = {
            'httpMethod': introspector.get_http_method(),
            'summary': introspector.get_summary(),
            'nickname': introspector.get_nickname(),
            'notes': formatter(introspector.get_notes()),
            'responseClass': serializer_name,
        }

        # Add operation parameters
        operation['parameters'] = self._generate_method_parameters(introspector)

        # Add operation responses
        responses = introspector.get_response_messages()
        if isinstance(responses, dict) and len(responses) > 0:
            messages = []
            for code in responses:
                description = responses[code]
                messages.append({
                    'code': code,
                    'message': formatter(description)
                })
            operation['responseMessages'] = messages

        return operation

    def _generate_method_parameters(self, introspector):
        params = []

        params += self._generate_method_url_parameters(introspector)
        params += self._generate_method_query_parameters(introspector)
        if introspector.get_http_method() in ["GET", "DELETE"]:
            return params

        form_params = self._generate_method_form_parameters(introspector)
        params += form_params

        if not form_params:
            body_params = self._generate_method_body_parameters(introspector)
            params += body_params

        return params

    def _generate_method_url_parameters(self, introspector):
        """
        Gets the parameters from the URL
        """
        url_params = re.findall('/{([^}]*)}', introspector.path)
        params = []

        for param in url_params:
            params.append({
                'paramType': 'path',
                'name': param,
                'type': 'string',
                'required': True
            })

        return params

    def _generate_method_query_parameters(self, introspector):
        params = []

        if 'query' in introspector.documentation and introspector.documentation['query'] is not None:
            params += introspector.documentation['query']

        if 'query' in introspector.parent.documentation and introspector.parent.documentation['query'] is not None:
            params += introspector.parent.documentation['query']

        return params

    def _generate_method_form_parameters(self, introspector):
        params = []

        serializer = introspector.get_deserializer_class()
        if serializer is None:
            return params

        # Loop the base fields
        fields = serializer().get_fields()
        for name, field in fields.items():
            if getattr(field, 'read_only', False):
                continue

            prop = ModelGenerator.generate_field(field)
            prop['paramType'] = 'form'
            prop['name'] = name
            params.append(prop)

        return params

    def _generate_method_body_parameters(self, introspector):
        serializer = introspector.get_deserializer_class()
        if serializer is None:
            return []

        return [{
            'name': serializer.__name__,
            'dataType': serializer.__name__,
            'paramType': 'body',
        }]


class ModelGenerator:
    def __init__(self):
        self.serializers = {}
        self.models = {}

    def register(self, serializer):
        id = SerializerIntrospector.get_identifier(serializer)
        if id not in self.models:
            self.serializers[id] = self.get_serializer_class(serializer)

    def generate(self):
        while len(self.serializers) > 0:
            (id, serializer) = self.serializers.popitem()
            if id in self.models:
                continue

            self.models[id] = self._generate_model(id, serializer)
        return self.models

    def _generate_model(self, id, serializer):
        fields = serializer().get_fields()
        properties = {}
        for name, field in fields.items():
            properties[name] = self.generate_field(field, model_generator=self)

        return {
            'id': id,
            'properties': properties
        }


    @staticmethod
    def get_serializer_class(serializer):
        if inspect.isclass(serializer):
            return serializer
        return serializer.__class__

    @staticmethod
    def generate_field(field, model_generator=None):
        """
        Convert a serializer field to a api representation
        """
        prop = {
            'type': field.type_label,
            'required': getattr(field, 'required', None),
            'readOnly': getattr(field, 'read_only', None),

            'description': getattr(field, 'help_text', ''),

            'defaultValue': getattr(field, 'default', None),
            'minimum': getattr(field, 'min_length', None),
            'maximum': getattr(field, 'max_length', None),
        }

        if field.type_label == 'multiple choice' and isinstance(field.choices, list):
            prop['type'] = 'string'
            prop['enum'] = [k for k, v in field.choices]

        if field.type_label == 'field':
            is_primitive = field_type = None
            if isinstance(field, PrimaryKeyRelatedField):
                is_primitive = True
                # TODO resolve pk type
                field_type = 'integer'
            if isinstance(field, BaseSerializer):
                is_primitive = False
                field_type = SerializerIntrospector.get_identifier(field)
                if model_generator is not None:
                    model_generator.register(field)

            if field_type is not None:
                if field.many:
                    prop['type'] = 'array'
                    if is_primitive:
                        prop['items'] = {'type': field_type}
                    else:
                        prop['items'] = {'$ref': field_type}
                else:
                    prop['type'] = field_type

        return dict((k, v) for k, v in prop.items() if v is not None)
