#coding:utf8

import os
import sys
import attr
import logging
import base64

from pathlib import Path
from requests import Request
from dotenv import load_dotenv
from jinja2 import Environment, FileSystemLoader
import requests

from typing import List, Dict, Tuple, Any, IO
import cattr

from .validates import validate_name


logger = logging.getLogger(__name__)

BYTES_ENCODE_MAP = {
    'base64': lambda b:  str(base64.b64encode(b)),
    'hex': bytes.hex,
    'raw': None,
}

VALUE_TYPE_MAP = {
    'str': lambda b: b,
    'int': int,
    'float': float
}

@attr.s
class WrkConfig(object):
    threads= attr.ib(type=int, default=20)
    thread_connections= attr.ib(type=int, default=30)
    latency=attr.ib(type=bool, default=False)
    duration = attr.ib(type=str, default="10s")


@attr.s
class ApiField(object):
    name = attr.ib(type=str, default="")
    value = attr.ib(type=str, default="")
    type = attr.ib(type=str, default="str")
    # 支持 raw , base64 , hex
    encode = attr.ib(type=str, default="")

@attr.s
class ApiConfig(object):
    name = attr.ib(
        type=str,
        validator= attr.validators.instance_of(str)
    )

    @name.validator
    def validate_name(self, attribute, value):
        if not value :
            raise ValueError(f"field name must exist")

        if not validate_name(value):
            raise ValueError(f"value [{value}] is illegal")

    desc = attr.ib(type=str, default="")

    method = attr.ib(type=str, default="POST")
    path = attr.ib(type=str, default="")

    # 支持以下值:
    # :json, :form; `:` 表示特定格式，目前只支持 json 和 form
    # @文件路径, `@` 表示把文件内容放到 body 里
    # 其他内容为字符串内容
    body = attr.ib(type=str, default=":json")

    # http header
    headers = attr.ib(type=List[ApiField], default=[])

    # http url query param
    params = attr.ib(type=List[ApiField], default=[])

    # json or form fields
    # value 里如果传 @文件路径，表示后面接着是文件路径
    # 表示是要上传文件
    fields = attr.ib(type=List[ApiField], default=[])


def load_env_file(fpath):
    load_dotenv(fpath)

def render_config_file(fpath):
    config_dir = os.path.dirname(fpath)

    data = None
    with open(fpath, 'r') as f:
        data = f.read()

    env = Environment(loader=FileSystemLoader(config_dir))
    t = env.from_string(data)
    return t.render(**os.environ)

def make_wrkconfig(config) -> WrkConfig:
    return cattr.structure(config['wrk'], WrkConfig)

def make_apiconfigs(config) -> List[ApiConfig]:
    return cattr.structure(config['apis'], List[ApiConfig])


@attr.s
class EasyWrkContext(object):
    base_url = attr.ib(type=str)
    config_file_dir = attr.ib(type=Path)
    wrk_config = attr.ib(type=WrkConfig)
    api_config_list = attr.ib(type=List[ApiConfig])
    api_config_map = attr.ib(type=Dict[str, ApiConfig])

    def get_api_dir(self, api_name) -> Path:
        api_dir = self.config_file_dir.joinpath('benchmark', api_name)
        if not api_dir.is_dir():
            api_dir.mkdir(exist_ok=True, parents=True)

        return api_dir


def create_easywrk_context(base_url:str, config_file_dir:Path, config):
    wrk_config = make_wrkconfig(config)
    api_config_list = make_apiconfigs(config)

    api_config_map = {}
    for api in api_config_list:
        if api.name in api_config_map:
            logger.warning(f"api [{api.name}] is repeat, please check config file")

        api_config_map[api.name] = api

    return EasyWrkContext(
        base_url = base_url,
        config_file_dir = config_file_dir,
        wrk_config = wrk_config, 
        api_config_list = api_config_list, 
        api_config_map = api_config_map
        )


@attr.s
class RequestBuilder(object):
    url = attr.ib(type=str, default="")
    method = attr.ib(type=str, default="")

    params = attr.ib(type=List[Tuple], default=[])
    headers = attr.ib(type=Dict[str, str], default={})

    data = attr.ib(type=bytes, default=None)
    json = attr.ib(type=Dict[str, Any], default=None)
    files = attr.ib(type=List[Tuple], default=None)

    def build(self):
        req = Request(
            url = self.url,
            method = self.method,
            headers= self.headers,
            params= self.params,
            data= self.data,
            json = self.json,
            files= self.files
        )
        return req.prepare()


class BuildRequestException(Exception):
    def __init__(self, msg:str):
        super().__init__(msg)

def join_url_path(base_url:str, path:str):
    l = [base_url,]
    if not base_url.endswith('/') and not path.startswith('/'):
        l.append('/')
    elif base_url.endswith('/') and path.startswith('/'):
        l.append(path[1:])
    else:
        l.append(path)

    return "".join(l)

def build_request(context: EasyWrkContext , api_config: ApiConfig):
    url = join_url_path(context.base_url, api_config.path)
    req_builder = RequestBuilder(
        url = url, 
        method = api_config.method,
    )

    build_headers_map(req_builder, api_config)
    build_params(req_builder, api_config)
    build_body(context.config_file_dir, req_builder, api_config)

    return req_builder


def build_headers_map(req_builder:RequestBuilder, api_config: ApiConfig):
    m = {}
    for header in api_config.headers:
        if header.name in m:
            x = f"header [{header.name}] already exist"
            raise BuildRequestException(x)
        m[header.name] = header.value

    req_builder.headers = m
    return req_builder 

def build_params(req_builder: RequestBuilder, api_config: ApiConfig):
    l = []
    for item in api_config.params:
        l.append((item.name, item.value))

    req_builder.params = l
    return req_builder

def _get_file_path(config_file_dir:Path, value:str):
    p = value
    if os.path.isabs(p):
        p = Path(p)
    else:
        p = config_file_dir.joinpath(p).absolute()

    return p

def _is_file_field(value:str):
    if value.startswith("@@"):
        return False

    return value.startswith("@")

def _encode_file_data(config_file_dir:Path, value:str, encode:str):
    p = value[1:]

    encode_func = None

    if len(encode) > 0:
        if encode not in BYTES_ENCODE_MAP:
            raise BuildRequestException(f"not support encode value [{encode}]")

        encode_func = BYTES_ENCODE_MAP.get(encode)

    p = _get_file_path(config_file_dir, value)

    if encode_func is None:
        with p.open("r") as f:
            return f.read()

    with p.open("rb") as f:
        return encode_func(f.read())


def build_forms(config_file_dir:Path, req_builder: RequestBuilder, api_config:ApiConfig):
    data = []
    files = []
    if not api_config.fields:
        print("not found any form field")
        sys.exit(1)

    for field in api_config.fields:
        if not _is_file_field(field.value):
            data.append((field.name, field.value))
            continue

        p = _get_file_path(config_file_dir, field.value[1:])
        files.append((field.name, p.open("rb")))

    req_builder.data = data
    req_builder.files = files

    return req_builder

def build_json(config_file_dir:Path, req_builder: RequestBuilder, api_config: ApiConfig):
    data = {}

    finish_fields = []

    if not api_config.fields:
        print("not found any json field")
        sys.exit(1)

    for field in api_config.fields:

        name:str = field.name

        if name.startswith('/'):
            raise BuildRequestException(f"field [{field.name}] cannot start with [/]")

        if name.endswith('/'):
            name = name[0:-1]

        if name in finish_fields:
            raise BuildRequestException(f"field [{field.name}] already in json data")

        value = field.value
        if _is_file_field(value):
            value = _encode_file_data(config_file_dir, value, field.encode)
        else:
            convert = VALUE_TYPE_MAP.get(field.type)
            if convert is None:
                raise BuildRequestException(f"not found type convert for field [{field.name}]")

            value = convert(value)

        if not '/' in name:
            data[field.name] = value
        else:
            name_list = name.split('/')
            current = data
            last_idx = len(name_list) - 1
            for idx, item in enumerate(name_list):
                if idx == last_idx:
                    current[item] = value
                    break

                v = current.get(item)
                if v is None:
                    v = {}
                    current[item] = v
                current = v

        finish_fields.append(name)

    req_builder.json = data
    return req_builder

def render_file(config_file_dir:Path, req_builder: RequestBuilder, api_config: ApiConfig, fpath:str):
    p = _get_file_path(config_file_dir, fpath)

    data = None
    with p.open('r') as f:
        data = f.read()

    env = Environment(loader=FileSystemLoader(config_file_dir))
    t = env.from_string(data)
    req_builder.data = t.render(**os.environ).encode('utf-8')
    return req_builder

def build_body(config_file_dir:Path, req_builder: RequestBuilder, api_config: ApiConfig):
    body = api_config.body

    if body is None or len(body) == 0:
        return

    if _is_file_field(body):
        p = _get_file_path(config_file_dir, body[1:])

        with p.open("rb") as f:
            req_builder.data = f.read()
            return req_builder

    if body.startswith(":") and not body.startswith("::"):
        if body == ':json':
            return build_json(config_file_dir, req_builder, api_config)

        if body == ":form":
            return build_forms(config_file_dir, req_builder, api_config)

        if body == ':render:':
            b = body[8:]
            return render_file(config_file_dir, req_builder, api_config, b)

        raise BuildRequestException(f"not support body value [{body}]")

    req_builder.data = body.encode("utf-8")
    return req_builder
