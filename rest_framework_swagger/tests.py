from django.core.urlresolvers import RegexURLResolver

from django.conf import settings
from django.conf.urls import patterns, url, include
from django.contrib.auth.models import User
from django.contrib.admindocs.utils import trim_docstring
from django.test import TestCase
from django.utils.importlib import import_module
from django.views.generic import View

from rest_framework.views import APIView
from rest_framework.generics import ListCreateAPIView
from rest_framework import serializers
from rest_framework.routers import DefaultRouter
from rest_framework.viewsets import ModelViewSet

from .urlparser import UrlParser
from .docgenerator import DocumentationGenerator
from .docparsers import SimpleDocumentationParser, RstLikeDocumentationParser
from .introspectors import ViewSetIntrospector, APIViewIntrospector, IntrospectorHelper, APIViewMethodIntrospector


class MockApiView(APIView):
    """
    A Test View

    This is more commenting
    """
    def get(self, request):
        """
        Get method specific comments
        """
        pass
    pass


class NonApiView(View):
    pass


class CommentSerializer(serializers.Serializer):
    email = serializers.EmailField()
    content = serializers.CharField(max_length=200)
    created = serializers.DateTimeField()


class UrlParserTest(TestCase):
    def setUp(self):
        self.url_patterns = patterns('',
            url(r'a-view/?$', MockApiView.as_view(), name='a test view'),
            url(r'a-view/child/?$', MockApiView.as_view()),
            url(r'a-view/child2/?$', MockApiView.as_view()),
            url(r'another-view/?$', MockApiView.as_view(), name='another test view'),
        )

    def test_get_apis(self):
        urlparser = UrlParser()
        urls = import_module(settings.ROOT_URLCONF)
        # Overwrite settings with test patterns
        urls.urlpatterns = self.url_patterns
        apis = urlparser.get_apis()

        for api in apis:
            self.assertIn(api['pattern'], self.url_patterns)

    def test_flatten_url_tree(self):
        urlparser = UrlParser()
        apis = urlparser.get_apis(self.url_patterns)

        self.assertEqual(len(self.url_patterns), len(apis))

    def test_flatten_url_tree_url_import(self):
        urls = patterns('', url(r'api/base/path/', include(self.url_patterns)))
        urlparser = UrlParser()
        apis = urlparser.get_apis(urls)

        self.assertEqual(len(self.url_patterns), len(apis))

    def test_flatten_url_tree_with_filter(self):
        urlparser = UrlParser()
        apis = urlparser.get_apis(self.url_patterns, filter_path="a-view")

        self.assertEqual(1, len(apis))

    def test_flatten_url_tree_excluded_namesapce(self):
        urls = patterns('',
            url(r'api/base/path/', include(self.url_patterns, namespace='exclude'))
        )
        urlparser = UrlParser()
        apis = urlparser.__flatten_patterns_tree__(patterns=urls, exclude_namespaces='exclude')

        self.assertEqual([], apis)

    def test_flatten_url_tree_url_import_with_routers(self):

        class MockApiViewSet(ModelViewSet):
            serializer_class = CommentSerializer
            model = User

        class AnotherMockApiViewSet(ModelViewSet):
            serializer_class = CommentSerializer
            model = User

        router = DefaultRouter()
        router.register(r'other_views', MockApiViewSet)
        router.register(r'more_views', MockApiViewSet)

        urls_app = patterns('', url(r'^', include(router.urls)))
        urls = patterns('',
            url(r'api/', include(urls_app)),
            url(r'test/', include(urls_app))
        )
        urlparser = UrlParser()
        apis = urlparser.get_apis(urls)

        self.assertEqual(sum(api['path'].find('api') != -1 for api in apis), 4)
        self.assertEqual(sum(api['path'].find('test') != -1 for api in apis), 4)

    def test_get_api_callback(self):
        urlparser = UrlParser()
        callback = urlparser.__get_pattern_api_callback__(self.url_patterns[0])

        self.assertTrue(issubclass(callback, MockApiView))

    def test_get_api_callback_not_rest_view(self):
        urlparser = UrlParser()
        non_api = patterns('',
            url(r'something', NonApiView.as_view())
        )
        callback = urlparser.__get_pattern_api_callback__(non_api)

        self.assertIsNone(callback)

    def test_get_top_level_api(self):
        urlparser = UrlParser()
        apis = urlparser.get_top_level_apis(urlparser.get_apis(self.url_patterns))

        self.assertEqual(4, len(apis))

    def test_assemble_endpoint_data(self):
        """
        Tests that the endpoint data is correctly packaged
        """
        urlparser = UrlParser()
        pattern = self.url_patterns[0]

        data = urlparser.__assemble_endpoint_data__(pattern)

        self.assertEqual(data['path'], '/a-view/')
        self.assertEqual(data['callback'], MockApiView)
        self.assertEqual(data['pattern'], pattern)

    def test_assemble_data_with_non_api_callback(self):
        bad_pattern = patterns('', url(r'^some_view/', NonApiView.as_view()))

        urlparser = UrlParser()
        data = urlparser.__assemble_endpoint_data__(bad_pattern)

        self.assertIsNone(data)

    def test_exclude_router_api_root(self):
        class MyViewSet(ModelViewSet):
            serializer_class = CommentSerializer
            model = User

        router = DefaultRouter()
        router.register('test', MyViewSet)

        urls_created = len(router.urls)

        parser = UrlParser()
        apis = parser.get_apis(router.urls)

        self.assertEqual(4, urls_created - len(apis))


class NestedUrlParserTest(TestCase):
    def setUp(self):
        class FuzzyApiView(APIView):
            def get(self, request):
                pass

        class ShinyApiView(APIView):
            def get(self, request):
                pass

        api_fuzzy_url_patterns = patterns(
            '', url(r'^item/$', FuzzyApiView.as_view(), name='find_me'))
        api_shiny_url_patterns = patterns(
            '', url(r'^item/$', ShinyApiView.as_view(), name='hide_me'))

        fuzzy_app_urls = patterns(
            '', url(r'^api/', include(api_fuzzy_url_patterns,
                                      namespace='api_fuzzy_app')))
        shiny_app_urls = patterns(
            '', url(r'^api/', include(api_shiny_url_patterns,
                                      namespace='api_shiny_app')))

        self.project_urls = patterns(
            '',
            url('my_fuzzy_app/', include(fuzzy_app_urls)),
            url('my_shiny_app/', include(shiny_app_urls)),
        )

    def test_exclude_nested_urls(self):

        url_parser = UrlParser()
        # Overwrite settings with test patterns
        urlpatterns = self.project_urls
        apis = url_parser.get_apis(urlpatterns,
                                   exclude_namespaces=['api_shiny_app'])
        self.assertEqual(len(apis), 1)
        self.assertEqual(apis[0]['pattern'].name, 'find_me')


class DocumentationGeneratorTest(TestCase):
    def setUp(self):
        self.url_patterns = patterns('',
            url(r'a-view/?$', MockApiView.as_view(), name='a test view'),
            url(r'a-view/child/?$', MockApiView.as_view()),
            url(r'a-view/<pk>/?$', MockApiView.as_view(), name="detailed view for mock"),
            url(r'another-view/?$', MockApiView.as_view(), name='another test view'),
        )

    def test_get_operations(self):

        class AnAPIView(APIView):
            def post(self, *args, **kwargs):
                pass

        api = {
            'path': 'a-path/',
            'callback': AnAPIView,
            'pattern': patterns('')
        }
        docgen = DocumentationGenerator()
        info = docgen.generate([api])

        self.assertEqual('POST', info['apis'][0]['operations'][0]['httpMethod'])

    def test_generate_operations_with_no_methods(self):

        class AnAPIView(APIView):
            pass

        api = {
            'path': 'a-path/',
            'callback': AnAPIView,
            'pattern': patterns('')
        }
        docgen = DocumentationGenerator()
        info = docgen.generate([api])

        self.assertEqual([],  info['apis'][0]['operations'])
        self.assertEqual({},  info['models'])

    def test_get_models(self):
        class SerializedAPI(ListCreateAPIView):
            serializer_class = CommentSerializer

        urlparser = UrlParser()
        url_patterns = patterns('', url(r'my-api/', SerializedAPI.as_view()))
        apis = urlparser.get_apis(url_patterns)

        docgen = DocumentationGenerator()
        info = docgen.generate(apis)

        self.assertIn('CommentSerializer', info['models'])
        self.assertIn('properties', info['models']['CommentSerializer'])
        self.assertEqual(3, len(info['models']['CommentSerializer']['properties']))

    def test_get_serializer_class_access_request_context(self):
        test_case = self
        called = []

        class MyListView(ListCreateAPIView):
            serializer_class = CommentSerializer
            def get_serializer_class(self):
                test_case.assertIsNotNone(self.request)
                called.append(True)
                self.serializer_class.context = {'request': self.request}
                return self.serializer_class


        urlparser = UrlParser()
        url_patterns = patterns('', url(r'my-api/', MyListView.as_view()))
        apis = urlparser.get_apis(url_patterns)

        docgen = DocumentationGenerator()
        info = docgen.generate(apis)

        self.assertIn('CommentSerializer', info['models'])
        self.assertGreater(len(called), 0)


class IntrospectorHelperTest(TestCase):
    def test_get_serializer_name(self):
        self.assertIsNone(IntrospectorHelper.get_serializer_name(None))

        self.assertEqual('IntrospectorHelperTest', IntrospectorHelper.get_serializer_name(IntrospectorHelperTest))

    def test_import_from_string(self):
        # Test invalid arguments
        self.assertEqual(None, IntrospectorHelper.import_from_string('', None))
        self.assertEqual(None, IntrospectorHelper.import_from_string('CommentSerializer', None))

        # Test valid arguments
        self.assertEqual(CommentSerializer, IntrospectorHelper.import_from_string('CommentSerializer', self))
        self.assertEqual(CommentSerializer, IntrospectorHelper.import_from_string('.tests.CommentSerializer', self))

        # Test invalid import arguments
        self.assertEqual(CommentSerializer, IntrospectorHelper.import_from_string('..rest_framework_swagger.tests.CommentSerializer', self))
        self.assertEqual(None, IntrospectorHelper.import_from_string('...rest_framework_swagger.tests.CommentSerializer', self))
        self.assertEqual(None, IntrospectorHelper.import_from_string('ImNotHere', self))

        class FakeModule:
            __module__ = 'evil.test'
        self.assertEqual(None, IntrospectorHelper.import_from_string('CommentSerializer', FakeModule))


class SimpleDocumentationParserTest(TestCase):
    def setUp(self):
        self.parser = SimpleDocumentationParser()

    def tearDown(self):
        self.parser = None

    def test_parse(self):
        docstring = """
            Creates a new user.
            Returns: token - auth token

            email -- e-mail address
            password -- password, optional
            city -- city, optional
            street -- street, optional
            number -- house number, optional
            zip_code -- zip code 10 chars, optional
            phone -- phone number in US format (XXX-XXX-XXXX), optional
            """
        expected = {
            'query': [
                {'dataType': '', 'paramType': 'query', 'name': 'email', 'description': 'e-mail address'},
                {'dataType': '', 'paramType': 'query', 'name': 'password', 'description': 'password, optional'},
                {'dataType': '', 'paramType': 'query', 'name': 'city', 'description': 'city, optional'},
                {'dataType': '', 'paramType': 'query', 'name': 'street', 'description': 'street, optional'},
                {'dataType': '', 'paramType': 'query', 'name': 'number', 'description': 'house number, optional'},
                {'dataType': '', 'paramType': 'query', 'name': 'zip_code', 'description': 'zip code 10 chars, optional'},
                {'dataType': '', 'paramType': 'query', 'name': 'phone', 'description': 'phone number in US format (XXX-XXX-XXXX), optional'}
            ],
            'description': 'Creates a new user.\nReturns: token - auth token',
            'summary': 'Creates a new user'
        }
        self.assertDictEqual(expected, self.parser.parse(docstring))

    def test_strip_params_from_docstring(self):
        docstring = """
            My comments are here

            param -- my param
            """
        docstring = self.parser.strip_params_from_docstring(trim_docstring(docstring))

        self.assertEqual("My comments are here", docstring)

    def test_strip_params_from_docstring_multiline(self):
        docstring = """
            Creates a new user.
            Returns: token - auth token

            email -- e-mail address
            password -- password, optional
            city -- city, optional
            street -- street, optional
            number -- house number, optional
            zip_code -- zip code 10 chars, optional
            phone -- phone number in US format (XXX-XXX-XXXX), optional
            """
        docstring = self.parser.strip_params_from_docstring(docstring)

        expected = 'Creates a new user.\nReturns: token - auth token'
        self.assertEqual(expected, docstring)


class RstLikeDocumentationParserTest(TestCase):
    def setUp(self):
        self.parser = RstLikeDocumentationParser()

    def tearDown(self):
        self.parser = None

    def test_parse(self):
        docstring = """
            Creates a new user.
            Returns: token - auth token
            """
        expected = {
            'query': None,
            'description': 'Creates a new user.\nReturns: token - auth token',
            'summary': 'Creates a new user'
        }
        self.assertDictEqual(expected, self.parser.parse(docstring))

        docstring = """
            :Query:
              size
                  The size of the fox (in meters)
              weight : float
                  :required:
                  The weight of the fox (in stones)
              age : int
                  The age of the fox (in years)

                  This may also be None

            :Post:
              size
                  The size of the fox (in meters)

            :serializer: .serializer
            :deserializer: .deserializer

            :response:
                200
                    Ok
                404: Not found
            :unknown:
                test
                    test
            """
        expected = {
            'description': '',
            'summary': '',
            'query': [
                {'dataType': '', 'paramType': 'form', 'type': '', 'name': 'size', 'description': 'The size of the fox (in meters)'},
                {'paramType': 'form', 'required': True, 'type': 'float', 'name': 'weight', 'description': 'The weight of the fox (in stones)'},
                {'paramType': 'form', 'type': 'int', 'name': 'age', 'description': 'The age of the fox (in years)\n\nThis may also be None'}
            ],
            'post': [
                {'dataType': '', 'paramType': 'form', 'type': '', 'name': 'size', 'description': 'The size of the fox (in meters)'}
            ],
            'serializer': '.serializer',
            'deserializer': '.deserializer',
            'responses': {
                '200': 'Ok',
                '404': 'Not found'
            }
        }
        self.assertDictEqual(expected, self.parser.parse(docstring))


class ViewSetTestIntrospectorTest(TestCase):
    def test_get_allowed_methods(self):
        """
        Tests a ModelViewSet's allowed methods. If the path includes something like {pk},
        consider it an object view, otherwise, a list view
        """

        class MyViewSet(ModelViewSet):
            serializer_class = CommentSerializer
            model = User

        # Test a list endpoint
        introspector = ViewSetIntrospector(
            MyViewSet,
            '/api/endpoint',
            url(r'^/api/endpoint$', MyViewSet.as_view({
                'get': 'list',
                'post': 'create'
            }))
        )
        allowed_methods = list(introspector)
        self.assertEqual(2, len(allowed_methods))
        allowed_methods = [introspector.get_http_method() for introspector in allowed_methods]
        self.assertIn('POST', allowed_methods)
        self.assertIn('GET', allowed_methods)

        # Test an object endpoint
        introspector = ViewSetIntrospector(
            MyViewSet,
            '/api/endpoint/{pk}',
            url(
                r'^/api/endpoint/(?P<{pk}>[^/]+)$',
                MyViewSet.as_view({
                    'get': 'retrieve',
                    'put': 'update',
                    'patch': 'partial_update',
                    'delete': 'destroy'
                })
            )
        )
        allowed_methods = list(introspector)
        self.assertEqual(4, len(allowed_methods))
        allowed_methods = [introspector.get_http_method() for introspector in allowed_methods]
        self.assertIn('PUT', allowed_methods)
        self.assertIn('PATCH', allowed_methods)
        self.assertIn('DELETE', allowed_methods)
        self.assertIn('GET', allowed_methods)


class BaseViewIntrospectorTest(TestCase):
    def test_get_summary(self):
        introspector = APIViewIntrospector(MockApiView, '/', RegexURLResolver(r'^/', ''))
        self.assertEqual('A Test View', introspector.get_summary())

    def test_get_description(self):
        introspector = APIViewIntrospector(MockApiView, '/', RegexURLResolver(r'^/', ''))
        self.assertEqual('A Test View\n\nThis is more commenting', introspector.get_description())

    def test_get_serializer_class(self):
        introspector = APIViewIntrospector(MockApiView, '/', RegexURLResolver(r'^/', ''))
        self.assertEqual(None, introspector.get_serializer_class())


class BaseMethodIntrospectorTest(TestCase):
    def test_get_method_docs(self):

        class TestApiView(APIView):
            def get(self, *args):
                """
                Here are my comments
                """
            pass

        class_introspector = ViewSetIntrospector(TestApiView, '/{pk}', RegexURLResolver(r'^/(?P<{pk}>[^/]+)$', ''))
        introspector = APIViewMethodIntrospector(class_introspector, 'GET')
        docs_get = introspector.get_docs()

        self.assertEqual("Here are my comments", docs_get.strip())

    def test_get_method_summary_without_docstring(self):

        class MyListView(ListCreateAPIView):
            """
            My comment
            """
            pass

        class_introspector = ViewSetIntrospector(MyListView, '/{pk}', RegexURLResolver(r'^/(?P<{pk}>[^/]+)$', ''))
        introspector = APIViewMethodIntrospector(class_introspector, 'POST')
        method_docs = introspector.get_summary()

        self.assertEqual("My comment", method_docs)

    def test_build_body_parameters(self):
        class SerializedAPI(ListCreateAPIView):
            serializer_class = CommentSerializer

        class_introspector = ViewSetIntrospector(SerializedAPI, '/', RegexURLResolver(r'^/$', ''))
        introspector = APIViewMethodIntrospector(class_introspector, 'POST')
        params = introspector.build_body_parameters()

        self.assertEqual('CommentSerializer', params['name'])

    def test_build_form_parameters(self):
        class SerializedAPI(ListCreateAPIView):
            serializer_class = CommentSerializer

        class_introspector = ViewSetIntrospector(SerializedAPI, '/', RegexURLResolver(r'^/$', ''))
        introspector = APIViewMethodIntrospector(class_introspector, 'POST')
        params = introspector.build_form_parameters()

        self.assertEqual(len(CommentSerializer().get_fields()), len(params))

    def test_build_form_parameters_allowable_values(self):

        class MySerializer(serializers.Serializer):
            content = serializers.CharField(max_length=200, min_length=10, default="Vandalay Industries")
            a_read_only_field = serializers.BooleanField(read_only=True)

        class MyAPIView(ListCreateAPIView):
            serializer_class = MySerializer

        class_introspector = ViewSetIntrospector(MyAPIView, '/', RegexURLResolver(r'^/$', ''))
        introspector = APIViewMethodIntrospector(class_introspector, 'POST')
        params = introspector.build_form_parameters()

        self.assertEqual(1, len(params))  # Read only field is ignored
        param = params[0]

        self.assertEqual('content', param['name'])
        self.assertEqual('form', param['paramType'])
        self.assertEqual(True, param['required'])
        self.assertEqual(200, param['allowableValues']['max'])
        self.assertEqual(10, param['allowableValues']['min'])
        self.assertEqual('Vandalay Industries', param['defaultValue'])
