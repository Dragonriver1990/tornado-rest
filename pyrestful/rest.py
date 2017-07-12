#!/usr/bin/env python
# -*- coding: utf-8 -*-

import inspect
import json
import re
import xml.dom.minidom

import tornado.ioloop
import tornado.web
import tornado.wsgi
from pyconvert.pyconv import convert2XML, convert2JSON

from pyrestful import mediatypes, types


class RestApplication(tornado.web.Application):
    """
    RestApplication
    通过这个类型，创建的应用提供的服务的接口满足标准的REST
    """
    resource = None

    def __init__(self, rest_resources, handlers=None,
                 default_host="", transforms=None, **settings):
        """
        初始化，主要就是根据资源，将资源包含的操作转换成rest风格的接口

        :param rest_resources: 资源（资源中提供RESTFul接口）
               这里实现的资源类是继承
        :param handlers: 普通handlers，不一定符合真RESTFul标准，可能是hybrid Restful接口
        :param default_host: 与tornado Application相同
        :param transforms: 与tornado Application相同
        :param settings: 与tornado Application相同
        """
        rest_handlers = list()

        for r in rest_resources:
            svs = self.generate_rest_service_handlers(r)
            rest_handlers += svs

        if handlers:
            rest_handlers += handlers
        # 调用父类初始化函数
        tornado.web.Application.__init__(self, rest_handlers, default_host, transforms, **settings)

    @staticmethod
    def generate_rest_service_handlers(resource):
        """
        这一块是核心，将资源包含的操作转换成接口
        :param resource:
        :return:
        """
        svs = resource.get_handlers()
        return svs


class RestWSGIApplication(tornado.wsgi.WSGIApplication):
    """
    RestWSGIApplication
    通过这个类型，创建的应用提供的服务的接口满足标准的REST
    """
    resource = None

    def __init__(self, rest_resources, resource=None, handlers=None,
                 default_host="", transforms=None, **settings):
        """
        初始化，主要就是根据资源，将资源包含的操作转换成rest风格的接口

        :param rest_resources: 资源（资源中提供RESTFul接口）
               这里实现的资源类是继承
        :param resource:
        :param handlers: 普通handlers，不一定符合真RESTFul标准，可能是hybrid Restful接口
        :param default_host: 与tornado Application相同
        :param transforms: 与tornado Application相同
        :param settings: 与tornado Application相同
        """
        rest_handlers = list()
        self.resource = resource

        for r in rest_resources:
            svs = self.generate_rest_service_handlers(r)
            rest_handlers += svs

        if handlers:
            rest_handlers += handlers
        # 调用父类初始化函数
        tornado.wsgi.WSGIApplication.__init__(self, rest_handlers, default_host, transforms, **settings)

    @staticmethod
    def generate_rest_service_handlers(self, resource):
        """
        这一块是核心，将资源包含的操作转换成接口
        :param resource:
        :return:
        """
        svs = resource.get_handlers()
        return svs


class RestHandler(tornado.web.RequestHandler):
    """
    实现Rest 接口的核心模块
    """
    def __init__(self, application, request, **kwargs):
        tornado.web.RequestHandler.__init__(self, application, request, **kwargs)
        self.result = None

    def get(self):
        """ Executes get method """
        self._exe("GET")

    def post(self):
        """ Executes post method """
        self._exe("POST")

    def put(self):
        """ Executes put method """
        self._exe("PUT")

    def patch(self):
        """ Executes patch method """
        self._exe("PATCH")

    def delete(self):
        """ Executes put method """
        self._exe("DELETE")

    def _exe(self, method):
        """
        执行函数的核心模块
        :param method:
        :return:
        """
        # 处理URL，获取URL中的资源名和参数
        request_path = self.request.path
        path = request_path.split("/")
        services_and_params = list(filter(lambda x: x != "", path))

        # 设置HTTP文本类型
        content_type = None
        if "Content-Type" in self.request.headers.keys():
            content_type = self.request.headers["Content-Type"]

        # 充分利用Python特性的一行代码，获取资源Handler中所有被config装饰过的函数名
        functions = list(  # 将结果转成列表
            filter(  # 高阶函数，
                lambda op: hasattr(getattr(self, op), "_service_name") and inspect.ismethod(getattr(self, op)),
                dir(self)))
        # 获取资源类支持的HTTP方法：GET/POST/DELETE/PUT等
        http_methods = list(map(lambda op: getattr(getattr(self, op), "_method"), functions))

        if method not in http_methods:
            raise tornado.web.HTTPError(405, "The service not have %s verb" % method)

        # list(map(lambda op: getattr(self, op), functions))  获取资源类方法的每个operation进行
        for operation in list(map(lambda op: getattr(self, op), functions)):
            # 循环遍历资源类中每个方法的OP属性，是否满足当前的请求，如果满足进行处理
            service_name = getattr(operation, "_service_name")
            service_params = getattr(operation, "_service_params")
            # If the _types is not specified, assumes str types for the params
            params_types = getattr(operation, "_types")
            func_params = getattr(operation, "_func_params")
            params_types += [str] * (len(func_params) - len(params_types))
            produces = getattr(operation, "_produces")  # 输出格式
            consumes = getattr(operation, "_consumes")  # 输入格式
            services_from_request = list(filter(lambda x: x in path, service_name))
            manual_response = getattr(operation, "_manual_response")
            catch_fire = getattr(operation, "_catch_fire")
            op_method = getattr(operation, "_method")

            if op_method == self.request.method and service_name == services_from_request and len(
                    service_params) + len(service_name) == len(services_and_params):
                try:
                    # 获取HTTP请求参数，包括？之前的资源参数和？之后的参数，注意顺序
                    params_values = self._find_params_value_of_url(service_name, request_path) + \
                                    self._find_params_value_of_arguments(operation)
                    p_values = self._convert_params_values(params_values, params_types)
                    # 如果HTTP请求的request和response没预设参数，则使用HTTP请求头中的content-type参数
                    # 接写来就是对请求的body进行处理
                    # 如下代码是原来作者写的，感觉比较冗余，一般一个服务的数据传输格式是统一的。
                    # 而具体request中的body数据如何处理，是业务而定，这块使用的时候可以随时修改
                    # if not (consumes or produces):
                    #     consumes = content_type
                    #     produces = content_type
                    # if consumes == mediatypes.APPLICATION_XML:
                    #     if params_types[0] in [str]:
                    #         param_obj = xml.dom.minidom.parseString(self.request.body)
                    #     else:
                    #         param_obj = convertXML2OBJ(params_types[0],
                    #                                    xml.dom.minidom.parseString(self.request.body).documentElement)
                    #     p_values.append(param_obj)
                    # elif consumes == mediatypes.APPLICATION_JSON:
                    #     body = self.request.body
                    #     if sys.version_info > (3,):
                    #         body = str(self.request.body, "utf-8")
                    #     if params_types[0] in [dict, str]:
                    #         param_obj = json.loads(body)
                    #     else:
                    #         param_obj = convertJSON2OBJ(params_types[0], json.loads(body))
                    #     p_values.append(param_obj)

                    # 真正的业务逻辑函数
                    response = operation(*p_values)

                    # 对输出的结果进行处理
                    if not response:
                        return
                    if produces:
                        self.set_header("Content-Type", produces)
                    if manual_response:
                        return
                    if produces == mediatypes.APPLICATION_JSON and hasattr(response, "__module__"):
                        response = convert2JSON(response)
                    elif produces == mediatypes.APPLICATION_XML and hasattr(response, "__module__") and not isinstance(
                            response, xml.dom.minidom.Document):
                        response = convert2XML(response)

                    if produces == mediatypes.APPLICATION_JSON and isinstance(response, dict):
                        self.write(response)
                        self.finish()
                    elif produces == mediatypes.APPLICATION_JSON and isinstance(response, list):
                        self.write(json.dumps(response))
                        self.finish()
                    elif produces in [mediatypes.APPLICATION_XML, mediatypes.TEXT_XML] and\
                            isinstance(response, xml.dom.minidom.Document):
                        self.write(response.toxml())
                        self.finish()
                    else:
                        self.gen_http_error(500, "Internal Server Error : response is not %s document" % produces)
                        if catch_fire:
                            raise PyRestfulException("Internal Server Error : response is not %s document" % produces)
                except Exception as detail:
                    self.gen_http_error(500, "Internal Server Error : %s" % detail)
                    if catch_fire:
                        raise PyRestfulException(detail)

    @staticmethod
    def _find_params_value_of_url(services, url):
        """
        获取路径中的参数非HTTP请求参数，就是？之前包含在路径中的参数
        :param services:  路径中包含的资源列表
        :param url:
        :return:
        """
        values_of_query = list()
        url_split = url.split("?")[0].split("/")

        values = [item for item in url_split if item not in services and item]
        for v in values:
            values_of_query.append(v)
        return values_of_query

    def _find_params_value_of_arguments(self, operation):
        """
        获取路径中的参数，HTTP请求参数，就是？后面的参数
        :param operation:
        :return:
        """
        values = []
        a = getattr(operation, "_service_params")
        b = getattr(operation, "_func_params")
        if len(self.request.arguments) > 0:
            params = [item for item in b if item not in a]
            for p in params:
                if p in self.request.arguments.keys():
                    v = self.get_argument(p)
                    values.append(v)
                else:
                    values.append(None)
        elif len(self.request.arguments) == 0:
            values = [None] * (len(b) - len(a))
        return values

    @staticmethod
    def _convert_params_values(values_list, params_types):
        """
        根据指定的参数类型列表，对参数进行类型传观
        :param values_list:
        :param params_types:
        :return:
        """
        values = list()
        i = 0
        for v in values_list:
            if v:
                values.append(types.convert(v, params_types[i]))
            else:
                values.append(v)
            i += 1
        return values

    def gen_http_error(self, status, msg):
        """ Generates the custom HTTP error """
        self.clear()
        self.set_status(status)
        self.write("<html><body>" + str(msg) + "</body></html>")
        self.finish()

    def get_services(self):
        """ Generates the resources (uri) to deploy the Rest Services """
        services = []
        for f in dir(self):
            o = getattr(self, f)
            if callable(o) and hasattr(o, "_service_name"):
                services.append(getattr(o, "_service_name"))
        return services

    @classmethod
    def get_paths(cls):
        """
        获取资源类下面都有属性，如果属性是可调用的，也就是函数
        函数即对象，如果对象含有_path属性，则获取属性的值，
        _path值即url

        :return
            [
                "/customer",
                "/customer/{id_customer}",
            ]
        """
        paths = []
        for f in dir(cls):
            o = getattr(cls, f)
            if callable(o) and hasattr(o, "_path"):
                paths.append(getattr(o, "_path"))
        return paths

    @classmethod
    def get_handlers(cls):
        """
        获取（path, handler）映射关系表  一个资源RestHandler可以有多个path与之对应
        这里的Handler是资源类Handler,继承RestHandler
        """
        svs = []
        paths = cls.get_paths()
        # 将URL进行转换
        for p in paths:
            # "/api/{id}/task/{task_id}?id=9&type=9"  —>   "/api/.*/task/.*?id=9&type=9"
            s = re.sub(r"(?<={)\w+}", ".*", p).replace("{", "")
            # "/api/.*/task/.*?id=9&type=9" ->  "/api/.*/task/.*id=9type=9"
            # 这里有对"<xxx>"形式的匹配，获取查询参数
            o = re.sub(r"(?<=<)\w+", "", s).replace("<", "").replace(">", "").replace("&", "").replace("?", "")
            svs.append((o, cls))
        return svs


class PyRestfulException(Exception):
    """ Class for PyRestful exceptions """

    def __init__(self, message):
        self.message = message

    def __str__(self):
        return repr(self.message)


def config(func, method, **kwargs):
    """
    装饰 func
    """
    path = None
    produces = None
    consumes = None
    types = None
    manual_response = None
    catch_fire = False

    if len(kwargs):
        path = kwargs["_path"]
        if "_produces" in kwargs:
            produces = kwargs["_produces"]
        if "_consumes" in kwargs:
            consumes = kwargs["_consumes"]
        if "_types" in kwargs:
            types = kwargs["_types"]
        if "_manual_response" in kwargs:
            manual_response = kwargs["_manual_response"]
        if "_catch_fire" in kwargs:
            catch_fire = kwargs["_catch_fire"]

    def operation(*args, **kwargs):
        return func(*args, **kwargs)

    # 将operation函数是为一个对象，为对象设置属性
    operation.func_name = func.__name__
    operation._method = method
    operation._produces = produces
    operation._consumes = consumes
    operation._path = path
    operation._manual_response = manual_response
    operation._catch_fire = catch_fire
    # func是Handler的方法，第一个参数是对象本身self，因此参数从args[1]开始
    func_params = inspect.getargspec(func).args[1:]
    operation._func_params = func_params
    operation._types = types or [str] * len(func_params)

    # 找到URL中资源名词 "/api/{instance_id}/instance/{task_id}" ->  ["api", "instance"]
    operation._service_name = re.findall(r"(?<=/)\w+", path)
    # 找到URL中的参数 "/api/{instance_id}/instance/{task_id}" ->  ["instance_id", "task_id"]
    operation._service_params = re.findall(r"(?<={)\w+", path)
    # 获取涉及到查询的参数，实际项目很少用到
    operation._query_params = re.findall(r"(?<=<)\w+", path)

    # 资源的表征状态判断， 判断资源的表征状态是否支持
    if produces not in [mediatypes.APPLICATION_JSON, mediatypes.APPLICATION_XML, mediatypes.TEXT_XML, None]:
        raise PyRestfulException("The media type used do not exist : " + operation.func_name)
    return operation


# 下面几个方法是装饰器，主要就是对资源的操作进行装饰
# 主要就是给函装饰的函数增加属性，方便后面进行接口生成

def get(**kwargs):
    """
    Decorator for config a python function like a Rest GET verb
    装饰器需要以字典形式传递参数
    _path: api url
    _produces: 资源表征形式
    _consumes:
    _catch_fire:
    _types: 函数传递的参数类型列表（这个列表的中的类型尽量和装饰的函数的参数一一对应）
            如果不对应，后面缺省的会默认补齐为字符串类型
    _manual_responses:
    """

    def method(f):
        return config(f, "GET", **kwargs)

    return method


def post(**kwargs):
    """ Decorator for config a python function like a Rest POST verb """

    def method(f):
        return config(f, "POST", **kwargs)

    return method


def put(**kwargs):
    """ Decorator for config a python function like a Rest PUT verb	"""

    def method(f):
        return config(f, "PUT", **kwargs)

    return method


def patch(**kwargs):
    """ Decorator for config a python function like a Rest PATCH verb """

    def method(f):
        return config(f, "PATCH", **kwargs)

    return method


def delete(**kwargs):
    """ Decorator for config a python function like a Rest PUT verb	"""

    def method(f):
        return config(f, "DELETE", **kwargs)

    return method