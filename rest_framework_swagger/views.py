from django.views.generic import View
from django.utils.safestring import mark_safe
from django.shortcuts import render_to_response, RequestContext
from django.core.exceptions import PermissionDenied

from rest_framework.views import Response

from rest_framework_swagger.apidocview import APIDocView
from rest_framework_swagger.docgenerator import DocumentationGenerator
from rest_framework_swagger.settings import swagger_settings

UrlParser = getattr(swagger_settings, 'DEFAULT_URL_PARSER_CLASSES')


class SwaggerUIView(View):

    def get(self, request, *args, **kwargs):

        if not self.has_permission(request):
            raise PermissionDenied()

        template_name = "rest_framework_swagger/index.html"
        data = {
            'swagger_settings': {
                'discovery_url': "%sapi-docs/" % request.build_absolute_uri(),
                'api_key': getattr(swagger_settings, 'api_key', ''),
                'enabled_methods': mark_safe(getattr(swagger_settings, 'enabled_methods'))
            }
        }
        response = render_to_response(template_name, RequestContext(request, data))

        return response

    def has_permission(self, request):
        if getattr(swagger_settings, 'is_superuser') and not request.user.is_superuser:
            return False

        if getattr(swagger_settings, 'is_authenticated') and not request.user.is_authenticated():
            return False

        return True


class SwaggerResourcesView(APIDocView):

    def get(self, request):
        apis = []
        resources = self.get_resources()

        for path in resources:
            apis.append({
                'path': "/%s" % path,
            })

        return Response({
            'apiVersion': getattr(swagger_settings, 'api_version', ''),
            'swaggerVersion': '1.2',
            'basePath': self.host.rstrip('/'),
            'apis': apis
        })

    def get_resources(self):
        urlparser = UrlParser()
        apis = urlparser.get_apis(exclude_namespaces=getattr(swagger_settings, 'exclude_namespaces'))
        return urlparser.get_top_level_apis(apis)


class SwaggerApiView(APIDocView):

    def get(self, request, path):
        apis = self.get_api_for_resource(path)

        generator = DocumentationGenerator()
        apis_info = generator.generate(apis)

        return Response({
            'apis': apis_info['apis'],
            'models': apis_info['models'],
            'basePath': self.api_full_uri.rstrip('/'),
        })

    def get_api_for_resource(self, filter_path):
        urlparser = UrlParser()
        return urlparser.get_apis(filter_path=filter_path)
