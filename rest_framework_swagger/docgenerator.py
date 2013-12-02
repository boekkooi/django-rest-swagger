""" Generates API documentation by introspection. """
from django.http import HttpRequest

from rest_framework import viewsets

from .introspectors import APIViewIntrospector, \
    ViewSetIntrospector, BaseMethodIntrospector, IntrospectorHelper


class DocumentationGenerator(object):
    def generate(self, apis):
        """
        Returns documentation for a list of APIs
        """
        apis_docs = []
        models_docs = {}
        for api in apis:
            api_info = self.retrieve_api_info(api)

            apis_docs.append({
                'description': IntrospectorHelper.get_view_description(api['callback']),
                'path': api['path'],
                'operations': api_info['operations'],
            })

            if len(api_info['models']) > 0:
                models_docs = dict(models_docs, **api_info['models'])

        return {
            'apis': apis_docs,
            'models': models_docs,
        }

    def retrieve_api_info(self, api):
        """
        Returns docs for the allowed methods of an API endpoint
        """
        introspector = self.resolve_api_introspector(api)

        operations = []
        models = {}

        for method_introspector in introspector:
            if not isinstance(method_introspector, BaseMethodIntrospector) or \
                    method_introspector.get_http_method() == "OPTIONS":
                continue  # No one cares. I impose JSON.

            # Generate the operation information
            operations.append(self.generate_method_operation(method_introspector))

            # Generate the model information (if needed)
            serializer = method_introspector.get_serializer_class()
            serializer_name = IntrospectorHelper.get_serializer_name(serializer)
            if serializer is not None and serializer_name not in models:
                models[serializer_name] = self.generate_model(serializer)

        return {
            'operations': operations,
            'models': models
        }

    def resolve_api_introspector(self, api):
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

    def generate_method_operation(self, introspector):
        serializer = introspector.get_serializer_class()
        serializer_name = IntrospectorHelper.get_serializer_name(serializer)

        operation = {
            'httpMethod': introspector.get_http_method(),
            'summary': introspector.get_summary(),
            'nickname': introspector.get_nickname(),
            'notes': introspector.get_notes(),
            'responseClass': serializer_name,
        }

        parameters = introspector.get_parameters()
        if len(parameters) > 0:
            operation['parameters'] = parameters
        return operation

    def generate_model(self, serializer):
        serializer_name = IntrospectorHelper.get_serializer_name(serializer)
        fields = serializer().get_fields()

        properties = {}
        for name, field in fields.items():
            properties[name] = {
                'type': field.type_label,
                'required': getattr(field, 'required', None),
                'allowableValues': {
                    'min': getattr(field, 'min_length', None),
                    'max': getattr(field, 'max_length', None),
                    'defaultValue': getattr(field, 'default', None),
                    'readOnly': getattr(field, 'read_only', None),
                    'valueType': 'RANGE',
                }
            }

        return {
            'id': serializer_name,
            'properties': properties,
        }