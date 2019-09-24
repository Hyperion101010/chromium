#!/usr/bin/python
#
# Copyright 2019 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Creates config files for building weston."""

from __future__ import print_function

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import gn_helpers

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
CHROMIUM_ROOT_DIR = os.path.abspath(os.path.join(BASE_DIR, '..', '..'))

sys.path.append(os.path.join(CHROMIUM_ROOT_DIR, 'build'))

MESON = ['meson.py']

DEFAULT_BUILD_ARGS = [
    '-Dbuild_tools=false', '-Dbuild_tests=false', '--buildtype', 'release'
]


def PrintAndCheckCall(argv, *args, **kwargs):
    print('\n-------------------------------------------------\nRunning %s' %
          ' '.join(argv))
    c = subprocess.check_call(argv, *args, **kwargs)


def RewriteFile(path, search_replace):
    print('\n---- %s\n' % path)
    with open(path) as f:
        contents = f.read()
    with open(path, 'w') as f:
        for search, replace in search_replace:
            contents = re.sub(search, replace, contents)

        # Cleanup trailing newlines.
        f.write(contents.strip() + '\n')


def CopyConfigsAndCleanup(config_dir, dest_dir):
    if not os.path.exists(dest_dir):
        os.makedirs(dest_dir)

    shutil.copy(os.path.join(config_dir, 'config.h'), dest_dir)

    shutil.rmtree(config_dir)


def GenerateConfig(config_file_path, env, special_args=[]):
    RewriteFile(
        config_file_path,
        [(r'(#define BUILD_WAYLAND_COMPOSITOR 1)',
          r'// \1 -- Comment')])


def main():
    linux_env = os.environ
    linux_env['CC'] = 'clang'

    # Create a new config file.
    Path(config_file_path).touch()
    GenerateConfig(config_file_path, linux_env)


if __name__ == '__main__':
    main()
