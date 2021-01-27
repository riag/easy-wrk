# coding:utf8

import os
from pathlib import Path
import sys
import logging
from requests.models import Request

from tomlkit import parse
from tabulate import tabulate

from .common import load_dotenv, render_config_file
from .common import EasyWrkContext, RequestBuilder, create_easywrk_context, build_request
from .wrk import Wrk

logger = logging.getLogger(__name__)

cmd_help_map = {}

def register_cmd_help(name, parser):
    global cmd_help_map
    cmd_help_map[name] = parser

def help_command(args, other_argv=None):
    parser = cmd_help_map.get(args.name, None)
    if parser is None:
        print(f"not support [{args.name}] command")
        return

    parser.print_help()

def load_config_file(args, verbose):
    
    if not os.path.isfile(args.config_file):
        logger.error(f"config file [{args.config_file}] does not exist")
        sys.exit(-1)

    if not os.path.isfile(args.env_file):
        logger.info(f"env file [{args.env_file}] does not exist")    
    else:
        load_dotenv(args.env_file)

    text = render_config_file(args.config_file)
    if verbose:
        print("config file: \n")
        print(text)

    return parse(text)

init_env_text="""
WRK_BIN = "wrk"
BASE_URL="http://127.0.0.1:8080"
"""

init_easywrk_text="""
[wrk]
threads=10
thread_connections=10
latency=true
duration="10s"

[[apis]]
name="get"
desc="Get 请求"
path="/api/get"
method="GET"
body=""

    [[apis.params]]
    name="param-1"
    value="param-1-value"

    [[apis.params]]
    name="param-2"
    value="param-2-value"

[[apis]]
name="post"
desc="Post 请求"
path="/api/post"
method="POST"
body=":form"

    [[apis.fields]]
    name = "field-1"
    value = "field-1-value"

    [[apis.fields]]
    name = "field-2"
    value = "field-2-value"
"""

def init_command(args, other_args=None):
    env_file = Path("./.env")
    eaywrk_file = Path("./easywrk.toml")

    if env_file.is_file():
        print(f"{env_file} alreay exist")
        return

    if eaywrk_file.is_file():
        print(f"{eaywrk_file} alreay exist")
        return

    with env_file.open('w') as f:
        f.write(init_env_text)

    with eaywrk_file.open('w') as f:
        f.write(init_easywrk_text)


def get_base_url():
    base_url = os.environ.get('BASE_URL', '')
    if not base_url:
        print("not define environ [BASE_URL]")
        sys.exit(1)

    return base_url


def view_config_command(args, other_argv=None):
    load_config_file(args, True)


def list_command(args, other_argv=None):

    config = load_config_file(args, False)
    config_file_dir = Path(os.path.dirname(args.config_file))

    base_url = get_base_url()

    context: EasyWrkContext = create_easywrk_context(base_url, config_file_dir, config)

    header = ("API", "DESC")
    table = []
    for api_config in context.api_config_list:
        table.append((api_config.name, api_config.desc))

    print('')
    print(tabulate(table, headers=header))
    print('')

GLOBAL_HTTP_VERSION_MAP = {
    10: "HTTP/1.0",
    11: "HTTP/1.1"
}


def _do_reqeust_command(args, other_argv=None, print_response_body=True):

    config = load_config_file(args, False)
    config_file_dir = Path(os.path.dirname(args.config_file))

    base_url = get_base_url()

    context: EasyWrkContext = create_easywrk_context(base_url, config_file_dir, config)

    name = args.name[0]
    api_config = context.api_config_map.get(name, None)
    if api_config is None:
        print(f"not found api [{name}]")
        return

    req_builder: RequestBuilder = build_request(context, api_config)
    prepare_req = req_builder.build()

    logger.info("try to connect server...")
    logger.info("url is %s", prepare_req.url)
    logger.info("method is %s", prepare_req.method)
    logger.info("headers is %s\n", prepare_req.headers)

    resp = req_builder.try_connect()
    if resp.status_code != 200:
        logger.error(f"Error: response status code is {resp.status_code}")
        sys.exit(-1)
    
    logger.info("")

    http_version = GLOBAL_HTTP_VERSION_MAP.get(resp.raw.version, "")
    logger.info("%s %d %s", http_version, resp.status_code, resp.reason)
    for k,v  in resp.headers.items():
        logger.info("%s:%s" % (k, v))
    logger.info("")
    if print_response_body:
        logger.info(resp.text)

    return context, api_config, prepare_req

def request_command(args, other_argv=None):
    _do_reqeust_command(args, other_argv, True)

def run_command(args, other_argv=None):
    context, api_config, prepare_req = _do_reqeust_command(args, other_argv, False)

    wrk_bin = os.environ.get('WRK_BIN', 'wrk')
    api_dir = context.get_api_dir(api_config.name)

    wrk = Wrk(
        context.wrk_config,  wrk_bin,
        prepare_req.url, prepare_req.method,
        prepare_req.headers, prepare_req.body
    )
    wrk.run(api_dir, other_argv)