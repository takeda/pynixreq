from __future__ import absolute_import, division, print_function, unicode_literals

import atexit
import distutils.core
import json
import os.path
import shutil
import stat
import sys
import tarfile
import tempfile
import zipfile
from distutils.dist import Distribution
from distutils.util import strtobool

from packaging.markers import default_environment
from pkg_resources import parse_requirements

if False:
	from typing import Text, Union, cast


if sys.version_info.major < 3:
	# reload(sys)
	# sys.setdefaultencoding('undefined')  # Make Python 2 stop automatically convert types

	def s(data):
		# type: (Union[Text, str]) -> str
		return data if isinstance(data, str) else data.encode('utf-8')

	def u(text):
		# type: (Union[Text, str]) -> Text
		return cast(bytes, text).decode('utf-8') if isinstance(text, bytes) else text
else:
	def s(data):
		# type: (Union[Text, str]) -> str
		assert isinstance(data, str), "Function called with bytes on Python 3+"
		return data

	def u(text):
		# type: (Union[Text, str]) -> Text
		assert isinstance(text, str), "Function called with bytes on Python 3+"
		return text


def change_permissions(dest):
	# type: (Text) -> None

	def make_writeable(path):
		# type: (Text) -> None
		statinfo = os.stat(path)
		os.chmod(path, statinfo.st_mode | stat.S_IWUSR)

	make_writeable(dest)
	for root, dirs, files in os.walk(dest):
		for dir in dirs:
			make_writeable(os.path.join(root, dir))
		for file in files:
			make_writeable(os.path.join(root, file))


def extract_source(src):
	# type: (str) -> Text
	tmp = tempfile.mkdtemp()

	def cleanup():
		print('Removing %s ...' % tmp)
		shutil.rmtree(tmp)
	atexit.register(cleanup)

	if os.path.isdir(src):
		dest = os.path.join(tmp, 'src')
		print('Copying source to %s ...' % dest)
		shutil.copytree(src, dest)
	elif tarfile.is_tarfile(src):
		print('Extracting tar source to %s ...' % tmp)
		with tarfile.open(src) as tar_fp:
			dirs = set(map(lambda x: x.split('/', 1)[0], tar_fp.getnames()))
			if len(dirs) != 1:
				raise RuntimeError('Expected a single directory, got: %s' % dirs)
def is_within_directory(directory, target):
	
	abs_directory = os.path.abspath(directory)
	abs_target = os.path.abspath(target)

	prefix = os.path.commonprefix([abs_directory, abs_target])
	
	return prefix == abs_directory

def safe_extract(tar, path=".", members=None, *, numeric_owner=False):

	for member in tar.getmembers():
		member_path = os.path.join(path, member.name)
		if not is_within_directory(path, member_path):
			raise Exception("Attempted Path Traversal in Tar File")

	tar.extractall(path, members, numeric_owner=numeric_owner) 
	

safe_extract(tar_fp, tmp)
			dest = os.path.join(tmp, dirs.pop())
	elif zipfile.is_zipfile(src):
		print('Extracting zip source to %s ...' % tmp)
		with zipfile.ZipFile(src) as zip_fp:
			dirs = set(map(lambda x: x.split('/', 1)[0], zip_fp.namelist()))
			if len(dirs) != 1:
				raise RuntimeError('Expected a single directory, got: %s' % dirs)
			zip_fp.extractall(tmp)
			dest = os.path.join(tmp, dirs.pop())
	else:
		raise RuntimeError('%s is of unknown format' % src)

	return dest


def get_distro(src):
	# type: (Text) -> Distribution

	script_name = 'setup.py'
	g = {
		'__file__': script_name,
		'__name__': '__main__'
	}
	last_cwd = os.getcwd()
	last_argv = list(sys.argv)
	last_path = list(sys.path)
	distutils.core._setup_distribution = None  # type: ignore
	distutils.core._setup_stop_after = 'config'  # type: ignore
	try:
		os.chdir(src)
		sys.argv[0] = s(script_name)
		sys.path.insert(0, s(''))
		with open(script_name) as fp:
			exec(fp.read(), g)
	finally:
		os.chdir(last_cwd)
		sys.argv = last_argv
		sys.path = last_path
		distutils.core._setup_stop_after = None  # type: ignore

	if distutils.core._setup_distribution is None:  # type: ignore
		raise RuntimeError("'distutils.core.setup()' was never called -- "
			"perhaps '%s' is not a Distutils setup script?" % script_name)

	return distutils.core._setup_distribution


def is_nix_mode():
	# type: () -> bool
	return strtobool(os.environ.get('nix_mode', 'f'))


def req_names(deps):
	if not is_nix_mode():
		return deps

	# return [canonicalize_name(dep.name) for dep in parse_requirements(deps or []) if not dep.marker or dep.marker.evaluate()]
	return [dep.name for dep in parse_requirements(deps or []) if not dep.marker or dep.marker.evaluate()]


def req_names_extras(extras):
	return {
		key: req_names(value) for key, value in extras.items()
	}

# def strip_unicode(text):
# 	"""Nix currently doesn't work well with unicode, so we are stripping it
# 	https://github.com/NixOS/nix/issues/1491"""
# 	return text.encode('ascii', 'replace').decode('ascii')


def main():
	# type () -> None

	if 'src' not in os.environ:
		with open(os.environ['out'], 'wb') as fp:
			fp.write(json.dumps(default_environment(), indent=4, ensure_ascii=False, sort_keys=True).encode('utf-8'))
		return

	dest = extract_source(os.environ['src'])
	change_permissions(dest)
	distro = get_distro(dest)

	output = {
		'metadata': {
			'name': u(distro.get_name()),
			'version': u(distro.get_version()),
			'author': u(distro.get_author()),
			'author_email': u(distro.get_author_email()),
			'description': u(distro.get_description()),
			'license': u(distro.get_license())
		},
		'requirements': {
			'install': [u(x) for x in req_names(getattr(distro, 'install_requires', distro.get_requires()))],
			'test': [u(x) for x in req_names(getattr(distro, 'tests_require', []) or [])],
			'setup': [u(x) for x in req_names(getattr(distro, 'setup_requires', []))],
			'extras': req_names_extras(getattr(distro, 'extras_require', {}))
		}
	}

	with open(os.environ['out'], 'wb') as fp:
		fp.write(json.dumps(output, indent=4, ensure_ascii=False, sort_keys=True).encode('utf-8'))


if __name__ == s('__main__'):
	main()
