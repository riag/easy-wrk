# coding:utf8

import logging

from pathlib import Path
from typing import List
import subprocess

from attr.validators import instance_of

from .common import WrkConfig

logger = logging.getLogger(__name__)

lua_read_file_func="""
function read_file(path)
  local file, errorMessage = io.open(path, "rb")
  if not file then
    error("Could not read the file: "..path.." Error : " .. errorMessage .. "\\n")
  end

  local content = file:read "*all"
  file:close()
  return content
end

"""

class Wrk(object):
    def __init__(self, wrk_config: WrkConfig, wrk_bin, url, method, headers, body):
        self.wrk_config = wrk_config
        self.wrk_bin = wrk_bin
        self.url = url
        self.method = method
        self.headers = headers
        if body and (type(body) is str):
            self.body = body.encode("utf8")
        else:
            self.body = body


    def make_cmd_list(self, api_dir:Path, other_args:List[str]):
        connections = self.wrk_config.thread_connections * self.wrk_config.threads
        logger.info(
            "total connections: %d", connections
            )
        cmd_list = [
            self.wrk_bin, 
            '-c', str(connections), 
            '-t', str(self.wrk_config.threads),
        ]

        if self.wrk_config.duration:
            cmd_list.extend(("-d", self.wrk_config.duration))
        cmd_list.append(self.url)

        if self.wrk_config.latency:
            cmd_list.append('--latency')

        body_file = api_dir.joinpath('wrk.body')
        lua_file = api_dir.joinpath('wrk.lua')
        with lua_file.open('w') as f:
            if self.body:
                f.write(lua_read_file_func)
                m = 'wrk.body = read_file("%s") \n' % body_file
                f.write(m)

            f.write('wrk.method = "%s"\n' % self.method)
            if self.headers:
                for k, v in self.headers.items():
                    m = 'wrk.headers["%s"] = "%s" \n' % (k, v)
                    f.write(m)

        if self.body:
            with body_file.open('wb') as f:
                f.write(self.body)

        cmd_list.extend(
            ('--script', str(lua_file))
        )

        if other_args :
            cmd_list.extend(other_args)

        return cmd_list

    
    def run(self, api_dir:Path, other_args:List[str]):
        cmd_list = self.make_cmd_list(
            api_dir, other_args
        )
        cmd = ' '.join(cmd_list)
        logger.info("wrk commd: %s \n", cmd)
        logger.info("start benchmark...")

        subprocess.check_call(cmd_list)
