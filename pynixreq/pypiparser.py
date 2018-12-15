from __future__ import annotations

import posixpath
import re
from html.parser import HTMLParser
from typing import Dict, List, Tuple, Optional
from urllib.parse import urljoin, urlsplit

from packaging.specifiers import SpecifierSet
from packaging.version import parse as version_parse, Version

from pynixreq.data import Candidate

RE_HASH = re.compile(r'(sha1|sha224|sha384|sha256|sha512|md5)=([a-f0-9]+)')
SDIST_EXTS = ('.tar.xz', '.txz', '.tar.lz', '.tlz', '.tar.lzma', '.tar.bz2', '.tbz', '.tar.gz', '.tgz', '.zip', '.tar')


class PyPIParser(HTMLParser):
	def __init__(self, index_url: str, base_name: str):
		self.index_url = index_url
		self.base_name = base_name

		self._attrs: List[Tuple[str, str]] = None
		self._data: str = None

		basename_version = re.sub(r'[-_.]', r'[-_.]', base_name.lower()) + r'-([a-z0-9_.!+-]+)'
		self._re_version = re.compile(basename_version)

		self.candidates: Dict[Version, Candidate] = {}

		super().__init__()

	@staticmethod
	def get_hash(url: str) -> Tuple[Optional[str], Optional[str]]:
		parts = urlsplit(url)
		match = RE_HASH.search(parts.fragment)
		if match:
			name = match.group(1)
			value = match.group(2)

			return name, value

		return None, None

	def get_url(self, url: str) -> str:
		new_url = urljoin(self.index_url, url)
		pos = new_url.find('#')
		return new_url[:pos if pos > -1 else len(new_url)]

	@staticmethod
	def splitext(path: str) -> Tuple[str, str]:
		base, ext = posixpath.splitext(path)
		if base.lower().endswith('.tar'):
			ext = base[-4:] + ext
			base = base[:-4]

		return base, ext

	def get_version(self, filebase: str) -> Version:
		match = self._re_version.search(filebase.lower())
		assert match, "Couldn't find version in %r" % filebase
		return version_parse(match.group(1))

	def process_package(self):
		assert self._attrs is not None
		assert self._data is not None

		base, ext = self.splitext(self._data)

		if ext not in SDIST_EXTS:
			return

		attrs = dict(self._attrs)
		version = self.get_version(base)
		url = self.get_url(attrs['href'])
		hash_type, hash = self.get_hash(attrs['href'])
		requires_python = SpecifierSet(attrs.get('data-requires-python', ""))

		# Prefer extensions in the order given in SDIST_EXT
		if version in self.candidates:
			old_ext = self.splitext(self.candidates[version].url)[1]
			if SDIST_EXTS.index(old_ext) < SDIST_EXTS.index(ext):
				return

		self.candidates[version] = Candidate(self.base_name, version, url, hash_type, hash, requires_python)

	def handle_starttag(self, tag: str, attrs: List[Tuple[str, str]]):
		if tag != 'a':
			return

		assert self._attrs is None
		assert self._data is None
		self._attrs = attrs

	def handle_endtag(self, tag: str):
		if tag != 'a':
			return

		self.process_package()
		self._attrs = None
		self._data = None

	def handle_data(self, data: str):
		if self._attrs is None:
			return  # ignore non-relevant tags

		self._data = data

	def error(self, message):
		raise RuntimeError(f"Unable to parse HTML: {message}")
