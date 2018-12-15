from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import aiohttp
from packaging.utils import canonicalize_name
from packaging.version import Version

from .data import Candidate
from .exceptions import PyPINotAvailableError
from .pypiparser import PyPIParser


class PyPI:
	def __init__(self, config: Dict[str, Any]):
		self.index: str = config.get('index-url', 'https://pypi.org/simple')
		self.extra_index: Optional[str] = config.get('extra-index-url')

		self.session = aiohttp.ClientSession(connector=aiohttp.TCPConnector(limit=8, verify_ssl=False))

	def get_urls(self, name: str) -> List[str]:
		def ensure_slash(url: str) -> str:
			return f'{url.rstrip("/")}/'

		# convert all underscores and dots to dashes and append slash e.g.
		# setuptools_scm -> setuptools-scm/
		# zc.buildout -> zc-buildout/
		normalized_name = ensure_slash(canonicalize_name(name))

		urls = []
		if self.extra_index:
			urls.append(urljoin(ensure_slash(self.extra_index), normalized_name))
		urls.append(urljoin(ensure_slash(self.index), normalized_name))

		return urls

	async def get_package_versions(self, name: str) -> Dict[Version, Candidate]:
		urls = self.get_urls(name)

		for url in urls:
			try:
				async with self.session.get(url) as response:  # type: aiohttp.ClientResponse
					if response.status != 200:
						print(f'{url}: {response.status} error - {response.reason}')
						continue

					html = await response.text()
			except (aiohttp.ClientError, aiohttp.ClientConnectionError) as e:
				print(f'{url}: {repr(e)}')
				continue
			else:
				parser = PyPIParser(url, name)
				parser.feed(html)
				parser.close()
				return parser.candidates

		raise PyPINotAvailableError(f"Error obtaining data from PyPI for {name}; tried { ', '.join(urls) }")

	# async def get_requirement(self, session: aiohttp.ClientSession, requirement: Requirement) -> Package:
	# 	print(f'Fetching {requirement}')
	# 	packages = await self.get_package_list(session, requirement.name)
	# 	print(f'Fetching {requirement} ... done')
	# 	package_versions = sorted(packages.keys(), reverse=True)
	#
	# 	package = next(packages[version] for version in package_versions if version in requirement.specifier)
	#
	# 	if package.hash_type in BLACKLISTED_HASH:
	# 		print(f'{package.url} has a blacklisted hash; computing a new one ...')
	#
	# 		hash_type, hash, nix_path = nix_hash(package.url, package.hash_type, package.hash)
	# 		print(f'{package.hash_type}={package.hash} -> {hash_type}={hash}')
	# 		print(f'Prefetched the package in nix store under {nix_path}')
	#
	# 		package.update_hash(hash_type, hash)
	#
	# 	return package
	#
	# async def process_requirements(self, requirements: Set[Requirement]):
	# 	with aiohttp.TCPConnector(limit=8) as conn:
	# 		async with aiohttp.ClientSession(connector=conn) as session:
	# 			tasks = [self.get_requirement(session, requirement) for requirement in requirements]
	# 			results = [await task for task in asyncio.as_completed(tasks)]
	#
	# 			return results
