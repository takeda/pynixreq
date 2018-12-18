# pynixreq
Python/setuptools -> nix integration (work in progress)

This is work in progress:

1. algorithm to figure out package versions is very basic and won't always to find the solution
2. the code uses asyncio, but at this time still runs serially (the plan is to do that once other things are finalized an #1 is replaced with something better)
3. a lot of code is no longer used and will need to be removed
4. the nix code is very basic at the moment (POC quality)
5. and many other issues

This is yet another python -> nix integration, the reason I created this is because I was not satisfied with existing tooling.
The goal of this project is to make Nix understand distutils/setuptools to fetch dependencies i.e. if project is packaged
properly to be on PyPi, then this code should be able to understand it.
