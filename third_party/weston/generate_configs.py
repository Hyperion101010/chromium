#!/usr/bin/python
#
# Copyright 2019 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Creates config files for building Weston."""

from __future__ import print_function

import os
import re
import shutil
import subprocess
import sys
import tempfile

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
BASE_DIR = BASE_DIR + '/src'
CHROMIUM_ROOT_DIR = os.path.abspath(os.path.join(BASE_DIR, '..', '..', '..'))

sys.path.append(os.path.join(CHROMIUM_ROOT_DIR, 'build'))
import gn_helpers

MESON = ['meson']

DEFAULT_BUILD_ARGS = [
    '-Dbuild_tests=false','--buildtype', 'release', '-Dbackend-drm-screencast-vaapi=false','-Dbackend-rdp=false',
    '-Dxwayland=false', '-Dcolor-management-lcms=false',
    '-Dpipewire=false',
    '-Dcolor-management-colord=false', '-Dremoting=false','-Dsimple-dmabuf-drm=auto',
    '-Dshell-ivi=false', '-Ddemo-clients=false', '-Dsimple-clients=egl', '-Dlauncher-logind=false',
    '-Dweston-launch=false', '-Dxwayland=false', '-Dscreenshare=false', '-Dsystemd=false',
]

WINDOWS_BUILD_ARGS = ['-Dc_winlibs=']


def PrintAndCheckCall(argv, *args, **kwargs):
  print('\n-------------------------------------------------\nRunning %s' %
        ' '.join(argv))
  c = subprocess.check_call(argv, *args, **kwargs)

def RewriteFile(path, search_replace):
  with open(path) as f:
    contents = f.read()
  with open(path, 'w') as f:
    for search, replace in search_replace:
      contents = re.sub(search, replace, contents)

    # Cleanup trailing newlines.
    f.write(contents.strip() + '\n')

def SetupWindowsCrossCompileToolchain(target_arch):
  # First retrieve various MSVC and Windows SDK paths.
  output = subprocess.check_output([
      os.path.join(CHROMIUM_ROOT_DIR, 'build', 'vs_toolchain.py'),
      'get_toolchain_dir'
  ])

  # Turn this into a dictionary.
  win_dirs = gn_helpers.FromGNArgs(output)

  # Use those paths with a second script which will tell us the proper include
  # and lib paths to specify for cflags and ldflags respectively.
  output = subprocess.check_output([
      'python',
      os.path.join(CHROMIUM_ROOT_DIR, 'build', 'toolchain', 'win',
                   'setup_toolchain.py'), win_dirs['vs_path'],
      win_dirs['sdk_path'], win_dirs['runtime_dirs'], 'win', target_arch, 'none'
  ])

  flags = gn_helpers.FromGNArgs(output)
  cwd = os.getcwd()

  target_env = os.environ

  include_paths = []
  for cflag in flags['include_flags_imsvc'].split(' '):
    # Apparently setup_toolchain prefers relative include paths, which
    # may work for chrome, but it does not work for ffmpeg, so let's make
    # them asbolute again.
    include_path = cflag.strip('"')
    if include_path.startswith('-imsvc'):
      include_path = os.path.abspath(os.path.join(cwd, include_path[6:]))
    include_paths.append(include_path)

  # TODO(dalecurtis): Why isn't the ucrt path printed?
  flags['vc_lib_ucrt_path'] = flags['vc_lib_um_path'].replace('/um/', '/ucrt/')

  # Unlike the cflags, the lib include paths are each in a separate variable.
  lib_paths = []
  for k in flags:
    # libpath_flags is like cflags. Since it is also redundant, skip it.
    if 'lib' in k and k != 'libpath_flags':
      lib_paths.append(flags[k])

  target_env = os.environ
  target_env['INCLUDE'] = ';'.join(include_paths)
  target_env['LIB'] = ';'.join(lib_paths)
  return target_env


def CopyConfigsAndCleanup(config_dir, dest_dir):
  if not os.path.exists(dest_dir):
    os.makedirs(dest_dir)

  shutil.copy(os.path.join(config_dir, 'config.h'), dest_dir)

  # The .asm file will not be present for all configurations.
  asm_file = os.path.join(config_dir, 'config.asm')
  if os.path.exists(asm_file):
    shutil.copy(asm_file, dest_dir)

  shutil.rmtree(config_dir)


def RewriteGitFile(path, data):
  with open(path, 'w') as f:
    contents = data

    # Cleanup trailing newlines.
    f.write(contents.strip() + '\n')

def CopyGitConfigsAndCleanup(config_dir, dest_dir):
  if not os.path.exists(dest_dir):
    os.makedirs(dest_dir)

  shutil.copy(os.path.join(config_dir, 'git-version.h'), dest_dir)
  shutil.rmtree(config_dir)

def GenerateGitConfig(config_dir,env,special_args=[]):
  temp_dir = tempfile.mkdtemp()
  PrintAndCheckCall(
      MESON + DEFAULT_BUILD_ARGS + special_args + [temp_dir],
      cwd='src',
      env=env)
  # We don't want non-visible log strings polluting the official binary.
  label = subprocess.check_output(["git", "describe", "--always"]).strip()
  label = label.decode("utf-8")
  RewriteGitFile(
      os.path.join(temp_dir, 'git-version.h'),
      "#define BUILD_ID \"{label}\"".format(label=label))
  CopyGitConfigsAndCleanup(temp_dir, config_dir)


def GenerateConfig(config_dir, env, special_args=[]):
  temp_dir = tempfile.mkdtemp()
  PrintAndCheckCall(
      MESON + DEFAULT_BUILD_ARGS + special_args + [temp_dir],
      cwd='src',
      env=env)

  # We don't want non-visible log strings polluting the official binary.
  RewriteFile(
      os.path.join(temp_dir, 'config.h'),
      [(r'(#define CONFIG_LOG .*)',
        r'// \1 -- Logging is controlled by Chromium')])

  # Clang LTO doesn't respect stack alignment, so we must use the platform's
  # default stack alignment in that case; https://crbug.com/928743.
  RewriteFile(
      os.path.join(temp_dir, 'config.h'),
      [(r'(#define STACK_ALIGNMENT \d{1,2})',
        r'// \1 -- Stack alignment is controlled by Chromium')])
  if (os.path.exists(os.path.join(config_dir, 'config.asm'))):
    RewriteFile(
        os.path.join(temp_dir, 'config.asm'),
        [(r'(%define STACK_ALIGNMENT \d{1,2})',
          r'; \1 -- Stack alignment is controlled by Chromium')])

  CopyConfigsAndCleanup(temp_dir, config_dir)


def GenerateWindowsArm64Config(src_dir):
  win_arm64_dir = 'config/win/arm64'
  if not os.path.exists(win_arm64_dir):
    os.makedirs(win_arm64_dir)

  shutil.copy(os.path.join(src_dir, 'config.h'), win_arm64_dir)

  # Flip flags such that it looks like an arm64 configuration.
  RewriteFile(
      os.path.join(win_arm64_dir, 'config.h'),
      [(r'#define ARCH_X86 1', r'#define ARCH_X86 0'),
       (r'#define ARCH_X86_64 1', r'#define ARCH_X86_64 0'),
       (r'#define ARCH_AARCH64 0', r'#define ARCH_AARCH64 1')])

def ChangeConfigPath( ):
  configfile = os.path.abspath(os.path.dirname(__file__))
  configfile = os.path.join(configfile,"config/linux/x64/config.h")
  temp_dir = tempfile.mkdtemp()
  data = ""
  with open(configfile,'r') as f:
    for line in f:
      if "BINDIR" in line:
        continue
      elif "DATADIR" in line:
        continue
      elif "LIBEXECDIR" in line:
        continue
      elif "LIBWESTON_MODULEDIR" in line:
        continue
      elif "MODULEDIR" in line:
        continue
      else:
        data += line      
  RewriteGitFile(os.path.join(temp_dir, 'config.h'),data)
  CopyConfigsAndCleanup(temp_dir,CHROMIUM_ROOT_DIR+"/third_party/weston/config/linux/x64")
  print("Replaced paths with real paths")

def libweston_version_generator():
  data = """
  /*
 * Copyright © 2013 Intel Corporation
 *
 * Permission is hereby granted, free of charge, to any person obtaining
 * a copy of this software and associated documentation files (the
 * "Software"), to deal in the Software without restriction, including
 * without limitation the rights to use, copy, modify, merge, publish,
 * distribute, sublicense, and/or sell copies of the Software, and to
 * permit persons to whom the Software is furnished to do so, subject to
 * the following conditions:
 *
 * The above copyright notice and this permission notice (including the
 * next paragraph) shall be included in all copies or substantial
 * portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
 * EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
 * MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
 * NONINFRINGEMENT.  IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS
 * BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN
 * ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
 * CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
 * SOFTWARE.
 */

#ifndef WESTON_VERSION_H
#define WESTON_VERSION_H

#define WESTON_VERSION_MAJOR {version_major}
#define WESTON_VERSION_MINOR {version_minor}
#define WESTON_VERSION_MICRO {version_micro}
#define WESTON_VERSION {weston_version}

/* This macro may not do what you expect.  Weston doesn't guarantee
 * a stable API between 1.X and 1.Y, and thus this macro will return
 * FALSE on any WESTON_VERSION_AT_LEAST(1,X,0) if the actual version
 * is 1.Y.0 and X != Y).  In particular, it fails if X < Y, that is,
 * 1.3.0 is considered to not be "at least" 1.4.0.
 *
 * If you want to test for the version number being 1.3.0 or above or
 * maybe in a range (eg 1.2.0 to 1.4.0), just use the WESTON_VERSION_*
 * defines above directly.
 */

#define WESTON_VERSION_AT_LEAST(major, minor, micro) \
        (WESTON_VERSION_MAJOR == (major) && \
         WESTON_VERSION_MINOR == (minor) && \
         WESTON_VERSION_MICRO >= (micro))

#endif
  """
  configfile = os.path.abspath(os.path.dirname(__file__))
  configfile = os.path.join(configfile,"config/linux/x64/config.h")
  version_number = "0.0.0"
  with open(configfile,'r') as f:
    for line in f:
      if "PACKAGE_VERSION" in line:
        dt = (line.strip("\n")).split(" ")
        version_number = dt[-1]
  version_number_list = (version_number.strip("\"\n\"")).split(".")
  version_major = version_number_list[0]
  version_minor = version_number_list[1]
  version_micro = version_number_list[2]
  data = data.format(version_major=version_major,version_minor=version_minor,version_micro=version_micro,weston_version=version_number)
  with open(os.path.join(os.path.abspath(os.path.dirname(__file__)),"src/include/libweston/version.h"), 'w') as f:
    contents = data
  # Cleanup trailing newlines.
    f.write(contents.strip() + '\n')
  print("Created version.h file from version.h.in\n")

def main():
  linux_env = os.environ
  linux_env['CC'] = 'clang'
  GenerateGitConfig('version',linux_env)
  GenerateConfig('config/linux/x64', linux_env)
  ChangeConfigPath()
  libweston_version_generator()



if __name__ == '__main__':
  main()