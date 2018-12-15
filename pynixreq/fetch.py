from __future__ import annotations

import asyncio
import posixpath
import re
import subprocess
from enum import Enum, auto
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any, Dict,Iterable, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlsplit

import aiohttp
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version, parse as version_parse

RE_HASH = re.compile(r'(sha1|sha224|sha384|sha256|sha512|md5)=([a-f0-9]+)')
SDIST_EXTS = ('.tar.bz2', '.tbz', '.tar.xz', '.txz', '.tlz', '.tar.lz', '.tar.lzma', '.tar.gz', '.tgz', '.tar', '.zip')
ZIP_EXTS = ('zip',)
BLACKLISTED_HASH = ('md5',)


class Types(Enum):
	SDIST = auto()
	WHEEL = auto()
	ZIP = auto()


@dataclass
class Package:
	name: str
	version: Version
	type: Types
	url: str
	hash_type: str
	hash: str

	def to_nix(self):
		return [
			f'"{self.name}" = buildPythonPackage {{',
			f'\tpname = "{self.name}";',
			f'\tversion = "{self.version}";',
			'\tsrc = fetchurl {',
			f'\t\turl = "{self.url}";',
			f'\t\t{self.hash_type} = "{self.hash}";',
			'\t};',
			'};'
		]

	def update_hash(self, hash_type: str, hash: str) -> None:
		self.hash_type = hash_type
		self.hash = hash

	def _is_comparable(self, other):
		return isinstance(other, Package) and self.name == other.name

	def __lt__(self, other):
		if not self._is_comparable(other):
			return NotImplemented

		return other.version < self.version

	def __le__(self, other):
		if not self._is_comparable(other):
			return NotImplemented

		return other.version <= self.version

	def __eq__(self, other):
		if not self._is_comparable(other):
			return NotImplemented

		return other.version == self.version

	def __ne__(self, other):
		if not self._is_comparable(other):
			return NotImplemented

		return other.version != self.version

	def __gt__(self, other):
		if not self._is_comparable(other):
			return NotImplemented

		return other.version > self.version

	def __ge__(self, other):
		if not self._is_comparable(other):
			return NotImplemented

		return other.version >= self.version


def nix_hash(url: str, old_hash_type: str, old_hash: str) -> Tuple[str, str, str]:
	result = subprocess.run(['nix-prefetch-url', '--print-path', '--type', old_hash_type, url, old_hash], capture_output=True, check=True)
	output = result.stdout.splitlines()

	assert output[0].decode() == old_hash
	nix_path = output[1].decode()

	result = subprocess.run(['nix-hash', '--flat', '--base32', '--type', 'sha512', nix_path], capture_output=True, check=True)
	output = result.stdout.splitlines()
	new_hash = output[0].decode()

	return 'sha512', new_hash, nix_path


class PyPIParser(HTMLParser):
	def __init__(self, basename: str, index_base: str):
		self.base_name = basename
		self.index_base = index_base

		self.packages: Dict[Version, Package] = {}
		self._attrs: List[Tuple[str, str]] = None
		self._data: str = None

		basename_version = re.sub(r'[\-_.]', r'[\-_.]', basename) + r'-([a-z0-9_.!+-]+)'
		self._re_version = re.compile(basename_version, re.I)

		super().__init__()

	def get_hash(self, url: str) -> Tuple[Optional[str], Optional[str]]:
		parts = urlsplit(url)
		match = RE_HASH.search(parts.fragment)
		if match:
			name = match.group(1)
			value = match.group(2)

			return name, value

		return None, None

	def get_url(self, url: str) -> str:
		new_url = urljoin(self.index_base, url)
		pos = new_url.find('#')
		return new_url[:pos if pos > -1 else len(new_url)]

	@staticmethod
	def splitext(path: str) -> Tuple[str, str]:
		base, ext = posixpath.splitext(path)
		if base.lower().endswith('.tar'):
			ext = base[-4:] + ext
			base = base[:-4]

		return base, ext

	def get_version(self, filebase: str) -> str:
		match = self._re_version.search(filebase)
		return match.group(1) if match else None

	def add_package(self):
		assert self._attrs is not None
		assert self._data is not None

		base, ext = self.splitext(self._data)

		if ext not in SDIST_EXTS:
			return

		attrs = dict(self._attrs)

		version_str = self.get_version(base)
		if version_str is None:
			print(f"Unable to parse version from {base}, ignoring ...")
			return

		version = version_parse(version_str)
		url = self.get_url(attrs['href'])
		hash_type, hash = self.get_hash(attrs['href'])

		self.packages[version] = Package(self.base_name, version, Types.SDIST, url, hash_type, hash)

	def handle_starttag(self, tag: str, attrs: List[Tuple[str, str]]):
		if tag != 'a':
			return

		assert self._attrs is None
		assert self._data is None
		self._attrs = attrs

	def handle_endtag(self, tag: str):
		if tag != 'a':
			return

		self.add_package()
		self._attrs = None
		self._data = None

	def handle_data(self, data: str):
		if self._attrs is None:
			return  # ignore non-relevant tags

		self._data = data


class PyPI:
	def __init__(self, config: Dict[str, Any]):
		self.index: str = config.get('index-url', 'https://pypi.org/simple')
		self.extra_index: Optional[str] = config.get('extra-index-url')

	def get_urls(self, name: str) -> List[str]:
		def ensure_slash(url: str) -> str:
			return f'{url.rstrip("/")}/'

		# normalized_name = ensure_slash(canonicalize_name(name))
		normalized_name = ensure_slash(name)

		urls = []
		if self.extra_index:
			urls.append(urljoin(ensure_slash(self.extra_index), normalized_name))
		urls.append(urljoin(ensure_slash(self.index), normalized_name))

		return urls

	@staticmethod
	async def fetch(session: aiohttp.ClientSession, url: str) -> str:
		async with session.get(url) as response:  # type: aiohttp.ClientResponse
			return await response.text()

	async def get_package_list(self, session: aiohttp.ClientSession, name: str) -> Dict[Version, Package]:
		urls = self.get_urls(name)

		for url in urls:
			try:
				async with session.get(url) as response:  # type: aiohttp.ClientResponse
					if response.status != 200:
						print(f'{url}: {response.status} error - {response.reason}')
						continue

					html = await response.text()
			except (aiohttp.ClientError, aiohttp.ClientConnectionError) as e:
				print(f'{url}: {repr(e)}')
				continue
			else:
				parser = PyPIParser(name, url)
				parser.feed(html)
				parser.close()
				return parser.packages

	async def get_requirement(self, session: aiohttp.ClientSession, requirement: Requirement) -> Package:
		print(f'Fetching {requirement}')
		packages = await self.get_package_list(session, requirement.name)
		print(f'Fetching {requirement} ... done')
		package_versions = sorted(packages.keys(), reverse=True)

		package = next(packages[version] for version in package_versions if version in requirement.specifier)

		if package.hash_type in BLACKLISTED_HASH:
			print(f'{package.url} has a blacklisted hash; computing a new one ...')

			hash_type, hash, nix_path = nix_hash(package.url, package.hash_type, package.hash)
			print(f'{package.hash_type}={package.hash} -> {hash_type}={hash}')
			print(f'Prefetched the package in nix store under {nix_path}')

			package.update_hash(hash_type, hash)

		return package

	async def process_requirements(self, requirements: Set[Requirement]):
		with aiohttp.TCPConnector(limit=8) as conn:
			async with aiohttp.ClientSession(connector=conn) as session:
				tasks = [self.get_requirement(session, requirement) for requirement in requirements]
				results = [await task for task in asyncio.as_completed(tasks)]

				return results
